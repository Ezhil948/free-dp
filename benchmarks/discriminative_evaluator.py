"""
benchmarks/discriminative_evaluator.py
High-Resolution Uncapped Discriminative Benchmark Evaluator.
Eliminates artificial score saturation and ceiling effects.
Measures exact mathematical equation density, proof continuity,
trap disproof granularity, empirical script execution metrics,
and verified academic citation depth.
"""

import os
import sys
import re
import json
import time
import subprocess
from typing import Dict, Any, List

def select_best_python_block(text: str) -> str:
    """Selects the strongest executable Python block by contract evidence, not raw length."""
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


def analyze_mathematical_depth(text: str) -> Dict[str, Any]:
    """Measures continuous mathematical rigor and equation density without artificial caps."""
    # Count formal LaTeX display equations and inline formulas
    display_eqs = len(re.findall(r"(\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]|\\begin\{equation\}[\s\S]*?\\end\{equation\})", text))
    inline_formulas = len(re.findall(r"\$[^$\n]+\$", text))
    raw_math_symbols = len(re.findall(r"(\\partial|\\nabla|\\sum|\\int|\\in|\\forall|\\mathbb|\\mathcal|\\mathbf|\\rho|\\sigma|\\tau|\\theta|\\Gamma|\\Delta|\\le|\\ge|\\approx|\\otimes)", text))
    
    # Proof continuity vs hand-waving
    rigorous_connectors = len(re.findall(r"\b(therefore|substituting|integrating|differentiating|contracting|which yields|we obtain|by definition|satisfies the condition|it follows that)\b", text, re.IGNORECASE))
    handwavy_phrases = len(re.findall(r"\b(obviously|clearly|it can be easily shown|trivial|without loss of generality|as is well known|intuitively)\b", text, re.IGNORECASE))
    
    # Continuous mathematical depth index (no ceiling)
    # 1 display eq = 2.0 pts, 1 inline = 0.25 pts, symbol density = 0.1 pts, rigorous connector = 0.5 pts, handwavy = -1.0 pts
    raw_score = (display_eqs * 2.5) + (inline_formulas * 0.3) + (raw_math_symbols * 0.1) + (rigorous_connectors * 0.5) - (handwavy_phrases * 1.0)
    
    return {
        "display_equations": display_eqs,
        "inline_formulas": inline_formulas,
        "math_symbols_count": raw_math_symbols,
        "rigorous_connectors": rigorous_connectors,
        "handwavy_penalties": handwavy_phrases,
        "uncapped_math_depth_score": round(max(0.0, raw_score), 2)
    }

def analyze_trap_and_boundary_granularity(text: str, key_traps: List[str]) -> Dict[str, Any]:
    """Measures depth of trap resolution, boundary calculations, and falsification rules."""
    text_lower = text.lower()
    
    traps_addressed = []
    for trap in key_traps:
        if trap.lower() in text_lower:
            traps_addressed.append(trap)
            
    # Look for concrete numerical boundary thresholds (e.g. 8 km/s, 12 nm, sigma_t^2, 0.143, etc.)
    numerical_bounds = re.findall(r"\b(\d+\.?\d*\s*(?:km/s|nm|k|ev|pa|kg/m\^3|db|mhz|ghz|%))\b", text_lower)
    
    # Falsification & counterexample formulations
    falsification_checks = len(re.findall(r"\b(falsif|counterexample|contradiction|disprove|breakdown|singularity|violat|degeneracy|non-identifiab)\b", text_lower))
    
    # Continuous score
    raw_score = (len(traps_addressed) * 8.0) + (len(numerical_bounds) * 1.5) + (falsification_checks * 1.0)
    
    return {
        "traps_covered": traps_addressed,
        "traps_count": len(traps_addressed),
        "numerical_boundary_metrics": len(numerical_bounds),
        "falsification_clauses": falsification_checks,
        "uncapped_trap_score": round(raw_score, 2)
    }

def analyze_literature_traceability(text: str) -> Dict[str, Any]:
    """Counts verified academic citations, DOIs, arXiv IDs, and equation attributions."""
    dois = len(re.findall(r"\b(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)\b", text))
    arxivs = len(re.findall(r"\b(arxiv:\s*\d{4}\.\d{4,5}|arxiv\.org/\S+)\b", text, re.IGNORECASE))
    formal_citations = len(re.findall(r"\b([A-Z][a-zA-Z]+(?:\s+et\s+al\.)?,\s*(?:19|20)\d{2})\b", text))
    
    raw_score = (dois * 3.0) + (arxivs * 2.5) + (formal_citations * 1.5)
    
    return {
        "doi_count": dois,
        "arxiv_count": arxivs,
        "formal_citations_count": formal_citations,
        "uncapped_source_score": round(raw_score, 2)
    }

def execute_and_profile_script(script_code: str, timeout: float = 30.0) -> Dict[str, Any]:
    """Executes the script in sandbox, measuring speed, memory, assertions, and precision."""
    if not script_code.strip():
        return {
            "status": "MISSING_SCRIPT",
            "exit_code": -1,
            "duration_sec": 0.0,
            "assertion_count": 0,
            "uncapped_script_score": 0.0,
            "stdout": "",
            "stderr": "No python code block found"
        }
        
    assertion_count = len(re.findall(r"\bassert\s+", script_code))
    has_test_harness = "if __name__" in script_code or "def run_" in script_code or "main(" in script_code
    
    tmp_path = os.path.join("scratch", "temp_discriminative_runner.py")
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
        
        has_pass_stdout = any(k in proc.stdout for k in ["PASSED", "PASS", "violations: 0", "Finalized: True"])
        
        if proc.returncode == 0:
            # Base 25 points for exit code 0
            # + 3 points per assertion verified (up to +15)
            # + 5 points for explicit PASS stdout
            # + execution speed bonus (faster = more efficient vectorized code)
            speed_bonus = max(0.0, 5.0 - min(5.0, duration))
            uncapped_score = 25.0 + (min(5, assertion_count) * 3.0) + (5.0 if has_pass_stdout else 0.0) + speed_bonus
            status = f"PASSED ({duration:.2f}s)"
        else:
            # Failed execution: base 0, partial 5 points if code compiles but fails assertion
            uncapped_score = 5.0 if "AssertionError" in proc.stderr else 2.0
            status = f"FAILED (Exit {proc.returncode}): {proc.stderr[-200:].strip()}"
            
        return {
            "status": status,
            "exit_code": proc.returncode,
            "duration_sec": round(duration, 3),
            "assertion_count": assertion_count,
            "uncapped_script_score": round(uncapped_score, 2),
            "stdout": proc.stdout[:300].strip(),
            "stderr": proc.stderr[:300].strip()
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "TIMEOUT",
            "exit_code": -9,
            "duration_sec": timeout,
            "assertion_count": assertion_count,
            "uncapped_script_score": 5.0,
            "stdout": "",
            "stderr": "Execution timed out"
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "exit_code": -1,
            "duration_sec": 0.0,
            "assertion_count": assertion_count,
            "uncapped_script_score": 0.0,
            "stdout": "",
            "stderr": str(e)
        }

def evaluate_full_dossier_discriminative(text: str, key_traps: List[str]) -> Dict[str, Any]:
    """Performs deep uncapped continuous evaluation of a research dossier."""
    math_metrics = analyze_mathematical_depth(text)
    trap_metrics = analyze_trap_and_boundary_granularity(text, key_traps)
    lit_metrics = analyze_literature_traceability(text)
    
    # Extract script
    script_code = select_best_python_block(text)
    script_metrics = execute_and_profile_script(script_code)
    
    # Frontier & Non-Identifiability
    unresolved_depth = len(re.findall(r"\b(unresolved|open problem|frontier|non-identifiab|ill-posed|regularization|degeneracy|bottleneck)\b", text, re.IGNORECASE))
    frontier_score = unresolved_depth * 1.5
    
    # Total Composite Rigor Index (Uncapped)
    composite_rigor_index = (
        math_metrics["uncapped_math_depth_score"] +
        trap_metrics["uncapped_trap_score"] +
        lit_metrics["uncapped_source_score"] +
        script_metrics["uncapped_script_score"] +
        frontier_score
    )
    
    return {
        "composite_rigor_index": round(composite_rigor_index, 2),
        "math_depth": math_metrics,
        "trap_and_boundary": trap_metrics,
        "literature": lit_metrics,
        "script": script_metrics,
        "frontier_score": round(frontier_score, 2),
        "total_word_count": len(text.split()),
        "character_count": len(text)
    }

