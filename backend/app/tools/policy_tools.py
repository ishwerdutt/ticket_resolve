"""
Policy search tool — Production Hybrid RAG Implementation.

Performs BM25 sparse keyword search + pgvector dense cosine search
fused via Reciprocal Rank Fusion (k=60), returning top passages with
formatted section citations.
"""
import time
from typing import Dict, List, Any, Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.rag.embeddings import aget_embedding, format_vector_sql

# Mapping of doc_id to human-readable document titles
DOC_TITLES: Dict[str, str] = {
    "return_policy": "Return Policy",
    "shipping_policy": "Shipping Policy",
    "cancellation_modification_policy": "Cancellation & Modification Policy",
    "warranty_guarantee": "Warranty & Quality Guarantee",
    "faqs": "Frequently Asked Questions",
}

RRF_K: float = 60.0
CANDIDATE_POOL_LIMIT: int = 20


def format_citation(doc_id: str, section: str) -> str:
    """Format citation string, e.g., 'Return Policy § Return Window and Eligibility'."""
    doc_title = DOC_TITLES.get(doc_id, doc_id.replace("_", " ").title())
    return f"{doc_title} § {section}"


def compute_rrf_score(sparse_rank: int | None, dense_rank: int | None, k: float = RRF_K) -> float:
    """Compute Reciprocal Rank Fusion score for ranking or evaluation."""
    score = 0.0
    if sparse_rank is not None and sparse_rank > 0:
        score += 1.0 / (k + sparse_rank)
    if dense_rank is not None and dense_rank > 0:
        score += 1.0 / (k + dense_rank)
    return score


async def search_policy(
    query: str,
    db: AsyncSession,
    top_k: int = 3,
    conversation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Search ThreadNest policy documents using hybrid BM25 + pgvector RRF retrieval.

    Args:
        query: User or agent policy question.
        db: AsyncSession database handle.
        top_k: Number of passages to return (default: 3).
        conversation_id: Optional conversation UUID to persist tool call telemetry.

    Returns:
        Dict with keys:
            passages: list of dicts with doc_id, section, citation, text, score
            count: int
            query: str
    """
    start_time = time.time()
    cleaned_query = query.strip() if query else ""
    if not cleaned_query:
        return {"passages": [], "count": 0, "query": query}

    # 1. Generate query embedding asynchronously
    query_vector = await aget_embedding(cleaned_query)
    query_vec_sql = format_vector_sql(query_vector)

    # 2. Hybrid SQL CTE with Reciprocal Rank Fusion (k=60)
    hybrid_sql = text("""
        WITH sparse_search AS (
            SELECT 
                id,
                doc_id,
                section,
                text,
                ROW_NUMBER() OVER (
                    ORDER BY ts_rank_cd(tsv, websearch_to_tsquery('english', :query)) DESC
                ) AS sparse_rank
            FROM policy_chunks
            WHERE tsv @@ websearch_to_tsquery('english', :query)
            LIMIT :candidate_limit
        ),
        dense_search AS (
            SELECT 
                id,
                doc_id,
                section,
                text,
                ROW_NUMBER() OVER (
                    ORDER BY embedding <=> CAST(:query_vec AS vector) ASC
                ) AS dense_rank
            FROM policy_chunks
            WHERE embedding IS NOT NULL
            LIMIT :candidate_limit
        ),
        fused AS (
            SELECT
                COALESCE(s.id, d.id) AS id,
                COALESCE(s.doc_id, d.doc_id) AS doc_id,
                COALESCE(s.section, d.section) AS section,
                COALESCE(s.text, d.text) AS text,
                (
                    COALESCE(1.0 / (60.0 + s.sparse_rank), 0.0) +
                    COALESCE(1.0 / (60.0 + d.dense_rank), 0.0)
                ) AS rrf_score
            FROM sparse_search s
            FULL OUTER JOIN dense_search d ON s.id = d.id
        )
        SELECT id, doc_id, section, text, rrf_score
        FROM fused
        ORDER BY rrf_score DESC
        LIMIT :top_k;
    """)

    result = await db.execute(
        hybrid_sql,
        {
            "query": cleaned_query,
            "query_vec": query_vec_sql,
            "candidate_limit": CANDIDATE_POOL_LIMIT,
            "top_k": top_k,
        },
    )

    rows = result.mappings().all()
    passages: List[Dict[str, Any]] = []

    for row in rows:
        doc_id = row["doc_id"]
        section = row["section"]
        score = float(row.get("rrf_score", 0.0))

        passages.append({
            "doc_id": doc_id,
            "section": section,
            "citation": format_citation(doc_id, section),
            "text": row["text"],
            "score": round(score, 4),
        })

    result_payload = {
        "passages": passages,
        "count": len(passages),
        "query": query,
    }

    if conversation_id:
        try:
            from app.models.db import ToolCall
            latency_ms = int((time.time() - start_time) * 1000)
            tc = ToolCall(
                conversation_id=conversation_id,
                tool="search_policy",
                args_json={"query": query, "top_k": top_k},
                result_json={
                    "citations": [p["citation"] for p in passages],
                    "count": len(passages),
                },
                latency_ms=latency_ms,
            )
            db.add(tc)
            await db.flush()
        except Exception:
            pass

    return result_payload
