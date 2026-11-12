---
name: free-dp
description: "Run multi-agent deep research using pooled free-tier smaller models (Gemini Flash-Lite, Groq Qwen/GPT-OSS, OpenRouter) with arXiv/OpenAlex PDF harvesting, AST-sandboxed Python verification, and adversarial claim auditing. Invoke when the user asks for /free-dp, deep research, primary literature proofs, or rigorous mathematical/engineering verification."
---

# free-dp — IDE Deep Research Skill

When the user triggers `/free-dp` or asks for deep research on a technical, mathematical, quantitative, or scientific problem:

## 1. Execute the Research Engine

Locate the `free-dp` repository directory (either the current workspace or where `run_council.py` is installed) and run:

```bash
python run_council.py --prompt "<USER_RESEARCH_PROMPT>" --mode auto
```

### Execution Modes (`--mode`)

- `focused`: 1 domain room (fastest, ~2–3 min, ~30–40 free model calls)
- `bimodal`: 2 domain rooms (~4–5 min)
- `comprehensive`: 4 domain rooms (deepest multi-angle coverage, ~6–8 min)
- `auto`: Automatically selects room count based on prompt complexity

### Passing a Long Prompt via File

If the prompt contains complex LaTeX or multi-part specifications, write it to a temporary file first and pass `--prompt-file`:

```bash
python run_council.py --prompt-file scratch/current_prompt.txt --mode auto
```

## 2. Retrieve & Present the Results

When `run_council.py` finishes with exit code `0`, it writes two files in the `free-dp` root (and archives them in `runs/run_<timestamp>_<id>/`):

1. **`FINAL_VERDICT.md`**: The synthesized executive verdict, mathematical derivations, verified Python simulation code, trap analysis, and citations.
2. **`final_dossier.md`**: The complete, uncompressed multi-room evidence ledger, worker outputs, sandbox execution certificates, and per-call model telemetry table.

**Your action as the IDE Agent:**

- Read `FINAL_VERDICT.md` (and `final_dossier.md` if the user asks for raw worker evidence or telemetry).
- Present the verified findings, equations, and executable code directly to the user, or apply them to the user's codebase as requested.
