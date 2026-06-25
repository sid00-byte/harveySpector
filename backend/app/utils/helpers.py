"""
Shared utility functions for HarveySpecter backend.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone


def generate_id() -> str:
    """Generate a short unique identifier."""
    return uuid.uuid4().hex


def utc_now() -> datetime:
    """Return the current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


def truncate(text: str, max_length: int = 500, suffix: str = "...") -> str:
    """Truncate text to *max_length* characters, appending *suffix* if cut."""
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix


def sanitize_filename(filename: str) -> str:
    """Remove or replace characters unsafe for filesystem paths."""
    # Keep alphanumerics, dots, hyphens, underscores
    safe = re.sub(r"[^\w.\-]", "_", filename)
    # Collapse multiple underscores
    safe = re.sub(r"_+", "_", safe)
    return safe.strip("_")


def format_citation(
    section: str,
    page: int,
    line_start: int,
    line_end: int | None = None,
) -> str:
    """Format a standard HarveySpecter citation string.

    >>> format_citation("56(1)", 47, 12, 34)
    '[Section 56(1), Page 47, Lines 12-34]'
    """
    line_part = f"Line {line_start}"
    if line_end and line_end != line_start:
        line_part = f"Lines {line_start}-{line_end}"
    return f"[Section {section}, Page {page}, {line_part}]"


def parse_citation(citation_str: str) -> dict[str, str | int] | None:
    """Parse a citation string back into components.

    Returns None if the string doesn't match the expected format.
    """
    pattern = re.compile(
        r"\[Section\s+(.+?),\s*Page\s+(\d+),\s*Lines?\s+(\d+)(?:-(\d+))?\]"
    )
    match = pattern.search(citation_str)
    if not match:
        return None
    return {
        "section": match.group(1),
        "page": int(match.group(2)),
        "line_start": int(match.group(3)),
        "line_end": int(match.group(4)) if match.group(4) else int(match.group(3)),
    }
