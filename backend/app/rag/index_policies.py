"""
Policy Ingestion CLI script.

Usage:
    python -m app.rag.index_policies [--policies-dir PATH] [--clear] [--dry-run] [--batch-size N]
"""
import argparse
import asyncio
import logging
import sys
import uuid
from pathlib import Path
from typing import List, Dict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.rag.chunker import chunk_markdown
from app.rag.embeddings import get_embeddings, format_vector_sql

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("index_policies")

DEFAULT_POLICIES_DIR = Path(__file__).resolve().parent.parent / "policies"


async def index_policies(
    policies_dir: Path,
    clear_existing: bool = True,
    dry_run: bool = False,
    batch_size: int = 100,
) -> int:
    """
    Index all markdown policy files from policies_dir into policy_chunks table.
    """
    if not policies_dir.exists():
        logger.error(f"Policies directory not found: {policies_dir}")
        return 0

    md_files = sorted(list(policies_dir.glob("*.md")))
    if not md_files:
        logger.warning(f"No markdown (.md) policy files found in {policies_dir}")
        return 0

    logger.info(f"Found {len(md_files)} policy documents in {policies_dir}")

    all_chunks: List[Dict] = []
    doc_ids_to_index: List[str] = []

    for file_path in md_files:
        doc_id = file_path.stem  # e.g., 'return_policy'
        doc_ids_to_index.append(doc_id)

        content = file_path.read_text(encoding="utf-8")
        chunks = chunk_markdown(content, doc_id=doc_id)
        logger.info(f"Parsed '{doc_id}': {len(chunks)} chunks, total tokens: {sum(c['token_count'] for c in chunks)}")
        all_chunks.extend(chunks)

    if not all_chunks:
        logger.warning("No chunks generated from policy documents.")
        return 0

    logger.info(f"Total chunks to index: {len(all_chunks)}")

    if dry_run:
        logger.info("DRY-RUN mode enabled. Displaying first 3 chunks and exiting without DB writes:")
        for idx, c in enumerate(all_chunks[:3]):
            logger.info(f"[{idx+1}] Doc: {c['doc_id']} | Section: {c['section']} | Tokens: {c['token_count']}")
            logger.info(f"Text Preview: {c['text'][:120]}...\n")
        return len(all_chunks)

    # Generate embeddings in batches
    logger.info(f"Generating embeddings for {len(all_chunks)} chunks via OpenAI text-embedding-3-small...")
    texts_to_embed = [c["text"] for c in all_chunks]
    embeddings = get_embeddings(texts_to_embed, batch_size=batch_size)

    # Insert into database
    logger.info(f"Connecting to database at {settings.DATABASE_URL.split('@')[-1]}...")
    engine = create_async_engine(settings.DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        if clear_existing:
            logger.info(f"Clearing existing policy chunks for docs: {doc_ids_to_index}...")
            await conn.execute(
                text("DELETE FROM policy_chunks WHERE doc_id = ANY(:doc_ids)"),
                {"doc_ids": doc_ids_to_index},
            )

        insert_stmt = text("""
            INSERT INTO policy_chunks (id, doc_id, section, text, embedding)
            VALUES (:id, :doc_id, :section, :text, CAST(:embedding AS vector))
        """)

        logger.info("Inserting chunk records into 'policy_chunks'...")
        for chunk, emb in zip(all_chunks, embeddings):
            chunk_id = uuid.uuid4()
            emb_str = format_vector_sql(emb)
            await conn.execute(
                insert_stmt,
                {
                    "id": chunk_id,
                    "doc_id": chunk["doc_id"],
                    "section": chunk["section"],
                    "text": chunk["text"],
                    "embedding": emb_str,
                },
            )

        # Verify count
        count_res = await conn.execute(text("SELECT count(*) FROM policy_chunks;"))
        total_rows = count_res.scalar()
        logger.info(f"Successfully indexed! Total rows in 'policy_chunks': {total_rows}")

    await engine.dispose()
    return len(all_chunks)


def main():
    parser = argparse.ArgumentParser(description="ThreadNest Policy Ingestion CLI")
    parser.add_argument(
        "--policies-dir",
        type=Path,
        default=DEFAULT_POLICIES_DIR,
        help="Path to markdown policy directory",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        default=True,
        help="Clear existing chunks for the target docs before inserting (default: True)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chunk and inspect without calling OpenAI or writing to DB",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Embedding batch size",
    )

    args = parser.parse_args()
    try:
        count = asyncio.run(
            index_policies(
                policies_dir=args.policies_dir,
                clear_existing=args.clear,
                dry_run=args.dry_run,
                batch_size=args.batch_size,
            )
        )
        sys.exit(0 if count > 0 or args.dry_run else 1)
    except Exception as e:
        logger.exception(f"Error during policy ingestion: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
