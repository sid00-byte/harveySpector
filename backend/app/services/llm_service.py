"""
Gemini LLM service for HarveySpecter.

Provides high-level functions for compliance analysis, chat responses,
and search-query formulation — all backed by the Gemini generative model
via the ``google-genai`` SDK.

Every response must include citations in the canonical format:
    [Section X(Y), Page P, Lines L1-L2]
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from google import genai
from google.genai import types as genai_types

from app.config import settings
from app.models.schemas import ActChunk

logger = logging.getLogger(__name__)

# ── System prompts ─────────────────────────────────────────────────────

COMPLIANCE_SYSTEM_PROMPT = """\
You are HarveySpecter, an expert AI legal compliance analyst specialising in
the Indian Companies Act, 2013.

TASK
----
Analyse the user-provided corporate document against the Companies Act, 2013.
For every compliance finding you must:

1. State whether the item is COMPLIANT, NON_COMPLIANT, WARNING, or NEEDS_REVIEW.
2. Explain the finding clearly and concisely.
3. Cite the exact provision using the format:
       [Section X(Y), Page P, Lines L1-L2]
   where X is the section number, Y is the sub-section (if any), P is the
   page number in the Act PDF, and L1-L2 are the line numbers.
4. Suggest corrective action where applicable.
5. List any statutory forms (e.g. MGT-14, DIR-12) that may need to be filed.

OUTPUT FORMAT
-------------
Return a JSON object with these keys:
{
  "summary": "<overall assessment in 2-3 sentences>",
  "overall_status": "COMPLIANT | NON_COMPLIANT | WARNING | NEEDS_REVIEW",
  "items": [
    {
      "status": "COMPLIANT | NON_COMPLIANT | WARNING | NEEDS_REVIEW",
      "title": "<short title>",
      "description": "<detailed explanation>",
      "references": [
        {
          "section": "Section 173(1)",
          "page": 102,
          "line_start": 15,
          "line_end": 28,
          "text": "<verbatim excerpt from the Act>"
        }
      ],
      "suggestion": "<recommended corrective action>",
      "relevant_forms": ["MGT-14"]
    }
  ],
  "applicable_sections": ["Section 173", "Section 174"],
  "required_forms": ["MGT-14", "DIR-12"]
}

RULES
-----
- ONLY cite sections you find in the provided knowledge-base context.
- Do NOT hallucinate section numbers or page/line numbers.
- If the context does not contain enough information to make a determination,
  say so explicitly and mark the item as NEEDS_REVIEW.
- Be precise and actionable — this output will be used by company secretaries.
"""

CHAT_SYSTEM_PROMPT = """\
You are HarveySpecter, an elite Senior Company Secretary (CS) and Corporate Legal Consultant specializing in the Indian Companies Act, 2013. Your goal is to serve as a world-class, one-stop legal consultant for Indian Chartered Accountants (CAs), Company Secretaries (CSs), and corporate lawyers.

When answering, you must conduct deep legal analysis, logical reasoning, and critical thinking:

1. CORE LEGAL GROUNDING:
   - Base your answers firmly on the provided Companies Act sections, rules, and case facts.
   - Always cite exact provisions in the format: [Section X(Y), Page P, Lines L1-L2].
   - Mention the relevant Rule name (e.g., Companies (Meetings of Board and its Powers) Rules, 2014) where applicable.

2. LOGICAL & CRITICAL THINKING WORKFLOW:
   - Identify the exact nature of the company (OPC, Private, Small, Public, Listed) as different thresholds and exemptions apply.
   - Cross-reference thresholds (e.g., paid-up capital, turnover, net worth, loan amounts) to determine applicability of provisions (like CSR, Audit Committee, Independent Directors).
   - Outline the consequences of default, including specific penalties, fines, compounding options, or imprisonment terms for the company and its officers-in-default.

3. ACTIONABLE ADVICE & ROC FILINGS:
   - Specify every single MCA Form (e.g., MGT-14, DIR-12, PAS-3, SH-7, CHG-1, AOC-4) that must be filed, along with its statutory filing timeline (e.g., 30 days) and consequences of delay.
   - Outline a clear step-by-step compliance checklist/roadmap (e.g., 1. Seven-day board notice, 2. Quorum check, 3. Pass resolution, 4. File ROC form).

4. DRAFTING CAPABILITY:
   - If asked (or if highly relevant to the problem), provide professional templates for Board Resolutions, Special Resolutions, Notices of General Meetings, or Explanatory Statements.

Maintain an authoritative, precise, helpful, and highly professional tone suited for experienced legal practitioners.
"""

QUERY_FORMULATION_PROMPT = """\
Given the following document text, generate 3-5 specific search queries that
would help find the most relevant sections of the Companies Act, 2013 for
compliance analysis. Focus on:

1. Corporate governance requirements mentioned or implied
2. Filing and disclosure obligations
3. Director/shareholder responsibilities
4. Financial reporting requirements
5. Any specific compliance areas the document touches on

Return ONLY a JSON array of query strings, e.g.:
["board meeting frequency requirements", "director appointment procedures", ...]
"""


def _get_client() -> genai.Client:
    """Return a configured Gemini client."""
    return genai.Client(api_key=settings.GEMINI_API_KEY)


def _format_context(chunks: list[ActChunk]) -> str:
    """Format Act chunks into a context string for the LLM."""
    if not chunks:
        return "[No relevant sections found in the knowledge base]"

    parts: list[str] = []
    for chunk in chunks:
        header = f"--- {chunk.section_number}"
        if chunk.section_title:
            header += f": {chunk.section_title}"
        header += f" (Page {chunk.page_number}, Lines {chunk.line_start}-{chunk.line_end}) ---"

        parts.append(header)
        parts.append(chunk.text)
        parts.append("")

    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════
#  Compliance analysis
# ═══════════════════════════════════════════════════════════════════════


async def analyze_compliance(
    document_text: str,
    relevant_chunks: list[ActChunk],
    focus_areas: list[str] | None = None,
) -> dict[str, Any]:
    """Run a full compliance analysis of *document_text* against the Act.

    Args:
        document_text: The extracted text of the uploaded document.
        relevant_chunks: Pre-retrieved chunks from the knowledge base.
        focus_areas: Optional list of sections/topics to prioritise.

    Returns:
        A dict matching the ComplianceReport schema.
    """
    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set. A valid Gemini API key is required for compliance analysis.")

    client = _get_client()
    context = _format_context(relevant_chunks)

    user_message = f"DOCUMENT TO ANALYSE:\n{document_text[:15000]}\n\n"
    user_message += f"RELEVANT COMPANIES ACT SECTIONS:\n{context}\n\n"

    if focus_areas:
        user_message += f"FOCUS AREAS: {', '.join(focus_areas)}\n\n"

    user_message += "Analyse this document for Companies Act 2013 compliance."

    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=settings.GEMINI_MODEL,
            contents=user_message,
            config=genai_types.GenerateContentConfig(
                system_instruction=COMPLIANCE_SYSTEM_PROMPT,
                temperature=0.2,
                max_output_tokens=8192,
                response_mime_type="application/json",
            ),
        )

        raw_text = response.text or "{}"
        # Strip markdown code fences if present
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]

        report: dict[str, Any] = json.loads(raw_text)
        return report

    except json.JSONDecodeError:
        logger.error("Failed to parse LLM compliance response as JSON")
        return {
            "summary": "Analysis completed but the response could not be parsed.",
            "overall_status": "NEEDS_REVIEW",
            "items": [],
            "applicable_sections": [],
            "required_forms": [],
        }
    except Exception as exc:
        logger.error("Compliance analysis failed: %s", exc)
        raise RuntimeError(f"Compliance analysis failed: {exc}") from exc


# ═══════════════════════════════════════════════════════════════════════
#  Chat / follow-up
# ═══════════════════════════════════════════════════════════════════════


async def chat_response(
    message: str,
    context_chunks: list[ActChunk] | str,
    history: list[dict[str, str]] | None = None,
) -> str:
    """Generate a non-streaming chat response.

    Args:
        message: The user's question or follow-up.
        context_chunks: Relevant Act chunks (or pre-formatted context string) for grounding.
        history: Prior conversation turns as ``[{"role": ..., "content": ...}]``.

    Returns:
        The assistant's reply as a string.
    """
    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set. A valid Gemini API key is required for chat responses.")

    client = _get_client()
    if isinstance(context_chunks, str):
        context = context_chunks
    else:
        context = _format_context(context_chunks)

    contents: list[genai_types.Content] = []

    # Replay history
    if history:
        for turn in history:
            contents.append(
                genai_types.Content(
                    role="user" if turn["role"] == "user" else "model",
                    parts=[genai_types.Part(text=turn["content"])],
                )
            )

    # Current message with context
    user_text = f"RELEVANT COMPANIES ACT SECTIONS:\n{context}\n\nQUESTION:\n{message}"
    contents.append(
        genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=user_text)],
        )
    )

    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=settings.GEMINI_MODEL,
            contents=contents,
            config=genai_types.GenerateContentConfig(
                system_instruction=CHAT_SYSTEM_PROMPT,
                temperature=0.3,
                max_output_tokens=4096,
            ),
        )
        return response.text or ""
    except Exception as exc:
        logger.error("Chat response generation failed: %s", exc)
        raise RuntimeError(f"Chat response failed: {exc}") from exc


async def chat_response_stream(
    message: str,
    context_chunks: list[ActChunk],
    history: list[dict[str, str]] | None = None,
) -> AsyncGenerator[str, None]:
    """Generate a *streaming* chat response, yielding text chunks.

    Args:
        message: The user's question.
        context_chunks: Relevant Act chunks.
        history: Prior conversation turns.

    Yields:
        Text fragments as they arrive from the model.
    """
    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set. A valid Gemini API key is required for streaming chat responses.")

    client = _get_client()
    context = _format_context(context_chunks)

    contents: list[genai_types.Content] = []
    if history:
        for turn in history:
            contents.append(
                genai_types.Content(
                    role="user" if turn["role"] == "user" else "model",
                    parts=[genai_types.Part(text=turn["content"])],
                )
            )

    user_text = f"RELEVANT COMPANIES ACT SECTIONS:\n{context}\n\nQUESTION:\n{message}"
    contents.append(
        genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=user_text)],
        )
    )

    try:
        stream = await asyncio.to_thread(
            client.models.generate_content_stream,
            model=settings.GEMINI_MODEL,
            contents=contents,
            config=genai_types.GenerateContentConfig(
                system_instruction=CHAT_SYSTEM_PROMPT,
                temperature=0.3,
                max_output_tokens=4096,
            ),
        )
        for chunk in stream:
            if chunk.text:
                yield chunk.text
    except Exception as exc:
        logger.error("Streaming chat failed: %s", exc)
        yield f"\n\n[Error: {exc}]"


# ═══════════════════════════════════════════════════════════════════════
#  Query formulation
# ═══════════════════════════════════════════════════════════════════════


async def formulate_queries(document_text: str) -> list[str]:
    """Use Gemini to generate search queries for knowledge-base retrieval.

    Given the uploaded document text, the LLM produces targeted queries
    that will surface the most relevant Companies Act provisions.

    Args:
        document_text: Extracted text from the user's document.

    Returns:
        A list of search query strings (typically 3-5).
    """
    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set. A valid Gemini API key is required for query formulation.")

    client = _get_client()

    user_text = f"DOCUMENT TEXT (truncated):\n{document_text[:10000]}"

    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=settings.GEMINI_MODEL,
            contents=user_text,
            config=genai_types.GenerateContentConfig(
                system_instruction=QUERY_FORMULATION_PROMPT,
                temperature=0.3,
                max_output_tokens=1024,
                response_mime_type="application/json",
            ),
        )

        raw = response.text or "[]"
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw[:-3]

        queries: list[str] = json.loads(raw)
        if not isinstance(queries, list):
            queries = [str(queries)]
        return queries

    except (json.JSONDecodeError, Exception) as exc:
        logger.warning("Query formulation fell back to defaults: %s", exc)
        # Sensible defaults when the LLM can't formulate queries
        return [
            "board meeting requirements Companies Act 2013",
            "director appointment compliance",
            "annual filing requirements companies act",
            "shareholder meeting provisions",
        ]


class LLMService:
    """Service class wrapper for Gemini LLM operations."""

    async def chat_response(
        self,
        message: str,
        context: list[ActChunk] | str | None = None,
        history: list[dict[str, str]] | None = None,
        *,
        context_chunks: list[ActChunk] | str | None = None,
    ) -> str:
        ctx = context if context is not None else context_chunks
        return await chat_response(message, ctx, history)

    async def chat_response_stream(
        self,
        message: str,
        context_chunks: list[ActChunk],
        history: list[dict[str, str]] | None = None,
    ) -> AsyncGenerator[str, None]:
        async for chunk in chat_response_stream(message, context_chunks, history):
            yield chunk

    async def formulate_queries(self, document_text: str) -> list[str]:
        return await formulate_queries(document_text)

    async def analyze_compliance(
        self,
        document_text: str,
        relevant_chunks: list[ActChunk],
        focus_areas: list[str] | None = None,
    ) -> dict[str, Any]:
        return await analyze_compliance(document_text, relevant_chunks, focus_areas)

