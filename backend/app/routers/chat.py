"""
Chat router — interactive follow-up conversation about compliance findings.

POST /          → send a message, receive AI response with citations
GET  /history/{case_id} → retrieve conversation history for a case
"""

from __future__ import annotations

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

    # Get conversation history
    history = _chat_store.get(request.case_id, [])

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

    # Build context from relevant chunks
    context_parts: list[str] = []
    for chunk in relevant_chunks:
        context_parts.append(
            f"[Section {chunk.section_number or 'N/A'}, "
            f"Page {chunk.page_number or 'N/A'}, "
            f"Lines {chunk.line_start or 'N/A'}-{chunk.line_end or 'N/A'}]\n"
            f"{chunk.text or ''}"
        )
    context = "\n\n---\n\n".join(context_parts) if context_parts else ""

    # Build history for the LLM
    llm_history = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in history[-10:]  # Last 10 messages for context
    ]

    # Generate response
    try:
        reply = await llm.chat_response(
            message=request.message,
            context=context,
            history=llm_history,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Chat response generation failed: {exc}",
        ) from exc

    # Verify citations in the response
    try:
        verified_citations = await verifier.verify_citations(reply)
    except Exception:
        verified_citations = []

    # Store messages
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
async def get_chat_history(case_id: str) -> ChatHistoryResponse:
    """Retrieve all messages in a conversation by case ID."""
    messages = _chat_store.get(case_id, [])

    chat_messages = [
        ChatMessage(
            role=msg["role"],
            content=msg["content"],
            timestamp=datetime.fromisoformat(msg["timestamp"]),
            citations=[VerifiedCitation(**c) for c in msg.get("citations", [])],
        )
        for msg in messages
    ]

    return ChatHistoryResponse(
        case_id=case_id,
        messages=chat_messages,
        total_messages=len(chat_messages),
    )
