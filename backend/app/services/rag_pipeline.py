"""
RAG pipeline orchestrator for HarveySpecter.

Coordinates the full retrieval-augmented generation flow:

1. Extract text from the uploaded document.
2. Use Gemini to formulate targeted search queries.
3. Run hybrid search (BM25 + vector) against the knowledge base.
4. Rerank candidate chunks using Gemini.
5. Generate a compliance analysis with citations.
6. Verify every citation against the source chunks.
7. Return a structured ``ComplianceReport``.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from app.config import settings
from app.models.schemas import (
    ActChunk,
    ActReference,
    AnalysisStatus,
    CitationStatus,
    ComplianceItem,
    ComplianceReport,
    ComplianceStatus,
    VerifiedCitation,
)
from app.services import (
    citation_verifier,
    embeddings,
    llm_service,
)
from app.services.document_processor import process_document
from app.services.vector_store import VectorStore

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
#  Main pipeline
# ═══════════════════════════════════════════════════════════════════════


class RAGPipeline:
    """RAG pipeline orchestrator class for HarveySpecter."""

    def __init__(self, vector_store: VectorStore) -> None:
        self.vector_store = vector_store

    async def analyze_document(
        self,
        document_text: str,
        focus_areas: list[str] | None = None,
        include_suggestions: bool = True,
    ) -> ComplianceReport:
        """Execute the end-to-end compliance analysis on document text."""
        # ── 1. Formulate search queries ────────────────────────────────────
        queries = await llm_service.formulate_queries(document_text)
        logger.info("Formulated %d search queries", len(queries))

        # ── 2. Hybrid search across all queries ────────────────────────────
        all_chunks = await _retrieve_chunks(queries, self.vector_store)
        logger.info("Retrieved %d unique chunks from knowledge base", len(all_chunks))

        # ── 3. Rerank with Gemini ──────────────────────────────────────────
        reranked = await _rerank_chunks(document_text, all_chunks)
        logger.info("Reranked to top %d chunks", len(reranked))

        # ── 4. Generate compliance analysis ────────────────────────────────
        raw_report = await llm_service.analyze_compliance(
            document_text=document_text,
            relevant_chunks=reranked,
            focus_areas=focus_areas,
        )

        # ── 5. Verify citations ────────────────────────────────────────────
        report_text = _extract_report_text(raw_report)
        verified_citations = await citation_verifier.verify_citations(
            report_text, self.vector_store
        )

        # ── 6. Assemble the ComplianceReport ───────────────────────────────
        report = _build_report(raw_report, verified_citations)
        return report


async def run_compliance_analysis(
    document_id: str,
    vector_store: VectorStore,
    focus_areas: list[str] | None = None,
) -> ComplianceReport:
    """Execute the end-to-end RAG compliance pipeline.

    This is a helper function that retrieves document text and delegates to RAGPipeline.
    """
    doc_record = await vector_store.get_document(document_id)
    if doc_record is None:
        raise ValueError(f"Document not found: {document_id}")

    document_text: str = doc_record.get("text_content", "")
    if not document_text.strip():
        raise ValueError(f"Document {document_id} has no extracted text")

    logger.info("Starting compliance analysis for document %s", document_id)
    pipeline = RAGPipeline(vector_store)
    return await pipeline.analyze_document(document_text, focus_areas)


# ═══════════════════════════════════════════════════════════════════════
#  Pipeline stages
# ═══════════════════════════════════════════════════════════════════════


async def _retrieve_chunks(
    queries: list[str],
    vector_store: VectorStore,
) -> list[ActChunk]:
    """Run hybrid search for each query and de-duplicate."""
    seen_ids: set[str] = set()
    unique_chunks: list[ActChunk] = []

    for query in queries:
        try:
            query_embedding = await embeddings.generate_embedding(query)
        except Exception as exc:
            logger.warning("Failed to generate embedding for query: %s. Falling back to dummy embedding.", exc)
            query_embedding = [0.0] * settings.GEMINI_EMBEDDING_DIMENSION

        chunks = await vector_store.hybrid_search(
            query_text=query,
            query_embedding=query_embedding,
            top_k=settings.RAG_TOP_K,
        )
        for chunk in chunks:
            if chunk.chunk_id not in seen_ids:
                seen_ids.add(chunk.chunk_id)
                unique_chunks.append(chunk)

    return unique_chunks


async def _rerank_chunks(
    document_text: str,
    chunks: list[ActChunk],
) -> list[ActChunk]:
    """Use Gemini to rerank chunks by relevance to the document.

    For the MVP, we use a simple prompt-based approach.  A production
    system would use a dedicated cross-encoder or Gemini's ranking API.
    """
    if len(chunks) <= settings.RAG_RERANK_TOP_K:
        return chunks

    # Build a numbered list of chunk summaries for the LLM
    summaries = []
    for idx, chunk in enumerate(chunks):
        summary = (
            f"{idx}. [Section {chunk.section_number}] "
            f"{chunk.text[:200]}..."
        )
        summaries.append(summary)

    prompt = (
        f"Given this document excerpt:\n{document_text[:3000]}\n\n"
        f"Rank these Companies Act sections by relevance (most relevant first). "
        f"Return ONLY a JSON array of the index numbers, e.g. [3, 0, 7, 1, 5].\n\n"
        + "\n".join(summaries)
    )

    try:
        import asyncio
        import json

        from google import genai
        from google.genai import types as genai_types

        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=512,
                response_mime_type="application/json",
            ),
        )

        raw = response.text or "[]"
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw[:-3]

        indices: list[int] = json.loads(raw)
        reranked = []
        for idx in indices[: settings.RAG_RERANK_TOP_K]:
            if 0 <= idx < len(chunks):
                reranked.append(chunks[idx])

        if reranked:
            return reranked

    except Exception as exc:
        logger.warning("Reranking failed, using original order: %s", exc)

    # Fallback: return first N chunks
    return chunks[: settings.RAG_RERANK_TOP_K]


# ═══════════════════════════════════════════════════════════════════════
#  Report assembly
# ═══════════════════════════════════════════════════════════════════════


def _extract_report_text(raw_report: dict[str, Any]) -> str:
    """Flatten a raw LLM report dict into a single string for citation parsing."""
    parts: list[str] = [raw_report.get("summary", "")]

    for item in raw_report.get("items", []):
        parts.append(item.get("description", ""))
        parts.append(item.get("suggestion", ""))
        for ref in item.get("references", []):
            parts.append(ref.get("text", ""))

    return "\n".join(parts)


def _build_report(
    raw: dict[str, Any],
    citations: list[VerifiedCitation],
) -> ComplianceReport:
    """Convert the raw LLM JSON + verified citations into a ComplianceReport."""
    items: list[ComplianceItem] = []

    for raw_item in raw.get("items", []):
        references = []
        for ref in raw_item.get("references", []):
            references.append(
                ActReference(
                    section=ref.get("section", ""),
                    page=ref.get("page", 0),
                    line_start=ref.get("line_start", 0),
                    line_end=ref.get("line_end", 0),
                    text=ref.get("text", ""),
                )
            )

        status_str = raw_item.get("status", "NEEDS_REVIEW").upper()
        try:
            status = ComplianceStatus(status_str)
        except ValueError:
            status = ComplianceStatus.NEEDS_REVIEW

        items.append(
            ComplianceItem(
                status=status,
                title=raw_item.get("title", ""),
                description=raw_item.get("description", ""),
                references=references,
                suggestion=raw_item.get("suggestion", ""),
                relevant_forms=raw_item.get("relevant_forms", []),
            )
        )

    overall_str = raw.get("overall_status", "NEEDS_REVIEW").upper()
    try:
        overall = ComplianceStatus(overall_str)
    except ValueError:
        overall = ComplianceStatus.NEEDS_REVIEW

    return ComplianceReport(
        summary=raw.get("summary", ""),
        overall_status=overall,
        items=items,
        citations=citations,
        applicable_sections=raw.get("applicable_sections", []),
        required_forms=raw.get("required_forms", []),
        generated_at=datetime.utcnow(),
    )


# ═══════════════════════════════════════════════════════════════════════
#  Chat follow-up (convenience wrapper)
# ═══════════════════════════════════════════════════════════════════════


async def handle_chat_message(
    message: str,
    case_id: str,
    vector_store: VectorStore,
    document_id: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> tuple[str, list[VerifiedCitation]]:
    """Handle a chat follow-up question with RAG context.

    Args:
        message: The user's question.
        case_id: Conversation group identifier.
        vector_store: Initialised vector store.
        document_id: Optional document to include as context.
        history: Prior conversation turns.

    Returns:
        Tuple of (reply_text, verified_citations).
    """
    # Retrieve relevant chunks for the question
    try:
        query_embedding = await embeddings.generate_embedding(message)
    except Exception as exc:
        logger.warning("Failed to generate embedding for chat query: %s. Falling back to dummy embedding.", exc)
        query_embedding = [0.0] * settings.GEMINI_EMBEDDING_DIMENSION

    chunks = await vector_store.hybrid_search(
        query_text=message,
        query_embedding=query_embedding,
        top_k=settings.RAG_TOP_K,
    )

    # Generate response
    reply = await llm_service.chat_response(
        message=message,
        context_chunks=chunks,
        history=history,
    )

    # Verify citations in the reply
    verified = await citation_verifier.verify_citations(reply, vector_store)

    # Persist messages
    await vector_store.store_chat_message(case_id, "user", message)
    await vector_store.store_chat_message(
        case_id,
        "assistant",
        reply,
        citations_json=[c.model_dump() for c in verified],
    )

    return reply, verified
