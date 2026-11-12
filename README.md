# free-dp

**`free-dp`** is an IDE agent skill and Python CLI that pools free-tier smaller models (`gemini-3.1-flash-lite`, Groq `qwen/qwen3.8-27b` & `openai/gpt-oss-120b`, OpenRouter free models) into a multi-stage research council with arXiv/OpenAlex PDF extraction and AST-sandboxed Python code execution.

No web dashboard. No paid API credits required. Drop it into your IDE, invoke `/free-dp` in chat, and your coding agent runs the research council in the background and reads the verified report (`FINAL_VERDICT.md` + `final_dossier.md`) directly into your session.

---

## What It Actually Does

Single-pass calls to small/free models hallucinate citations, drop constants in derivations, and write broken numerical scripts. `free-dp` compensates for smaller model weights with mechanical verification:

1. **Key Rotation & Free-Tier Multiplexing (`key_rotator.py`, `model_client.py`)**: Pools up to 10 Google AI Studio keys, 3 Groq keys, and 3 OpenRouter keys. Tracks rolling 60-second RPM/TPM windows and fails over in `<1ms` on HTTP 429/413 without blocking.
2. **Primary Literature Harvesting (`paper_harvester.py`, `content_extractor.py`)**: Queries arXiv and OpenAlex (`has_fulltext:true`), downloads full PDFs, and extracts raw text and formulas with `PyMuPDF` (`fitz`). Uses `trafilatura` + Jina Reader (`r.jina.ai`) for web extraction.
3. **2-Room Multi-Agent Deliberation (`council_orchestrator.py`, `worker_pool.py`)**:
   - **Room 1 (Council Chamber)**: Decomposes the prompt, runs a 2-round critique and peer-rebuttal chain across 4 domain leads (`CM1`–`CM4`), and locks a dispute ledger.
   - **Room 2 (Domain Execution)**: Harvests papers/web sources, runs empirical extraction workers, and executes an author-excluded adversarial claim audit (`[VERIFIED]`, `[REFUTED]`, `[UNSUPPORTED]`).
4. **AST-Sandboxed Code Execution & Self-Repair (`script_runner.py`)**: Extracts generated Python simulation/verification blocks, checks the AST to block unsafe imports (`os`, `sys`, `subprocess`, `socket`), runs the script in a subprocess, and triggers up to 3 automated repair passes if assertions or syntax fail.

---

## Setup & IDE Skill Usage

### 1. Install Dependencies

```bash
git clone https://github.com/Ezhil948/free-dp.git
cd free-dp
pip install -r requirements.txt
```

### 2. Add Free API Keys in `.env` (Recommended: 10 Free Gemini Keys)

Copy [`.env.example`](.env.example) to `.env` (`cp .env.example .env`) and fill in your keys (`.env` is gitignored).

> [!TIP]
> **Why 10 Free Gemini Keys Are Recommended:**
> Google AI Studio provides free API keys with a quota of **15 Requests Per Minute (RPM)** and **1,000,000 Tokens Per Minute (TPM)** per key for `gemini-3.1-flash-lite`. Because an institutional deep research council makes between **50 and 230 parallel calls** per research question across 4 domain members and empirical worker pools, a single free key will hit rate limits.
>
> By providing 10 free Gemini keys (`GEMINI_API_KEY_1` through `GEMINI_API_KEY_10` created across free Google accounts), `key_rotator.py` multiplexes requests in sub-millisecond round-robin and rolling 60-second window tracking, unlocking an aggregate quota of **150 RPM and 10,000,000 TPM** — giving you continuous, non-blocking deep research with **$0 API cost**.

```ini
# Google AI Studio Free Keys (Recommended: 10 Keys for 150 RPM / 10M TPM)
# https://aistudio.google.com/app/apikey
GEMINI_API_KEY_1=your_key_1
GEMINI_API_KEY_2=your_key_2
GEMINI_API_KEY_3=your_key_3
GEMINI_API_KEY_4=your_key_4
GEMINI_API_KEY_5=your_key_5
GEMINI_API_KEY_6=your_key_6
GEMINI_API_KEY_7=your_key_7
GEMINI_API_KEY_8=your_key_8
GEMINI_API_KEY_9=your_key_9
GEMINI_API_KEY_10=your_key_10

# Optional Analytical & Empirical Workers (Groq & OpenRouter Free Tiers)
GROQ_API_KEY_1=your_key_1
GROQ_API_KEY_2=your_key_2
GROQ_API_KEY_3=your_key_3
OPENROUTER_API_KEY_1=your_key_1
TAVILY_API_KEY=your_key_optional
```

### 3. Use as an IDE Skill (`/free-dp`)

- **Workspace-local (automatic)**: Opening this folder in Antigravity, Cursor, Claude Code, Codex, or OpenCode automatically loads `.agents/skills/free-dp/SKILL.md`.
- **Global IDE skill (use in any project)**: Copy `skills/free-dp` into your global skills directory (e.g., `~/.gemini/config/skills/free-dp` or `~/.claude/skills/free-dp`).

In your IDE chat, type:
```text
/free-dp Derive the 5-species Park two-temperature hypersonic post-shock relaxation equations and verify with a 1D stiff ODE solver.
```

Your IDE agent will execute `python run_council.py --prompt "..."`, wait for the council to finish, and read `FINAL_VERDICT.md` back into chat.

### 4. Direct CLI Usage

```bash
# Automatic room allocation
python run_council.py --prompt "Your research question"

# Explicit mode: focused (1 room), bimodal (2 rooms), comprehensive (4 rooms)
python run_council.py --prompt-file benchmarks/prompts/prompt_6_hypersonic_aerothermo.txt --mode focused

# Inspect latest dossier in terminal
python show_dossier.py
```

---

## Benchmarks & Ranking: `free-dp` (Free Flash-Lite Pool) vs. Gemini Argon Deep Research

We benchmarked `free-dp` (running entirely on free-tier `gemini-3.1-flash-lite` + `gemini-flash-lite-latest` keys) head-to-head against **Gemini Argon Deep Research** on PhD-level mathematical physics, nanoelectronics, and differential geometry prompts.

All raw prompts, Argon replies, `free-dp` verdicts, machine-readable JSON scores, and evaluators are in [`benchmarks/`](benchmarks/):
- Full scoring breakdown: [`benchmarks/ARGON_VS_FREE_DP_SCORING_BREAKDOWN.md`](benchmarks/ARGON_VS_FREE_DP_SCORING_BREAKDOWN.md)
- Raw JSON scores: [`benchmarks/argon_vs_free_dp_scores.json`](benchmarks/argon_vs_free_dp_scores.json)

### 1. Official 100-Point Frozen Academic Rubric Ranking (Prompts P6–P9)

Evaluated by [`benchmarks/run_council_prompts_6_7_8_9.py`](benchmarks/run_council_prompts_6_7_8_9.py) across 5 capped categories: **Core Proofs (30)**, **Sandboxed Python Script Execution (25)**, **Traps & Boundaries (20)**, **Primary Sources (15)**, and **Open Frontiers (10)**.

| Prompt | System | Rank | Total (/100) | Wall-Clock Time | LLM Calls & Tokens | Proofs (/30) | Python Script (/25) | Traps (/20) | Sources (/15) | Frontiers (/10) | Script Execution Result | Files |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :--- |
| **P6: Hypersonic Aerothermo** | **`free-dp`** | **#1** | **95.0** | **7m 09s** | **68 calls** (458k tok) | **30.0** | **20.0** | **20.0** | **15.0** | **10.0** | `PASSED (1.77s, Exit 0)` | [Prompt](benchmarks/prompts/prompt_6_hypersonic_aerothermo.txt) · [`free-dp`](benchmarks/free_dp_replies/P6_FINAL_VERDICT.md) |
| **P6: Hypersonic Aerothermo** | Gemini Argon | #2 | 68.0 *(91.0\*)* | ~10m (cloud) | — (single-agent) | **30.0** | 2.0 *(25.0\*)* | 17.0 | **15.0** | 4.0 | `TIMEOUT (>20s)` *(PASSED 3.41s)* | [Argon Reply](benchmarks/argon_replies/P6_hypersonic_argon_reply.md) |
| **P7: Sub-2nm GAA Nanosheet** | Gemini Argon | **#1** | **91.5** | ~12m (cloud) | — (single-agent) | 27.5 | **25.0** | **20.0** | **15.0** | 4.0 | `PASSED (1.92s, Exit 0)` | [Prompt](benchmarks/prompts/prompt_7_sub2nm_gaa_negf.txt) · [Argon Reply](benchmarks/argon_replies/P7_gaa_negf_argon_reply.md) |
| **P7: Sub-2nm GAA Nanosheet** | **`free-dp`** | #2 | 78.0 | **5m 44s** | **138 calls** (960k tok) | **30.0** | 5.0 | **20.0** | 13.0 | **10.0** | `FAILED (AssertionError)` | [`free-dp`](benchmarks/free_dp_replies/P7_FINAL_VERDICT.md) |
| **P8: Riemannian Score Diffusion** | **`free-dp`** | **#1** | **85.5** | **6m 19s** | **68 calls** (498k tok) | **27.5** | **15.0** | **20.0** | 13.0 | **10.0** | `PASSED (0.44s, Exit 0)` | [Prompt](benchmarks/prompts/prompt_8_riemannian_score_diffusion.txt) · [`free-dp`](benchmarks/free_dp_replies/P8_FINAL_VERDICT.md) |
| **P8: Riemannian Score Diffusion** | Gemini Argon | #2 | 71.5 | ~10m (cloud) | — (single-agent) | **27.5** | 5.0 | **20.0** | **15.0** | 4.0 | `FAILED (AssertionError: 1 viol)` | [Argon Reply](benchmarks/argon_replies/P8_riemannian_diffusion_argon_reply.md) |
| **P9: Cryo-EM 3D Reconstruction** | **`free-dp`** | **#1** | **90.0** | **7m 47s** | **72 calls** (534k tok) | **30.0** | **15.0** | **20.0** | **15.0** | **10.0** | `PASSED (0.44s, Exit 0)` | [Prompt](benchmarks/prompts/prompt_9_cryoem_heterogeneity_fsc.txt) · [`free-dp`](benchmarks/free_dp_replies/P9_FINAL_VERDICT.md) |
| **P9: Cryo-EM 3D Reconstruction** | Gemini Argon | #2 | 74.0 | ~11m (cloud) | — (single-agent) | **30.0** | 5.0 | **20.0** | **15.0** | 4.0 | `FAILED (AssertionError: 1 viol)` | [Argon Reply](benchmarks/argon_replies/P9_cryoem_argon_reply.md) |
| **4-Prompt Mean (P6–P9 Head-to-Head)** | **`free-dp`** | **#1** | **87.13 / 100** | **6m 45s** | **86.5 calls** (612k tok) | **29.38** | **13.75** | **20.00** | 14.00 | **10.00** | **3 / 4 Passed (75%)** | — |
| **4-Prompt Mean (P6–P9 Head-to-Head)** | Gemini Argon | #2 | 76.25 / 100 *(82.00\*)* | ~11m | — | 28.75 | 9.25 *(15.00\*)* | 19.25 | **15.00** | 4.00 | **1 / 4 Passed (`2 / 4` w/ 30s)** | — |

---

### 2. Why the Uncapped Score (`CRI`) Is Different — And What Happens When We Remove or Limit LaTeX Math-Count Inflation

To test where a frontier model still beats a free smaller-model council, we also wrote [`benchmarks/discriminative_evaluator.py`](benchmarks/discriminative_evaluator.py), which removes all category ceilings.

#### Why the Raw Uncapped CRI Favors Argon:
In `discriminative_evaluator.py`, `analyze_mathematical_depth()` counts **every raw LaTeX formatting delimiter in the document with no cap**:
- Every `$$...$$` display block = `+2.5 pts`
- Every `$...$` inline math snippet = `+0.3 pts`
- Every `\partial`, `\nabla`, `\sum`, `\int`, `\mathbb` = `+0.1 pts`

Because Gemini Argon wraps almost every single variable mention (`$T$`, `$T_v$`, `$\rho$`) and intermediate algebraic step in `$$...$$` blocks (`50` display blocks + `317` inline spans + `401` symbols on P6 = **`261.70 pts`**; `52` display blocks + `415` inline spans + `778` symbols on P8 = **`335.30 pts`**; `49` display blocks + `318` inline spans + `628` symbols on P9 = **`282.20 pts`** just from LaTeX delimiter counts), **71% to 74% of Argon's entire Raw Uncapped Score comes solely from counting `$` signs and LaTeX tokens** — completely masking the fact that Argon's Python simulations on **both P8 and P9 crashed with `AssertionError: Verification failed with 1 violations`**.

#### What Happens When We Limit Math (Cap at 30 pts) or Remove Math-Count Inflation:

| Prompt | System | Display Eqs (`$$`) | Inline Math (`$`) | Uncapped Math Score | Traps Score | Literature Score (DOIs/arXivs) | Sandbox Script Score | Frontier Score | **1. Raw Uncapped CRI** | **2. Math-Removed CRI** *(No LaTeX Count)* | **3. Math-Capped CRI** *(Math Max 30)* | **4. Pure Tech Verification** *(Traps+Code+Frontiers)* |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **P6 (Hypersonic)** | **`free-dp`** | 0 | 135 | 50.40 | **53.00** (5/5 traps) | **55.00** (10 DOI, 10 arXiv) | 31.23 (`PASSED 1.77s`) | **12.00** | 201.63 | **151.23 (#1)** | **181.23 (#1)** | **96.23 (#1)** |
| **P6 (Hypersonic)** | Gemini Argon | 50 | 317 | **261.70** | 47.50 (4/5 traps) | 10.50 (3 DOI, 0 arXiv) | **37.59** (`PASSED 3.41s`) | 1.50 | **358.79 (#1)** | 97.09 (#2) | 127.09 (#2) | 86.59 (#2) |
| **P7 (GAA NEGF)** | **`free-dp`** | 19 | **415** | 204.60 | **112.00** (6/6 traps, 36 bounds) | 4.00 (0 DOI, 1 arXiv) | 5.00 (`FAILED assert`) | **19.50** | 345.10 | 140.50 (#2) | 170.50 (#2) | 136.50 (#2) |
| **P7 (GAA NEGF)** | Gemini Argon | 35 | 393 | **237.10** | 95.00 (6/6 traps, 28 bounds) | **30.00** (10 DOI, 0 arXiv) | **48.08** (`PASSED 1.92s`) | 7.50 | **417.68 (#1)** | **180.58 (#1)** | **210.58 (#1)** | **150.58 (#1)** |
| **P8 (Riemannian)** | **`free-dp`** | 11 | 162 | 89.90 | **60.00** (5/5 traps, 20 clauses) | 4.00 (`[SRC-CMx]` tags) | **29.56** (`PASSED 0.44s`) | **10.50** | 193.96 | 104.06 (#2\*) | 134.06 (#2\*) | **100.06 (#1)** |
| **P8 (Riemannian)** | Gemini Argon | 52 | 415 | **335.30** | 49.00 (5/5 traps, 9 clauses) | **81.00** (16 DOI, 22 `(Name, Yr)`) | 5.00 (`FAILED assert`) | 1.50 | **471.80 (#1)** | **136.50 (#1\*)** | **166.50 (#1\*)** | 55.50 (#2) |
| **P9 (Cryo-EM)** | **`free-dp`** | 7 | 103 | 57.30 | **54.00** (6/6 traps, 6 clauses) | **64.00** (10 DOI, 10 arXiv) | **29.56** (`PASSED 0.44s`) | **12.00** | 216.86 | **159.56 (#1)** | **189.56 (#1)** | **95.56 (#1)** |
| **P9 (Cryo-EM)** | Gemini Argon | 49 | 318 | **282.20** | 50.50 (6/6 traps, 1 clause) | 45.00 (10 DOI, 0 arXiv) | 5.00 (`FAILED assert`) | 1.50 | **384.20 (#1)** | 102.00 (#2) | 132.00 (#2) | 57.00 (#2) |
| **4-Prompt Mean** | **`free-dp`** | 9.3 | 203.8 | 100.55 | **69.75** | 31.75 | 23.84 (`3/4 PASSED`) | **13.50** | 239.39 | **138.84 (#1)** | **168.84 (#1)** | **107.09 (#1)** |
| **4-Prompt Mean** | Gemini Argon | 46.5 | 360.8 | **279.08** | 60.50 | **41.63** | 23.92 (`2/4 PASSED`) | 3.00 | **408.12 (#1)** | 129.04 (#2) | 159.04 (#2) | 87.42 (#2) |

**Key Findings When Math-Count Inflation Is Removed or Capped:**
1. **Overall 4-Prompt Average (P6–P9)**: Once LaTeX delimiter counting is either removed or capped at 30 points, **`free-dp` beats Gemini Argon on the 4-prompt mean across every evaluation regime**:
   - **100-Point Frozen Rubric Mean**: **`free-dp` wins `87.13 / 100` vs `76.25 / 100`** (`82.00 / 100` if Argon is given a 30s timeout on P6).
   - **Math-Removed CRI Mean**: **`free-dp` wins `138.84` vs `129.04` (`+9.80` pts)**.
   - **Math-Capped (Max 30) CRI Mean**: **`free-dp` wins `168.84` vs `159.04` (`+9.80` pts)**.
   - **Pure Technical Verification Mean (Traps + Sandbox Execution + Frontiers)**: **`free-dp` wins `107.09` vs `87.42` (`+19.67` pts)**.
2. **On P9 (Cryo-EM 3D Reconstruction)**: Removing or capping the LaTeX token count flips the score by **`+224.90` points** in `free-dp`'s favor — from trailing `216.86 vs 384.20` on raw `$` counts to **winning `159.56 vs 102.00` (Math-Removed)** and **`189.56 vs 132.00` (Math-Capped)**. `free-dp` beats Argon on **every single non-math category on P9**: Sandbox Script (`29.56 PASSED` vs `5.00 FAILED` — Argon's script crashed with `AssertionError` because its `tight_binary_mask` produced `mean_masked_uncorrected_fsc = -0.0101 < 0.50`), Literature (`64.0` vs `45.0`), Traps (`54.0` vs `50.5`), and Frontiers (`12.0` vs `1.5`).
3. **On P6 (Hypersonic Aerothermodynamics)**: Removing or capping the LaTeX token count flips the score by **`+211.30` points** in `free-dp`'s favor — winning **`151.23 vs 97.09` (Math-Removed)** and **`181.23 vs 127.09` (Math-Capped at 30)**.
4. **On P8 (Riemannian Score Diffusion)**: `free-dp` beats Argon on **Trap & Falsification Granularity (`60.0` vs `49.0`)**, **Executable Sandbox Script (`29.56 PASSED` vs `5.00 FAILED`)**, and **Open Frontiers (`10.5` vs `1.5`)** — winning **`100.06 vs 55.50`** across all verification & reasoning components.
5. **On P7 (Sub-2nm GAA Nanosheet NEGF)**: `free-dp` writes **more inline formulas (`415` vs `393`) and more math symbols (`331` vs `312`)** than Argon, and beats Argon on **Traps (`112.0` vs `95.0`)** and **Frontiers (`19.5` vs `7.5`)**. Argon wins P7 (`180.58` vs `140.50` Math-Removed) solely because Argon's coupled NEGF Python script passed (`48.08` pts) whereas `free-dp`'s script failed its assertion tolerance (`5.0` pts).

---

### 3. 5-Prompt Doctoral Verification Suite (Prompts P1–P5)

Re-run at any time with `python benchmarks/run_master_5prompt_benchmark.py`:

| Prompt | Domain | Total Score | Council Time | Model Calls & Tokens | Proofs (30) | Sandbox Script (25) | Traps (20) | Sources (15) | Open Bounds (10) | Script Status & Cert Hash | Verdict File |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :--- |
| **P1** | Rough Volterra Volatility & Microstructure Noise | **91.0 / 100** | **8m 32s** | **84 calls** (640k tok) | 29.0 | 25.0 | 20.0 | 11.0 | 6.0 | `PASSED (21.68s)` `25fe0a3ca8457558` | [P1 Verdict](benchmarks/free_dp_replies/P1_FINAL_VERDICT.md) |
| **P2** | Longitudinal Causal Inference & Network Interference | **85.0 / 100** | **9m 22s** | **116 calls** (890k tok) | 27.5 | 25.0 | 15.5 | 10.0 | 7.0 | `PASSED (15.94s)` `e6996d44520e48d4` | [P2 Verdict](benchmarks/free_dp_replies/P2_FINAL_VERDICT.md) |
| **P3** | Distributed Byzantine Consensus (Partial Synchrony) | **93.0 / 100** | **7m 54s** | **91 calls** (613k tok) | 29.0 | 25.0 | 18.0 | 15.0 | 6.0 | `PASSED (1.35s)` `6d10bf065826d82a` | [P3 Verdict](benchmarks/free_dp_replies/P3_FINAL_VERDICT.md) |
| **P4** | Special Relativistic Magnetohydrodynamics (RMHD) | **97.0 / 100** | **5m 09s** | **48 calls** (391k tok) | 30.0 | 25.0 | 20.0 | 15.0 | 7.0 | `PASSED (0.96s)` `0929d5c554e9e3a3` | [P4 Verdict](benchmarks/free_dp_replies/P4_FINAL_VERDICT.md) |
| **P5** | Post-Quantum Lattice Cryptography (ML-KEM / ML-DSA) | **91.0 / 100** | **7m 03s** | **231 calls** (1,572k tok) | 30.0 | 25.0 | 13.0 | 13.0 | 10.0 | `PASSED (0.85s)` `315e486b50033748` | [P5 Verdict](benchmarks/free_dp_replies/P5_FINAL_VERDICT.md) |
| **Mean** | **5-Prompt Suite Average** | **91.4 / 100** | **7m 36s** | **114 calls** (821k tok) | **29.1** | **25.0** | **17.3** | **12.8** | **7.2** | **5 / 5 Passed** | — |

---

## Repository Structure

```text
free-dp/
├── run_council.py               # CLI entry point
├── council_orchestrator.py      # Stage 1-3 council deliberation, audit & synthesis
├── worker_pool.py               # Room 2 empirical & analytical worker pools
├── model_client.py              # Multi-provider LLM caller & truncation detector
├── key_rotator.py               # Non-blocking rate-limit & token multiplexer
├── paper_harvester.py           # arXiv & OpenAlex PDF downloader + PyMuPDF parser
├── discovery_engine.py          # Wikidata & canonical domain discovery
├── content_extractor.py         # Trafilatura + Jina Reader web extractor
├── rag_engine.py                # Local LanceDB hybrid search + FlashRank reranker
├── script_runner.py             # AST security check + subprocess Python sandbox
├── provenance_engine.py         # Evidence ledger & claim provenance tracker
├── dataset_catalog.py           # DuckDB Parquet schema inspector
├── dataset_engine.py            # Local / R2 dataset query engine
├── task_anchor.py               # Prompt constraint & deliverable extractor
├── skill_injector.py            # Domain skill prompt injector
├── search_worker.py             # Tavily / DuckDuckGo search adapter
├── live_probe.py                # Endpoint verifier
├── upload_dataset.py            # CSV-to-Parquet dataset ingestion utility
├── show_dossier.py              # Terminal dossier viewer
├── skills/free-dp/SKILL.md      # Distributable IDE skill definition
├── .agents/skills/free-dp/      # Auto-loaded workspace skill
├── benchmarks/                  # Prompts (P1-P9), Argon replies, free-dp verdicts & evaluators
├── .env                         # Environment variable names (keys blank)
├── .env.example                 # Environment template
├── requirements.txt             # Python dependencies
└── pyproject.toml               # Package configuration
```

## License

MIT License. See [LICENSE](LICENSE).
