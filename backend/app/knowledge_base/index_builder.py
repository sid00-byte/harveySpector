"""
Index builder — orchestrates the full knowledge base build.

Combines PDF ingestion, embedding generation, and vector storage
into a single command-line workflow.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.knowledge_base.ingest_act import ingest_act
from app.services.embeddings import EmbeddingService
from app.services.vector_store import VectorStore

logger = logging.getLogger(__name__)


async def build_index(
    pdf_dir: str | Path = "data/companies_act_2013",
) -> int:
    """Build the full knowledge-base index from PDFs in the given directory.

    Processes all PDF files found in the directory.

    Returns the total number of chunks indexed.
    """
    pdf_dir = Path(pdf_dir)
    pdf_files = list(pdf_dir.glob("*.pdf"))

    if not pdf_files:
        logger.error(f"No PDF files found in {pdf_dir}")
        return 0

    logger.info(f"Found {len(pdf_files)} PDF file(s) in {pdf_dir}")

    # Initialise services
    vector_store = VectorStore()
    await vector_store.initialize()
    await vector_store.create_tables()

    embedding_service = EmbeddingService()

    total_chunks = 0

    for pdf_path in pdf_files:
        logger.info(f"Processing: {pdf_path.name}")
        try:
            chunks = await ingest_act(pdf_path, vector_store, embedding_service)
            total_chunks += len(chunks)
            logger.info(f"  → {len(chunks)} chunks indexed from {pdf_path.name}")
        except Exception as exc:
            logger.error(f"  ✗ Failed to process {pdf_path.name}: {exc}")

    await vector_store.close()
    logger.info(f"Index build complete: {total_chunks} total chunks")
    return total_chunks


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    count = asyncio.run(build_index())
    print(f"\n✅ Knowledge base built: {count} chunks indexed")
