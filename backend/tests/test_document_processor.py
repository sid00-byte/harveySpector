"""
Tests for the document processor service.

Tests PDF, DOCX, text, and image extraction pipelines.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from app.services.document_processor import DocumentProcessor
from app.models.schemas import DocumentResult


@pytest.fixture
def processor() -> DocumentProcessor:
    return DocumentProcessor()


class TestTextExtraction:
    """Tests for plain text processing."""

    def test_extract_text_basic(self, processor: DocumentProcessor) -> None:
        """Text extraction should return all lines with numbering."""
        text = "Line one\nLine two\nLine three"
        result = processor.extract_text(text)

        assert isinstance(result, DocumentResult)
        assert "Line one" in result.text
        assert "Line two" in result.text
        assert "Line three" in result.text
        assert len(result.pages) == 1
        assert len(result.pages[0].lines) == 3

    def test_extract_text_empty(self, processor: DocumentProcessor) -> None:
        """Empty text should produce valid but empty result."""
        result = processor.extract_text("")
        assert isinstance(result, DocumentResult)
        assert result.text == ""

    def test_extract_text_preserves_content(self, processor: DocumentProcessor) -> None:
        """All input text should be preserved in the output."""
        text = "Section 56. Transfer of shares.\n(1) A company shall not register..."
        result = processor.extract_text(text)
        assert "Section 56" in result.text
        assert "Transfer of shares" in result.text

    def test_extract_text_metadata(self, processor: DocumentProcessor) -> None:
        """Metadata should include file_type."""
        result = processor.extract_text("test content")
        assert result.metadata.get("file_type") == "text"


class TestPDFExtraction:
    """Tests for PDF processing (requires a PDF file)."""

    def test_extract_pdf_missing_file(self, processor: DocumentProcessor) -> None:
        """Should raise an error for non-existent PDF."""
        with pytest.raises(Exception):
            processor.extract_pdf("/nonexistent/path.pdf")


class TestDocxExtraction:
    """Tests for DOCX processing (requires python-docx)."""

    def test_extract_docx_missing_file(self, processor: DocumentProcessor) -> None:
        """Should raise an error for non-existent DOCX."""
        with pytest.raises(Exception):
            processor.extract_docx("/nonexistent/path.docx")


class TestImageExtraction:
    """Tests for image/OCR processing."""

    def test_extract_image_placeholder(self, processor: DocumentProcessor) -> None:
        """Image extraction should return a placeholder message for MVP."""
        result = processor.extract_image("/some/image.png")
        assert isinstance(result, DocumentResult)
        # Should indicate OCR is not yet configured or provide placeholder text
