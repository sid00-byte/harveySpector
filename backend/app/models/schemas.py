"""
Pydantic request / response schemas for the HarveySpecter API.

Every public-facing data contract lives here so that routers stay thin
and services have a clear, validated interface to programme against.
"""

from __future__ import annotations

import uuid
from datetime import datetime
try:
    from enum import StrEnum
except ImportError:
    from enum import Enum
    class StrEnum(str, Enum):
        pass
from typing import Any

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════════
#  Enums
# ═══════════════════════════════════════════════════════════════════════


class ComplianceStatus(StrEnum):
    """Outcome of a single compliance check item."""

    COMPLIANT = "COMPLIANT"
    NON_COMPLIANT = "NON_COMPLIANT"
    WARNING = "WARNING"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class CitationStatus(StrEnum):
    """Result of post-generation citation verification."""

    VERIFIED = "VERIFIED"
    APPROXIMATE = "APPROXIMATE"
    UNVERIFIED = "UNVERIFIED"


class AnalysisStatus(StrEnum):
    """Lifecycle state of an analysis job."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# ═══════════════════════════════════════════════════════════════════════
#  Document processing
# ═══════════════════════════════════════════════════════════════════════


class PageLine(BaseModel):
    """A single line of text extracted from a page."""

    line_number: int
    text: str


class PageContent(BaseModel):
    """All lines extracted from a single page (or paragraph group)."""

    page_number: int
    lines: list[PageLine] = Field(default_factory=list)
    raw_text: str = ""


class DocumentResult(BaseModel):
    """Unified output from any document-processing pipeline."""

    text: str = Field(description="Full concatenated extracted text")
    pages: list[PageContent] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════
#  Knowledge-base chunks
# ═══════════════════════════════════════════════════════════════════════


class ActChunk(BaseModel):
    """A structured chunk from the Companies Act, 2013."""

    chunk_id: str = Field(
        default_factory=lambda: f"ca2013-{uuid.uuid4().hex[:8]}",
        description="Unique identifier, e.g. 'ca2013-sec56-sub1'",
    )
    chapter_number: str = ""
    chapter_title: str = ""
    section_number: str = ""
    section_title: str = ""
    subsection: str | None = None
    text: str = ""
    page_number: int = 0
    line_start: int = 0
    line_end: int = 0
    related_forms: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════
#  Act references & citations
# ═══════════════════════════════════════════════════════════════════════


class ActReference(BaseModel):
    """A precise pointer into the Companies Act source text."""

    section: str = Field(description="e.g. 'Section 56(1)'")
    page: int
    line_start: int
    line_end: int
    text: str = Field(description="Verbatim text from the Act")


class VerifiedCitation(BaseModel):
    """A citation that has been checked against the knowledge base."""

    raw_citation: str = Field(description="Citation string as emitted by the LLM")
    status: CitationStatus = CitationStatus.UNVERIFIED
    matched_chunk_id: str | None = None
    matched_text: str | None = None


# ═══════════════════════════════════════════════════════════════════════
#  Compliance report
# ═══════════════════════════════════════════════════════════════════════


class ComplianceItem(BaseModel):
    """One discrete compliance finding."""

    status: ComplianceStatus
    title: str
    description: str
    references: list[ActReference] = Field(default_factory=list)
    suggestion: str = ""
    relevant_forms: list[str] = Field(default_factory=list)


class ComplianceReport(BaseModel):
    """Full structured output of a compliance analysis run."""

    summary: str
    overall_status: ComplianceStatus
    items: list[ComplianceItem] = Field(default_factory=list)
    citations: list[VerifiedCitation] = Field(default_factory=list)
    applicable_sections: list[str] = Field(default_factory=list)
    required_forms: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)


# ═══════════════════════════════════════════════════════════════════════
#  Request / response: Documents
# ═══════════════════════════════════════════════════════════════════════


class UploadResponse(BaseModel):
    """Returned after a successful document upload."""

    document_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    filename: str
    file_type: str
    page_count: int = 0
    message: str = "Document uploaded and processed successfully"


class DocumentDetail(BaseModel):
    """Metadata about a stored document."""

    document_id: str
    filename: str
    file_type: str
    page_count: int
    uploaded_at: datetime
    text_preview: str = ""


class DocumentTextResponse(BaseModel):
    """Full extracted text for a document."""

    document_id: str
    text: str
    pages: list[PageContent] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════
#  Request / response: Analysis
# ═══════════════════════════════════════════════════════════════════════


class AnalysisRequest(BaseModel):
    """Kick off a compliance analysis."""

    document_id: str
    focus_areas: list[str] = Field(
        default_factory=list,
        description="Optional list of Act sections / topics to focus on",
    )
    include_suggestions: bool = True


class AnalysisResponse(BaseModel):
    """Wrapper returned immediately when an analysis is queued."""

    analysis_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    document_id: str
    status: AnalysisStatus = AnalysisStatus.PENDING
    message: str = "Analysis queued"


class AnalysisResultResponse(BaseModel):
    """Full analysis result — polled or pushed."""

    analysis_id: str
    document_id: str
    status: AnalysisStatus
    report: ComplianceReport | None = None
    error: str | None = None


# ═══════════════════════════════════════════════════════════════════════
#  Request / response: Chat
# ═══════════════════════════════════════════════════════════════════════


class ChatMessage(BaseModel):
    """A single message in a conversation."""

    role: str = Field(description="'user' or 'assistant'")
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    citations: list[VerifiedCitation] = Field(default_factory=list)


class ChatRequest(BaseModel):
    """Incoming chat / follow-up message from the user."""

    case_id: str = Field(description="Groups messages in one analysis session")
    message: str
    document_id: str | None = None
    history: list[ChatMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    """Non-streaming chat response."""

    case_id: str
    reply: str
    citations: list[VerifiedCitation] = Field(default_factory=list)
    references: list[ActReference] = Field(default_factory=list)


class ChatHistoryResponse(BaseModel):
    """Paginated chat history for a case."""

    case_id: str
    messages: list[ChatMessage] = Field(default_factory=list)
    total_messages: int = 0
