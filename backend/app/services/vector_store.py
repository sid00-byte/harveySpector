"""
pgvector-backed vector store for HarveySpecter.

Manages the ``act_chunks`` table (including the ``embedding`` vector column)
using raw ``asyncpg`` for performance.  Provides hybrid search that combines
BM25-style full-text search with cosine-similarity vector search.
"""

from __future__ import annotations

import json
import logging
from typing import Any
import sqlite3
import asyncio
from datetime import datetime, timezone

import asyncpg

from app.config import settings
from app.models.schemas import ActChunk

logger = logging.getLogger(__name__)


class VectorStore:
    """Async pgvector operations over a connection pool with local SQLite fallback."""

    def __init__(self) -> None:
        self._pool: asyncpg.Pool | None = None
        self._fallback_db_path = "data/harvey_fallback.db"
        self._is_fallback = False

    # ── Lifecycle ──────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Create the asyncpg connection pool or fall back to SQLite."""
        try:
            self._pool = await asyncpg.create_pool(
                dsn=settings.DATABASE_URL,
                min_size=2,
                max_size=10,
            )
            logger.info("Database connection pool created")
        except Exception as exc:
            logger.warning("Failed to create database pool: %s. Falling back to local SQLite database.", exc)
            self._is_fallback = True
            import os
            os.makedirs("data", exist_ok=True)

    async def close(self) -> None:
        """Gracefully close the pool."""
        if self._pool:
            await self._pool.close()
            logger.info("Database connection pool closed")

    @property
    def pool(self) -> asyncpg.Pool:
        """Return the pool, raising if not initialised."""
        if self._pool is None:
            if self._is_fallback:
                raise RuntimeError("VectorStore is in SQLite fallback mode — asyncpg pool not available")
            raise RuntimeError("VectorStore not initialised — call initialize() first")
        return self._pool

    # ── DDL ────────────────────────────────────────────────────────────

    async def create_tables(self) -> None:
        """Ensure the pgvector extension and required tables exist.

        This is idempotent — safe to call on every startup.
        """
        if self._is_fallback:
            await asyncio.to_thread(self._sqlite_create_tables)
            return

        dim = settings.GEMINI_EMBEDDING_DIMENSION

        async with self.pool.acquire() as conn:
            # Enable pgvector extension
            try:
                await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            except Exception as exc:
                logger.warning("Could not enable vector extension: %s", exc)

            # Act chunks table with embedding column
            try:
                await conn.execute(f"""
                    CREATE TABLE IF NOT EXISTS act_chunks (
                        chunk_id       TEXT PRIMARY KEY,
                        chapter_number TEXT DEFAULT '',
                        chapter_title  TEXT DEFAULT '',
                        section_number TEXT DEFAULT '',
                        section_title  TEXT DEFAULT '',
                        subsection     TEXT,
                        text           TEXT NOT NULL,
                        page_number    INTEGER DEFAULT 0,
                        line_start     INTEGER DEFAULT 0,
                        line_end       INTEGER DEFAULT 0,
                        related_forms  TEXT[] DEFAULT ARRAY[]::TEXT[],
                        keywords       TEXT[] DEFAULT ARRAY[]::TEXT[],
                        embedding      vector({dim})
                    );
                """)
            except Exception as exc:
                logger.error("Could not create act_chunks table: %s", exc)
                raise exc

             # Full-text search index using GIN
            try:
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS ix_act_chunks_fts
                    ON act_chunks USING gin(to_tsvector('english', text));
                """)
            except Exception as exc:
                logger.warning("Could not create GIN index: %s", exc)

            # Metadata indexes for fast lookups
            try:
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS ix_act_chunks_sec_num ON act_chunks (section_number);
                """)
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS ix_act_chunks_chap_num ON act_chunks (chapter_number);
                """)
            except Exception as exc:
                logger.warning("Could not create metadata indexes: %s", exc)

            # Vector similarity index (IVFFlat)
            try:
                await conn.execute(f"""
                    CREATE INDEX IF NOT EXISTS ix_act_chunks_embedding
                    ON act_chunks USING ivfflat (embedding vector_cosine_ops)
                    WITH (lists = 50);
                """)
            except Exception as exc:
                logger.warning("Could not create vector index: %s", exc)

            # Documents table
            try:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS documents (
                        id             TEXT PRIMARY KEY,
                        filename       TEXT NOT NULL,
                        file_type      TEXT NOT NULL,
                        file_path      TEXT NOT NULL,
                        page_count     INTEGER DEFAULT 0,
                        text_content   TEXT DEFAULT '',
                        pages_json     JSONB DEFAULT '[]'::jsonb,
                        metadata_json  JSONB DEFAULT '{{}}'::jsonb,
                        uploaded_at    TIMESTAMPTZ DEFAULT now()
                    );
                """)
            except Exception as exc:
                logger.warning("Could not create documents table: %s", exc)

            # Analyses table
            try:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS analyses (
                        id             TEXT PRIMARY KEY,
                        document_id    TEXT NOT NULL,
                        status         TEXT DEFAULT 'PENDING',
                        focus_areas    TEXT[] DEFAULT ARRAY[]::TEXT[],
                        report_json    JSONB,
                        error          TEXT,
                        created_at     TIMESTAMPTZ DEFAULT now(),
                        completed_at   TIMESTAMPTZ
                    );
                """)
            except Exception as exc:
                logger.warning("Could not create analyses table: %s", exc)

            # Chat messages table
            try:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS chat_messages (
                        id             SERIAL PRIMARY KEY,
                        case_id        TEXT NOT NULL,
                        role           TEXT NOT NULL,
                        content        TEXT NOT NULL,
                        citations_json JSONB DEFAULT '[]'::jsonb,
                        created_at     TIMESTAMPTZ DEFAULT now()
                    );
                """)
            except Exception as exc:
                logger.warning("Could not create chat_messages table: %s", exc)

            try:
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS ix_chat_case_time
                    ON chat_messages (case_id, created_at);
                """)
            except Exception:
                try:
                    await conn.execute("""
                        CREATE INDEX IF NOT EXISTS ix_chat_case_time
                        ON chat_messages ("caseId", "createdAt");
                    """)
                except Exception as exc:
                    logger.warning("Could not create chat messages index: %s", exc)

        logger.info("Database tables verified / created")

    # ── Chunk storage ──────────────────────────────────────────────────

    async def store_chunks(
        self,
        chunks: list[ActChunk],
        embeddings: list[list[float]],
    ) -> int:
        """Batch-insert Act chunks with their embeddings.

        Args:
            chunks: Parsed Act chunks.
            embeddings: Corresponding embedding vectors (same order/length).

        Returns:
            Number of rows inserted.
        """
        if self._is_fallback:
            return await asyncio.to_thread(self._sqlite_store_chunks, chunks, embeddings)

        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length")

        rows: list[tuple[Any, ...]] = []
        for chunk, emb in zip(chunks, embeddings):
            emb_str = "[" + ",".join(str(v) for v in emb) + "]"
            rows.append((
                chunk.chunk_id,
                chunk.chapter_number,
                chunk.chapter_title,
                chunk.section_number,
                chunk.section_title,
                chunk.subsection,
                chunk.text,
                chunk.page_number,
                chunk.line_start,
                chunk.line_end,
                chunk.related_forms,
                chunk.keywords,
                emb_str,
            ))

        async with self.pool.acquire() as conn:
            inserted = await conn.executemany(
                """
                INSERT INTO act_chunks (
                    chunk_id, chapter_number, chapter_title,
                    section_number, section_title, subsection,
                    text, page_number, line_start, line_end,
                    related_forms, keywords, embedding
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13::vector
                )
                ON CONFLICT (chunk_id) DO UPDATE SET
                    text = EXCLUDED.text,
                    embedding = EXCLUDED.embedding;
                """,
                rows,
            )

        logger.info("Stored %d Act chunks", len(rows))
        return len(rows)

    # ── Hybrid search ──────────────────────────────────────────────────

    async def hybrid_search(
        self,
        query_text: str,
        query_embedding: list[float],
        top_k: int = 15,
        *,
        vector_weight: float = 0.6,
        bm25_weight: float = 0.4,
    ) -> list[ActChunk]:
        """Combine BM25 full-text search with cosine-similarity vector search.

        The final ranking is a weighted sum of both scores, normalised
        to [0, 1].  This hybrid approach captures both lexical matches
        (important for section numbers, form names) and semantic similarity.

        Args:
            query_text: Raw query string for BM25.
            query_embedding: Dense vector for cosine search.
            top_k: Number of results to return.
            vector_weight: Weight for vector similarity (0-1).
            bm25_weight: Weight for BM25 score (0-1).

        Returns:
            Ranked list of ``ActChunk`` instances.
        """
        if self._is_fallback:
            return await asyncio.to_thread(
                self._sqlite_hybrid_search,
                query_text,
                query_embedding,
                top_k,
                vector_weight=vector_weight,
                bm25_weight=bm25_weight,
            )

        emb_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

        sql = f"""
            WITH vector_results AS (
                SELECT
                    chunk_id,
                    1 - (embedding <=> $1::vector) AS vector_score
                FROM act_chunks
                ORDER BY embedding <=> $1::vector
                LIMIT $3
            ),
            bm25_results AS (
                SELECT
                    chunk_id,
                    ts_rank_cd(
                        to_tsvector('english', text),
                        plainto_tsquery('english', $2)
                    ) AS bm25_score
                FROM act_chunks
                WHERE to_tsvector('english', text) @@ plainto_tsquery('english', $2)
                ORDER BY bm25_score DESC
                LIMIT $3
            ),
            combined AS (
                SELECT
                    COALESCE(v.chunk_id, b.chunk_id) AS chunk_id,
                    (COALESCE(v.vector_score, 0) * {vector_weight}) +
                    (COALESCE(b.bm25_score, 0) * {bm25_weight}) AS combined_score
                FROM vector_results v
                FULL OUTER JOIN bm25_results b ON v.chunk_id = b.chunk_id
                ORDER BY combined_score DESC
                LIMIT $3
            )
            SELECT
                c.chunk_id, c.chapter_number, c.chapter_title,
                c.section_number, c.section_title, c.subsection,
                c.text, c.page_number, c.line_start, c.line_end,
                c.related_forms, c.keywords
            FROM combined comb
            JOIN act_chunks c ON c.chunk_id = comb.chunk_id
            ORDER BY comb.combined_score DESC;
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, emb_str, query_text, top_k)

        return [
            ActChunk(
                chunk_id=row["chunk_id"],
                chapter_number=row["chapter_number"],
                chapter_title=row["chapter_title"],
                section_number=row["section_number"],
                section_title=row["section_title"],
                subsection=row["subsection"],
                text=row["text"],
                page_number=row["page_number"],
                line_start=row["line_start"],
                line_end=row["line_end"],
                related_forms=list(row["related_forms"] or []),
                keywords=list(row["keywords"] or []),
            )
            for row in rows
        ]

    # ── Single-chunk lookup ────────────────────────────────────────────

    async def get_chunk_by_id(self, chunk_id: str) -> ActChunk | None:
        """Retrieve a single chunk by its ID.

        Args:
            chunk_id: The unique chunk identifier.

        Returns:
            An ``ActChunk`` or ``None`` if not found.
        """
        if self._is_fallback:
            return await asyncio.to_thread(self._sqlite_get_chunk_by_id, chunk_id)

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT chunk_id, chapter_number, chapter_title,
                       section_number, section_title, subsection,
                       text, page_number, line_start, line_end,
                       related_forms, keywords
                FROM act_chunks WHERE chunk_id = $1;
                """,
                chunk_id,
            )

        if row is None:
            return None

        return ActChunk(
            chunk_id=row["chunk_id"],
            chapter_number=row["chapter_number"],
            chapter_title=row["chapter_title"],
            section_number=row["section_number"],
            section_title=row["section_title"],
            subsection=row["subsection"],
            text=row["text"],
            page_number=row["page_number"],
            line_start=row["line_start"],
            line_end=row["line_end"],
            related_forms=list(row["related_forms"] or []),
            keywords=list(row["keywords"] or []),
        )

    # ── Section search ─────────────────────────────────────────────────

    async def find_chunks_by_section(self, section_number: str) -> list[ActChunk]:
        """Find all chunks for a given section number.

        Useful for citation verification — given a cited section, retrieve
        the actual source text.

        Args:
            section_number: e.g. ``"173"`` or ``"56"``.

        Returns:
            List of matching ``ActChunk`` instances.
        """
        if self._is_fallback:
            return await asyncio.to_thread(self._sqlite_find_chunks_by_section, section_number)

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT chunk_id, chapter_number, chapter_title,
                       section_number, section_title, subsection,
                       text, page_number, line_start, line_end,
                       related_forms, keywords
                FROM act_chunks
                WHERE section_number = $1
                ORDER BY line_start;
                """,
                section_number,
            )

        return [
            ActChunk(
                chunk_id=row["chunk_id"],
                chapter_number=row["chapter_number"],
                chapter_title=row["chapter_title"],
                section_number=row["section_number"],
                section_title=row["section_title"],
                subsection=row["subsection"],
                text=row["text"],
                page_number=row["page_number"],
                line_start=row["line_start"],
                line_end=row["line_end"],
                related_forms=list(row["related_forms"] or []),
                keywords=list(row["keywords"] or []),
            )
            for row in rows
        ]

    # ── Document CRUD (convenience) ───────────────────────────────────

    async def store_document(
        self,
        doc_id: str,
        filename: str,
        file_type: str,
        file_path: str,
        page_count: int,
        text_content: str,
        pages_json: list[dict[str, Any]],
        metadata_json: dict[str, Any],
    ) -> None:
        """Persist a document record."""
        if self._is_fallback:
            return await asyncio.to_thread(
                self._sqlite_store_document,
                doc_id, filename, file_type, file_path, page_count, text_content, pages_json, metadata_json
            )

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO documents (
                    id, filename, file_type, file_path,
                    page_count, text_content, pages_json, metadata_json
                ) VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb)
                ON CONFLICT (id) DO UPDATE SET
                    text_content = EXCLUDED.text_content,
                    pages_json = EXCLUDED.pages_json;
                """,
                doc_id, filename, file_type, file_path,
                page_count, text_content,
                json.dumps(pages_json),
                json.dumps(metadata_json),
            )

    async def get_document(self, doc_id: str) -> dict[str, Any] | None:
        """Retrieve a document record by ID."""
        if self._is_fallback:
            return await asyncio.to_thread(self._sqlite_get_document, doc_id)

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM documents WHERE id = $1;", doc_id
            )
        return dict(row) if row else None

    # ── Analysis CRUD ─────────────────────────────────────────────────

    async def store_analysis(
        self,
        analysis_id: str,
        document_id: str,
        status: str = "PENDING",
        focus_areas: list[str] | None = None,
    ) -> None:
        """Create an analysis record."""
        if self._is_fallback:
            return await asyncio.to_thread(
                self._sqlite_store_analysis, analysis_id, document_id, status, focus_areas
            )

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO analyses (id, document_id, status, focus_areas)
                VALUES ($1, $2, $3, $4);
                """,
                analysis_id, document_id, status, focus_areas or [],
            )

    async def update_analysis(
        self,
        analysis_id: str,
        status: str,
        report_json: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """Update an analysis record with results or error."""
        if self._is_fallback:
            return await asyncio.to_thread(
                self._sqlite_update_analysis, analysis_id, status, report_json, error
            )

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE analyses
                SET status = $2,
                    report_json = $3::jsonb,
                    error = $4,
                    completed_at = now()
                WHERE id = $1;
                """,
                analysis_id, status,
                json.dumps(report_json) if report_json else None,
                error,
            )

    async def get_analysis(self, analysis_id: str) -> dict[str, Any] | None:
        """Retrieve an analysis record by ID."""
        if self._is_fallback:
            return await asyncio.to_thread(self._sqlite_get_analysis, analysis_id)

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM analyses WHERE id = $1;", analysis_id
            )
        return dict(row) if row else None

    # ── Chat message CRUD ─────────────────────────────────────────────

    async def store_chat_message(
        self,
        case_id: str,
        role: str,
        content: str,
        citations_json: list[dict[str, Any]] | None = None,
    ) -> None:
        """Persist a single chat message."""
        if self._is_fallback:
            return await asyncio.to_thread(
                self._sqlite_store_chat_message, case_id, role, content, citations_json
            )

        import uuid
        msg_id = f"msg-{uuid.uuid4().hex[:12]}"
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO chat_messages (id, "caseId", role, content, "references")
                VALUES ($1, $2, $3, $4, $5::jsonb);
                """,
                msg_id, case_id, role, content,
                json.dumps(citations_json or []),
            )

    async def get_chat_history(self, case_id: str) -> list[dict[str, Any]]:
        """Return all messages for a case, ordered chronologically."""
        if self._is_fallback:
            return await asyncio.to_thread(self._sqlite_get_chat_history, case_id)

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT role, content, "references" AS citations_json, "createdAt" AS created_at
                FROM chat_messages
                WHERE "caseId" = $1
                ORDER BY "createdAt" ASC;
                """,
                case_id,
            )
        return [dict(row) for row in rows]

    # ── SQLite Fallback Implementations ───────────────────────────────

    def _get_sqlite_conn(self):
        conn = sqlite3.connect(self._fallback_db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _sqlite_create_tables(self) -> None:
        with self._get_sqlite_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS act_chunks (
                    chunk_id       TEXT PRIMARY KEY,
                    chapter_number TEXT,
                    chapter_title  TEXT,
                    section_number TEXT,
                    section_title  TEXT,
                    subsection     TEXT,
                    text           TEXT NOT NULL,
                    page_number    INTEGER,
                    line_start     INTEGER,
                    line_end       INTEGER,
                    related_forms  TEXT,
                    keywords       TEXT,
                    embedding      TEXT
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id             TEXT PRIMARY KEY,
                    filename       TEXT NOT NULL,
                    file_type      TEXT NOT NULL,
                    file_path      TEXT NOT NULL,
                    page_count     INTEGER,
                    text_content   TEXT,
                    pages_json     TEXT,
                    metadata_json  TEXT,
                    uploaded_at    TEXT
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS analyses (
                    id             TEXT PRIMARY KEY,
                    document_id    TEXT NOT NULL,
                    status         TEXT,
                    focus_areas    TEXT,
                    report_json    TEXT,
                    error          TEXT,
                    created_at     TEXT,
                    completed_at   TEXT
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id        TEXT NOT NULL,
                    role           TEXT NOT NULL,
                    content        TEXT NOT NULL,
                    citations_json TEXT,
                    created_at     TEXT
                );
            """)
        logger.info("SQLite fallback tables verified / created")

    def _sqlite_store_chunks(self, chunks: list[ActChunk], embeddings: list[list[float]]) -> int:
        with self._get_sqlite_conn() as conn:
            rows = []
            for chunk, emb in zip(chunks, embeddings):
                emb_str = json.dumps(emb)
                rows.append((
                    chunk.chunk_id,
                    chunk.chapter_number,
                    chunk.chapter_title,
                    chunk.section_number,
                    chunk.section_title,
                    chunk.subsection,
                    chunk.text,
                    chunk.page_number,
                    chunk.line_start,
                    chunk.line_end,
                    json.dumps(chunk.related_forms),
                    json.dumps(chunk.keywords),
                    emb_str
                ))
            conn.executemany("""
                INSERT OR REPLACE INTO act_chunks (
                    chunk_id, chapter_number, chapter_title,
                    section_number, section_title, subsection,
                    text, page_number, line_start, line_end,
                    related_forms, keywords, embedding
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, rows)
            return len(rows)

    def _sqlite_hybrid_search(
        self,
        query_text: str,
        query_embedding: list[float],
        top_k: int = 15,
        *,
        vector_weight: float = 0.6,
        bm25_weight: float = 0.4,
    ) -> list[ActChunk]:
        with self._get_sqlite_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM act_chunks")
            rows = cursor.fetchall()
        
        import numpy as np
        
        results = []
        q_vec = np.array(query_embedding)
        q_words = set(query_text.lower().split())
        
        for row in rows:
            emb_str = row["embedding"]
            vector_score = 0.0
            if emb_str:
                try:
                    emb_vec = np.array(json.loads(emb_str))
                    norm_prod = np.linalg.norm(q_vec) * np.linalg.norm(emb_vec)
                    if norm_prod > 0:
                        vector_score = np.dot(q_vec, emb_vec) / norm_prod
                except Exception:
                    pass
            
            chunk_text = row["text"].lower()
            match_count = sum(1 for w in q_words if w in chunk_text)
            bm25_score = (match_count / max(len(q_words), 1))
            
            combined_score = (vector_score * vector_weight) + (bm25_score * bm25_weight)
            
            try:
                related_forms = json.loads(row["related_forms"]) if row["related_forms"] else []
            except Exception:
                related_forms = []
            try:
                keywords = json.loads(row["keywords"]) if row["keywords"] else []
            except Exception:
                keywords = []
                
            chunk = ActChunk(
                chunk_id=row["chunk_id"],
                chapter_number=row["chapter_number"] or "",
                chapter_title=row["chapter_title"] or "",
                section_number=row["section_number"] or "",
                section_title=row["section_title"] or "",
                subsection=row["subsection"],
                text=row["text"],
                page_number=row["page_number"] or 0,
                line_start=row["line_start"] or 0,
                line_end=row["line_end"] or 0,
                related_forms=related_forms,
                keywords=keywords,
            )
            results.append((chunk, combined_score))
            
        results.sort(key=lambda x: x[1], reverse=True)
        return [r[0] for r in results[:top_k]]

    def _sqlite_get_chunk_by_id(self, chunk_id: str) -> ActChunk | None:
        with self._get_sqlite_conn() as conn:
            row = conn.execute("SELECT * FROM act_chunks WHERE chunk_id = ?", (chunk_id,)).fetchone()
        if not row:
            return None
        try:
            related_forms = json.loads(row["related_forms"]) if row["related_forms"] else []
        except Exception:
            related_forms = []
        try:
            keywords = json.loads(row["keywords"]) if row["keywords"] else []
        except Exception:
            keywords = []
        return ActChunk(
            chunk_id=row["chunk_id"],
            chapter_number=row["chapter_number"] or "",
            chapter_title=row["chapter_title"] or "",
            section_number=row["section_number"] or "",
            section_title=row["section_title"] or "",
            subsection=row["subsection"],
            text=row["text"],
            page_number=row["page_number"] or 0,
            line_start=row["line_start"] or 0,
            line_end=row["line_end"] or 0,
            related_forms=related_forms,
            keywords=keywords,
        )

    def _sqlite_find_chunks_by_section(self, section_number: str) -> list[ActChunk]:
        with self._get_sqlite_conn() as conn:
            rows = conn.execute("SELECT * FROM act_chunks WHERE section_number = ? ORDER BY line_start", (section_number,)).fetchall()
        chunks = []
        for row in rows:
            try:
                related_forms = json.loads(row["related_forms"]) if row["related_forms"] else []
            except Exception:
                related_forms = []
            try:
                keywords = json.loads(row["keywords"]) if row["keywords"] else []
            except Exception:
                keywords = []
            chunks.append(ActChunk(
                chunk_id=row["chunk_id"],
                chapter_number=row["chapter_number"] or "",
                chapter_title=row["chapter_title"] or "",
                section_number=row["section_number"] or "",
                section_title=row["section_title"] or "",
                subsection=row["subsection"],
                text=row["text"],
                page_number=row["page_number"] or 0,
                line_start=row["line_start"] or 0,
                line_end=row["line_end"] or 0,
                related_forms=related_forms,
                keywords=keywords,
            ))
        return chunks

    def _sqlite_store_document(
        self,
        doc_id: str,
        filename: str,
        file_type: str,
        file_path: str,
        page_count: int,
        text_content: str,
        pages_json: list[dict[str, Any]],
        metadata_json: dict[str, Any],
    ) -> None:
        with self._get_sqlite_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO documents (
                    id, filename, file_type, file_path,
                    page_count, text_content, pages_json, metadata_json, uploaded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (doc_id, filename, file_type, file_path,
                 page_count, text_content,
                 json.dumps(pages_json),
                 json.dumps(metadata_json),
                 datetime.now(timezone.utc).isoformat())
            )

    def _sqlite_get_document(self, doc_id: str) -> dict[str, Any] | None:
        with self._get_sqlite_conn() as conn:
            row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not row:
            return None
        res = dict(row)
        res["pages_json"] = json.loads(res["pages_json"]) if res["pages_json"] else []
        res["metadata_json"] = json.loads(res["metadata_json"]) if res["metadata_json"] else {}
        return res

    def _sqlite_store_analysis(
        self,
        analysis_id: str,
        document_id: str,
        status: str = "PENDING",
        focus_areas: list[str] | None = None,
    ) -> None:
        with self._get_sqlite_conn() as conn:
            conn.execute(
                """
                INSERT INTO analyses (id, document_id, status, focus_areas, created_at)
                VALUES (?, ?, ?, ?, ?);
                """,
                (analysis_id, document_id, status, json.dumps(focus_areas or []), datetime.now(timezone.utc).isoformat()),
            )

    def _sqlite_update_analysis(
        self,
        analysis_id: str,
        status: str,
        report_json: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        with self._get_sqlite_conn() as conn:
            conn.execute(
                """
                UPDATE analyses
                SET status = ?,
                    report_json = ?,
                    error = ?,
                    completed_at = ?
                WHERE id = ?;
                """,
                (status, json.dumps(report_json) if report_json else None, error, datetime.now(timezone.utc).isoformat(), analysis_id),
            )

    def _sqlite_get_analysis(self, analysis_id: str) -> dict[str, Any] | None:
        with self._get_sqlite_conn() as conn:
            row = conn.execute("SELECT * FROM analyses WHERE id = ?;", (analysis_id,)).fetchone()
        if not row:
            return None
        res = dict(row)
        res["focus_areas"] = json.loads(res["focus_areas"]) if res["focus_areas"] else []
        res["report_json"] = json.loads(res["report_json"]) if res["report_json"] else None
        return res

    def _sqlite_store_chat_message(
        self,
        case_id: str,
        role: str,
        content: str,
        citations_json: list[dict[str, Any]] | None = None,
    ) -> None:
        with self._get_sqlite_conn() as conn:
            conn.execute(
                """
                INSERT INTO chat_messages (case_id, role, content, citations_json, created_at)
                VALUES (?, ?, ?, ?, ?);
                """,
                (case_id, role, content, json.dumps(citations_json or []), datetime.now(timezone.utc).isoformat()),
            )

    def _sqlite_get_chat_history(self, case_id: str) -> list[dict[str, Any]]:
        with self._get_sqlite_conn() as conn:
            rows = conn.execute(
                """
                SELECT role, content, citations_json, created_at
                FROM chat_messages
                WHERE case_id = ?
                ORDER BY created_at ASC;
                """,
                (case_id,),
            ).fetchall()
        res = []
        for row in rows:
            d = dict(row)
            d["citations_json"] = json.loads(d["citations_json"]) if d["citations_json"] else []
            res.append(d)
        return res
