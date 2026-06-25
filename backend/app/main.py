"""
HarveySpecter — FastAPI application entry point.

Initialises middleware, mounts routers, and exposes the health-check
endpoint used by Docker HEALTHCHECK and monitoring probes.
"""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import analyze, chat, documents
from app.services.vector_store import VectorStore


# ── Lifespan ───────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown lifecycle hook.

    • On startup: ensures the pgvector tables exist.
    • On shutdown: closes the database connection pool.
    """
    vector_store = VectorStore()
    try:
        await vector_store.initialize()
        await vector_store.create_tables()
        app.state.vector_store = vector_store
        yield
    finally:
        await vector_store.close()


# ── App factory ────────────────────────────────────────────────────────


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""

    application = FastAPI(
        title="HarveySpecter",
        description=(
            "AI-powered compliance engine for the Companies Act, 2013. "
            "Upload corporate documents, get instant compliance analysis "
            "with precise section-level citations."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ── CORS ───────────────────────────────────────────────────────────
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ────────────────────────────────────────────────────────
    application.include_router(
        documents.router,
        prefix="/api/v1/documents",
        tags=["Documents"],
    )
    application.include_router(
        analyze.router,
        prefix="/api/v1/analyze",
        tags=["Analysis"],
    )
    application.include_router(
        chat.router,
        prefix="/api/v1/chat",
        tags=["Chat"],
    )

    # ── Health-check ───────────────────────────────────────────────────

    @application.get("/health", tags=["System"])
    async def health_check() -> dict[str, Any]:
        """Lightweight liveness probe."""
        return {
            "status": "healthy",
            "service": "harveyspecter",
            "version": "0.1.0",
        }

    return application


app = create_app()
