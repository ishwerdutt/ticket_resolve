# TEST_READY: ThreadNest AI Customer Support Agent (Week 3 Milestone)

**Target Codebase**: `/home/carpenter/Desktop/dev/personal_projects/ai_support_agent`  
**Milestone**: Week 3 Milestone — Policy Documents, Hybrid Policy RAG Retrieval Pipeline & Refined Agent Flows  
**Status**: **TEST-READY / VERIFIED**  
**Date**: 2026-10-29  

---

## 1. Test Runner & Invocation Instructions

The test suite runs inside the backend Python virtual environment (`backend/.venv`) using `pytest` and `pytest-asyncio`.

### 1.1 Virtual Environment & Prerequisites
- Python: `>= 3.12` (Runtime: `Python 3.14.4`)
- Test Framework: `pytest 9.2.0`, `pytest-asyncio 1.4.1`, `pytest-mock 3.17.0`
- PostgreSQL: `PostgreSQL 16` with `pgvector` extension running on `localhost:5434` (DB: `ai_support`, User: `support_user`)

### 1.2 Primary Test Commands

#### Standard Full Test Suite Execution
```bash
cd /home/carpenter/Desktop/dev/personal_projects/ai_support_agent/backend
.venv/bin/pytest tests/ -v
```
*Expected Result*: **69 passed** in ~2.04 seconds (exit code 0).

#### Offline Airgap Verification (100% Isolated / Dummy API Key)
```bash
cd /home/carpenter/Desktop/dev/personal_projects/ai_support_agent/backend
OPENAI_API_KEY="sk-unauthorized-dummy-key" .venv/bin/pytest tests/ -v
```
*Expected Result*: **69 passed** in ~2.16 seconds (exit code 0). Zero outbound network calls to `api.openai.com`.

#### Baseline Regression Immunity Verification (15 Original Tests)
```bash
cd /home/carpenter/Desktop/dev/personal_projects/ai_support_agent/backend
.venv/bin/pytest tests/test_tools.py tests/test_order_agent.py tests/test_tickets.py -v
```
*Expected Result*: **15 passed** in ~1.01 seconds (exit code 0). Zero regressions.

#### Live Database Integration Test
```bash
cd /home/carpenter/Desktop/dev/personal_projects/ai_support_agent/backend
.venv/bin/pytest tests/test_challenger_m2.py -k "test_live_postgres_hybrid_policy_search" -v -s
```
*Expected Result*: **1 passed** in ~2.09 seconds against live PostgreSQL on port 5434.

---

## 2. Test Execution Summary & Breakdown

### 2.1 File-by-File Test Breakdown
| Test File | Scope | Test Items | Execution Time | Pass Rate | Status |
|-----------|-------|:----------:|:--------------:|:---------:|:------:|
| `tests/test_tools.py` | Baseline Tool Unit Tests (Order & Refund) | 5 | 0.25s | 100% (5/5) | PASSED |
| `tests/test_order_agent.py` | Baseline LangGraph Order & Shipment Agent Loop | 8 | 0.70s | 100% (8/8) | PASSED |
| `tests/test_tickets.py` | Baseline Ticket API / Customer Ticket Lookup | 2 | 0.06s | 100% (2/2) | PASSED |
| `tests/test_policy_rag.py` | Milestone 2 Policy Chunking, Embedding & Hybrid RAG | 19 | 0.65s | 100% (19/19) | PASSED |
| `tests/test_refund_flows.py` | Milestone 2 Refund & Replacement Agent Flows & Approvals | 19 | 1.06s | 100% (19/19) | PASSED |
| `tests/test_challenger_m2.py` | Adversarial Stress & Boundary Suite (Challenger) | 16 | 1.73s | 100% (16/16) | PASSED |
| **Total Test Suite** | **Comprehensive Full Regression Suite** | **69** | **2.04s** | **100% (69/69)** | **PASSED** |

---

## 3. Coverage Summary Table by Tier

| Tier | Category | Scope & Description | Test Count | Key Test Assertions |
|:----:|:---------|:--------------------|:----------:|:--------------------|
| **Tier 1** | **Feature Coverage (Happy Path)** | Core feature execution under expected valid inputs: chunking policy markdown, batch embedding generation, database upserting, sparse BM25 + dense pgvector retrieval, refund auto-approval for valid delivered orders $\le$ ₹1000, replacement queueing for valid items, agent policy citation generation. | **24** | `test_chunk_markdown_real_policy_file`, `test_get_embeddings_batch_sync_mocked`, `test_search_policy_hybrid_retrieval_and_rrf`, `test_check_refund_eligibility_valid_within_30_days`, `test_create_refund_auto_approve_at_or_below_1000`, `test_create_replacement_success_queues_approval`, `test_agent_flow_policy_inquiry_with_citation_e2e`, `test_track_shipment_dispatched_order` |
| **Tier 2** | **Boundary & Corner Cases** | Precision edge testing at numeric, temporal, and security boundaries: exact ₹1000.00 vs ₹1000.01 auto-approve cutoff; 30-day window limit (exact 30 days vs 30 days 23 hours vs 31 days expired); non-delivered statuses (`dispatched`, `pending`, missing `delivered_at`); 200–400 token chunk boundary splitting and small section merging; empty query/input fallbacks; invalid UUID formats; item mismatch (404); cross-customer order isolation (403). | **22** | `test_refund_exact_boundary_1000_00_inr`, `test_refund_exact_boundary_1000_01_inr`, `test_refund_eligibility_delivered_exactly_30_days_ago`, `test_refund_eligibility_delivered_30_days_23_hours_ago`, `test_refund_eligibility_delivered_exactly_31_days_ago`, `test_refund_eligibility_not_delivered_dispatched`, `test_chunk_markdown_token_sizing_and_splitting_long_sections`, `test_replacement_item_not_in_order_404`, `test_replacement_cross_customer_forbidden_403` |
| **Tier 3** | **Cross-Feature Combinations** | Integration of multiple subsystems: hybrid RRF rank fusion combining BM25 and pgvector CTEs; sequential refund flow enforcing `check_refund_eligibility` preceding `create_refund`; replacement creation requiring order existence, customer ownership, item containment, and staff approval queue generation; tool dispatcher error translation from HTTP exceptions to LLM JSON responses. | **12** | `test_search_policy_hybrid_retrieval_and_rrf`, `test_index_policies_batch_indexing_and_db_insertion`, `test_create_refund_queues_approval_above_1000`, `test_create_replacement_idempotent_response`, `test_replacement_dispatch_tool_catches_404_gracefully`, `test_replacement_dispatch_tool_catches_403_gracefully`, `test_dispatch_tool_catches_http_forbidden` |
| **Tier 4** | **Real-World Application Scenarios** | Multi-turn conversational workflows through the full LangGraph state machine: customer policy inquiry retrieving relevant passages and citing `According to our [Doc] § [Section], ...`; automated refund approval with instant credit messaging; refund approval queuing with ticket/approval ID and staff SLA messaging; replacement queuing with reverse pickup instructions; live PostgreSQL hybrid retrieval on active database. | **11** | `test_agent_multi_turn_policy_citations_e2e`, `test_agent_flow_policy_inquiry_with_citation_e2e`, `test_agent_flow_refund_auto_approve_e2e`, `test_agent_flow_refund_approval_queued_e2e`, `test_agent_flow_replacement_queued_e2e`, `test_order_status_agent_loop_e2e`, `test_live_postgres_hybrid_policy_search` |
| **Total** | | **All 4 Tiers Verified** | **69** | **Zero test failures, zero regressions, 100% pass rate** |

---

## 4. Feature Checklist Mapping (PROJECT.md Feature Inventory)

| # | Feature | Requirement Source | Implementation Artifacts | Verification Test Cases | Status |
|:---:|:---|:---|:---|:---|:---:|
| 1 | Return Policy Document | ORIGINAL_REQUEST §R1 | `backend/app/policies/return_policy.md` | `test_chunk_markdown_real_policy_file`, `test_live_postgres_hybrid_policy_search` | VERIFIED |
| 2 | Shipping Policy Document | ORIGINAL_REQUEST §R1 | `backend/app/policies/shipping_policy.md` | `test_chunk_markdown_real_policy_file`, `test_live_postgres_hybrid_policy_search` | VERIFIED |
| 3 | Cancellation & Modification Policy | ORIGINAL_REQUEST §R1 | `backend/app/policies/cancellation_modification_policy.md` | `test_chunk_markdown_real_policy_file`, `test_live_postgres_hybrid_policy_search` | VERIFIED |
| 4 | Warranty & Quality Guarantee | ORIGINAL_REQUEST §R1 | `backend/app/policies/warranty_guarantee.md` | `test_chunk_markdown_real_policy_file`, `test_live_postgres_hybrid_policy_search` | VERIFIED |
| 5 | FAQs Policy Document | ORIGINAL_REQUEST §R1 | `backend/app/policies/faqs.md` | `test_chunk_markdown_real_policy_file`, `test_live_postgres_hybrid_policy_search` | VERIFIED |
| 6 | Database Schema & Migration | ORIGINAL_REQUEST §R2 | `backend/migrations/init.sql` (HNSW index on `embedding`, B-tree on `doc_id`, `tsvector`) | PostgreSQL live DB inspection, `test_live_postgres_hybrid_policy_search` | VERIFIED |
| 7 | SQLAlchemy Model Mapping | ORIGINAL_REQUEST §R2 | `backend/app/models/db.py` (`PolicyChunk` ORM model with `PGVector` and `TSVECTOR`) | `test_index_policies_batch_indexing_and_db_insertion`, `test_live_postgres_hybrid_policy_search` | VERIFIED |
| 8 | Config Database Port Update | Explorer Survey | `backend/app/config.py` (Default port 5434, env support) | `test_live_postgres_hybrid_policy_search` connecting to localhost:5434 | VERIFIED |
| 9 | Policy Chunking Engine | ORIGINAL_REQUEST §R2 | `backend/app/rag/chunker.py` (`chunk_markdown` 200–400 tokens, heading cleaning) | `test_chunk_markdown_empty_input`, `test_chunk_markdown_heading_preservation_and_cleaning`, `test_clean_heading_numeric_and_fallbacks`, `test_chunk_markdown_token_sizing_and_splitting_long_sections`, `test_chunk_markdown_small_section_merging` | VERIFIED |
| 10 | OpenAI Embedding Client | ORIGINAL_REQUEST §R2 | `backend/app/rag/embeddings.py` (`get_embedding`, `aget_embedding`, batch support) | `test_get_embedding_sync_mocked`, `test_get_embeddings_batch_sync_mocked`, `test_aget_embedding_async_mocked`, `test_aget_embeddings_batch_async_mocked` | VERIFIED |
| 11 | Policy Ingestion CLI | ORIGINAL_REQUEST §R2 | `backend/app/rag/index_policies.py` (CLI indexer with `--dry-run` and batch upsert) | `test_index_policies_dry_run`, `test_index_policies_missing_or_empty_directory`, `test_index_policies_batch_indexing_and_db_insertion` | VERIFIED |
| 12 | Hybrid Policy Search Tool | ORIGINAL_REQUEST §R2 | `backend/app/tools/policy_tools.py`, `backend/app/rag/retriever.py` | `test_format_citation_and_rrf_scoring`, `test_search_policy_empty_query`, `test_search_policy_hybrid_retrieval_and_rrf`, `test_live_postgres_hybrid_policy_search` | VERIFIED |
| 13 | Policy Citation in Agent | ORIGINAL_REQUEST §R3 | `backend/app/agent/prompts.py` (`MANDATORY POLICY CITATIONS`: `According to our [Doc] § [Section], ...`) | `test_system_prompt_mandates_citation_format`, `test_agent_flow_policy_inquiry_with_citation_e2e`, `test_agent_multi_turn_policy_citations_e2e` | VERIFIED |
| 14 | Refined Refund Flow | ORIGINAL_REQUEST §R3 | `backend/app/tools/refund_tools.py` ($\le$ 1000 INR auto-approve, > 1000 INR queued in `approvals`) | `test_create_refund_auto_approve_at_or_below_1000`, `test_create_refund_queues_approval_above_1000`, `test_refund_exact_boundary_1000_00_inr`, `test_refund_exact_boundary_1000_01_inr`, `test_agent_flow_refund_auto_approve_e2e`, `test_agent_flow_refund_approval_queued_e2e` | VERIFIED |
| 15 | Refined Replacement Flow | ORIGINAL_REQUEST §R3 | `backend/app/tools/replacement_tools.py` (order & item validation, queued in `approvals`) | `test_create_replacement_invalid_uuid_and_not_found`, `test_create_replacement_wrong_customer_forbidden`, `test_create_replacement_item_not_in_order_rejected`, `test_create_replacement_success_queues_approval`, `test_agent_flow_replacement_queued_e2e`, `test_replacement_valid_item_queued_in_approvals`, `test_replacement_item_not_in_order_404`, `test_replacement_cross_customer_forbidden_403` | VERIFIED |
| 16 | Policy RAG Unit Tests | ORIGINAL_REQUEST §R4 | `backend/tests/test_policy_rag.py` (19 comprehensive tests) | 19 tests passing in `test_policy_rag.py` | VERIFIED |
| 17 | Refund & Replacement Tests | ORIGINAL_REQUEST §R4 | `backend/tests/test_refund_flows.py` (19 comprehensive tests) | 19 tests passing in `test_refund_flows.py` | VERIFIED |
| 18 | Regression Test Suite | ORIGINAL_REQUEST §R4 | `backend/tests/` (all 15 baseline tests preserved and passing) | 15 baseline tests in `test_tools.py`, `test_order_agent.py`, `test_tickets.py` passing | VERIFIED |

---

## 5. Offline Airgap Isolation & Regression Immunity Verification

### 5.1 100% Offline Airgap Isolation
- **Condition**: Test suite executed with `OPENAI_API_KEY="sk-unauthorized-dummy-key"`.
- **Result**: **69 passed in 2.16s** (exit code 0).
- **Verification Details**:
  - All OpenAI embedding calls in `test_policy_rag.py` use mocked AsyncMock/MagicMock clients and deterministic 1536-dimensional mock embedding vectors (`generate_mock_embedding`).
  - All LLM chat completion calls in `test_refund_flows.py` and `test_challenger_m2.py` use mock responses structured with tool calls and citation text.
  - Zero live network requests are issued to `api.openai.com` during the test run.
  - No dummy key errors or authentication failures occur.

### 5.2 Baseline Regression Immunity
- **Baseline Test Items**: 15 tests
  - `tests/test_tools.py`: 5 tests passed
  - `tests/test_order_agent.py`: 8 tests passed
  - `tests/test_tickets.py`: 2 tests passed
- **Result**: **15 passed in 1.01s** (exit code 0).
- **Verification Details**: Zero modifications broke pre-existing customer authentication, order status retrieval, address updates, or ticket lookups.

---

## 6. Live PostgreSQL Database Verification (localhost:5434)

Empirical database verification was performed directly against the running PostgreSQL 16 container (`ai_support` on `localhost:5434`, user `support_user`):

### 6.1 Total Indexed Chunks
```sql
SELECT count(*) FROM policy_chunks;
```
**Result**: **28 chunks**

### 6.2 Breakdown by Policy Document
```sql
SELECT doc_id, count(*) AS chunk_count 
FROM policy_chunks 
GROUP BY doc_id 
ORDER BY doc_id;
```

| Document ID (`doc_id`) | Markdown Source File | Chunk Count |
|:---|:---|:---:|
| `cancellation_modification_policy` | `backend/app/policies/cancellation_modification_policy.md` | 5 |
| `faqs` | `backend/app/policies/faqs.md` | 7 |
| `return_policy` | `backend/app/policies/return_policy.md` | 6 |
| `shipping_policy` | `backend/app/policies/shipping_policy.md` | 5 |
| `warranty_guarantee` | `backend/app/policies/warranty_guarantee.md` | 5 |
| **Total Chunks** | | **28** |

### 6.3 Schema & Index Verification
- Extension: `CREATE EXTENSION IF NOT EXISTS vector;` active.
- Column `embedding`: `vector(1536)` populated with 1536-dimensional vectors.
- Column `tsv`: `tsvector` generated via `to_tsvector('english', section || ' ' || text)`.
- Indexes:
  - HNSW Index: `idx_policy_chunks_embedding` using `vector_cosine_ops` (m=16, ef_construction=64).
  - GIN Index: `idx_policy_chunks_tsv` on `tsv` for full-text search.
  - B-tree Index: `idx_policy_chunks_doc_id` on `doc_id`.

---

## 7. Verification Attestation

The test suite and deliverables have undergone independent multi-tier verification:
1. **Worker Verification (`teamwork_worker_m2_1`)**: Implemented all agent prompt guidelines, schema requirements, and 38 new unit/flow tests; 53/53 tests passing.
2. **Reviewer Verification (`teamwork_reviewer_m2_1`, `teamwork_reviewer_m2_2`)**: Confirmed prompt citation mechanics, replacement tool contracts, and offline mock isolation with verdict **APPROVE**.
3. **Challenger Stress Testing (`teamwork_challenger_m2_1`, `teamwork_challenger_m2_2`)**: Authored 16 adversarial tests verifying exact boundary thresholds (1000.00 vs 1000.01 INR, 30 days vs 31 days) and live PostgreSQL retrieval with verdict **APPROVE**.
4. **Forensic Integrity Audit (`teamwork_auditor_m2_1`)**: Executed AST analysis and mock detection across production code confirming zero facades, zero test skipping, zero mock leakage into production, and genuine assertions across all 69 tests with verdict **CLEAN**.

The ThreadNest AI Customer Support Agent Week 3 codebase is **TEST-READY**.
