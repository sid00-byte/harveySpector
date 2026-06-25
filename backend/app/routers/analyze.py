"""
Analysis router — triggers and retrieves compliance analyses.

POST /analyze   → kick off a compliance analysis for an uploaded document
GET  /analysis/{id}       → poll for the result
GET  /analysis/{id}/report → retrieve the formatted compliance report
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks

from app.config import settings
from app.models.schemas import (
    AnalysisRequest,
    AnalysisResponse,
    AnalysisResultResponse,
    AnalysisStatus,
    ComplianceReport,
    ComplianceStatus,
)
from app.services.rag_pipeline import RAGPipeline
from app.services.vector_store import VectorStore

router = APIRouter()

# In-memory analysis store for MVP — replace with PostgreSQL in production
_analysis_store: dict[str, dict[str, Any]] = {}


async def run_analysis_task(
    analysis_id: str,
    doc_id: str,
    document_text: str,
    focus_areas: list[str] | None,
    include_suggestions: bool,
    vector_store: VectorStore,
):
    """Background task to run compliance analysis without blocking the HTTP thread."""
    try:
        pipeline = RAGPipeline(vector_store=vector_store)
        report = await pipeline.analyze_document(
            document_text=document_text,
            focus_areas=focus_areas,
            include_suggestions=include_suggestions,
        )

        _analysis_store[analysis_id] = {
            "analysis_id": analysis_id,
            "document_id": doc_id,
            "status": AnalysisStatus.COMPLETED,
            "report": report.model_dump() if report else None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "error": None,
        }
    except Exception as exc:
        _analysis_store[analysis_id] = {
            "analysis_id": analysis_id,
            "document_id": doc_id,
            "status": AnalysisStatus.FAILED,
            "report": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "error": str(exc),
        }


@router.post(
    "/",
    response_model=AnalysisResponse,
    summary="Start a compliance analysis",
)
async def start_analysis(
    request: AnalysisRequest,
    req: Request,
    background_tasks: BackgroundTasks,
) -> AnalysisResponse:
    """Kick off a compliance analysis against the Companies Act, 2013 in the background."""
    # Look up the uploaded document
    from app.routers.documents import _document_store

    doc = _document_store.get(request.document_id)
    if not doc:
        raise HTTPException(
            status_code=404,
            detail=f"Document '{request.document_id}' not found. Upload first.",
        )

    analysis_id = uuid.uuid4().hex

    # Initialize analysis store with PROCESSING status
    _analysis_store[analysis_id] = {
        "analysis_id": analysis_id,
        "document_id": request.document_id,
        "status": AnalysisStatus.PROCESSING,
        "report": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "error": None,
    }

    # Queue the background analysis
    vector_store = req.app.state.vector_store
    background_tasks.add_task(
        run_analysis_task,
        analysis_id,
        request.document_id,
        doc["text"],
        request.focus_areas,
        request.include_suggestions,
        vector_store,
    )

    return AnalysisResponse(
        analysis_id=analysis_id,
        document_id=request.document_id,
        status=AnalysisStatus.PROCESSING,
        message="Analysis started in the background",
    )


@router.get(
    "/analysis/{analysis_id}",
    response_model=AnalysisResultResponse,
    summary="Get analysis result",
)
async def get_analysis(analysis_id: str) -> AnalysisResultResponse:
    """Retrieve the result of a compliance analysis by ID."""
    analysis = _analysis_store.get(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    report = None
    if analysis["report"]:
        report = ComplianceReport(**analysis["report"])

    return AnalysisResultResponse(
        analysis_id=analysis["analysis_id"],
        document_id=analysis["document_id"],
        status=AnalysisStatus(analysis["status"]),
        report=report,
        error=analysis.get("error"),
    )


@router.get(
    "/analysis/{analysis_id}/report",
    summary="Get formatted compliance report",
)
async def get_analysis_report(analysis_id: str) -> dict[str, Any]:
    """Return the compliance report in a format optimised for frontend rendering."""
    analysis = _analysis_store.get(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    if analysis["status"] != AnalysisStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Analysis is in '{analysis['status']}' state — not ready",
        )

    report_data = analysis.get("report")
    if not report_data:
        raise HTTPException(status_code=404, detail="No report data available")

    report = ComplianceReport(**report_data)

    # Build front-end-friendly summary
    compliant_count = sum(
        1 for i in report.items if i.status == ComplianceStatus.COMPLIANT
    )
    non_compliant_count = sum(
        1 for i in report.items if i.status == ComplianceStatus.NON_COMPLIANT
    )
    warning_count = sum(
        1 for i in report.items if i.status == ComplianceStatus.WARNING
    )

    return {
        "analysis_id": analysis_id,
        "summary": report.summary,
        "overall_status": report.overall_status,
        "compliance_score": round(
            (compliant_count / max(len(report.items), 1)) * 100, 1
        ),
        "counts": {
            "compliant": compliant_count,
            "non_compliant": non_compliant_count,
            "warning": warning_count,
            "total": len(report.items),
        },
        "items": [item.model_dump() for item in report.items],
        "required_forms": report.required_forms,
        "citations": [c.model_dump() for c in report.citations],
        "generated_at": report.generated_at.isoformat(),
    }
