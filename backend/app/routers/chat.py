"""
Chat router — interactive follow-up conversation about compliance findings.

POST /          → send a message, receive AI response with citations
GET  /history/{case_id} → retrieve conversation history for a case
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.config import settings
from app.models.schemas import (
    ChatHistoryResponse,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    VerifiedCitation,
)
from app.services.llm_service import LLMService
from app.services.vector_store import VectorStore
from app.services.embeddings import EmbeddingService
from app.services.citation_verifier import CitationVerifier

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory chat store for MVP
_chat_store: dict[str, list[dict[str, Any]]] = {}


@router.post(
    "/",
    response_model=ChatResponse,
    summary="Send a chat message",
)
async def send_message(
    request: ChatRequest,
    req: Request,
) -> ChatResponse:
    """Send a follow-up message and receive an AI response grounded in the
    Companies Act, 2013.

    The response includes verified citations for every legal reference.
    """
    llm = LLMService()
    vector_store: VectorStore = req.app.state.vector_store
    embedding_service = EmbeddingService()
    verifier = CitationVerifier(vector_store=vector_store)

    # Get conversation history from database, fallback to in-memory
    try:
        db_history = await vector_store.get_chat_history(request.case_id)
        if db_history:
            history = [
                {"role": msg["role"], "content": msg["content"]}
                for msg in db_history
            ]
        else:
            history = _chat_store.get(request.case_id, [])
    except Exception as exc:
        logger.warning("Could not retrieve chat history from database: %s", exc)
        history = _chat_store.get(request.case_id, [])

    # Fetch case document text and latest report to build a rich grounding context
    document_text = ""
    doc_name = ""
    latest_report = None
    compliance_score = None

    try:
        if vector_store._is_fallback:
            # Query SQLite for document and latest report
            with vector_store._get_sqlite_conn() as conn:
                # Get document text
                doc_row = conn.execute(
                    """
                    SELECT text_content, file_name 
                    FROM documents 
                    WHERE case_id = ? 
                    LIMIT 1;
                    """,
                    (request.case_id,)
                ).fetchone()
                if doc_row:
                    document_text = doc_row["text_content"] or ""
                    doc_name = doc_row["file_name"] or ""
                
                # Get latest analysis report
                analysis_row = conn.execute(
                    """
                    SELECT report_json 
                    FROM analyses 
                    WHERE case_id = ? AND status = 'COMPLETED' 
                    ORDER BY created_at DESC 
                    LIMIT 1;
                    """,
                    (request.case_id,)
                ).fetchone()
                if analysis_row:
                    latest_report = json.loads(analysis_row["report_json"]) if analysis_row["report_json"] else None
        else:
            # Query PostgreSQL connection
            async with vector_store.pool.acquire() as conn:
                # Try Prisma schema for document
                try:
                    doc_row = await conn.fetchrow(
                        'SELECT "extractedText" AS text, "fileName" AS name FROM documents WHERE "caseId" = $1 LIMIT 1;',
                        request.case_id
                    )
                    if doc_row:
                        document_text = doc_row["text"] or ""
                        doc_name = doc_row["name"] or ""
                except Exception:
                    # Fallback to snake_case schema for document
                    doc_row = await conn.fetchrow(
                        'SELECT extracted_text AS text, file_name AS name FROM documents WHERE case_id = $1 LIMIT 1;',
                        request.case_id
                    )
                    if doc_row:
                        document_text = doc_row["text"] or ""
                        doc_name = doc_row["name"] or ""

                # Try Prisma schema for analysis report
                try:
                    analysis_row = await conn.fetchrow(
                        'SELECT report, "complianceScore" AS score FROM analyses WHERE "caseId" = $1 AND status = \'completed\' ORDER BY "createdAt" DESC LIMIT 1;',
                        request.case_id
                    )
                    if analysis_row:
                        latest_report = analysis_row["report"]
                        compliance_score = analysis_row["score"]
                except Exception:
                    # Fallback to snake_case schema for analysis report
                    analysis_row = await conn.fetchrow(
                        'SELECT report_json AS report, compliance_score AS score FROM analyses WHERE case_id = $1 AND status = \'completed\' ORDER BY created_at DESC LIMIT 1;',
                        request.case_id
                    )
                    if analysis_row:
                        latest_report = analysis_row["report"]
                        compliance_score = analysis_row["score"]
    except Exception as exc:
        logger.warning("Could not retrieve document text or report from database: %s", exc)

    # Generate query embedding and search for relevant Act chunks
    try:
        query_embedding = await embedding_service.generate_embedding(request.message)
    except Exception:
        # Fall back to dummy embedding if API is exhausted/unavailable
        query_embedding = [0.0] * settings.GEMINI_EMBEDDING_DIMENSION

    try:
        relevant_chunks = await vector_store.hybrid_search(
            query_text=request.message,
            query_embedding=query_embedding,
            top_k=10,
        )
    except Exception:
        relevant_chunks = []

    # Build context from relevant chunks, document text, and report findings
    context_parts: list[str] = []

    # 1. Add details about the current audited document if available
    if doc_name and document_text:
        context_parts.append(
            f"AUDITED DOCUMENT DETAILS:\n"
            f"Document Name: {doc_name}\n"
            f"Extracted Content Snippet:\n{document_text[:4000]}"
        )

    # 2. Add details about the compliance analysis report if available
    if latest_report:
        findings_summary = []
        if isinstance(latest_report, str):
            try:
                latest_report = json.loads(latest_report)
            except Exception:
                pass
        
        if isinstance(latest_report, dict):
            comp_score = latest_report.get("compliance_score", compliance_score)
            summary = latest_report.get("summary", "")
            items = latest_report.get("items", [])
            required_forms = latest_report.get("required_forms", [])
            
            findings_summary.append(f"Compliance Score: {comp_score}%")
            findings_summary.append(f"Analysis Summary: {summary}")
            if required_forms:
                findings_summary.append(f"Required Forms: {', '.join(required_forms)}")
            
            findings_summary.append("Detailed Findings:")
            for item in items:
                status = item.get("status", "N/A")
                title = item.get("title", "")
                desc = item.get("description", "")
                sugg = item.get("suggestion", "")
                refs = []
                for r in item.get("references", []):
                    refs.append(f"Section {r.get('section', 'N/A')}")
                
                findings_summary.append(
                    f"- [{status}] {title}: {desc}\n"
                    f"  Legal Citations: {', '.join(refs)}\n"
                    f"  Recommended Fix: {sugg}"
                )
        
        context_parts.append(
            f"COMPLIANCE REPORT FINDINGS:\n" + "\n".join(findings_summary)
        )

    # 3. Add retrieved sections from Companies Act, 2013
    for chunk in relevant_chunks:
        context_parts.append(
            f"[Section {chunk.section_number or 'N/A'}, "
            f"Page {chunk.page_number or 'N/A'}, "
            f"Lines {chunk.line_start or 'N/A'}-{chunk.line_end or 'N/A'}]\n"
            f"{chunk.text or ''}"
        )
    context = "\n\n---\n\n".join(context_parts) if context_parts else ""

    # Build history for the LLM
    llm_history = history[-10:]  # Last 10 messages for context

    # Generate response
    try:
        reply = await llm.chat_response(
            message=request.message,
            context=context,
            history=llm_history,
        )
    except Exception as exc:
        logger.warning("Gemini chat response failed: %s. Using rate-limit fallback reply.", exc)
        reply = (
            "⚠️ **Gemini API Limit Exceeded / Service Congestion**\n\n"
            "I'm currently unable to generate a real-time response from the Gemini model "
            "because the free-tier API quota limit has been reached or the service is experiencing high demand.\n\n"
            f"**Your Question**: \"{request.message}\"\n\n"
            "**Retrieved Companies Act Context**:\n"
            + (context[:1500] + "..." if context else "[No relevant sections found in the knowledge base]")
        )

    # Verify citations in the response
    try:
        verified_citations = await verifier.verify_citations(reply)
    except Exception:
        verified_citations = []

    # Store messages in database
    try:
        await vector_store.store_chat_message(
            case_id=request.case_id,
            role="user",
            content=request.message,
            citations_json=[]
        )
        await vector_store.store_chat_message(
            case_id=request.case_id,
            role="assistant",
            content=reply,
            citations_json=[c.model_dump() for c in verified_citations]
        )
    except Exception as exc:
        logger.warning("Could not persist chat messages to database: %s", exc)

    # Keep in-memory store as fallback
    now = datetime.now(timezone.utc).isoformat()
    if request.case_id not in _chat_store:
        _chat_store[request.case_id] = []

    _chat_store[request.case_id].append({
        "role": "user",
        "content": request.message,
        "timestamp": now,
        "citations": [],
    })
    _chat_store[request.case_id].append({
        "role": "assistant",
        "content": reply,
        "timestamp": now,
        "citations": [c.model_dump() for c in verified_citations],
    })

    # Build ActReference list from relevant chunks
    from app.models.schemas import ActReference

    references = [
        ActReference(
            section=f"Section {ch.section_number or 'N/A'}",
            page=ch.page_number or 0,
            line_start=ch.line_start or 0,
            line_end=ch.line_end or 0,
            text=(ch.text or "")[:200],
        )
        for ch in relevant_chunks[:5]
    ]

    return ChatResponse(
        case_id=request.case_id,
        reply=reply,
        citations=verified_citations,
        references=references,
    )


@router.get(
    "/history/{case_id}",
    response_model=ChatHistoryResponse,
    summary="Get chat history for a case",
)
async def get_chat_history(
    case_id: str,
    req: Request,
) -> ChatHistoryResponse:
    """Retrieve all messages in a conversation by case ID."""
    vector_store: VectorStore = req.app.state.vector_store

    try:
        db_history = await vector_store.get_chat_history(case_id)
        if db_history:
            chat_messages = []
            for msg in db_history:
                citations_raw = msg.get("citations_json") or []
                if isinstance(citations_raw, str):
                    try:
                        citations_raw = json.loads(citations_raw)
                    except Exception:
                        citations_raw = []

                ts = msg.get("created_at") or datetime.utcnow()
                if isinstance(ts, str):
                    try:
                        ts = datetime.fromisoformat(ts)
                    except Exception:
                        ts = datetime.utcnow()

                chat_messages.append(
                    ChatMessage(
                        role=msg["role"],
                        content=msg["content"],
                        timestamp=ts,
                        citations=[VerifiedCitation(**c) for c in citations_raw],
                    )
                )
            return ChatHistoryResponse(
                case_id=case_id,
                messages=chat_messages,
                total_messages=len(chat_messages),
            )
    except Exception as exc:
        logger.warning("Failed to retrieve chat history from database: %s", exc)

    # Fallback to in-memory store
    messages = _chat_store.get(case_id, [])

    chat_messages = [
        ChatMessage(
            role=msg["role"],
            content=msg["content"],
            timestamp=datetime.fromisoformat(msg["timestamp"]) if isinstance(msg["timestamp"], str) else msg["timestamp"],
            citations=[VerifiedCitation(**c) for c in msg.get("citations", [])],
        )
        for msg in messages
    ]

    return ChatHistoryResponse(
        case_id=case_id,
        messages=chat_messages,
        total_messages=len(chat_messages),
    )
