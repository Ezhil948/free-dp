# Production Architecture: A Domain-Agnostic, Primary-Source Research Engine

**Source:** GPT-4o / Architectural Consultation  
**Date:** 2026-11-07  
**Core Objective:** Replace fragile, noisy web scraping with dynamic provenance discovery, primary-source verification, hybrid local RAG, and cross-encoder reranking without domain hardcoding or overfitting.

---

## 1. Executive Summary & Recommended Architecture

Dynamic provenance discovery + multi-engine search + controlled crawling + hybrid RAG + cross-encoder verification.

The problem is not primarily a web-scraping problem. It is a **source discovery, source verification, and information retrieval problem**.

The fundamental flaw in standard search-to-agent pipelines:
`User query -> DuckDuckGo Search -> Top 10 URLs -> BeautifulSoup -> Chunking -> Vector DB -> Agents`
Search-result ranking is **not** the same as source authority. A website can rank first because of SEO, backlinks, and affiliate content while containing zero original or accurate technical metrics.

### Five Independent Layers:
1. **Dynamic source and canonical-domain discovery** (Wikidata entity resolution + search consensus).
2. **Source provenance verification** (Mathematical trust scoring, canonical redirects, identity matching).
3. **Primary-source crawling and extraction** (Trafilatura static -> Crawl4AI browser rendering -> Jina Reader fallback).
4. **Hybrid local retrieval and semantic reranking** (LanceDB FTS/BM25 + SentenceTransformers embeddings + FlashRank TinyBERT cross-encoder).
5. **Evidence-controlled distribution to research agents** (Task-anchored chunk allocation with citation enforcement).

> **Cardinal Rule:** Unverified search results must never enter the trusted RAG corpus.

---

## 2. Dynamic Official-Site Discovery (Zero Hardcoding)

### 2.1 Entity Resolution Pre-Search
Extract structured entities before querying:
```json
{
  "entities": [
    { "name": "PostgreSQL", "type": "software_project", "aliases": ["Postgres"] }
  ],
  "research_intents": ["architecture", "implementation", "documentation"],
  "required_source_roles": ["official_documentation", "maintainer_repository", "technical_specification"]
}
```

### 2.2 Wikidata as Official-Domain Discovery Seed
Leverage Wikidata property `P856` (`official website`):
- Query `https://www.wikidata.org/w/api.php?action=wbsearchentities&search={entity}&language=en&format=json`
- Retrieve entity ID -> fetch structured claims -> extract `P856`.
- Completely open, zero authentication, zero API keys, dynamic for companies, projects, organizations, open-source libraries.

### 2.3 Search Consensus Queries
Generate dynamic queries based on entity classification:
- `"{ENTITY}" official website`
- `"{ENTITY}" official documentation`
- `"{ENTITY}" developer documentation`
- `"{ENTITY}" API reference`
- `"{ENTITY}" rate limits`
Use operators dynamically (`site:discovered-domain.com`, `-review`, `-affiliate`).

### 2.4 Domain Provenance Scoring Model
| Signal | Weight |
|---|---|
| Wikidata official website match | +3 |
| Candidate linked from verified homepage | +3 |
| Documentation linked from official navigation | +2 |
| Independent search providers agree on domain | +2 |
| Structured Organization/Product identity matches (JSON-LD) | +2 |
| Entity name matches website metadata | +1 |
| Third-party affiliate or listicle indicators | -3 |
| Entity identity mismatch | -4 |
| Spam, doorway or content-farm indicators | -3 |
| Bot challenge / HTTP 202/403 | REJECT |

States: `VERIFIED_OFFICIAL` -> `POSSIBLY_OFFICIAL` -> `UNVERIFIED`.
Only `VERIFIED_OFFICIAL` enters the primary RAG index.

---

## 3. Search APIs & Discovery Backends

| Provider | Free Allowance | Strength | Limitation / Need |
|---|---|---|---|
| **Tavily** | 1,000 credits/mo | AI-optimized agent search, direct clean extracts | Requires API Key (User Signup) |
| **Exa** | $10/mo + $10 bonus | Neural/semantic search, path filtering | Requires API Key (User Signup) |
| **Jina Reader** | 20 RPM free (no key), 500 RPM with key (10M tokens) | Converts any URL to clean LLM-ready markdown | Zero key needed for 20 RPM! |
| **Brave Search** | $5/mo free credits | Independent index, Goggles filtering | Requires API Key |
| **SearXNG** | Free (self-hosted) | Multi-engine meta-search | Needs local Docker/Python host |

---

## 4. Extraction Cascade & Bot-Defense Pipeline

```
Official URL 
  ↓
HTTPX GET (with proper browser User-Agent & timeout)
  ↓
Status Check:
  200 OK -> Trafilatura extraction (fast, clean markdown, strips boilerplate)
  202 / 403 / 429 / JS-heavy -> Fallback to Jina Reader (https://r.jina.ai/{url})
  Still failing -> Fallback to Crawl4AI / Playwright browser rendering
  Bot challenge page detected -> REJECT immediately (never ingest)
```

---

## 5. Local Hybrid RAG & Semantic Reranking

- **Vector Database**: **LanceDB** (embedded, zero-server, in-process, hybrid vector + BM25 FTS).
- **Embedding Model**: `sentence-transformers/all-MiniLM-L6-v2` (384-dim, compact, local CPU).
- **Semantic Reranking**: **FlashRank** (`ms-marco-TinyBERT-L-2-v2`, 4MB, ultra-fast CPU cross-encoder, no PyTorch needed).
- **Two-Stage Retrieval Flow**:
  1. User Subquestion -> LanceDB Hybrid (Vector + BM25) -> Top 30 candidate chunks.
  2. Top 30 candidate chunks -> FlashRank Cross-Encoder -> Top 5-10 highest-scoring verified passages.
  3. Top passages -> Distributed to Empirical/Analytical Workers.

---

## 6. Worker Evidence Allocation & Coverage Tracking

- Centralized Orchestrator manages discovery, provenance, crawling, and indexing.
- Workers receive structured evidence packages:
  ```json
  {
    "task": "Investigate authentication and rate limits",
    "evidence": [
      {
        "chunk_id": "chunk_001",
        "text": "...",
        "source_url": "https://official.vendor.com/docs/rate-limits",
        "source_role": "official_documentation",
        "provenance_confidence": 0.98
      }
    ]
  }
  ```
- Workers must cite chunk IDs. Supervisor checks evidence coverage across subquestions (e.g., Rate Limits: Covered, Pricing: Covered). If missing, triggers another dynamic discovery loop.

