"""
benchmarks/run_council_prompts_6_7_8_9.py
Autonomous Council Deliberation and Scoring Suite for Prompts 6, 7, 8, and 9.
Executes run_council.py independently for each prompt, captures exact model telemetry,
extracts and verifies generated empirical code, scores the council output against
the 100-point rubric, and compiles a comprehensive performance ledger.
"""

import os
import sys
import re
import json
import time
import shutil
import subprocess
from datetime import datetime
from typing import Dict, Any, List

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

PROMPTS_CONFIG = {
    "P6": {
        "title": "Hypersonic Aerothermodynamics & Finite-Rate Plasma Kinetics",
        "domain": "Aerospace / Hypersonic Aerothermodynamics",
        "required_subsections": ["1.", "2.", "3.", "4.", "5."],
        "key_theorems": ["park", "landau-teller", "millikan-white", "rankine-hugoniot", "goulard", "zeldovich"],
        "key_traps": ["frozen shock jump", "ionization", "equilibrium specific heat", "catalytic wall", "non-equilibrium"],
        "key_equations": ["t_a", "q_{v-t}", "y_s", "\\dot{\\omega}", "m_\\infty", "k_c"],
        "key_citations": ["park", "millikan", "white", "goulard", "landau", "teller"]
    },
    "P7": {
        "title": "Sub-2nm Gate-All-Around (GAA) Nanosheet FET Quantum Transport (NEGF)",
        "domain": "Nanoelectronics / Semiconductor Device Physics",
        "required_subsections": ["1.", "2.", "3.", "4.", "5."],
        "key_theorems": ["negf", "green's function", "landauer", "buttiker", "sancho", "effective mass", "poisson"],
        "key_traps": ["sub-2nm", "gate length", "source-to-drain tunneling", "ballistic", "self-energy", "quantum confinement"],
        "key_equations": ["g^r", "\\sigma_s", "\\sigma_d", "\\gamma_s", "t(e)", "i_{ds}"],
        "key_citations": ["datta", "landauer", "buttiker", "sancho", "caroli"]
    },
    "P8": {
        "title": "Riemannian Score-Based Diffusion Models & Submanifold Geometry",
        "domain": "Machine Learning Theory / Stochastic Differential Equations",
        "required_subsections": ["1.", "2.", "3.", "4.", "5."],
        "key_theorems": ["manifold hypothesis", "ambient score", "riemannian", "laplace-beltrami", "anderson", "tweedie", "varadhan"],
        "key_traps": ["singularity", "normal component", "tangent component", "lebesgue", "degenerate covariance", "moore-penrose"],
        "key_equations": ["1/\\sigma_t^2", "\\nabla_x \\log p_t", "d_m", "w_2", "\\delta_m"],
        "key_citations": ["song", "de bortoli", "lu", "varadhan", "sohl-dickstein"]
    },
    "P9": {
        "title": "Cryo-EM 3D Single-Particle Reconstruction & Continuous Heterogeneity",
        "domain": "Biophysics / Inverse Problems",
        "required_subsections": ["1.", "2.", "3.", "4.", "5."],
        "key_theorems": ["fourier shell correlation", "fsc", "fourier slice", "rosenthal-henderson", "spectral snr", "cryodrgn", "3dflex"],
        "key_traps": ["einstein from noise", "masking artifact", "0.143", "phase randomization", "b-factor", "gauge ambiguity"],
        "key_equations": ["0.143", "ssnr", "ctf", "so(3)", "\\sum"],
        "key_citations": ["rosenthal", "henderson", "frank", "scheres", "chen", "zhong"]
    }
}

PROMPTS_TO_RUN = [
    {
        "id": "P6",
        "name": "Prompt 6: Hypersonic Aerothermodynamics & Finite-Rate Plasma Kinetics",
        "file": os.path.join("scratch", "prompt_6_hypersonic_aerothermo.txt"),
        "config_key": "P6"
    },
    {
        "id": "P7",
        "name": "Prompt 7: Sub-2nm GAA Nanosheet FET Quantum Transport (NEGF)",
        "file": os.path.join("scratch", "prompt_7_sub2nm_gaa_negf.txt"),
        "config_key": "P7"
    },
    {
        "id": "P8",
        "name": "Prompt 8: Riemannian Score-Based Diffusion Models & Submanifold Geometry",
        "file": os.path.join("scratch", "prompt_8_riemannian_score_diffusion.txt"),
        "config_key": "P8"
    },
    {
        "id": "P9",
        "name": "Prompt 9: Cryo-EM 3D Single-Particle Reconstruction & Continuous Heterogeneity",
        "file": os.path.join("scratch", "prompt_9_cryoem_heterogeneity_fsc.txt"),
        "config_key": "P9"
    }
]


def select_best_python_block(text: str) -> str:
    """
    Selects the strongest executable Python block by contract evidence, not raw length.

    Long dossiers often contain early Room 2 scratch templates plus a shorter, verified Phase 8
    simulator. Length alone picked the unverified template, so score on executable contracts:
    __main__ guard, assertions, PASS/violations markers, and penalty for leaked Gold templates.
    """
    blocks = re.findall(r"```(?:python|py|python3)\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if not blocks:
        return ""

    def score(block: str) -> float:
        s = 0.0
        if re.search(r"if\s+__name__\s*==\s*['\"]__main__['\"]", block):
            s += 50.0
        s += min(20.0, 4.0 * len(re.findall(r"\bassert\b", block)))
        if re.search(r"\b(PASSED|PASS|violations:\s*0)\b", block):
            s += 15.0
        if re.search(r"data[/\\]xauusd", block, re.IGNORECASE):
            s -= 10.0
        s += min(10.0, len(block) / 2000.0)
        return s

    return max(blocks, key=score).strip()


def extract_latest_python_block(text: str) -> str:
    return select_best_python_block(text)


def audit_verdict_content(config: Dict[str, Any], text: str) -> Dict[str, Any]:
    text_lower = text.lower()
    
    # 1. Core Proofs & Mathematical Rigor (30 pts)
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
    
    thm_matches = sum(1 for thm in config["key_theorems"] if thm in text_lower)
    proof_score += min(5.0, thm_matches * 1.0)
    proof_score = min(30.0, proof_score)
    
    # 2. Traps & Physical Boundary Regimes (20 pts)
    trap_score = 0.0
    trap_hits = sum(1 for trap in config["key_traps"] if trap in text_lower)
    trap_score += min(15.0, trap_hits * 3.0)
    if "boundary" in text_lower or "falsif" in text_lower or "regime" in text_lower:
        trap_score += 5.0
    trap_score = min(20.0, trap_score)
    
    # 3. Primary Academic Literature Traceability (15 pts)
    source_score = 0.0
    cite_hits = sum(1 for cite in config["key_citations"] if cite in text_lower)
    source_score += min(10.0, cite_hits * 2.0)
    if "doi" in text_lower or "arxiv" in text_lower or "http" in text_lower:
        source_score += 5.0
    source_score = min(15.0, source_score)
    
    # 4. Open Problems & Frontiers (10 pts)
    frontier_score = 0.0
    if "unresolved" in text_lower or "open problem" in text_lower or "frontier" in text_lower:
        frontier_score += 6.0
    if "non-identifiab" in text_lower or "degeneracy" in text_lower or "bottleneck" in text_lower:
        frontier_score += 4.0
    frontier_score = min(10.0, frontier_score)
    
    return {
        "core_proofs_30": round(proof_score, 1),
        "traps_boundaries_20": round(trap_score, 1),
        "sources_ledger_15": round(source_score, 1),
        "unresolved_bounds_10": round(frontier_score, 1)
    }


def execute_empirical_script(script_code: str, timeout: float = 20.0) -> Dict[str, Any]:
    if not script_code.strip():
        return {"success": False, "score": 0.0, "status": "MISSING_SCRIPT", "duration": 0.0}
    
    tmp_path = os.path.join("scratch", "temp_benchmark_runner.py")
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(script_code)
        
    start_t = time.perf_counter()
    try:
        proc = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        duration = time.perf_counter() - start_t
        stdout = proc.stdout
        stderr = proc.stderr
        
        has_pass_stdout = any(k in stdout for k in ["PASSED", "PASS", "violations: 0", "True", "Finalized: True"])
        has_assertions = "assert " in script_code or "assert_" in script_code
        has_imports = any(lib in script_code for lib in ["numpy", "scipy", "math", "dataclass"])
        
        if proc.returncode == 0:
            score = 15.0
            if has_pass_stdout:
                score += 5.0
            if has_assertions and has_imports:
                score += 5.0
            return {
                "success": True,
                "score": min(25.0, score),
                "status": f"PASSED ({duration:.2f}s)",
                "duration": duration,
                "stdout": stdout[:400]
            }
        else:
            return {
                "success": False,
                "score": 5.0 if has_imports else 0.0,
                "status": f"FAILED (Exit {proc.returncode}): {stderr[-300:]}",
                "duration": duration,
                "stderr": stderr[-300:]
            }
    except subprocess.TimeoutExpired:
        return {"success": False, "score": 2.0, "status": "TIMEOUT", "duration": timeout}
    except Exception as e:
        return {"success": False, "score": 0.0, "status": f"ERROR: {str(e)}", "duration": 0.0}


def run_single_prompt_council(p_info: Dict[str, Any]) -> Dict[str, Any]:
    p_id = p_info["id"]
    p_name = p_info["name"]
    p_file = p_info["file"]
    cfg_key = p_info["config_key"]
    cfg = PROMPTS_CONFIG[cfg_key]

    print("\n" + "=" * 80)
    print(f"🚀 LAUNCHING AUTONOMOUS COUNCIL EXECUTION: {p_name}")
    print(f"   Prompt Source: {p_file}")
    print(f"   Target Rubric Key: {cfg_key}")
    print("=" * 80)

    # 1. Clean previous run artifacts so a crashed run cannot be scored against an old dossier.
    for f in [
        "final_dossier.md",
        "FINAL_VERDICT.md",
        "final_council_verdict.md",
        "telemetry_latest.json",
        "council_telemetry.json"
    ]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except Exception:
                pass

    p_target = p_file if (os.path.isabs(p_file) or os.path.exists(p_file)) else os.path.join(REPO_ROOT, p_file)

    # 2. Launch run_council.py
    cmd = [
        sys.executable,
        os.path.join(REPO_ROOT, "run_council.py"),
        "--prompt-file", p_target
    ]
    print(f"• Executing command: {' '.join(cmd)}")
    start_time = time.time()
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=False)
    wall_time = time.time() - start_time
    print(f"• Council process finished with returncode {proc.returncode} in {wall_time:.2f}s ({int(wall_time//60)}m {int(wall_time%60)}s)")

    # 3. Read only a dossier produced by this run (fail closed on stale artifacts).
    verdict_text = ""
    verdict_fresh = False
    for v_candidate in ["final_dossier.md", "FINAL_VERDICT.md", "final_council_verdict.md"]:
        if not os.path.exists(v_candidate):
            continue
        try:
            if os.path.getmtime(v_candidate) < start_time - 1.0:
                print(f"⚠️ Ignoring stale artifact: {v_candidate} predates this run.")
                continue
        except OSError:
            continue
        with open(v_candidate, "r", encoding="utf-8", errors="replace") as f:
            candidate_text = f.read()
        if len(candidate_text) > 500:
            verdict_text = candidate_text
            verdict_fresh = True
            break

    failed_closed = proc.returncode != 0 or not verdict_fresh
    if failed_closed:
        if proc.returncode != 0:
            print(f"❌ run_council.py exited with code {proc.returncode}; scoring prompt {p_id} as 0 (fail-closed).")
        else:
            print(f"❌ No fresh dossier (mtime >= run start) produced for {p_id}; scoring 0 (fail-closed).")
        verdict_text = ""

    # 4. Extract telemetry
    telemetry = {}
    for t_candidate in ["telemetry_latest.json", "council_telemetry.json"]:
        if os.path.exists(t_candidate):
            try:
                with open(t_candidate, "r", encoding="utf-8") as tf:
                    telemetry = json.load(tf)
                    if telemetry:
                        break
            except Exception:
                pass

    # 5. Extract and test script
    script_code = extract_latest_python_block(verdict_text)
    script_res = execute_empirical_script(script_code)
    
    # Save isolated prompt script
    dest_script = os.path.join("scratch", f"council_{p_id}_generated_script.py")
    if script_code:
        with open(dest_script, "w", encoding="utf-8") as sf:
            sf.write(script_code)

    # Save isolated prompt verdict
    dest_verdict = os.path.join("scratch", f"council_{p_id}_verdict.md")
    if verdict_text:
        with open(dest_verdict, "w", encoding="utf-8") as vf:
            vf.write(verdict_text)

    # 6. Audit content
    content_scores = audit_verdict_content(cfg, verdict_text)

    # 7. Total score (forced to zero when the run failed or produced no fresh dossier)
    total_score = (
        content_scores["core_proofs_30"] +
        script_res["score"] +
        content_scores["traps_boundaries_20"] +
        content_scores["sources_ledger_15"] +
        content_scores["unresolved_bounds_10"]
    )
    if failed_closed:
        total_score = 0.0

    print("\n------------------------------------------------------------")
    print(f"📊 COUNCIL VERDICT SCORECARD FOR {p_id}: {total_score:.1f} / 100")
    print(f"   • Core Proofs:   {content_scores['core_proofs_30']} / 30")
    print(f"   • Script Exec:   {script_res['score']} / 25 ({script_res['status']})")
    print(f"   • Traps & Bounds:{content_scores['traps_boundaries_20']} / 20")
    print(f"   • Sources Ledger:{content_scores['sources_ledger_15']} / 15")
    print(f"   • Open Problems: {content_scores['unresolved_bounds_10']} / 10")
    print(f"   • Model Calls:   {telemetry.get('total_model_calls', 0)} calls ({telemetry.get('actual_tokens', 0):,} tokens)")
    print(f"   • Providers:     {telemetry.get('provider_breakdown', {})}")
    print(f"   • Models:        {telemetry.get('model_breakdown', {})}")
    print(f"   • Tavily:        {telemetry.get('tavily_searches', 0)} searches (Blocked: {telemetry.get('tavily_blocked', 0)})")
    print("------------------------------------------------------------\n")

    return {
        "prompt_id": p_id,
        "name": p_name,
        "status": "FAILED" if failed_closed else "COMPLETED",
        "fail_closed": failed_closed,
        "fresh_dossier": verdict_fresh,
        "wall_time_seconds": round(wall_time, 2),
        "wall_time_formatted": f"{int(wall_time//60)}m {int(wall_time%60)}s",
        "scores": {
            "total_score": round(total_score, 1),
            **content_scores,
            "microstructural_script_25": script_res["score"]
        },
        "script_status": script_res["status"],
        "cert_hash": "verified_run" if script_res["success"] else "unverified",
        "script_tested": dest_script,
        "telemetry": telemetry
    }


def main():
    target_prompts = PROMPTS_TO_RUN
    if len(sys.argv) > 1:
        chosen_ids = [arg.upper() for arg in sys.argv[1:]]
        target_prompts = [p for p in PROMPTS_TO_RUN if p["id"] in chosen_ids]

    print("==========================================================================")
    print("   COUNCIL v5 AUTONOMOUS BENCHMARK EVALUATOR FOR P6, P7, P8, P9")
    print(f"   Target Prompts: {[p['id'] for p in target_prompts]}")
    print(f"   Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("==========================================================================")

    suite_results = []
    summary_path = os.path.join("scratch", "council_p6_p7_p8_p9_summary.json")
    for p_info in target_prompts:
        try:
            res = run_single_prompt_council(p_info)
            suite_results.append(res)
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(suite_results, f, indent=2)
        except Exception as e:
            print(f"❌ Failed to run {p_info['id']}: {e}")
            import traceback
            traceback.print_exc()

    print("\n==========================================================================")
    print("                       ALL COUNCIL RUNS COMPLETED                          ")
    print("==========================================================================")
    for res in suite_results:
        print(f"• {res['prompt_id']}: Score {res.get('scores', {}).get('total_score', 'N/A')} / 100 | Time: {res.get('wall_time_formatted', 'N/A')} | Calls: {res.get('telemetry', {}).get('total_model_calls', 0)}")
    print("==========================================================================\n")


if __name__ == "__main__":
    main()

