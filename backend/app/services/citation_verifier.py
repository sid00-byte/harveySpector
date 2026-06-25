"""
Post-generation citation verifier for HarveySpecter.

After the LLM produces a compliance analysis or chat response, this module
parses out every citation in the canonical format
``[Section X(Y), Page P, Lines L1-L2]``, looks each one up in the
knowledge base, and marks it as VERIFIED, APPROXIMATE, or UNVERIFIED.

This is a critical trust layer — it ensures that no hallucinated section
references leak through to the end user.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.models.schemas import ActChunk, CitationStatus, VerifiedCitation
from app.services.vector_store import VectorStore

logger = logging.getLogger(__name__)

# ── Citation regex ─────────────────────────────────────────────────────
# Matches patterns like:
#   [Section 173(1), Page 102, Lines 15-28]
#   [Section 56, Page 34, Line 7]
#   [Section 2(68), Page 5, Lines 120-125]

CITATION_PATTERN = re.compile(
    r"\[Section\s+"
    r"(\d+)"                    # section number
    r"(?:\(([^)]+)\))?"         # optional sub-section in parens
    r",\s*Page\s+(\d+)"        # page number
    r",\s*Lines?\s+"
    r"(\d+)"                    # line_start
    r"(?:-(\d+))?"              # optional line_end
    r"\]",
    re.IGNORECASE,
)


@dataclass
class ParsedCitation:
    """Intermediate representation of a parsed citation string."""

    raw: str
    section_number: str
    subsection: str | None
    page: int
    line_start: int
    line_end: int | None


# ═══════════════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════════════


def parse_citations(text: str) -> list[ParsedCitation]:
    """Extract all citation strings from *text*.

    Args:
        text: LLM-generated analysis or chat response.

    Returns:
        A list of ``ParsedCitation`` instances (may be empty).
    """
    citations: list[ParsedCitation] = []

    for match in CITATION_PATTERN.finditer(text):
        raw = match.group(0)
        section_number = match.group(1)
        subsection = match.group(2)  # may be None
        page = int(match.group(3))
        line_start = int(match.group(4))
        line_end_str = match.group(5)
        line_end = int(line_end_str) if line_end_str else None

        citations.append(
            ParsedCitation(
                raw=raw,
                section_number=section_number,
                subsection=subsection,
                page=page,
                line_start=line_start,
                line_end=line_end,
            )
        )

    return citations


async def verify_citations(
    text: str,
    vector_store: VectorStore,
) -> list[VerifiedCitation]:
    """Parse and verify every citation in *text* against the knowledge base.

    Verification levels:
    - **VERIFIED** — a chunk exists with a matching section number, page,
      and overlapping line range.
    - **APPROXIMATE** — a chunk exists for the section but the page or
      line numbers don't match exactly (could be a pagination artefact).
    - **UNVERIFIED** — no chunk found for that section number at all.

    Args:
        text: The full LLM response text.
        vector_store: An initialised ``VectorStore`` instance.

    Returns:
        A list of ``VerifiedCitation`` objects — one per citation found.
    """
    parsed = parse_citations(text)

    if not parsed:
        logger.debug("No citations found in response text")
        return []

    results: list[VerifiedCitation] = []

    for cit in parsed:
        chunks = await vector_store.find_chunks_by_section(cit.section_number)

        if not chunks:
            results.append(
                VerifiedCitation(
                    raw_citation=cit.raw,
                    status=CitationStatus.UNVERIFIED,
                )
            )
            logger.warning("UNVERIFIED citation: %s (no chunks for section)", cit.raw)
            continue

        # Try to find an exact match
        exact_match = _find_exact_match(cit, chunks)
        if exact_match:
            results.append(
                VerifiedCitation(
                    raw_citation=cit.raw,
                    status=CitationStatus.VERIFIED,
                    matched_chunk_id=exact_match.chunk_id,
                    matched_text=exact_match.text[:500],
                )
            )
            continue

        # Fall back to approximate match (section exists but lines/page differ)
        best = _find_best_approximate(cit, chunks)
        results.append(
            VerifiedCitation(
                raw_citation=cit.raw,
                status=CitationStatus.APPROXIMATE,
                matched_chunk_id=best.chunk_id,
                matched_text=best.text[:500],
            )
        )
        logger.info(
            "APPROXIMATE citation: %s → chunk %s",
            cit.raw,
            best.chunk_id,
        )

    verified_count = sum(1 for r in results if r.status == CitationStatus.VERIFIED)
    approx_count = sum(1 for r in results if r.status == CitationStatus.APPROXIMATE)
    unverified_count = sum(1 for r in results if r.status == CitationStatus.UNVERIFIED)

    logger.info(
        "Citation verification: %d verified, %d approximate, %d unverified (of %d total)",
        verified_count,
        approx_count,
        unverified_count,
        len(results),
    )

    return results


# ═══════════════════════════════════════════════════════════════════════
#  Internal matching helpers
# ═══════════════════════════════════════════════════════════════════════


def _find_exact_match(
    citation: ParsedCitation,
    chunks: list[ActChunk],
) -> ActChunk | None:
    """Find a chunk whose page and line range exactly cover the citation."""
    for chunk in chunks:
        if chunk.page_number != citation.page:
            continue

        # Check subsection match if specified
        if citation.subsection and chunk.subsection:
            if citation.subsection != chunk.subsection:
                continue

        # Check line overlap
        if citation.line_end:
            if chunk.line_start <= citation.line_start and chunk.line_end >= citation.line_end:
                return chunk
        else:
            if chunk.line_start <= citation.line_start <= chunk.line_end:
                return chunk

    return None


def _find_best_approximate(
    citation: ParsedCitation,
    chunks: list[ActChunk],
) -> ActChunk:
    """Return the chunk with the best overlap for an approximate match.

    Uses a simple scoring heuristic:
    - Same page → +10
    - Same subsection → +5
    - Overlapping line range → +3
    - Close page (within 2) → +2
    """

    def _score(chunk: ActChunk) -> int:
        s = 0
        if chunk.page_number == citation.page:
            s += 10
        elif abs(chunk.page_number - citation.page) <= 2:
            s += 2

        if citation.subsection and chunk.subsection == citation.subsection:
            s += 5

        # Line overlap
        if citation.line_end:
            cit_range = set(range(citation.line_start, citation.line_end + 1))
            chunk_range = set(range(chunk.line_start, chunk.line_end + 1))
            if cit_range & chunk_range:
                s += 3
        else:
            if chunk.line_start <= citation.line_start <= chunk.line_end:
                s += 3

        return s

    return max(chunks, key=_score)


class CitationVerifier:
    """Service class wrapper for verifying citations in generated text."""

    def __init__(self, vector_store: VectorStore) -> None:
        self.vector_store = vector_store

    async def verify_citations(self, text: str) -> list[VerifiedCitation]:
        """Verify citations in text against the vector store."""
        return await verify_citations(text, self.vector_store)

