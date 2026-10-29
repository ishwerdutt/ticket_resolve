"""
Tests for Policy RAG Pipeline: Chunking, Embeddings, Ingestion, and Hybrid Retrieval.
100% offline testability with mocked OpenAI API and SQLAlchemy async database sessions.
"""
import math
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.rag.chunker import (
    chunk_markdown,
    clean_heading,
)
from app.rag.embeddings import (
    aget_embedding,
    aget_embeddings,
    format_vector_sql,
    generate_mock_embedding,
    get_embedding,
    get_embeddings,
)
from app.rag.index_policies import index_policies
from app.tools.policy_tools import (
    compute_rrf_score,
    format_citation,
    search_policy,
)

# ─── Section 1: Markdown Chunking Engine Unit Tests ─────────────────────────

def test_chunk_markdown_empty_input():
    """Empty or whitespace-only markdown should return an empty chunk list."""
    assert chunk_markdown("", "doc_empty") == []
    assert chunk_markdown("   \n\t  \n  ", "doc_ws") == []


def test_chunk_markdown_heading_preservation_and_cleaning():
    """Headings with numeric prefixes should be cleaned and preserved in section metadata."""
    md = """# Return Policy

## 1. Return Window and Eligibility

ThreadNest offers a generous 30-day return window from the date of confirmed delivery.
Customers can return any unworn, unwashed garment with original tags attached.
We strive to make the return process seamless and transparent for every customer.

### 1.1 Exceptions and Exclusions

Undergarments and customized apparel cannot be returned due to hygiene and bespoke standards.
All other standard clothing items are fully eligible for return or exchange within the window.
"""
    chunks = chunk_markdown(md, "return_policy", min_tokens=50, max_tokens=300)
    assert len(chunks) >= 1

    sections = [c["section"] for c in chunks]
    assert any("Return Window and Eligibility" in s for s in sections)

    for c in chunks:
        assert c["doc_id"] == "return_policy"
        assert c["token_count"] > 0
        assert "## " in c["text"]  # Context header preserved


def test_clean_heading_numeric_and_fallbacks():
    """Test clean_heading behavior with various headings, including Section prefixes and fallbacks."""
    assert clean_heading("## 1. Return Window and Eligibility") == "Return Window and Eligibility"
    assert clean_heading("### 1.1 Exceptions") == "Exceptions"
    assert clean_heading("Section 2: Delivery Timelines") == "Delivery Timelines"
    assert clean_heading("## Section 1") == "Section 1"
    assert clean_heading("## 2") == "2"
    assert clean_heading("Fabric Quality Standards") == "Fabric Quality Standards"


def test_chunk_markdown_token_sizing_and_splitting_long_sections():
    """Sections exceeding max_tokens must be split into sub-chunks <= max_tokens."""
    # Build a long section (~600 tokens)
    long_para = (
        "ThreadNest guarantees the highest fabric quality across all cotton, linen, and silk apparel. "
        "Our customer support team processes every request with detailed tracking and care. "
        "In the event of manufacturing defects, customers are entitled to a full replacement or refund. "
    ) * 15  # ~630 tokens

    md = f"## Comprehensive Fabric Warranty\n\n{long_para}"
    chunks = chunk_markdown(md, "warranty_policy", min_tokens=100, max_tokens=250)

    assert len(chunks) >= 2, "Long section should be split into multiple sub-chunks"
    for idx, c in enumerate(chunks):
        assert c["token_count"] <= 260, f"Chunk {idx} exceeds max_tokens boundary"
        assert c["section"] == "Comprehensive Fabric Warranty"
        assert c["text"].startswith("## Comprehensive Fabric Warranty")


def test_chunk_markdown_small_section_merging():
    """Adjacent undersized sections (< min_tokens) should merge if combined <= max_tokens."""
    md = """## Note on Packaging

Please retain the original box if possible.

## Return Shipping Method

ThreadNest arranges doorstep pickup via our logistics partners Delhivery and BlueDart.
"""
    # Both sections are very short (< 50 tokens each). They should merge.
    chunks = chunk_markdown(md, "shipping_policy", min_tokens=100, max_tokens=300)
    assert len(chunks) == 1, "Small adjacent sections should have been merged"
    assert "Packaging" in chunks[0]["text"]
    assert "Doorstep pickup" in chunks[0]["text"] or "Delhivery" in chunks[0]["text"]


def test_chunk_markdown_real_policy_file():
    """Test chunking against real policy documents in the codebase."""
    candidate_paths = [
        Path("app/policies/return_policy.md"),
        Path("app/models/policies/return_policy.md"),
        Path(__file__).resolve().parent.parent / "app" / "models" / "policies" / "return_policy.md",
        Path(__file__).resolve().parent.parent / "app" / "policies" / "return_policy.md",
    ]
    policy_file = next((p for p in candidate_paths if p.exists()), None)
    if policy_file:
        content = policy_file.read_text(encoding="utf-8")
        chunks = chunk_markdown(content, doc_id="return_policy", min_tokens=200, max_tokens=400)
        assert len(chunks) >= 4
        for c in chunks:
            assert c["doc_id"] == "return_policy"
            assert len(c["section"]) > 0
            assert c["token_count"] > 0


# ─── Section 2: OpenAI Embeddings Wrapper Unit Tests ────────────────────────

def test_get_embedding_empty_text():
    """Empty or whitespace text should return zero-vector without API invocation."""
    vec = get_embedding("")
    assert len(vec) == 1536
    assert all(x == 0.0 for x in vec)

    vec_ws = get_embedding("   \n\t ")
    assert len(vec_ws) == 1536
    assert all(x == 0.0 for x in vec_ws)


def test_get_embedding_sync_mocked():
    """get_embedding should invoke client.embeddings.create and return vector."""
    mock_client = MagicMock()
    mock_client.embeddings.create.return_value.data = [
        MagicMock(embedding=[0.05] * 1536)
    ]

    with patch("app.rag.embeddings.settings") as mock_settings:
        mock_settings.OPENAI_API_KEY = "sk-live-test-key"
        vec = get_embedding("ThreadNest Return Policy", client=mock_client)

    assert len(vec) == 1536
    assert vec[0] == 0.05
    mock_client.embeddings.create.assert_called_once_with(
        input=["ThreadNest Return Policy"],
        model="text-embedding-3-small",
    )


def test_get_embeddings_batch_sync_mocked():
    """get_embeddings should batch requests according to batch_size."""
    texts = [f"Policy section text {i}" for i in range(5)]
    mock_client = MagicMock()

    def make_batch_response(input, model):
        res = MagicMock()
        res.data = [MagicMock(embedding=[0.01 * (idx + 1)] * 1536) for idx in range(len(input))]
        return res

    mock_client.embeddings.create.side_effect = make_batch_response

    with patch("app.rag.embeddings.settings") as mock_settings:
        mock_settings.OPENAI_API_KEY = "sk-live-test-key"
        results = get_embeddings(texts, batch_size=2, client=mock_client)

    assert len(results) == 5
    assert mock_client.embeddings.create.call_count == 3  # batches: 2, 2, 1


@pytest.mark.asyncio
async def test_aget_embedding_async_mocked():
    """aget_embedding should asynchronously create embedding via client."""
    mock_async_client = AsyncMock()
    mock_async_client.embeddings.create = AsyncMock(
        return_value=MagicMock(data=[MagicMock(embedding=[0.08] * 1536)])
    )

    with patch("app.rag.embeddings.settings") as mock_settings:
        mock_settings.OPENAI_API_KEY = "sk-live-test-key"
        vec = await aget_embedding("Cancellation rules", client=mock_async_client)

    assert len(vec) == 1536
    assert vec[0] == 0.08
    mock_async_client.embeddings.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_aget_embeddings_batch_async_mocked():
    """aget_embeddings should batch texts asynchronously."""
    texts = ["Shipping zone 1", "Shipping zone 2", "Shipping zone 3"]
    mock_async_client = AsyncMock()

    async def make_async_batch(input, model):
        res = MagicMock()
        res.data = [MagicMock(embedding=[0.02] * 1536) for _ in input]
        return res

    mock_async_client.embeddings.create = AsyncMock(side_effect=make_async_batch)

    with patch("app.rag.embeddings.settings") as mock_settings:
        mock_settings.OPENAI_API_KEY = "sk-live-test-key"
        results = await aget_embeddings(texts, batch_size=2, client=mock_async_client)

    assert len(results) == 3
    assert mock_async_client.embeddings.create.await_count == 2


def test_generate_mock_embedding_properties():
    """generate_mock_embedding should produce deterministic 1536-dim unit vectors."""
    vec1 = generate_mock_embedding("ThreadNest Standard Shipping")
    vec2 = generate_mock_embedding("ThreadNest Standard Shipping")
    vec3 = generate_mock_embedding("ThreadNest Express Shipping")

    assert vec1 == vec2, "Mock embedding must be deterministic for identical inputs"
    assert vec1 != vec3, "Mock embedding must differ for distinct inputs"
    assert len(vec1) == 1536

    # Verify unit L2 norm
    l2_norm = math.sqrt(sum(x * x for x in vec1))
    assert math.isclose(l2_norm, 1.0, rel_tol=1e-4)


def test_format_vector_sql():
    """format_vector_sql must output a valid PostgreSQL pgvector literal."""
    v = [0.12345678, -0.98765432, 0.0]
    sql_literal = format_vector_sql(v)
    assert sql_literal == "[0.12345678,-0.98765432,0.00000000]"


# ─── Section 3: Policy Ingestion CLI Integration Tests ──────────────────────

@pytest.mark.asyncio
async def test_index_policies_dry_run(tmp_path):
    """Dry run should parse markdown documents and return chunk count without DB writes."""
    doc1 = tmp_path / "return_policy.md"
    doc1.write_text("## Return Policy\n\nCustomers can return items within 30 days of delivery.", encoding="utf-8")

    doc2 = tmp_path / "shipping_policy.md"
    doc2.write_text("## Shipping Policy\n\nStandard shipping takes 3-5 business days across India.", encoding="utf-8")

    count = await index_policies(policies_dir=tmp_path, dry_run=True)
    assert count == 2


@pytest.mark.asyncio
async def test_index_policies_missing_or_empty_directory(tmp_path):
    """Missing or empty directories should safely return 0 chunks indexed."""
    non_existent = tmp_path / "non_existent_dir"
    assert await index_policies(policies_dir=non_existent) == 0

    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()
    assert await index_policies(policies_dir=empty_dir) == 0


@pytest.mark.asyncio
async def test_index_policies_batch_indexing_and_db_insertion(tmp_path):
    """index_policies should clear previous doc entries and insert chunks into policy_chunks."""
    p_file = tmp_path / "faqs.md"
    p_file.write_text("## FAQ 1\n\nHow do I track my order? Use the tracking link sent via SMS.", encoding="utf-8")

    mock_conn = AsyncMock()
    mock_count_res = MagicMock()
    mock_count_res.scalar.return_value = 1
    mock_conn.execute = AsyncMock(return_value=mock_count_res)

    mock_begin = MagicMock()
    mock_begin.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_begin.__aexit__ = AsyncMock(return_value=None)

    mock_engine = MagicMock()
    mock_engine.begin.return_value = mock_begin
    mock_engine.dispose = AsyncMock()

    with patch("app.rag.index_policies.create_async_engine", return_value=mock_engine), \
         patch("app.rag.index_policies.get_embeddings", return_value=[[0.05] * 1536]):

        indexed_count = await index_policies(policies_dir=tmp_path, clear_existing=True, dry_run=False)

    assert indexed_count == 1
    assert mock_conn.execute.await_count >= 2  # 1 delete + 1 insert + 1 count check
    mock_engine.dispose.assert_awaited_once()


# ─── Section 4: Hybrid Retrieval & Citation Formatting Tests ────────────────

def test_format_citation_and_rrf_scoring():
    """Verify human-readable citation strings and Reciprocal Rank Fusion calculation."""
    # Known doc titles
    assert format_citation("return_policy", "Eligibility") == "Return Policy § Eligibility"
    assert format_citation("shipping_policy", "Rates") == "Shipping Policy § Rates"
    assert format_citation("warranty_guarantee", "Hardware") == "Warranty & Quality Guarantee § Hardware"
    assert format_citation("faqs", "Orders") == "Frequently Asked Questions § Orders"
    # Unknown doc fallback title
    assert format_citation("privacy_policy", "Data") == "Privacy Policy § Data"

    # Exact RRF formula checks (k=60)
    score_both = compute_rrf_score(sparse_rank=1, dense_rank=1, k=60.0)
    assert math.isclose(score_both, 1.0 / 61.0 + 1.0 / 61.0)

    score_sparse_only = compute_rrf_score(sparse_rank=2, dense_rank=None, k=60.0)
    assert math.isclose(score_sparse_only, 1.0 / 62.0)

    score_dense_only = compute_rrf_score(sparse_rank=None, dense_rank=5, k=60.0)
    assert math.isclose(score_dense_only, 1.0 / 65.0)


@pytest.mark.asyncio
async def test_search_policy_empty_query():
    """Empty query should immediately return empty passages without DB querying."""
    db = AsyncMock()
    res = await search_policy("", db=db)
    assert res == {"passages": [], "count": 0, "query": ""}
    db.execute.assert_not_called()

    res_ws = await search_policy("   \n\t ", db=db)
    assert res_ws["count"] == 0
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_search_policy_hybrid_retrieval_and_rrf():
    """search_policy should execute hybrid CTE with BM25 + pgvector and format citations."""
    mock_db = AsyncMock()

    mock_row = {
        "id": uuid.uuid4(),
        "doc_id": "return_policy",
        "section": "Return Window and Eligibility",
        "text": "ThreadNest accepts returns within 30 days of confirmed delivery.",
        "rrf_score": 0.0328,
    }

    mock_mappings = MagicMock()
    mock_mappings.all.return_value = [mock_row]

    mock_result = MagicMock()
    mock_result.mappings.return_value = mock_mappings
    mock_db.execute = AsyncMock(return_value=mock_result)

    with patch("app.tools.policy_tools.aget_embedding", return_value=[0.05] * 1536):
        res = await search_policy(query="what is the return window?", db=mock_db, top_k=3)

    assert res["count"] == 1
    assert res["query"] == "what is the return window?"

    passage = res["passages"][0]
    assert passage["doc_id"] == "return_policy"
    assert passage["section"] == "Return Window and Eligibility"
    assert passage["citation"] == "Return Policy § Return Window and Eligibility"
    assert passage["score"] == 0.0328
    assert "30 days" in passage["text"]

    # Verify SQL execution arguments
    mock_db.execute.assert_awaited_once()
    sql_arg, params = mock_db.execute.call_args[0]
    assert "WITH sparse_search AS" in str(sql_arg)
    assert params["query"] == "what is the return window?"
    assert params["top_k"] == 3
    assert params["candidate_limit"] == 20
