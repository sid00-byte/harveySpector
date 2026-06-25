"""
Gemini embedding generation for HarveySpecter.

Wraps the google-genai SDK to produce dense vector embeddings using the
``text-embedding-004`` model.  Supports both single-text and batched
generation with automatic exponential-backoff retry on rate-limit errors.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Sequence

from google import genai
from google.genai import types as genai_types

from app.config import settings

logger = logging.getLogger(__name__)

# Rate-limit retry parameters
_MAX_RETRIES = 5
_BASE_DELAY_SECONDS = 1.0
_BATCH_SIZE = 100  # Gemini batch limit


def _get_client() -> genai.Client:
    """Return a configured Gemini client (reusable, lightweight)."""
    return genai.Client(api_key=settings.GEMINI_API_KEY)


# ═══════════════════════════════════════════════════════════════════════
#  Single embedding
# ═══════════════════════════════════════════════════════════════════════


async def generate_embedding(text: str) -> list[float]:
    """Generate a single embedding vector for *text*.

    Args:
        text: The input string to embed.

    Returns:
        A list of floats representing the embedding vector.

    Raises:
        RuntimeError: After exhausting retries on transient errors.
    """
    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set. A valid Gemini API key is required to generate embeddings.")

    client = _get_client()

    for attempt in range(_MAX_RETRIES):
        try:
            result = await asyncio.to_thread(
                client.models.embed_content,
                model=settings.GEMINI_EMBEDDING_MODEL,
                contents=text,
                config=genai_types.EmbedContentConfig(
                    output_dimensionality=settings.GEMINI_EMBEDDING_DIMENSION,
                ),
            )
            return list(result.embeddings[0].values)
        except Exception as exc:
            if _is_rate_limit_error(exc) and attempt < _MAX_RETRIES - 1:
                delay = 65.0
                logger.warning(
                    "Rate-limited on embedding request (attempt %d/%d), retrying in %.1fs",
                    attempt + 1,
                    _MAX_RETRIES,
                    delay,
                )
                await asyncio.sleep(delay)
            else:
                logger.error("Embedding generation failed: %s", exc)
                raise RuntimeError(f"Embedding generation failed after {attempt + 1} attempts") from exc

    raise RuntimeError("Embedding generation failed: exhausted retries")  # pragma: no cover


# ═══════════════════════════════════════════════════════════════════════
#  Batch embeddings
# ═══════════════════════════════════════════════════════════════════════


async def generate_embeddings_batch(texts: Sequence[str]) -> list[list[float]]:
    """Generate embeddings for a batch of texts.

    Automatically splits into sub-batches of ``_BATCH_SIZE`` to stay
    within API limits and retries on transient rate-limit errors.

    Args:
        texts: Sequence of strings to embed.

    Returns:
        A list of embedding vectors in the same order as *texts*.
    """
    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set. A valid Gemini API key is required to generate batch embeddings.")

    all_embeddings: list[list[float]] = []
    client = _get_client()

    for batch_start in range(0, len(texts), _BATCH_SIZE):
        batch = list(texts[batch_start: batch_start + _BATCH_SIZE])
        embeddings = await _embed_batch_with_retry(client, batch)
        all_embeddings.extend(embeddings)
        
        # Self-throttling to stay under the 15 RPM free-tier limit (1 request every 4 seconds)
        if batch_start + _BATCH_SIZE < len(texts):
            logger.info("Throttling embedding requests... Sleeping for 4.5 seconds.")
            await asyncio.sleep(4.5)

    return all_embeddings


async def _embed_batch_with_retry(
    client: genai.Client,
    texts: list[str],
) -> list[list[float]]:
    """Embed a single sub-batch with exponential-backoff retry."""
    for attempt in range(_MAX_RETRIES):
        try:
            result = await asyncio.to_thread(
                client.models.embed_content,
                model=settings.GEMINI_EMBEDDING_MODEL,
                contents=texts,
                config=genai_types.EmbedContentConfig(
                    output_dimensionality=settings.GEMINI_EMBEDDING_DIMENSION,
                ),
            )
            return [list(e.values) for e in result.embeddings]
        except Exception as exc:
            if _is_rate_limit_error(exc) and attempt < _MAX_RETRIES - 1:
                delay = 65.0
                logger.warning(
                    "Rate-limited on batch embedding (attempt %d/%d, batch_size=%d), "
                    "retrying in %.1fs",
                    attempt + 1,
                    _MAX_RETRIES,
                    len(texts),
                    delay,
                )
                await asyncio.sleep(delay)
            else:
                logger.error("Batch embedding failed: %s", exc)
                raise RuntimeError(
                    f"Batch embedding failed after {attempt + 1} attempts"
                ) from exc

    raise RuntimeError("Batch embedding failed: exhausted retries")  # pragma: no cover


# ═══════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════


def _is_rate_limit_error(exc: BaseException) -> bool:
    """Heuristic check for rate-limit / quota errors from Gemini."""
    error_str = str(exc).lower()
    return any(
        indicator in error_str
        for indicator in ("429", "rate", "quota", "resource_exhausted")
    )


class EmbeddingService:
    """Service wrapper for generating dense vector embeddings using Gemini."""

    async def generate_embedding(self, text: str) -> list[float]:
        """Generate a single embedding vector for text."""
        return await generate_embedding(text)

    async def generate_embeddings_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts."""
        return await generate_embeddings_batch(texts)

