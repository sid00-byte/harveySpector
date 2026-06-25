"""
Companies Act, 2013 — PDF Ingestion Pipeline.

Parses the Act PDF page-by-page using PyMuPDF, identifies chapters and
sections via regex, creates structure-aware chunks with full page/line
metadata, and prepares them for embedding and vector storage.

Usage:
    python -m app.knowledge_base.ingest_act [--pdf-path path/to/act.pdf]
"""

from __future__ import annotations

import re
import logging
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

from app.models.schemas import ActChunk

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
#  Regex patterns for structural elements
# ═══════════════════════════════════════════════════════════════════════

# CHAPTER I, CHAPTER II, etc. (Roman numerals, sometimes followed by A)
CHAPTER_PATTERN = re.compile(
    r"^\s*CHAPTER\s+([IVXLCDM]+[A-Z]?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# Section numbers: "1.", "56.", "149.", etc. at start of a line, optionally prefixed with footnote superscript bracket indicators e.g. "1[270."
SECTION_PATTERN = re.compile(
    r"^\s*(?:\d+\[)?(\d{1,3}[A-Z]?)\.\s*(.+?)[\.\—\-]",
    re.MULTILINE,
)

# Sub-section pattern: "(1)", "(2)", "(a)", etc.
SUBSECTION_PATTERN = re.compile(r"^\s*\((\d+|[a-z])\)\s", re.MULTILINE)

# Common MCA forms referenced in the Act
FORM_KEYWORDS: dict[str, list[str]] = {
    "incorporation": ["SPICe+", "INC-22", "RUN"],
    "share": ["SH-4", "PAS-3", "SH-7"],
    "director": ["DIR-2", "DIR-3", "DIR-12", "DIR-3 KYC"],
    "annual": ["AOC-4", "MGT-7", "MGT-7A", "ADT-1"],
    "resolution": ["MGT-14"],
    "charge": ["CHG-1", "CHG-4"],
    "deposit": ["DPT-3"],
    "audit": ["ADT-1", "ADT-3"],
    "csr": ["CSR-1", "CSR-2"],
}


# ═══════════════════════════════════════════════════════════════════════
#  PDF Extraction
# ═══════════════════════════════════════════════════════════════════════


def extract_pages_with_metadata(pdf_path: str | Path) -> list[dict[str, Any]]:
    """Extract all text from a PDF with page and line-level metadata.

    Uses PyMuPDF's ``get_text("words")`` which returns tuples of:
        (x0, y0, x1, y1, "word", block_no, line_no, word_no)

    Returns a list of page dicts, each containing a list of line dicts.
    """
    doc = fitz.open(str(pdf_path))
    pages: list[dict[str, Any]] = []

    for page_idx, page in enumerate(doc):
        page_number = page_idx + 1
        words = page.get_text("words")

        # Group words by line_no within each block
        lines_map: dict[tuple[int, int], list[str]] = {}
        for w in words:
            block_no = w[5]
            line_no = w[6]
            key = (block_no, line_no)
            if key not in lines_map:
                lines_map[key] = []
            lines_map[key].append(w[4])

        # Build ordered lines
        lines: list[dict[str, Any]] = []
        for idx, (key, word_list) in enumerate(sorted(lines_map.items())):
            text = " ".join(word_list).strip()
            if text:
                lines.append({
                    "line_number": idx + 1,
                    "text": text,
                })

        page_text = "\n".join(line["text"] for line in lines)
        pages.append({
            "page_number": page_number,
            "lines": lines,
            "raw_text": page_text,
        })

    doc.close()
    return pages


# ═══════════════════════════════════════════════════════════════════════
#  Structure-Aware Chunking
# ═══════════════════════════════════════════════════════════════════════


def identify_forms(text: str) -> list[str]:
    """Identify MCA forms that may be relevant to the text."""
    found_forms: set[str] = set()
    text_lower = text.lower()
    for keyword, forms in FORM_KEYWORDS.items():
        if keyword in text_lower:
            found_forms.update(forms)
    # Also look for direct form references
    form_pattern = re.compile(r"\b([A-Z]{2,4}-\d+[A-Z]?)\b")
    for match in form_pattern.finditer(text):
        found_forms.add(match.group(1))
    return sorted(found_forms)


def extract_keywords(text: str) -> list[str]:
    """Extract relevant keywords from section text."""
    keyword_terms = [
        "director", "shareholder", "share", "capital", "debenture",
        "meeting", "resolution", "audit", "auditor", "dividend",
        "prospectus", "allotment", "transfer", "transmission",
        "charge", "deposit", "csr", "corporate social responsibility",
        "merger", "amalgamation", "winding up", "liquidation",
        "board", "quorum", "independent", "managerial", "remuneration",
        "registered office", "memorandum", "articles", "incorporation",
        "annual return", "financial statement", "books of account",
        "related party", "loan", "investment", "guarantee",
        "penalty", "fine", "imprisonment", "compoundable", "nclt",
        "oppression", "mismanagement", "valuer", "nidhi",
        "one person company", "opc", "private company", "public company",
        "small company", "listed company", "government company",
    ]
    text_lower = text.lower()
    return [kw for kw in keyword_terms if kw in text_lower]


def is_probable_footnote(text: str) -> bool:
    """Check if the text is likely a footnote or amendment explanation rather than a section heading."""
    text_lower = text.lower()
    footnote_indicators = [
        "subs. by", "ins. by", "omitted by", "w.e.f", 
        "substituted by", "inserted by", "amended by", 
        "cl. (", "clause (", "sec. ", "section ", "ibid."
    ]
    return any(ind in text_lower for ind in footnote_indicators)


def parse_act_into_chunks(pages: list[dict[str, Any]]) -> list[ActChunk]:
    """Parse extracted pages into structured, section-aware chunks.

    Strategy:
    1. Scan pages for CHAPTER headings → track current chapter
    2. Scan for Section numbers → create a new chunk per section
    3. Enrich each chunk with page/line metadata, related forms, keywords
    """
    chunks: list[ActChunk] = []
    current_chapter_number = ""
    current_chapter_title = ""
    current_section: dict[str, Any] | None = None

    # Monotonic section trackers to ignore TOC/footnotes
    last_section_num = 0
    last_section_str = ""

    for page in pages:
        page_number = page["page_number"]
        # Skip the Table of Contents pages
        if page_number < 16:
            continue

        for line in page["lines"]:
            line_text = line["text"]
            line_number = line["line_number"]

            # Check for chapter heading
            chapter_match = CHAPTER_PATTERN.search(line_text)
            if chapter_match:
                current_chapter_number = chapter_match.group(1)
                # The chapter title is usually on the next line — we'll update later
                current_chapter_title = ""
                continue

            # If we just found a chapter, the next non-empty line is its title
            if current_chapter_number and not current_chapter_title:
                title_text = line_text.strip()
                if title_text and not CHAPTER_PATTERN.match(title_text):
                    current_chapter_title = title_text
                    continue

            # Check for section heading
            section_match = SECTION_PATTERN.match(line_text)
            if section_match:
                sec_str = section_match.group(1)
                match_num = re.match(r"^\d+", sec_str)
                if match_num and not is_probable_footnote(line_text):
                    sec_num = int(match_num.group(0))
                    is_valid = False
                    if last_section_num == 0 and sec_num == 1:
                        is_valid = True
                    elif sec_num > last_section_num:
                        is_valid = True
                    elif sec_num == last_section_num and sec_str != last_section_str:
                        is_valid = True

                    if is_valid:
                        # Save the previous section as a chunk
                        if current_section and current_section["text_lines"]:
                            chunk = _build_chunk(current_section, current_chapter_number, current_chapter_title)
                            if chunk:
                                chunks.append(chunk)

                        # Start a new section
                        current_section = {
                            "section_number": sec_str,
                            "section_title": section_match.group(2).strip(),
                            "page_start": page_number,
                            "line_start": line_number,
                            "page_end": page_number,
                            "line_end": line_number,
                            "text_lines": [line_text],
                        }
                        last_section_num = sec_num
                        last_section_str = sec_str
                        continue

            # Accumulate text into current section
            if current_section:
                current_section["text_lines"].append(line_text)
                current_section["page_end"] = page_number
                current_section["line_end"] = line_number

    # Don't forget the last section
    if current_section and current_section["text_lines"]:
        chunk = _build_chunk(current_section, current_chapter_number, current_chapter_title)
        if chunk:
            chunks.append(chunk)

    logger.info(f"Parsed {len(chunks)} chunks from {len(pages)} pages")
    return chunks


def _build_chunk(
    section: dict[str, Any],
    chapter_number: str,
    chapter_title: str,
) -> ActChunk | None:
    """Build an ActChunk from accumulated section data."""
    text = "\n".join(section["text_lines"]).strip()
    if not text or len(text) < 10:
        return None

    section_num = section["section_number"]
    chunk_id = f"ca2013-sec{section_num}"

    return ActChunk(
        chunk_id=chunk_id,
        chapter_number=chapter_number,
        chapter_title=chapter_title,
        section_number=section_num,
        section_title=section.get("section_title", ""),
        subsection=None,
        text=text,
        page_number=section["page_start"],
        line_start=section["line_start"],
        line_end=section["line_end"],
        related_forms=identify_forms(text),
        keywords=extract_keywords(text),
    )


# ═══════════════════════════════════════════════════════════════════════
#  Main entry point
# ═══════════════════════════════════════════════════════════════════════


async def ingest_act(
    pdf_path: str | Path,
    vector_store: Any = None,
    embedding_service: Any = None,
) -> list[ActChunk]:
    """Full ingestion pipeline: PDF → chunks → embeddings → pgvector.

    Parameters
    ----------
    pdf_path
        Path to the Companies Act, 2013 PDF.
    vector_store
        VectorStore instance for persisting chunks + embeddings.
    embedding_service
        EmbeddingService instance for generating chunk embeddings.

    Returns
    -------
    list[ActChunk]
        The parsed and indexed chunks.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    logger.info(f"Starting ingestion of {pdf_path.name}...")

    # Step 1: Extract text with metadata
    pages = extract_pages_with_metadata(pdf_path)
    logger.info(f"Extracted {len(pages)} pages")

    # Step 2: Parse into structured chunks
    chunks = parse_act_into_chunks(pages)
    logger.info(f"Created {len(chunks)} section-level chunks")

    # Step 3: Generate embeddings and store (if services provided)
    if embedding_service and vector_store:
        logger.info("Generating embeddings...")
        texts = [chunk.text for chunk in chunks]
        embeddings = await embedding_service.generate_embeddings_batch(texts)

        logger.info("Storing chunks in vector database...")
        await vector_store.store_chunks(chunks, embeddings)
        logger.info("Ingestion complete!")
    else:
        logger.warning(
            "No vector_store or embedding_service provided — "
            "chunks parsed but not indexed"
        )

    return chunks


# CLI entry point
if __name__ == "__main__":
    import asyncio
    import argparse

    parser = argparse.ArgumentParser(
        description="Ingest the Companies Act, 2013 PDF into the vector database"
    )
    parser.add_argument(
        "--pdf-path",
        default="data/companies_act_2013/companies_act_2013.pdf",
        help="Path to the Companies Act PDF",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse only, don't store in database",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    async def main() -> None:
        if args.dry_run:
            chunks = await ingest_act(args.pdf_path)
            print(f"\n{'='*60}")
            print(f"Dry run complete: {len(chunks)} chunks parsed")
            print(f"{'='*60}")
            for i, chunk in enumerate(chunks[:5]):
                print(f"\n--- Chunk {i+1}: {chunk.chunk_id} ---")
                print(f"Chapter: {chunk.chapter_number} — {chunk.chapter_title}")
                print(f"Section: {chunk.section_number} — {chunk.section_title}")
                print(f"Page: {chunk.page_number}, Lines: {chunk.line_start}-{chunk.line_end}")
                print(f"Forms: {chunk.related_forms}")
                print(f"Keywords: {chunk.keywords[:5]}")
                print(f"Text preview: {chunk.text[:150]}...")
        else:
            from app.services.vector_store import VectorStore
            from app.services.embeddings import EmbeddingService

            vs = VectorStore()
            await vs.initialize()
            await vs.create_tables()

            es = EmbeddingService()
            chunks = await ingest_act(args.pdf_path, vs, es)

            await vs.close()
            print(f"\nIngestion complete: {len(chunks)} chunks indexed")

    asyncio.run(main())
