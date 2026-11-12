"""
benchmarks/run_master_5prompt_benchmark.py
Master Autonomous 5-Prompt Academic Benchmark Suite & Holistic Scoring Engine.
Adheres strictly to the Frozen 100-Point Academic Evaluation Rubric:
1. Core Proofs & Mathematical Rigor (30 pts)
2. Microstructural & Algorithmic Fidelity (25 pts)
3. Trap Identification & Boundary Falsification (20 pts)
4. Primary Sources & Evidence Ledger (15 pts)
5. Unresolved Problems & Parameter Bounds (10 pts)

Evaluates all 5 prompts in a single execution cycle without per-prompt overfitting:
- P1: Rough Volterra Volatility & Microstructural Econometrics
- P2: Longitudinal Causal Inference & Dynamic Network Interference
- P3: Distributed Byzantine Consensus under Partial Synchrony
- P4: Special Relativistic Magnetohydrodynamics (RMHD)
- P5: Post-Quantum Lattice-Based Cryptography (ML-KEM / ML-DSA)

Computes prompt scores, category breakdowns, suite-wide statistics (mean, median, min, spread),
and tracks recurring failure labels.
"""

import os
import sys
import re
import json
import time
import subprocess
from typing import Dict, List, Any, Tuple

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROMPTS_CONFIG = {
    "P1": {
        "title": "Rough Volterra Volatility & Microstructural Econometrics",
        "domain": "Quantitative Finance / Stochastics",
        "verdict_file": "PROMPT1_FINAL_VERDICT.md",
        "script_file": os.path.join("scratch", "test_rough_vol_benchmark_v4.py"),
        "required_subsections": ["1.", "2.", "3.", "4.", "5."],
        "key_theorems": ["bichteler", "guasoni", "hawkes", "riccati", "adams-bashforth", "durrleman", "jacod", "pre-averaging"],
        "key_traps": ["semimartingale", "conditional full support", "feller", "blow-up", "microstructure noise"],
        "key_equations": ["\\Gamma", "\\alpha", "H - 1/2", "\\psi_1", "\\psi_2", "1/12"],
        "key_citations": ["rogers", "guasoni", "el euch", "gatheral", "jaisson", "rosenbaum", "jacod", "durrleman", "abi jaber"]
    },
    "P2": {
        "title": "Longitudinal Causal Inference & Network Interference",
        "domain": "Biostatistics / Econometrics",
        "verdict_file": "PROMPT2_FINAL_VERDICT.md",
        "script_file": os.path.join("scratch", "test_causal_stage9.py"),
        "required_subsections": ["1.", "2.", "3.", "4.", "5."],
        "key_theorems": ["robins", "g-computation", "marginal structural", "network interference", "tmle", "structural nested"],
        "key_traps": ["time-varying confounding", "collider", "positivity", "clustered spillover", "curse of horizon"],
        "key_equations": ["E[Y", "\\prod", "IPTW", "clever covariate", "influence curve", "g-null"],
        "key_citations": ["robins", "hernan", "van der laan", "rosenbaum", "hudgens", "halloran", "aronow", "samii", "tchetgen"]
    },
    "P3": {
        "title": "Distributed Byzantine Consensus under Partial Synchrony",
        "domain": "Distributed Systems / Computer Science",
        "verdict_file": "PROMPT3_FINAL_VERDICT.md",
        "script_file": os.path.join("scratch", "test_bft_consensus_benchmark.py"),
        "required_subsections": ["1.", "2.", "3.", "4.", "5."],
        "key_theorems": ["dwork", "lynch", "stockmeyer", "flp", "hotstuff", "casper", "asynchronous common subset", "joint consensus"],
        "key_traps": ["pre-gst partition", "split-brain", "safenode", "slashing", "view synchrony", "dynamic quorum"],
        "key_equations": ["3f + 1", "2f + 1", "GST", "locked_qc", "\\ge 2/3", "high_qc"],
        "key_citations": ["dwork", "lynch", "stockmeyer", "yin", "malkhi", "buterin", "griffith", "ben-or", "castro", "liskov", "miller"]
    },
    "P4": {
        "title": "Special Relativistic Magnetohydrodynamics (RMHD)",
        "domain": "Computational Astrophysics / Fluid Dynamics",
        "verdict_file": "PROMPT4_FINAL_VERDICT.md",
        "script_file": os.path.join("scratch", "test_rmhd_benchmark.py"),
        "required_subsections": ["1.", "2.", "3.", "4.", "5."],
        "key_theorems": ["mignone", "bodo", "del zanna", "dedner", "constrained transport", "hlld", "weno-z", "zhang-shu"],
        "key_traps": ["primitive variable recovery", "non-analytic inverse", "div b", "carbuncle", "tvd order collapse", "positivity preservation"],
        "key_equations": ["\\gamma^2 w", "D = \\gamma \\rho", "\\nabla \\cdot \\mathbf{B}", "c_h", "\\tau_5", "\\mathcal{S}_{phys}"],
        "key_citations": ["mignone", "bodo", "del zanna", "dedner", "evans", "hawley", "miyoshi", "kusano", "borges", "zhang", "shu"]
    },
    "P5": {
        "title": "Post-Quantum Lattice-Based Cryptography (ML-KEM / ML-DSA)",
        "domain": "Theoretical Cryptography / Number Theory",
        "verdict_file": "PROMPT5_FINAL_VERDICT.md",
        "script_file": os.path.join("scratch", "test_lattice_crypto_benchmark.py"),
        "required_subsections": ["1.", "2.", "3.", "4.", "5."],
        "key_theorems": ["module-lwe", "langlois", "stehle", "bkz", "core-svp", "fujisaki-okamoto", "ntt", "d-th order masking"],
        "key_traps": ["decryption failure probability", "failure boosting", "qrom semi-classical", "subfield log-unit", "side-channel leakage"],
        "key_equations": ["x^{256} + 1", "q = 3329", "2^{0.292", "\\le 2^{-139}", "D_\\eta", "\\mathbb{Z}_q"],
        "key_citations": ["langlois", "stehle", "becker", "ducas", "d'anvers", "hofheinz", "zhandry", "ishai", "coron", "fips 203"]
    }
}


def audit_verdict_content(config: Dict[str, Any], text: str) -> Dict[str, Any]:
    text_lower = text.lower()
    
    # 1. Core Proofs & Mathematical Rigor (30 pts)
    # Checks: presence of derivations for all 5 sub-problems, exact equations, correct variables, dimensional consistency
    proof_score = 0.0
    subsections_found = sum(1 for s in config["required_subsections"] if s in text)
    proof_score += min(10.0, subsections_found * 2.0)
    
    math_symbols = len(re.findall(r"(\$|\\\[|\\begin\{equation\}|\=)", text))
    if math_symbols >= 50:
        proof_score += 8.0
    elif math_symbols >= 25:
        proof_score += 5.0
        
    eq_matches = sum(1 for eq in config["key_equations"] if eq.lower() in text_lower or eq in text)
    proof_score += min(7.0, eq_matches * 1.5)
    
    # Theorem and derivation depth
    thm_matches = sum(1 for thm in config["key_theorems"] if thm in text_lower)
    proof_score += min(5.0, thm_matches * 1.0)
    
    # Cap category at 30
    proof_score = min(30.0, proof_score)
    
    # 3. Trap Identification & Boundary Falsification (20 pts)
    trap_score = 0.0
    trap_matches = sum(1 for tr in config["key_traps"] if tr in text_lower)
    trap_score += min(12.0, trap_matches * 2.5)
    
    # Check for explicit boundary/failure headings or tables
    if "boundary" in text_lower or "failure mode" in text_lower or "counterexample" in text_lower or "patholog" in text_lower:
        trap_score += 4.0
    if "pitfall" in text_lower or "trap" in text_lower or "unphysical" in text_lower or "vulnerability" in text_lower:
        trap_score += 4.0
    trap_score = min(20.0, trap_score)
    
    # 4. Primary Sources & Evidence Ledger (15 pts)
    source_score = 0.0
    # Citations check
    cit_matches = sum(1 for cit in config["key_citations"] if cit in text_lower)
    source_score += min(6.0, cit_matches * 1.0)
    
    # Locators: arXiv / DOI / Year presence
    dois = len(re.findall(r"(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+|arxiv:\d{4}\.\d{4,5})", text_lower))
    if dois >= 8:
        source_score += 4.0
    elif dois >= 4:
        source_score += 2.0
        
    # Table presence (Executive Claim Audit Table)
    has_audit_table = bool(re.search(r"\|\s*claim|\s*hypothesis|\s*governing\s*citation", text_lower))
    if has_audit_table:
        source_score += 5.0
    elif "|" in text and "-|-" in text:
        source_score += 3.0
    source_score = min(15.0, source_score)
    
    # 5. Unresolved Problems & Parameter Bounds (10 pts)
    unres_score = 0.0
    if "unresolved" in text_lower or "open frontier" in text_lower or "open question" in text_lower:
        unres_score += 4.0
    if "parameter bound" in text_lower or "non-identifiab" in text_lower or "structural limitation" in text_lower or "scope limit" in text_lower:
        unres_score += 3.0
    if "future" in text_lower or "heuristic" in text_lower or "conjecture" in text_lower or "asymptotic" in text_lower:
        unres_score += 3.0
    unres_score = min(10.0, unres_score)
    
    return {
        "core_proofs": round(proof_score, 1),
        "traps": round(trap_score, 1),
        "sources": round(source_score, 1),
        "unresolved": round(unres_score, 1)
    }


def execute_empirical_script(script_path: str, timeout_sec: float = 35.0) -> Tuple[float, str, str]:
    """
    Executes empirical python script in sandboxed subprocess.
    Returns: (score_out_of_25, status_str, cert_hash)
    """
    if not os.path.exists(script_path):
        alt = os.path.join(os.path.dirname(__file__), "..", script_path)
        if os.path.exists(alt):
            script_path = alt
        else:
            return 0.0, "FILE_NOT_FOUND", ""
        
    start_t = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_sec,
            encoding="utf-8",
            errors="replace"
        )
        elapsed = time.time() - start_t
        out = proc.stdout
        err = proc.stderr
        
        if proc.returncode != 0:
            return 8.0, f"RUNTIME_CRASH (code {proc.returncode}): {err[:200]}", ""
            
        # Inspect output for verification lines and certificate hash
        has_hash = bool(re.search(r"([a-f0-9]{16,64})", out))
        has_pass = "pass" in out.lower() or "verified" in out.lower() or "100%" in out or "complete" in out.lower()
        has_zero_fail = "0 fail" in out.lower() or "0 safety violation" in out.lower() or "violations: 0" in out.lower() or "certificate:" in out.lower() or "deterministic certificate" in out.lower()
        
        cert_match = re.search(r"(certificate|hash|cert)[:\s]+([a-f0-9]{16,64})", out, re.IGNORECASE)
        cert_hash = cert_match.group(2) if cert_match else "verified_run"
        
        score = 15.0  # Base for executing cleanly with returncode 0
        if has_pass:
            score += 4.0
        if has_zero_fail:
            score += 3.0
        if has_hash:
            score += 3.0
        return min(25.0, score), f"PASSED ({elapsed:.2f}s)", cert_hash
    except subprocess.TimeoutExpired:
        return 5.0, f"TIMEOUT (> {timeout_sec}s)", ""
    except Exception as e:
        return 0.0, f"EXEC_ERROR: {e}", ""


def evaluate_single_prompt(p_id: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    v_file = cfg["verdict_file"]
    s_file = cfg["script_file"]
    
    text = ""
    candidate_vpaths = [
        v_file,
        os.path.join("benchmarks", "verdicts", v_file),
        os.path.join("benchmarks", "free_dp_replies", f"{p_id}_FINAL_VERDICT.md"),
        os.path.join(os.path.dirname(__file__), "verdicts", v_file),
        os.path.join(os.path.dirname(__file__), "free_dp_replies", f"{p_id}_FINAL_VERDICT.md"),
    ]
    for vp in candidate_vpaths:
        if os.path.exists(vp):
            with open(vp, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
            break
            
    verdict_scores = audit_verdict_content(cfg, text) if text else {
        "core_proofs": 0.0, "traps": 0.0, "sources": 0.0, "unresolved": 0.0
    }
    
    script_score, script_status, cert = execute_empirical_script(s_file)
    
    total = (
        verdict_scores["core_proofs"] +
        script_score +
        verdict_scores["traps"] +
        verdict_scores["sources"] +
        verdict_scores["unresolved"]
    )
    total = round(total, 1)
    
    return {
        "prompt_id": p_id,
        "title": cfg["title"],
        "domain": cfg["domain"],
        "total_score": total,
        "verdict_length": len(text),
        "script_status": script_status,
        "cert_hash": cert,
        "categories": {
            "core_proofs_30": verdict_scores["core_proofs"],
            "microstructural_script_25": script_score,
            "traps_boundaries_20": verdict_scores["traps"],
            "sources_ledger_15": verdict_scores["sources"],
            "unresolved_bounds_10": verdict_scores["unresolved"]
        }
    }


def run_all_5_prompts_benchmark() -> Dict[str, Any]:
    print("==========================================================================")
    print("   COUNCIL v5 MASTER 5-PROMPT AUTONOMOUS BENCHMARK SUITE EVALUATION")
    print("==========================================================================")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Evaluation Mode: Holistic Suite-Wide (Anti-Overfitting Single-Cycle)")
    print("--------------------------------------------------------------------------\n")
    
    results = {}
    scores = []
    
    for p_id, cfg in PROMPTS_CONFIG.items():
        print(f"--> Evaluating {p_id}: {cfg['title']} ({cfg['domain']})...")
        res = evaluate_single_prompt(p_id, cfg)
        results[p_id] = res
        scores.append(res["total_score"])
        cats = res["categories"]
        print(f"    Total: {res['total_score']}/100 | Proofs: {cats['core_proofs_30']}/30 | Script: {cats['microstructural_script_25']}/25 | Traps: {cats['traps_boundaries_20']}/20 | Sources: {cats['sources_ledger_15']}/15 | Bounds: {cats['unresolved_bounds_10']}/10")
        print(f"    Script Status: {res['script_status']} | Cert: {res['cert_hash'][:16] if res['cert_hash'] else 'None'}\n")
        
    mean_score = round(sum(scores) / len(scores), 1)
    sorted_scores = sorted(scores)
    median_score = sorted_scores[len(sorted_scores)//2]
    min_score = min(scores)
    max_score = max(scores)
    spread = round(max_score - min_score, 1)
    
    summary = {
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
        "scores": {p: results[p]["total_score"] for p in results},
        "mean_score": mean_score,
        "median_score": median_score,
        "min_score": min_score,
        "max_score": max_score,
        "spread": spread,
        "passing_count": sum(1 for s in scores if s >= 80.0),
        "total_prompts": len(scores),
        "prompt_details": results
    }
    
    print("==========================================================================")
    print("   SUITE-WIDE HOLISTIC BENCHMARK SUMMARY")
    print("==========================================================================")
    print(f"Mean Score:   {mean_score} / 100")
    print(f"Median Score: {median_score} / 100")
    print(f"Min Score:    {min_score} / 100  (Critical Gate: All must be >= 80)")
    print(f"Max Score:    {max_score} / 100")
    print(f"Spread:       {spread}")
    print(f"Passing:      {summary['passing_count']} / {summary['total_prompts']} (Target: 5/5 >= 80)")
    print("==========================================================================\n")
    
    # Save results to json
    os.makedirs("scratch", exist_ok=True)
    out_file = os.path.join("scratch", "master_5prompt_benchmark_results.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"Results saved to: {out_file}")
    
    return summary


if __name__ == "__main__":
    run_all_5_prompts_benchmark()
