"""
SQLAlchemy / asyncpg database models for HarveySpecter.

Uses SQLAlchemy 2.0+ style declarative mapping with async support.
The pgvector extension is used for embedding storage and similarity search.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class DocumentRecord(Base):
    """Tracks uploaded documents and their processing status."""

    __tablename__ = "documents"

    id = Column(String(64), primary_key=True)
    filename = Column(String(512), nullable=False)
    file_type = Column(String(128), nullable=False)
    file_path = Column(String(1024), nullable=False)
    page_count = Column(Integer, default=0)
    text_content = Column(Text, default="")
    pages_json = Column(JSONB, default=list)
    metadata_json = Column(JSONB, default=dict)
    uploaded_at = Column(DateTime, default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_documents_uploaded_at", "uploaded_at"),
    )


class ActChunkRecord(Base):
    """A structured chunk of the Companies Act 2013 stored with its embedding."""

    __tablename__ = "act_chunks"

    chunk_id = Column(String(128), primary_key=True)
    chapter_number = Column(String(32), default="")
    chapter_title = Column(String(512), default="")
    section_number = Column(String(32), default="")
    section_title = Column(String(512), default="")
    subsection = Column(String(64), nullable=True)
    text = Column(Text, nullable=False)
    page_number = Column(Integer, default=0)
    line_start = Column(Integer, default=0)
    line_end = Column(Integer, default=0)
    related_forms = Column(ARRAY(String), default=list)
    keywords = Column(ARRAY(String), default=list)
    # Embedding stored as a vector via pgvector — see vector_store for DDL
    # We keep the column definition in raw SQL to work with pgvector properly.

    __table_args__ = (
        Index("ix_act_chunks_section", "section_number"),
        Index("ix_act_chunks_chapter", "chapter_number"),
    )


class AnalysisRecord(Base):
    """Persists analysis jobs and their results."""

    __tablename__ = "analyses"

    id = Column(String(64), primary_key=True)
    document_id = Column(String(64), nullable=False, index=True)
    status = Column(String(32), default="PENDING")
    focus_areas = Column(ARRAY(String), default=list)
    report_json = Column(JSONB, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    completed_at = Column(DateTime, nullable=True)


class ChatMessageRecord(Base):
    """Stores individual chat messages grouped by case_id."""

    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(String(64), nullable=False, index=True)
    role = Column(String(16), nullable=False)
    content = Column(Text, nullable=False)
    citations_json = Column(JSONB, default=list)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_chat_messages_case_created", "case_id", "created_at"),
    )
