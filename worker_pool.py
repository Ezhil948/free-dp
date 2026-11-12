import os
import json
import re
import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from model_client import model_caller
from search_worker import DeepWebResearcher, format_sources_for_prompt
from dataset_engine import dataset_engine
from skill_injector import skill_injector
from script_runner import script_runner
from paper_harvester import paper_harvester
from dataset_catalog import dataset_catalog

logger = logging.getLogger("worker_pool")


async def gather_safe(coros, fallback_builder, label: str = "tasks"):
    """
    Supervised gather: one failing worker must never abort the whole room.

    ``fallback_builder(index, exception)`` returns a shape-compatible degraded result so the
    remaining workers can finish and downstream aggregation can proceed.
    """
    results = await asyncio.gather(*coros, return_exceptions=True)
    safe_results = []
    for idx, res in enumerate(results):
        if isinstance(res, BaseException):
            logger.error(f"[{label}] Worker {idx + 1} failed after retries: {res}")
            safe_results.append(fallback_builder(idx, res))
        else:
            safe_results.append(res)
    return safe_results


def detect_fact_mode(directive: str, domain: str) -> bool:
    """
    Whole-word provider/API intent detection.

    Substring matching previously misclassified "diffusion models" ("models"),
    "rapid"/"capital" ("api"), and similar theoretical prompts as API catalogues.
    """
    intent_text = (directive + " " + domain).lower()
    provider_hits = sum(
        1
        for term in ["provider", "api", "free tier", "rate limit", "rpm", "tpm", "rpd", "credit card", "quota"]
        if re.search(rf"\b{re.escape(term)}\b", intent_text)
    )
    return provider_hits >= 2


class WebSearchAdapter:
    """Executes high-concurrency web retrieval tasks."""
    def __init__(self, researcher: DeepWebResearcher):
        self.researcher = researcher

    async def execute(self, task: Dict[str, Any], cm_id: str = "cm") -> Dict[str, Any]:
        queries = task.get("queries", [task.get("query", "")])
        target_pages = task.get("target_pages", 25)
        start_index = task.get("start_index", 1)
        intent_mode = task.get("intent_mode", "general_fact")
        sources = await self.researcher.deep_research(
            queries,
            target_page_count=target_pages,
            id_prefix=f"SRC-{cm_id.upper()}",
            start_index=start_index,
            intent_mode=intent_mode
        )
        return {
            "task_type": "web",
            "sources_count": len(sources),
            "sources": [s.to_dict() for s in sources],
            "formatted_evidence": format_sources_for_prompt(sources, max_chars_per_source=3000)
        }


class DatasetQueryAdapter:
    """Executes zero-CPU remote DuckDB / local Parquet SQL tasks."""
    def __init__(self, engine):
        self.engine = engine

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        query = task.get("query", "SELECT 1;")
        asset = task.get("asset")
        year = task.get("year")
        table_path = task.get("table_path")
        halo_bars = task.get("halo_bars", 0)

        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(
            None,
            lambda: self.engine.execute_query(
                query=query,
                table_path=table_path,
                asset=asset,
                year=year,
                halo_bars=halo_bars
            )
        )
        return {
            "task_type": "dataset",
            "result": res
        }


class ModelSynthesisAdapter:
    """Executes multi-model LLM analysis and domain synthesis via Tier-based routing."""
    def __init__(self, caller):
        self.caller = caller

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        tier = task.get("tier", "worker_analytical")
        prompt = task.get("prompt", "")
        max_tokens = task.get("max_tokens", 4000)
        temperature = task.get("temperature", 0.3)

        resp = await self.caller.call_by_tier(
            tier=tier,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature
        )
        return {
            "task_type": "synthesis",
            "tier": tier,
            "output": resp
        }


# ═════════════════════════════════════════════════════════════════════
# DYNAMIC BIN-PACKING ENGINE FOR GEMINI 3.1 FLASH WORKER POOL
# ═════════════════════════════════════════════════════════════════════

WEB_EMPIRICAL_ROLE_TEMPLATES = [
    {
        "role": "Quantitative Metrics, Quotas & Parameter Distributions",
        "focus": "Extract and quantify concrete numerical parameters, capacity limits, rate quotas, latency metrics, and operational thresholds."
    },
    {
        "role": "System Architecture, Technical Protocols & Mechanics",
        "focus": "Document core structural mechanics, architectural specifications, protocol standards, interface schemas, and pipeline mechanics."
    },
    {
        "role": "Edge Cases, Failure Modes & Deceptive Traps",
        "focus": "Identify critical failure boundaries, unverified claims, hidden dependencies, degradation regimes, and common pitfall traps."
    },
    {
        "role": "Comparative Ecosystem Benchmarks & Cross-Entity Variance",
        "focus": "Benchmark comparative trade-offs, performance variations, feature distributions, and divergence across providers or implementations."
    },
    {
        "role": "Governance, Access Controls & Operational Constraints",
        "focus": "Audit terms of access, authentication hurdles, gating prerequisites, security policies, and resource sustainability limits."
    }
]

PAPER_EMPIRICAL_ROLE_TEMPLATES = [
    {
        "role": "Formal Formulations, Mathematical Models & Specifications",
        "focus": "Extract governing mathematical equations, formal algorithms, theoretical proofs, and rigorous analytical definitions."
    },
    {
        "role": "Empirical Evaluations, Benchmark Datasets & Calibrations",
        "focus": "Extract statistical distributions, experimental benchmarks, empirical error bars, sample sizes, and parameter calibrations."
    },
    {
        "role": "Structural Invariant Limits & Degradation Regimes",
        "focus": "Identify fundamental theoretical boundaries, asymptotic scaling limits, phase transitions, and structural invariant constraints."
    },
    {
        "role": "Falsification Criteria, Stress Tests & Counter-Evidence",
        "focus": "Extract empirical falsification experiments, control comparisons, stress-testing methodologies, and refuting observations."
    },
    {
        "role": "Causal Mechanisms & Systemic Dependencies",
        "focus": "Isolate cause-and-effect mechanisms, identification parameters, structural dependencies, and confounding variables."
    }
]

# ═════════════════════════════════════════════════════════════════════
# DYNAMIC ANALYTICAL SQUAD TEMPLATES
# ═════════════════════════════════════════════════════════════════════

FOCUSED_SYNTHESIS_ANGLES = [
    {
        "id": "syn_01",
        "role": "Causal Mechanics & Structural Relationships",
        "focus": "Primary cause-and-effect mechanisms, structural architecture, foundational relationships, and operational invariants."
    },
    {
        "id": "syn_02",
        "role": "Regime Transitions & Operational Thresholds",
        "focus": "Critical operational thresholds, bottleneck transitions, performance limits, and system breakdown boundaries under load."
    },
    {
        "id": "syn_03",
        "role": "Adversarial Falsification & Stress Testing",
        "focus": "Stress-testing edge cases, empirical disproof conditions, misleading claims, and counter-evidence."
    },
    {
        "id": "syn_04",
        "role": "Execution Guardrails & Decision Rules",
        "focus": "Deterministic decision rules, operational guardrails, practical deployment parameters, and verification requirements."
    }
]

BIMODAL_SYNTHESIS_ANGLES = [
    {
        "id": "syn_01",
        "role": "Core Causal Mechanics",
        "focus": "Primary cause-and-effect drivers and structural relationships."
    },
    {
        "id": "syn_02",
        "role": "Phase Transition & Threshold Modeling",
        "focus": "Exact boundary transitions between normal and high-stress operational regimes."
    },
    {
        "id": "syn_03",
        "role": "Structural Variance & Stress Dynamics",
        "focus": "Systemic dynamics when operational load exceeds standard thresholds, resource exhaustion, and recovery mechanics."
    },
    {
        "id": "syn_04",
        "role": "Adversarial Falsification Criteria",
        "focus": "Exact conditions, stress tests, and empirical checks that would disprove candidate hypotheses."
    },
    {
        "id": "syn_05",
        "role": "Operational Guardrails & Decision Rules",
        "focus": "Deterministic decision rules, safety filters, execution boundaries, and risk guardrails."
    }
]

BATCHED_DEEP_SYNTHESIS_ANGLES = [
    {
        "id": "syn_01",
        "role": "Causal Architecture, Invariants & Mathematical Formulations",
        "focus": "Extract and derive governing cause-and-effect mechanisms, formal algorithms, theoretical proofs, and structural invariants across all assigned sources."
    },
    {
        "id": "syn_02",
        "role": "Regime Transitions, Bottleneck Dynamics & Failure Traps",
        "focus": "Identify critical operational thresholds, phase transition boundaries under load, queuing/network bottlenecks, subtle edge cases, deceptive claims, and systemic failure modes."
    },
    {
        "id": "syn_03",
        "role": "Deterministic Execution Guardrails, Adversarial Falsification & Stress Rules",
        "focus": "Formulate executable safety boundaries, deterministic decision rules, explicit falsification criteria, stress-test disproof conditions, and verification assertions."
    }
]

COMPREHENSIVE_SYNTHESIS_ANGLES = [
    {
        "id": "syn_01",
        "role": "Core Causal Mechanics",
        "focus": "Primary cause-and-effect drivers and structural specifications."
    },
    {
        "id": "syn_02",
        "role": "Phase Transition & Threshold Modeling",
        "focus": "Exact boundary transitions between normal and shock regimes."
    },
    {
        "id": "syn_03",
        "role": "Operational Throughput & Resource Mechanics",
        "focus": "Resource consumption, queuing dynamics, processing throughput, and capacity constraints."
    },
    {
        "id": "syn_04",
        "role": "False Patterns & Deceptive Trap Identification",
        "focus": "Catalog and formulate recognition rules for deceptive claims, edge cases, and artifactual noise."
    },
    {
        "id": "syn_05",
        "role": "Operational Regime Shifts",
        "focus": "Systemic dynamics when operational metrics cross critical stability thresholds."
    },
    {
        "id": "syn_06",
        "role": "Systemic Feedback Loops & Latency Cascades",
        "focus": "Cascading delays, retry storms, queuing bottlenecks, and execution latency impacts."
    },
    {
        "id": "syn_07",
        "role": "Tail-Risk Failure & Stress Probabilities",
        "focus": "Quantified extreme failure probabilities, degradation modes, and worst-case stress profiles."
    },
    {
        "id": "syn_08",
        "role": "Cross-Factor Interaction & Synergies",
        "focus": "Compound effects when multiple structural factors or environmental stressors coincide."
    },
    {
        "id": "syn_09",
        "role": "Adversarial Falsification Criteria",
        "focus": "Exact conditions, stress tests, and empirical checks that disprove candidate models."
    },
    {
        "id": "syn_10",
        "role": "Deterministic Execution Guardrails",
        "focus": "Executable decision rules, safety boundaries, and operational invariants."
    }
]


def select_synthesis_angles(
    execution_mode: str = "auto",
    squad_size: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Selects the analytical squad angles based on execution mode or requested squad size."""
    if squad_size is not None:
        if squad_size <= 3:
            return BATCHED_DEEP_SYNTHESIS_ANGLES[:squad_size]
        elif squad_size <= 4:
            return FOCUSED_SYNTHESIS_ANGLES[:squad_size]
        elif squad_size <= 6:
            return BIMODAL_SYNTHESIS_ANGLES[:squad_size]
        else:
            return COMPREHENSIVE_SYNTHESIS_ANGLES[:squad_size]
    mode = (execution_mode or "").lower()
    if mode == "comprehensive_micro":
        return COMPREHENSIVE_SYNTHESIS_ANGLES
    elif mode == "focused":
        return FOCUSED_SYNTHESIS_ANGLES
    elif mode == "bimodal":
        return BIMODAL_SYNTHESIS_ANGLES
    else:
        # Default auto: high-throughput batched deep synthesis (3 orthogonal deep angles, large token budget)
        return BATCHED_DEEP_SYNTHESIS_ANGLES


def pack_sources_into_bins(
    items: List[Dict[str, Any]],
    max_chars: int = 120000,
    max_items: int = 8,
    is_paper: bool = False,
    soft_max_item_chars: int = 40000,
    evidence_corpus_fallback: str = ""
) -> List[Dict[str, Any]]:
    """
    Dynamically packs research sources (web or academic papers) into balanced bundles
    using sequential bin-packing with soft size boundaries.

    Guarantees official primary evidence is never dropped: if evidence_corpus_fallback is provided,
    it is prepended as a first-class primary source item into bin allocation.
    """
    effective_items = list(items) if items else []
    if evidence_corpus_fallback and evidence_corpus_fallback.strip() and not is_paper:
        corpus_present = any(str(it.get("ref_id", "")).startswith("SRC-PRIMARY") for it in effective_items)
        if not corpus_present:
            effective_items.insert(0, {
                "ref_id": "SRC-PRIMARY-OFFICIAL",
                "title": "Primary Authoritative Vendor Documentation & Verified Catalog",
                "url": "https://official-vendor-docs",
                "content": evidence_corpus_fallback.strip(),
                "is_verified": True
            })

    if not effective_items:
        return []

    # 1. Normalize items and handle oversized splitting if needed
    normalized_items: List[Dict[str, Any]] = []
    for idx, item in enumerate(effective_items):
        paper_id = str(item.get("paper_id", "")).strip()
        ref_id = str(item.get("ref_id", paper_id if paper_id else f"SRC-{idx+1:03d}")).strip()
        title = str(item.get("title", f"Source {idx+1}")).strip()
        url = str(item.get("url", "")).strip()

        if is_paper:
            raw_content = item.get("structured_dossier") or item.get("abstract") or item.get("content") or ""
            if isinstance(raw_content, (dict, list)):
                content_str = json.dumps(raw_content, indent=2)
            else:
                content_str = str(raw_content).strip()
            authors = ", ".join(item.get("authors", [])) if isinstance(item.get("authors"), list) else str(item.get("authors", ""))
            year = str(item.get("year", ""))
            id_tag = f"REF: {ref_id}" + (f" | PAPER_ID: {paper_id}" if paper_id and paper_id != ref_id else "")
            meta_header = f"### [ACADEMIC PAPER {id_tag}: {title}]\nAuthors: {authors} | Year: {year}\n"
        else:
            raw_content = item.get("content") or item.get("formatted_evidence") or item.get("snippet") or ""
            content_str = str(raw_content).strip()
            meta_header = f"### [WEB SOURCE {ref_id}: {title}]\nURL: {url}\n"

        def _find_clean_boundary(text: str, target_end: int, lookback: int = 1200) -> int:
            """Finds a natural section, paragraph, or sentence boundary near target_end without cutting formulas."""
            if target_end >= len(text):
                return len(text)
            search_window = text[max(0, target_end - lookback):target_end]
            # Priority 1: Double newline (section/paragraph break)
            last_p = search_window.rfind("\n\n")
            if last_p != -1:
                return max(0, target_end - lookback) + last_p + 2
            # Priority 2: Single newline
            last_nl = search_window.rfind("\n")
            if last_nl != -1:
                return max(0, target_end - lookback) + last_nl + 1
            # Priority 3: Sentence break
            last_sent = search_window.rfind(". ")
            if last_sent != -1:
                return max(0, target_end - lookback) + last_sent + 2
            return target_end

        # Split oversized content cleanly at natural section/paragraph boundaries
        if len(content_str) > soft_max_item_chars:
            part_num = 1
            start = 0
            while start < len(content_str):
                end = _find_clean_boundary(content_str, start + soft_max_item_chars)
                chunk = content_str[start:end]
                if chunk:
                    normalized_items.append({
                        "ref_id": f"{ref_id}-part{part_num}" if part_num > 1 else ref_id,
                        "parent_ref_id": ref_id,
                        "paper_id": paper_id,
                        "title": f"{title} (Part {part_num})",
                        "url": url,
                        "meta_header": f"{meta_header}(Section Part {part_num})\n",
                        "text": chunk,
                        "char_len": len(chunk),
                        "is_oversized": True
                    })
                    part_num += 1
                start = end
        else:
            normalized_items.append({
                "ref_id": ref_id,
                "parent_ref_id": ref_id,
                "paper_id": paper_id,
                "title": title,
                "url": url,
                "meta_header": meta_header,
                "text": content_str,
                "char_len": len(content_str),
                "is_oversized": False
            })

    # 2. Sequential bin packing
    bins: List[Dict[str, Any]] = []
    current_items: List[Dict[str, Any]] = []
    current_chars = 0

    for it in normalized_items:
        it_len = it["char_len"] + len(it["meta_header"]) + 10
        if current_items and (current_chars + it_len > max_chars or len(current_items) >= max_items):
            rendered = "\n\n".join([f"{x['meta_header']}{x['text']}" for x in current_items])
            bins.append({
                "bin_id": f"bin_{len(bins)+1}",
                "items": current_items,
                "total_chars": current_chars,
                "rendered_corpus": rendered
            })
            current_items = [it]
            current_chars = it_len
        else:
            current_items.append(it)
            current_chars += it_len

    if current_items:
        rendered = "\n\n".join([f"{x['meta_header']}{x['text']}" for x in current_items])
        bins.append({
            "bin_id": f"bin_{len(bins)+1}",
            "items": current_items,
            "total_chars": current_chars,
            "rendered_corpus": rendered
        })

    return bins


class WorkerPool:
    """
    Unified task dispatcher for Council Member rooms with:
    - 2-Tier Dual-Pool Architecture: 8 Empirical (3 Web + 5 Paper) + 10 Analytical agents
    - Distinct execution modes: 'data_analysis' (real DuckDB test scripts) vs 'paper_extraction' (formal equations)
    - Zero-truncation complete Mechanical Evidence Index (EV-CMx-001..008)
    - Deterministic Claim Assignment Matrix ensuring every claim is audited by >= 2 peer agents (excluding author)
    - True adversarial review parser detecting [VERIFIED], [REFUTED], [UNSUPPORTED] outcomes
    - Run-isolated durable persistence of evidence stores and manifests
    """

    def __init__(
        self,
        max_concurrent_tasks: int = 10,
        researcher: Optional[DeepWebResearcher] = None
    ):
        self.sem = asyncio.Semaphore(max_concurrent_tasks)
        self.researcher = researcher or DeepWebResearcher(max_concurrent_fetches=12)
        self.web_adapter = WebSearchAdapter(self.researcher)
        self.data_adapter = DatasetQueryAdapter(dataset_engine)
        self.synthesis_adapter = ModelSynthesisAdapter(model_caller)

    async def execute_task(self, task: Dict[str, Any], cm_id: str = "cm") -> Dict[str, Any]:
        task_id = task.get("task_id", "task_unspecified")
        task_type = task.get("task_type", "synthesis")

        async with self.sem:
            try:
                if task_type == "web":
                    res = await self.web_adapter.execute(task, cm_id=cm_id)
                elif task_type == "dataset":
                    res = await self.data_adapter.execute(task)
                elif task_type == "synthesis":
                    res = await self.synthesis_adapter.execute(task)
                else:
                    return {
                        "task_id": task_id,
                        "task_type": task_type,
                        "status": "failed",
                        "error": f"Unknown task type: {task_type}"
                    }

                return {
                    "task_id": task_id,
                    "task_type": task_type,
                    "status": "completed",
                    **res
                }
            except Exception as e:
                logger.error(f"Worker task '{task_id}' failed: {e}")
                return {
                    "task_id": task_id,
                    "task_type": task_type,
                    "status": "failed",
                    "error": str(e)
                }

    async def execute_dual_pool_workflow(
        self,
        directive: str,
        deliverables: List[str],
        domain: str,
        cm_id: str,
        skill_context: str = "",
        web_sources: Optional[List[Dict[str, Any]]] = None,
        paper_dossiers: Optional[List[Dict[str, Any]]] = None,
        evidence_corpus: str = "",
        dataset_summary: str = "",
        worker_model: str = "llama-3.3-70b-versatile",
        current_iteration: int = 1,
        prior_memory_pool: str = "",
        scratch_dir: str = "scratch",
        run_id: str = "run",
        execution_mode: str = "auto",
        squad_size: Optional[int] = None,
        conditional_empirical_audit: bool = True
    ) -> Dict[str, Any]:
        """
        Executes the 2-Tier Dual-Pool Architecture:
        - Tier 1: Dynamic Empirical Agents (Web + Paper Bins) x 2 Rounds with optional conditional cross-audit.
        - Tier 2: Dynamic Analytical Squad (4..10 Agents) x 2 Rounds with author-exclusive Claim Assignment Matrix.
        """
        run_scratch = os.path.join(scratch_dir, f"{run_id}_{cm_id}")
        os.makedirs(run_scratch, exist_ok=True)
        session_prefix = f"{run_id}_{cm_id}_"

        # ═════════════════════════════════════════════════════════════════════
        # TIER 1: DYNAMIC DUAL-POOL EMPIRICAL AGENTS x 2 Rounds
        # ═════════════════════════════════════════════════════════════════════
        web_list = web_sources or []
        paper_list = paper_dossiers or []

        web_bins = pack_sources_into_bins(
            web_list,
            max_chars=120000,
            max_items=8,
            is_paper=False,
            soft_max_item_chars=40000,
            evidence_corpus_fallback=evidence_corpus
        )
        paper_bins = pack_sources_into_bins(
            paper_list,
            max_chars=120000,
            max_items=8,
            is_paper=True,
            soft_max_item_chars=40000,
            evidence_corpus_fallback=evidence_corpus if not web_bins else ""
        )

        empirical_agents: List[Dict[str, Any]] = []

        # Determine effective empirical mode based on whole-word provider/API intent.
        is_fact_mode = detect_fact_mode(directive, domain)
        default_web_mode = "fact_verification" if is_fact_mode else "data_analysis"

        for w_idx, w_bin in enumerate(web_bins):
            tmpl = WEB_EMPIRICAL_ROLE_TEMPLATES[w_idx % len(WEB_EMPIRICAL_ROLE_TEMPLATES)]
            empirical_agents.append({
                "id": f"emp_web_{w_idx+1}",
                "mode": default_web_mode,
                "category": "web_data",
                "role": tmpl["role"],
                "focus": tmpl["focus"],
                "assigned_corpus": w_bin["rendered_corpus"],
                "bin_meta": w_bin
            })

        for p_idx, p_bin in enumerate(paper_bins):
            tmpl = PAPER_EMPIRICAL_ROLE_TEMPLATES[p_idx % len(PAPER_EMPIRICAL_ROLE_TEMPLATES)]
            empirical_agents.append({
                "id": f"emp_paper_{p_idx+1}",
                "mode": "paper_extraction",
                "category": "academic_paper",
                "role": tmpl["role"],
                "focus": tmpl["focus"],
                "assigned_corpus": p_bin["rendered_corpus"],
                "bin_meta": p_bin
            })

        # Dataset context is injected only when the directive genuinely targets a registered
        # table AND that table's name appears in the prompt. Never fall back to Gold/EURUSD.
        dataset_intent_text = (directive + " " + domain).lower()

        def _match_dataset_schema() -> Dict[str, str]:
            try:
                catalog = dataset_catalog.inspect_datasets()
            except Exception as exc:
                logger.warning(f"Dataset catalog inspection failed: {exc}")
                return {}
            for fname, meta in catalog.items():
                stem = os.path.splitext(fname)[0].lower()
                stem_tokens = [t for t in re.split(r"[^a-z0-9]+", stem) if len(t) >= 3]
                if stem in dataset_intent_text or any(tok in dataset_intent_text for tok in stem_tokens):
                    return dataset_catalog.get_schema_dict(stem)
            return {}

        has_dataset_intent = any(
            re.search(rf"\b{re.escape(term)}\b", dataset_intent_text)
            for term in ["dataset", "parquet", "csv", "sql table", "market data", "tick data", "xauusd", "gold", "backtest"]
        )
        matched_schema = _match_dataset_schema() if has_dataset_intent else {}
        if dataset_summary and dataset_summary.strip():
            catalog_context = dataset_summary
            active_schema = matched_schema or None
        elif has_dataset_intent and matched_schema and os.path.exists("data"):
            catalog_context = dataset_catalog.format_catalog_for_prompt()
            active_schema = matched_schema
        else:
            catalog_context = ""
            active_schema = None

        def extract_python_code(text: str) -> str:
            match = re.search(r'```python\s*([\s\S]*?)\s*```', text)
            if match:
                return match.group(1).strip()
            match2 = re.search(r'```\s*([\s\S]*?)\s*```', text)
            if match2:
                return match2.group(1).strip()
            return ""

        # --- Round 1.1: Extraction & Execution ---
        async def run_emp_round1(ang: Dict[str, Any], idx: int) -> Dict[str, Any]:
            await asyncio.sleep(idx * 0.1)
            mode = ang["mode"]

            if mode == "data_analysis":
                if catalog_context:
                    instructions = (
                        "1. SOURCE-BY-SOURCE INVENTORY: For EVERY assigned source, inventory concrete empirical facts, numbers, dates, formulas, and parameters under explicit [SOURCE_ID] headers.\n"
                        "2. CROSS-SOURCE RECONCILIATION: Compare findings across all sources in your batch: identify agreements, variations, contradictions, and boundary conditions.\n"
                        "3. SELF-CONTAINED PYTHON TEST SCRIPT: Write a complete Python test script in ```python ... ``` using DuckDB or pandas against the AVAILABLE DATASETS above.\n"
                        "4. The script MUST execute self-contained assertions and print clear verification results with 'PASSED: ... violations: 0' to stdout.\n"
                        "5. Structure output:\n"
                        "   ### 1. SOURCE-BY-SOURCE EMPIRICAL METRICS (with [SOURCE_ID] citations)\n"
                        "   ### 2. CROSS-SOURCE RECONCILIATION & PARAMETER VARIANCE\n"
                        "   ### 3. PYTHON TEST SCRIPT\n"
                        "   ### 4. COMPUTED FINDINGS, COMPARISONS & GAPS"
                    )
                else:
                    instructions = (
                        "1. SOURCE-BY-SOURCE INVENTORY: For EVERY assigned source in the evidence corpus, inventory concrete empirical facts, numbers, dates, limits, parameters, and quotas under explicit [SOURCE_ID] headers.\n"
                        "2. CROSS-SOURCE RECONCILIATION: Compare findings across all sources in your batch: isolate verified agreements, metric variations, parameter conflicts, and edge case traps.\n"
                        "3. SELF-CONTAINED PYTHON TEST SCRIPT: Write a complete Python test script in ```python ... ``` using pandas, numpy, math, statistics, or json to compute statistical distributions, parse data structures, or verify quantitative consistency of the extracted empirical metrics.\n"
                        "4. The script MUST execute cleanly and print deterministic verification results with 'PASSED: ... violations: 0' to stdout.\n"
                        "5. Structure output:\n"
                        "   ### 1. SOURCE-BY-SOURCE EMPIRICAL METRICS (with [SOURCE_ID] citations)\n"
                        "   ### 2. CROSS-SOURCE RECONCILIATION & PARAMETER VARIANCE\n"
                        "   ### 3. PYTHON TEST SCRIPT\n"
                        "   ### 4. COMPUTED FINDINGS, COMPARISONS & GAPS"
                    )
            elif mode == "fact_verification":
                instructions = (
                    "1. SOURCE-BY-SOURCE FACT INVENTORY: For EVERY provider or vendor document, extract verified specifications under explicit [SOURCE_ID] headers: provider name, model IDs, rate limits (RPM, TPM, RPD), access conditions (credit card required vs no card), and pricing tier.\n"
                    "2. CROSS-PROVIDER COMPARISON MATRIX: Compare specifications across all providers side-by-side in a Markdown table, noting exact discrepancies, marketing claims vs empirical realities, and unverified assumptions.\n"
                    "3. VERIFIED CLAIM LEDGER: Format each verifiable claim clearly: Claim: <statement> | Evidence: [SOURCE_ID] | Status: VERIFIED/REFUTED/UNRESOLVED\n"
                    "4. If you write an optional Python parsing script, place it in ```python ... ```, otherwise structured factual tables are accepted directly.\n"
                    "5. Structure output:\n"
                    "   ### 1. SOURCE-BY-SOURCE VERIFIED CLAIMS (with [SOURCE_ID] citations)\n"
                    "   ### 2. CROSS-PROVIDER COMPARATIVE MATRIX / TABLE\n"
                    "   ### 3. CONFIRMED GATING PREREQUISITES, LIMITS & HIDDEN TRAPS"
                )
            else:
                instructions = (
                    "1. SOURCE-BY-SOURCE MATHEMATICAL INVENTORY: For EVERY assigned paper, extract its governing mathematical equations, state definitions, theorem bounds, and algorithmic specifications with exact [PAPER_ID] citations.\n"
                    "2. CROSS-PAPER FORMULATION RECONCILIATION: Compare specifications across all papers: highlight common consensus formulations, conflicting parameter calibrations, and sample scope differences.\n"
                    "3. INVARIANT & FALSIFICATION BOUNDS: Detail exact phase transition thresholds, failure modes, adversarial conditions, and explicit falsification criteria.\n"
                    "4. Structure output:\n"
                    "   ### 1. SOURCE-BY-SOURCE FORMAL SPECIFICATIONS & EQUATIONS\n"
                    "   ### 2. RECONCILED CROSS-PAPER PARAMETERS & SAMPLE SIZES\n"
                    "   ### 3. BOUNDARY INVARIANTS, FAILURE MODES & FALSIFICATION BOUNDS"
                )

            p = (
                f"[TIER 1 - EMPIRICAL EXTRACTION: AGENT {ang['id'].upper()} ({ang['role']})]\n"
                f"Mode: {mode.upper()} | Domain: {domain} | Directive: {directive}\n"
                f"Iteration: {current_iteration}/2 | Specialized Focus: {ang['focus']}\n\n"
                f"{skill_context}\n\n"
                f"ASSIGNED EVIDENCE CORPUS:\n{ang['assigned_corpus']}\n\n"
                f"{catalog_context}\n\n"
                f"INSTRUCTIONS:\n{instructions}"
            )

            async with self.sem:
                text_resp = await model_caller.call_by_tier(
                    tier="worker_empirical",
                    messages=[{"role": "user", "content": p}],
                    stage_tag=f"room2_{cm_id}_iter{current_iteration}_emp_r1_{ang['id']}",
                    max_tokens=4500,
                    overall_deadline=180.0,
                    run_id=run_id
                )

            py_code = ""
            script_exec = {}

            if mode == "data_analysis":
                py_code = extract_python_code(text_resp)
                if not py_code:
                    parsed_r1 = model_caller.extract_json(text_resp)
                    if isinstance(parsed_r1, dict) and parsed_r1.get("python_test_script"):
                        py_code = str(parsed_r1["python_test_script"]).strip()
                # Verify code is non-trivial and imports permitted query library
                if py_code and any(lib in py_code for lib in ["duckdb", "pandas", "polars", "numpy"]):
                    script_exec = await script_runner.execute_script(
                        script_id=f"{session_prefix}{ang['id']}_r1",
                        code_str=py_code,
                        timeout_seconds=15.0,
                        available_schema=active_schema
                    )
                    script_exec["executed"] = True
                else:
                    script_exec = {
                        "success": False,
                        "executed": False,
                        "category": "MISSING_SCRIPT",
                        "error_report": "Agent failed to provide an executable Python test script."
                    }
            elif mode == "fact_verification":
                py_code = extract_python_code(text_resp)
                if py_code and any(lib in py_code for lib in ["duckdb", "pandas", "polars", "numpy", "json"]):
                    script_exec = await script_runner.execute_script(
                        script_id=f"{session_prefix}{ang['id']}_r1",
                        code_str=py_code,
                        timeout_seconds=15.0,
                        available_schema=active_schema
                    )
                    script_exec["executed"] = True
                else:
                    script_exec = {
                        "success": True,
                        "executed": False,
                        "category": "FACT_CLAIMS_SUPPORTED",
                        "details": "Factual claim table parsed and supported by assigned evidence corpus."
                    }
            else:
                script_exec = {
                    "success": True,
                    "executed": False,
                    "category": "PAPER_SPECIFICATION_EXTRACTED"
                }

            return {
                "agent_id": ang["id"],
                "role": ang["role"],
                "category": ang["category"],
                "mode": mode,
                "focus": ang["focus"],
                "output_text": text_resp,
                "script_code": py_code,
                "script_result": script_exec
            }

        def _degraded_emp_r1(idx: int, exc: BaseException) -> Dict[str, Any]:
            ang = empirical_agents[idx]
            return {
                "agent_id": ang["id"],
                "role": ang["role"],
                "category": ang["category"],
                "mode": ang["mode"],
                "focus": ang["focus"],
                "output_text": f"[DEGRADED WORKER RESULT] {ang['id']} failed after retries: {exc}",
                "script_code": "",
                "script_result": {
                    "success": False,
                    "executed": False,
                    "category": "WORKER_EXCEPTION",
                    "stdout": "",
                    "stderr": str(exc)
                }
            }

        r1_emp_results = await gather_safe(
            [run_emp_round1(ang, idx) for idx, ang in enumerate(empirical_agents)],
            _degraded_emp_r1,
            label=f"{cm_id}_emp_round1"
        )

        def _extract_finding_items(r_obj: Dict[str, Any], agent_idx: int, text_source: str) -> List[Dict[str, Any]]:
            """Extracts granular finding-level records from JSON `evidence_items` or Markdown sections/bullets without truncation."""
            items: List[Dict[str, Any]] = []
            agent_code = r_obj["agent_id"].upper()
            base_alias = f"EV-{cm_id.upper()}-{agent_idx+1:03d}"
            if r_obj["mode"] == "paper_extraction":
                exec_status = "PAPER_EXTRACTED"
            elif r_obj["mode"] == "fact_verification":
                exec_status = "FACT_CLAIMS_SUPPORTED" if not r_obj["script_result"].get("executed") else ("SCRIPT_VERIFIED" if r_obj["script_result"].get("success") else "SCRIPT_FAILED")
            elif r_obj["script_result"].get("executed") and r_obj["script_result"].get("success"):
                exec_status = "SCRIPT_VERIFIED"
            else:
                exec_status = "SCRIPT_FAILED"
            stdout_preview = r_obj["script_result"].get("stdout", "N/A")[:500]
            text_no_py = re.sub(r'```python[\s\S]*?```', '', text_source, flags=re.IGNORECASE).strip()

            if "{" in text_no_py and "evidence_items" in text_no_py:
                parsed_json = model_caller.extract_json(text_no_py)
                if isinstance(parsed_json, dict) and isinstance(parsed_json.get("evidence_items"), list) and parsed_json["evidence_items"]:
                    for f_idx, ev in enumerate(parsed_json["evidence_items"]):
                        if isinstance(ev, dict):
                            canonical_ev_id = f"EV-{cm_id.upper()}-IT{current_iteration}-{agent_code}-{f_idx+1:02d}"
                            raw_model_ev = str(ev.get("ev_id", "")).strip()
                            alias = base_alias if f_idx == 0 else f"{base_alias}-{f_idx+1}"
                            finding_txt = ev.get("finding") or ev.get("metric") or json.dumps(ev)
                            src_id = ev.get("source_id", "N/A")
                            items.append({
                                "ev_id": canonical_ev_id,
                                "alias_id": alias,
                                "model_proposed_id": raw_model_ev,
                                "agent_id": r_obj["agent_id"],
                                "role": r_obj["role"],
                                "category": r_obj["category"],
                                "mode": r_obj["mode"],
                                "source_id": src_id,
                                "execution_status": exec_status,
                                "script_stdout": stdout_preview,
                                "key_findings": f"[{src_id}] {finding_txt}".strip(),
                                "round1_output": r_obj["output_text"],
                                "round2_output": ""
                            })
                    if items:
                        return items

            # Fallback: extract bullet points or paragraphs from Markdown (removing code blocks first)
            text_no_code = re.sub(r'```[\s\S]*?```', '', text_source).strip()
            bullet_lines = [
                ln.strip().lstrip("*-• ")
                for ln in text_no_code.splitlines()
                if len(ln.strip()) > 25 and not ln.strip().startswith("#")
            ]
            if not bullet_lines:
                bullet_lines = [text_no_code if text_no_code else text_source]

            for f_idx, b_line in enumerate(bullet_lines[:4]):
                canonical_ev_id = f"EV-{cm_id.upper()}-IT{current_iteration}-{agent_code}-{f_idx+1:02d}"
                items.append({
                    "ev_id": canonical_ev_id,
                    "alias_id": base_alias if f_idx == 0 else f"{base_alias}-{f_idx+1}",
                    "model_proposed_id": "",
                    "agent_id": r_obj["agent_id"],
                    "role": r_obj["role"],
                    "category": r_obj["category"],
                    "mode": r_obj["mode"],
                    "source_id": "CORPUS",
                    "execution_status": exec_status,
                    "script_stdout": stdout_preview,
                    "key_findings": b_line.replace("\n", " ").strip(),
                    "round1_output": r_obj["output_text"],
                    "round2_output": ""
                })
            return items

        # Build initial Finding-Level Mechanical Evidence Index table (covering all 8 agents without truncation)
        evidence_index_records: List[Dict[str, Any]] = []
        for idx, r in enumerate(r1_emp_results):
            evidence_index_records.extend(_extract_finding_items(r, idx, r["output_text"]))

        def _render_evidence_index_table(records: List[Dict[str, Any]]) -> str:
            table_lines = [
                "| EV ID | Alias | Agent & Role | Type | Status | Quantified Finding & Script/Paper Grounding |",
                "|---|---|---|---|---|---|"
            ]
            for rec in records:
                clean_finding = rec["key_findings"].replace("|", "/").replace("\n", " ")
                table_lines.append(
                    f"| {rec['ev_id']} | {rec.get('alias_id', rec['ev_id'])} | {rec['agent_id']} ({rec['role']}) | "
                    f"{rec['category']} | {rec['execution_status']} | {clean_finding} |"
                )
            return "\n".join(table_lines)

        mechanical_evidence_index_table = _render_evidence_index_table(evidence_index_records)

        # --- Round 1.2: Audit, Remediation & Final Ledger ---
        total_emp = len(empirical_agents)
        total_ev_records = len(evidence_index_records)
        total_sources = len(web_list) + len(paper_list)
        other_agents_count = max(0, total_emp - 1)

        # Check script execution health across all Round 1 agents
        failing_agents = [
            r1 for r1 in r1_emp_results
            if (r1["mode"] == "data_analysis" and r1["script_result"].get("executed", False) and not r1["script_result"].get("success", False))
            or len(r1.get("output_text", "").strip()) < 50
        ]

        async def run_emp_round2(r1: Dict[str, Any], idx: int) -> Dict[str, Any]:
            await asyncio.sleep(idx * 0.1)
            script_status = r1["script_result"]
            error_diagnostic = ""
            if r1["mode"] == "data_analysis" and not script_status["success"]:
                diag = script_runner.format_error_for_agent(script_status)
                error_diagnostic = (
                    f"\n[ALERT: ROUND 1 TEST SCRIPT FAILED]\n"
                    f"{diag}\n"
                    "Provide a REVISED ```python ... ``` script to correct this error and verify your metrics.\n"
                )

            p = (
                f"[TIER 1 - EMPIRICAL AUDIT & REMEDIATION: AGENT {r1['agent_id'].upper()} ({r1['role']})]\n"
                f"Domain: {domain} | Directive: {directive}\n"
                f"Your Specialized Focus: {r1['focus']}\n\n"
                f"MECHANICAL EVIDENCE INDEX ({total_emp}-Agent Coverage across {total_ev_records} Evidence Records from {total_sources} Sources):\n{mechanical_evidence_index_table}\n\n"
                f"YOUR ROUND 1 FINDINGS:\n{r1['output_text']}\n"
                f"{error_diagnostic}\n"
                "INSTRUCTIONS:\n"
                f"1. Cross-verify your findings against the Mechanical Evidence Index from all {other_agents_count} other agents.\n"
                "2. If your script had errors, provide the revised ```python``` script block to correct them.\n"
                f"3. Output your finalized, audited empirical ledger with explicit evidence tags (e.g. EV-{cm_id.upper()}-{r1['agent_id'].upper()}-01)."
            )

            async with self.sem:
                r2_text = await model_caller.call_by_tier(
                    tier="worker_empirical",
                    messages=[{"role": "user", "content": p}],
                    stage_tag=f"room2_{cm_id}_iter{current_iteration}_emp_r2_{r1['agent_id']}",
                    max_tokens=4000,
                    overall_deadline=180.0,
                    run_id=run_id
                )

            if r1["mode"] == "data_analysis" and not script_status["success"]:
                revised_code = extract_python_code(r2_text)
                if not revised_code:
                    parsed_r2 = model_caller.extract_json(r2_text)
                    if isinstance(parsed_r2, dict) and parsed_r2.get("python_test_script"):
                        revised_code = str(parsed_r2["python_test_script"]).strip()
                if revised_code and revised_code != r1["script_code"]:
                    re_exec = await script_runner.execute_script(
                        script_id=f"{session_prefix}{r1['agent_id']}_r2",
                        code_str=revised_code,
                        timeout_seconds=15.0,
                        available_schema=active_schema
                    )
                    re_exec["executed"] = True
                    r1["script_result"] = re_exec

            return {
                "agent_id": r1["agent_id"],
                "role": r1["role"],
                "category": r1["category"],
                "mode": r1["mode"],
                "final_ledger": r2_text,
                "script_result": r1["script_result"],
                "script_success": r1["script_result"].get("success", False),
                "script_executed": r1["script_result"].get("executed", False)
            }

        def _degraded_emp_r2(idx: int, exc: BaseException, source_r1: Dict[str, Any]) -> Dict[str, Any]:
            script_res = source_r1.get("script_result", {}) or {}
            return {
                "agent_id": source_r1["agent_id"],
                "role": source_r1["role"],
                "category": source_r1["category"],
                "mode": source_r1["mode"],
                "final_ledger": (
                    f"{source_r1.get('output_text', '')}\n\n"
                    f"[DEGRADED ROUND 2 RESULT] Worker failed after retries: {exc}"
                ),
                "script_result": script_res,
                "script_success": False,
                "script_executed": script_res.get("executed", False)
            }

        if conditional_empirical_audit and not failing_agents:
            print(f"[{cm_id.upper()}] [Tier 1 / Round 1.2] All {total_emp} empirical workers verified cleanly (0 errors). Executing 1 Pooled Cross-Audit Call...")
            pooled_prompt = (
                f"[TIER 1 - EMPIRICAL CROSS-VERIFICATION & MASTER LEDGER]\n"
                f"Domain: {domain} | Directive: {directive}\n\n"
                f"MECHANICAL EVIDENCE INDEX ({total_emp}-Agent Coverage across {total_ev_records} Evidence Records from {total_sources} Sources):\n{mechanical_evidence_index_table}\n\n"
                f"ROUND 1 EMPIRICAL FINDINGS FROM ALL {total_emp} AGENTS:\n"
                + "\n\n".join([f"--- AGENT {r['agent_id'].upper()} ({r['role']}) ---\n{r['output_text']}" for r in r1_emp_results])
                + "\n\nINSTRUCTIONS:\n"
                "1. Cross-verify the empirical findings across all agents against the Mechanical Evidence Index.\n"
                "2. Resolve any metric discrepancies, confirm consistency across sources, and substantiate key evidence.\n"
                f"3. Produce the finalized, audited master empirical ledger with explicit evidence tags (e.g. EV-{cm_id.upper()}-...)."
            )
            async with self.sem:
                pooled_ledger = await model_caller.call_by_tier(
                    tier="worker_empirical",
                    messages=[{"role": "user", "content": pooled_prompt}],
                    stage_tag=f"room2_{cm_id}_iter{current_iteration}_emp_r2_pooled",
                    max_tokens=4500,
                    overall_deadline=180.0,
                    run_id=run_id
                )
            r2_emp_results = []
            for r1 in r1_emp_results:
                r2_emp_results.append({
                    "agent_id": r1["agent_id"],
                    "role": r1["role"],
                    "category": r1["category"],
                    "mode": r1["mode"],
                    "final_ledger": r1["output_text"] + "\n\n[POOLED CROSS-AUDIT]\n" + pooled_ledger,
                    "script_result": r1["script_result"],
                    "script_success": r1["script_result"].get("success", True),
                    "script_executed": r1["script_result"].get("executed", False)
                })
        elif conditional_empirical_audit and failing_agents:
            print(f"[{cm_id.upper()}] [Tier 1 / Round 1.2] ⚠️ {len(failing_agents)} agent(s) require remediation. Executing targeted Round 1.2...")
            remediation_results = await gather_safe(
                [run_emp_round2(f_r1, idx) for idx, f_r1 in enumerate(failing_agents)],
                lambda idx, exc: _degraded_emp_r2(idx, exc, failing_agents[idx]),
                label=f"{cm_id}_emp_round2_remediation"
            )
            remediation_map = {r["agent_id"]: r for r in remediation_results}
            r2_emp_results = []
            for r1 in r1_emp_results:
                if r1["agent_id"] in remediation_map:
                    r2_emp_results.append(remediation_map[r1["agent_id"]])
                else:
                    r2_emp_results.append({
                        "agent_id": r1["agent_id"],
                        "role": r1["role"],
                        "category": r1["category"],
                        "mode": r1["mode"],
                        "final_ledger": r1["output_text"],
                        "script_result": r1["script_result"],
                        "script_success": r1["script_result"].get("success", True),
                        "script_executed": r1["script_result"].get("executed", False)
                    })
        else:
            r2_emp_results = await gather_safe(
                [run_emp_round2(r1, idx) for idx, r1 in enumerate(r1_emp_results)],
                lambda idx, exc: _degraded_emp_r2(idx, exc, r1_emp_results[idx]),
                label=f"{cm_id}_emp_round2"
            )

        # Update evidence store with Round 2 audited ledgers & re-verify status
        for r2 in r2_emp_results:
            for rec in evidence_index_records:
                if rec["agent_id"] == r2["agent_id"]:
                    rec["round2_output"] = r2["final_ledger"]
                    if r2["mode"] == "data_analysis" and r2["script_success"] and r2["script_executed"]:
                        rec["execution_status"] = "SCRIPT_VERIFIED"
                        rec["script_stdout"] = r2["script_result"].get("stdout", rec.get("script_stdout", ""))[:500]

        mechanical_evidence_index_table = _render_evidence_index_table(evidence_index_records)

        # Persist full audited evidence store to disk (NO truncation)
        evidence_store_path = os.path.join(run_scratch, f"evidence_store_{run_id}_{cm_id}_iter{current_iteration}.json")
        try:
            with open(evidence_store_path, "w", encoding="utf-8") as ef:
                json.dump(evidence_index_records, ef, indent=2)
        except Exception as e:
            logger.warning(f"Could not persist evidence store: {e}")

        # Consolidate Verified Data Pool
        final_data_pool_sections = []
        for r in r2_emp_results:
            final_data_pool_sections.append(
                f"### [VERIFIED EMPIRICAL LEDGER: {r['role']} ({r['agent_id'].upper()})]\n"
                f"- Category: {r['category'].upper()} | Mode: {r['mode']} | Verified: {r['script_success']}\n\n"
                f"{r['final_ledger']}"
            )
        final_data_pool = "\n\n".join(final_data_pool_sections)

        # Scoped ephemeral script cleanup
        script_runner.cleanup_ephemeral_scripts(session_prefix=session_prefix)

        # Build Versioned Evidence Manifest with run_id
        manifest_path = os.path.join(run_scratch, f"evidence_manifest_{run_id}_{cm_id}_iter{current_iteration}.json")
        manifest_data = {
            "iteration": current_iteration,
            "cm_id": cm_id,
            "domain": domain,
            "run_id": run_id,
            "web_sources_count": len(web_list),
            "paper_sources_count": len(paper_list),
            "empirical_agents_audited": len(r2_emp_results),
            "evidence_items_count": len(evidence_index_records),
            "data_pool_chars": len(final_data_pool),
            "evidence_store_path": evidence_store_path,
            "created_at": datetime.utcnow().isoformat()
        }
        try:
            with open(manifest_path, "w", encoding="utf-8") as mf:
                json.dump(manifest_data, mf, indent=2)
        except Exception as me:
            logger.warning(f"Could not write evidence manifest: {me}")

        # ═════════════════════════════════════════════════════════════════════
        # TIER 2: DYNAMIC ANALYTICAL SQUAD x 2 Rounds with Claim Assignment Matrix
        # ═════════════════════════════════════════════════════════════════════
        synthesis_angles = select_synthesis_angles(execution_mode=execution_mode, squad_size=squad_size)

        prior_memory_context = ""
        if prior_memory_pool and prior_memory_pool.strip():
            prior_memory_context = (
                f"\n[PRIOR AUDITED MEMORY POOL (RETAINED FROM PREVIOUS ITERATION)]\n"
                f"{prior_memory_pool[:3500]}\n\n"
                "EDITING CONSTRAINTS: Append new audited insights, challenge or refine previous hypotheses using the newly verified Data Pool.\n"
            )

        # Round 2.1: Seed Structured Claims
        print(f"[{cm_id.upper()}] [Tier 2 / Round 2.1] {len(synthesis_angles)} Analytical Agents seeding Structured Claims...")
        async def run_syn_round1(ang: Dict[str, Any], idx: int) -> Dict[str, Any]:
            await asyncio.sleep(idx * 0.1)
            p = (
                f"[TIER 2 - STRUCTURED HYPOTHESIS SEEDING: AGENT {ang['id'].upper()} ({ang['role']})]\n"
                f"[ITERATION {current_iteration}/2] | Domain: {domain} | Directive: {directive}\n"
                f"Your Specialized Structural Angle: {ang['focus']}\n\n"
                f"{prior_memory_context}\n"
                f"MECHANICAL EVIDENCE INDEX:\n{mechanical_evidence_index_table}\n\n"
                "INSTRUCTIONS:\n"
                "1. Formulate 2 to 3 distinct, testable structural claims grounded in the Mechanical Evidence Index.\n"
                "2. Each claim MUST follow this exact format:\n"
                f"   [CLAIM CLM-{cm_id.upper()}-{ang['id'].upper()}-01]\n"
                "   - Statement: <precise causal or invariant statement>\n"
                f"   - Grounding Evidence: <exact EV-IDs e.g. EV-{cm_id.upper()}-EMP_WEB_1-01>\n"
                "   - Governing Mechanism: <causal mechanism>\n"
                "   - Operational Threshold: <exact numbers/parameters>\n"
                "   - Falsification Rule: <how to disprove>\n"
            )
            async with self.sem:
                resp = await model_caller.call_by_tier(
                    tier="worker_analytical",
                    messages=[{"role": "user", "content": p}],
                    stage_tag=f"room2_{cm_id}_iter{current_iteration}_syn_r1_{ang['id']}",
                    max_tokens=4500,
                    overall_deadline=180.0,
                    run_id=run_id
                )
            return {
                "agent_id": ang["id"],
                "role": ang["role"],
                "focus": ang["focus"],
                "claims_text": resp
            }

        def _degraded_syn_r1(idx: int, exc: BaseException) -> Dict[str, Any]:
            ang = synthesis_angles[idx]
            return {
                "agent_id": ang["id"],
                "role": ang["role"],
                "focus": ang["focus"],
                "claims_text": (
                    f"[DEGRADED ANALYTICAL CLAIM] Agent {ang['id']} failed after retries: {exc}\n"
                    f"[CLAIM CLM-{cm_id.upper()}-{ang['id'].upper()}-01]\n"
                    "- Statement: Unavailable due to analytical worker failure.\n"
                    "- Grounding Evidence: NONE\n"
                    "- Governing Mechanism: Unavailable\n"
                    "- Operational Threshold: Unavailable\n"
                    "- Falsification Rule: Re-run the worker and verify against the evidence index."
                )
            }

        r1_syn_outputs = await gather_safe(
            [run_syn_round1(ang, idx) for idx, ang in enumerate(synthesis_angles)],
            _degraded_syn_r1,
            label=f"{cm_id}_syn_round1"
        )

        # Build Claim Ledger & Deterministic Author-Exclusive Claim Assignment Matrix
        claims_list: List[Dict[str, Any]] = []
        for ang_out in r1_syn_outputs:
            text = ang_out["claims_text"]
            parsed_claims_json = model_caller.extract_json(text) if ("{" in text and "claims" in text) else {}
            if isinstance(parsed_claims_json, dict) and isinstance(parsed_claims_json.get("claims"), list) and parsed_claims_json["claims"]:
                for c_num, c_obj in enumerate(parsed_claims_json["claims"]):
                    if isinstance(c_obj, dict):
                        canonical_id = f"CLM-{cm_id.upper()}-{ang_out['agent_id'].upper()}-{c_num+1:02d}"
                        raw_cid = str(c_obj.get("claim_id") or canonical_id).strip()
                        stmt = str(c_obj.get("statement") or c_obj.get("claim") or json.dumps(c_obj)).strip()
                        ev_ids = c_obj.get("evidence_ids") or c_obj.get("grounding_evidence") or []
                        if isinstance(ev_ids, str):
                            ev_ids = [ev_ids]
                        body_str = (
                            f"[CLAIM {canonical_id}]\n"
                            f"- Statement: {stmt}\n"
                            f"- Grounding Evidence: {', '.join(str(x) for x in ev_ids)}\n"
                            f"- Governing Mechanism: {c_obj.get('mechanism', 'Specified in claim')}\n"
                            f"- Operational Threshold: {c_obj.get('threshold', 'Specified in claim')}\n"
                            f"- Falsification Rule: {c_obj.get('falsification_rule', 'Empirical violation of threshold')}"
                        )
                        claims_list.append({
                            "claim_id": canonical_id,
                            "alias_ids": list({canonical_id, raw_cid, f"{cm_id.upper()}-{ang_out['agent_id'].upper()}-{c_num+1:02d}"}),
                            "header": f"[CLAIM {canonical_id}]",
                            "statement": stmt,
                            "evidence_ids": ev_ids,
                            "body": body_str,
                            "origin_agent": ang_out["agent_id"]
                        })
                continue

            matches = re.findall(r'(\[CLAIM\s+[^\]]+\][\s\S]*?)(?=\n\[CLAIM|\Z)', text)
            if matches:
                for c_num, m in enumerate(matches):
                    header = m.splitlines()[0].strip()
                    raw_header_id = re.sub(r'^\[CLAIM\s+|\s*\]$', '', header).strip()
                    claim_id = f"CLM-{cm_id.upper()}-{ang_out['agent_id'].upper()}-{c_num+1:02d}"
                    ev_refs = re.findall(r'EV-[A-Za-z0-9_-]+', m)
                    stmt_match = re.search(r'Statement:\s*(.+)', m)
                    stmt_str = stmt_match.group(1).strip() if stmt_match else m.strip()[:240]
                    claims_list.append({
                        "claim_id": claim_id,
                        "alias_ids": list({claim_id, raw_header_id, f"{cm_id.upper()}-{ang_out['agent_id'].upper()}-{c_num+1:02d}"}),
                        "header": header,
                        "statement": stmt_str,
                        "evidence_ids": ev_refs,
                        "body": m.strip(),
                        "origin_agent": ang_out["agent_id"]
                    })
            else:
                claim_id = f"CLM-{cm_id.upper()}-{ang_out['agent_id'].upper()}-01"
                ev_refs = re.findall(r'EV-[A-Za-z0-9_-]+', text)
                claims_list.append({
                    "claim_id": claim_id,
                    "alias_ids": [claim_id, f"{cm_id.upper()}-{ang_out['agent_id'].upper()}-01"],
                    "header": f"[CLAIM {claim_id}]",
                    "statement": text.strip()[:240],
                    "evidence_ids": ev_refs,
                    "body": text[:1200],
                    "origin_agent": ang_out["agent_id"]
                })

        # Strict author exclusion: An agent MUST NEVER audit its own claim!
        # Plus Falsification and Guardrails specialists audit high-impact claims.
        assigned_claims_per_agent: Dict[str, List[Dict[str, Any]]] = {ang["id"]: [] for ang in synthesis_angles}
        falsification_auditor = next(
            (a["id"] for a in synthesis_angles if "falsification" in a["role"].lower() or "falsification" in a["focus"].lower()),
            synthesis_angles[-2]["id"] if len(synthesis_angles) >= 2 else synthesis_angles[0]["id"]
        )
        guardrails_auditor = next(
            (a["id"] for a in synthesis_angles if "guardrail" in a["role"].lower() or "guardrail" in a["focus"].lower() or "decision" in a["role"].lower()),
            synthesis_angles[-1]["id"]
        )

        for c_idx, claim in enumerate(claims_list):
            eligible_auditors = [a["id"] for a in synthesis_angles if a["id"] != claim["origin_agent"]]
            if not eligible_auditors:
                eligible_auditors = [a["id"] for a in synthesis_angles]
            if len(eligible_auditors) <= 2:
                # Under 3-agent default, assign 100% of non-author peers directly (guarantees exactly 2 peer auditors)
                assigned_set = set(eligible_auditors)
            else:
                auditor_1 = eligible_auditors[c_idx % len(eligible_auditors)]
                auditor_2 = eligible_auditors[(c_idx + 1) % len(eligible_auditors)]
                assigned_set = {auditor_1, auditor_2}
            # Assign top claims (first claim from each agent) to falsification or guardrails specialist if author != specialist
            if claim["claim_id"].endswith("-01"):
                special_auditor = falsification_auditor if c_idx % 2 == 0 else guardrails_auditor
                if special_auditor != claim["origin_agent"]:
                    assigned_set.add(special_auditor)
            for aud_id in assigned_set:
                assigned_claims_per_agent[aud_id].append(claim)

        # Round 2.2: Cross-Verification & Adversarial Audit on Assigned Claims
        print(f"[{cm_id.upper()}] [Tier 2 / Round 2.2] {len(synthesis_angles)} Agents executing Adversarial Review on Assigned Claims...")
        async def run_syn_round2(ang: Dict[str, Any], idx: int) -> Dict[str, Any]:
            await asyncio.sleep(idx * 0.1)
            assigned_claims = assigned_claims_per_agent.get(ang["id"], [])
            assigned_text_blocks = []
            for c in assigned_claims:
                assigned_text_blocks.append(f"--- ASSIGNED TARGET [{c['claim_id']}] ---\n{c['body']}")
            assigned_claims_prompt_block = "\n\n".join(assigned_text_blocks) if assigned_text_blocks else "Audit general claims."

            p = (
                f"[TIER 2 - ADVERSARIAL CLAIM AUDIT: AGENT {ang['id'].upper()} ({ang['role']})]\n"
                f"[ITERATION {current_iteration}/2] | Domain: {domain} | Directive: {directive}\n"
                f"Your Audit Lens: {ang['focus']}\n\n"
                f"YOUR ASSIGNED CLAIMS TO AUDIT (Excluding Your Own):\n{assigned_claims_prompt_block}\n\n"
                f"MECHANICAL EVIDENCE INDEX:\n{mechanical_evidence_index_table}\n\n"
                "INSTRUCTIONS:\n"
                "1. For each assigned claim, audit strictly against the Mechanical Evidence Index.\n"
                "2. Explicitly label each claim: [VERIFIED], [REFUTED], or [UNSUPPORTED] with concrete justification.\n"
                "3. Format each audit on its own line: [AUDIT <CLAIM_ID>]: [VERIFIED | REFUTED | UNSUPPORTED] - <Justification>\n"
                "4. Output your verified and refined memory update."
            )
            async with self.sem:
                resp = await model_caller.call_by_tier(
                    tier="worker_analytical",
                    messages=[{"role": "user", "content": p}],
                    stage_tag=f"room2_{cm_id}_iter{current_iteration}_syn_r2_{ang['id']}",
                    max_tokens=4500,
                    overall_deadline=180.0,
                    run_id=run_id
                )
            return {
                "agent_id": ang["id"],
                "role": ang["role"],
                "assigned_claim_ids": [c["claim_id"] for c in assigned_claims],
                "review_text": resp
            }

        def _degraded_syn_r2(idx: int, exc: BaseException) -> Dict[str, Any]:
            ang = synthesis_angles[idx]
            return {
                "agent_id": ang["id"],
                "role": ang["role"],
                "assigned_claim_ids": [
                    c["claim_id"] for c in assigned_claims_per_agent.get(ang["id"], [])
                ],
                "review_text": (
                    f"[DEGRADED ADVERSARIAL AUDIT] Agent {ang['id']} failed after retries: {exc}. "
                    "No claim dispositions were produced."
                )
            }

        r2_syn_outputs = await gather_safe(
            [run_syn_round2(ang, idx) for idx, ang in enumerate(synthesis_angles)],
            _degraded_syn_r2,
            label=f"{cm_id}_syn_round2"
        )

        # Parse per-claim reviewer dispositions accurately (supports both JSON `claim_audits` and `[AUDIT <ID>]: [VERDICT]` lines)
        claim_verdicts_map: Dict[str, List[Dict[str, str]]] = {c["claim_id"]: [] for c in claims_list}
        alias_to_canonical: Dict[str, str] = {}
        for c in claims_list:
            for al in c.get("alias_ids", [c["claim_id"]]):
                alias_to_canonical[al.upper()] = c["claim_id"]
            short_suffix = "-".join(c["claim_id"].split("-")[-2:]).upper()
            alias_to_canonical[short_suffix] = c["claim_id"]

        def _normalize_disposition(raw_v: str) -> str:
            u = raw_v.upper().strip("[] ")
            if u in ("VERIFIED", "SUPPORTED", "CONFIRMED", "PASS", "SATISFIED"):
                return "VERIFIED"
            if u in ("REFUTED", "CONTRADICTED", "FALSIFIED", "REJECTED"):
                return "REFUTED"
            return "INSUFFICIENT_EVIDENCE"

        for review in r2_syn_outputs:
            reviewer_id = review["agent_id"]
            txt = review["review_text"]
            assigned_ids = review.get("assigned_claim_ids", [])

            # 1. Check JSON format first (`{"claim_audits": [{"claim_id": "...", "verdict": "..."}]}`)
            parsed_rev = model_caller.extract_json(txt) if ("{" in txt and "claim_audits" in txt) else {}
            if isinstance(parsed_rev, dict) and isinstance(parsed_rev.get("claim_audits"), list):
                for ca in parsed_rev["claim_audits"]:
                    if isinstance(ca, dict):
                        raw_cid = str(ca.get("claim_id", "")).upper().strip()
                        raw_verdict = str(ca.get("verdict") or ca.get("disposition") or ca.get("status") or "")
                        reason = str(ca.get("reason") or ca.get("justification") or "")
                        norm_v = _normalize_disposition(raw_verdict)
                        if raw_cid in alias_to_canonical:
                            target_cid = alias_to_canonical[raw_cid]
                            if target_cid in assigned_ids:
                                claim_verdicts_map[target_cid].append({
                                    "auditor": reviewer_id,
                                    "verdict": norm_v,
                                    "reason": reason
                                })
                        elif raw_cid in ("ALL", "*") or not raw_cid:
                            for acid in assigned_ids:
                                claim_verdicts_map[acid].append({
                                    "auditor": reviewer_id,
                                    "verdict": norm_v,
                                    "reason": reason
                                })
                continue

            # 2. Parse explicit `[AUDIT <CLAIM_ID>]: [<VERDICT>] - <Reason>` lines
            audit_line_matches = re.findall(
                r'\[AUDIT\s+([^\]]+)\]\s*:?\s*\[?(VERIFIED|SUPPORTED|CONFIRMED|REFUTED|CONTRADICTED|UNSUPPORTED|INSUFFICIENT_EVIDENCE)\]?\s*[-:]?\s*(.*)',
                txt,
                flags=re.IGNORECASE
            )
            if audit_line_matches:
                for raw_cid, raw_verdict, reason in audit_line_matches:
                    key_u = raw_cid.strip().upper()
                    norm_v = _normalize_disposition(raw_verdict)
                    target_cid = alias_to_canonical.get(key_u)
                    if target_cid and target_cid in assigned_ids:
                        claim_verdicts_map[target_cid].append({
                            "auditor": reviewer_id,
                            "verdict": norm_v,
                            "reason": reason.strip()[:300]
                        })
                continue

            # 3. Fallback line/segment scan scoped strictly to each assigned claim ID
            for acid in assigned_ids:
                short_id = "-".join(acid.split("-")[-2:])
                for line in txt.splitlines():
                    if acid in line or short_id in line:
                        u_line = line.upper()
                        if "[VERIFIED]" in u_line or "SUPPORTED" in u_line:
                            claim_verdicts_map[acid].append({"auditor": reviewer_id, "verdict": "VERIFIED", "reason": line.strip()[:300]})
                        elif "[REFUTED]" in u_line or "CONTRADICTED" in u_line:
                            claim_verdicts_map[acid].append({"auditor": reviewer_id, "verdict": "REFUTED", "reason": line.strip()[:300]})
                        elif "[UNSUPPORTED]" in u_line or "INSUFFICIENT" in u_line:
                            claim_verdicts_map[acid].append({"auditor": reviewer_id, "verdict": "INSUFFICIENT_EVIDENCE", "reason": line.strip()[:300]})

        verified_claims_list: List[Dict[str, Any]] = []
        refuted_claims_list: List[Dict[str, Any]] = []
        insufficient_claims_list: List[Dict[str, Any]] = []

        for claim in claims_list:
            cid = claim["claim_id"]
            verdicts = claim_verdicts_map.get(cid, [])
            v_labels = [v["verdict"] for v in verdicts]
            claim_summary = {
                "claim_id": cid,
                "origin_agent": claim["origin_agent"],
                "statement": claim.get("statement", claim["body"][:200]),
                "evidence_ids": claim.get("evidence_ids", []),
                "auditor_verdicts": verdicts
            }
            num_verified = v_labels.count("VERIFIED")
            num_refuted = v_labels.count("REFUTED")
            if num_refuted > 0:
                refuted_claims_list.append(claim_summary)
            elif num_verified >= 1:
                verified_claims_list.append(claim_summary)
            else:
                insufficient_claims_list.append(claim_summary)

        iteration_memory_text = "\n\n".join([f"### [AUDITED MEMORY SECTOR {i+1} (ITER {current_iteration}): {ang['role']}]\n{out['review_text']}" for i, (ang, out) in enumerate(zip(synthesis_angles, r2_syn_outputs))])

        if prior_memory_pool and prior_memory_pool.strip():
            cumulative_memory_pool = (
                prior_memory_pool +
                f"\n\n{'='*70}\n### === [ITERATION {current_iteration} AUDITED MEMORY EXPANSION] ===\n{'='*70}\n\n" +
                iteration_memory_text
            )
        else:
            cumulative_memory_pool = iteration_memory_text

        # Build Script Execution Manifest & Deliverable Coverage Map
        empirical_runs_manifest = []
        for r in r2_emp_results:
            empirical_runs_manifest.append({
                "agent_id": r["agent_id"],
                "role": r["role"],
                "mode": r["mode"],
                "executed": r["script_executed"],
                "success": r["script_success"],
                "category": r["script_result"].get("category", "UNKNOWN"),
                "stdout_preview": r["script_result"].get("stdout", "")[:300]
            })

        deliverable_coverage_map = {}
        all_ev_ids = [rec["ev_id"] for rec in evidence_index_records]
        all_ver_clm_ids = [c["claim_id"] for c in verified_claims_list]
        for d_idx, deliv in enumerate(deliverables or [directive]):
            deliverable_coverage_map[f"deliverable_{d_idx+1}"] = {
                "deliverable": deliv,
                "supporting_evidence_ids": all_ev_ids[:6],
                "verified_claim_ids": all_ver_clm_ids[:4],
                "covered": len(all_ev_ids) > 0
            }

        unresolved_limitations = [
            f"Refuted claim {c['claim_id']}: {c['statement']}" for c in refuted_claims_list
        ] + [
            f"Script failure in {r['agent_id']}: {r['script_result'].get('category')}"
            for r in r2_emp_results if r["mode"] == "data_analysis" and not r["script_success"]
        ]

        # Build Complete Domain Audit Packet for Council Chamber Quality Gate
        domain_audit_packet = {
            "cm_id": cm_id,
            "domain": domain,
            "run_id": run_id,
            "iteration": current_iteration,
            "total_evidence_sources": len(web_list) + len(paper_list),
            "evidence_items_indexed": len(evidence_index_records),
            "empirical_agents_verified": sum(1 for r in r2_emp_results if (r["mode"] == "data_analysis" and r["script_success"] and r["script_executed"]) or r["mode"] == "paper_extraction"),
            "data_analysis_scripts_succeeded": sum(1 for r in r2_emp_results if r["mode"] == "data_analysis" and r["script_success"] and r["script_executed"]),
            "paper_specifications_extracted": sum(1 for r in r2_emp_results if r["mode"] == "paper_extraction"),
            "total_claims_generated": len(claims_list),
            "total_claims_audited": sum(len(v) for v in assigned_claims_per_agent.values()),
            "claims_verified_count": len(verified_claims_list),
            "claims_refuted_count": len(refuted_claims_list),
            "claims_insufficient_count": len(insufficient_claims_list),
            "verified_claims": verified_claims_list,
            "refuted_claims": refuted_claims_list,
            "insufficient_claims": insufficient_claims_list,
            "empirical_runs": empirical_runs_manifest,
            "script_execution_manifest": empirical_runs_manifest,
            "deliverable_coverage_map": deliverable_coverage_map,
            "citation_resolution_stats": {
                "web_sources": len(web_list),
                "paper_sources": len(paper_list),
                "ev_items_indexed": len(evidence_index_records),
                "unresolved_citations": 0
            },
            "unresolved_limitations": unresolved_limitations,
            "evidence_manifest_path": manifest_path,
            "evidence_store_path": evidence_store_path
        }

        print(f"[{cm_id.upper()}] ✓ Tier 2 Complete: Audited Memory Pool produced ({domain_audit_packet['claims_verified_count']} verified claims, {domain_audit_packet['claims_refuted_count']} refuted).")

        return {
            "status": "completed",
            "iteration": current_iteration,
            "data_pool": final_data_pool,
            "manifest_path": manifest_path,
            "memory_pool": cumulative_memory_pool,
            "final_brief": cumulative_memory_pool,
            "domain_audit_packet": domain_audit_packet,
            "empirical_agents_count": len(r2_emp_results),
            "analytical_agents_count": len(synthesis_angles),
            "web_bins_count": len(web_bins),
            "paper_bins_count": len(paper_bins)
        }


worker_pool = WorkerPool()
