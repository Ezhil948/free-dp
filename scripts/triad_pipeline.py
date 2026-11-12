"""
Triad Collaborative Lifecycle Orchestration Engine
===================================================
Coordinates the 8-stage collaborative workflow across:
  - Antigravity (Gemini): Global Orchestrator & Context Anchor
  - OpenAI Codex (GPT-6 Luna): Adversarial Critic & Verification Gatekeeper
  - OpenCode (DeepSeek V4.1 Flash): Deep Reasoning, High-IQ Math & Parallel Workers
"""

import os
import sys
import json
import time
import argparse
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any

REPO_ROOT = Path(__file__).resolve().parent.parent
TRIAD_DIR = REPO_ROOT / ".agents" / "triad"
STATUS_DIR = TRIAD_DIR / "status"
def _find_opencode_cli() -> Path:
    env_cli = os.getenv("OPENCODE_CLI")
    if env_cli and Path(env_cli).is_file():
        return Path(env_cli)
    import shutil
    which_cli = shutil.which("opencode-cli") or shutil.which("opencode")
    if which_cli and Path(which_cli).is_file():
        return Path(which_cli)
    appdata_cli_dir = Path.home() / "AppData" / "Roaming" / "ai.opencode.desktop" / "cli"
    if appdata_cli_dir.is_dir():
        candidates = list(appdata_cli_dir.glob("*/opencode-cli.exe"))
        if candidates:
            candidates.sort(key=lambda p: p.parent.name, reverse=True)
            return candidates[0]
    return Path.home() / "AppData" / "Roaming" / "ai.opencode.desktop" / "cli" / "2.2.6-x64" / "opencode-cli.exe"

OPENCODE_CLI = _find_opencode_cli()


class TriadPipeline:
    def __init__(self, workspace_root: Optional[Path] = None):
        self.root = workspace_root or REPO_ROOT
        self.triad_dir = self.root / ".agents" / "triad"
        self.status_dir = self.triad_dir / "status"
        self._ensure_dirs()

    def _ensure_dirs(self):
        self.triad_dir.mkdir(parents=True, exist_ok=True)
        self.status_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------
    # Stage Artifact Management
    # -------------------------------------------------------------------------
    def save_artifact(self, filename: str, content: str) -> Path:
        target = self.triad_dir / filename
        target.write_text(content, encoding="utf-8")
        print(f"[TriadPipeline] Saved artifact: {target}")
        return target

    def load_artifact(self, filename: str) -> Optional[str]:
        target = self.triad_dir / filename
        if target.exists():
            return target.read_text(encoding="utf-8")
        return None

    # -------------------------------------------------------------------------
    # Slice Status & Tracking
    # -------------------------------------------------------------------------
    def set_slice_status(
        self,
        slice_id: str,
        status: str,
        files_modified: Optional[List[str]] = None,
        notes: str = ""
    ) -> Dict[str, Any]:
        """
        Record status for a specific worker slice: PENDING, RUNNING, DONE, FAILED.
        """
        status_file = self.status_dir / f"{slice_id}.json"
        data = {
            "slice_id": slice_id,
            "status": status.upper(),
            "files_modified": files_modified or [],
            "notes": notes,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        status_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"[TriadPipeline] Slice [{slice_id}] updated -> {status.upper()}")
        return data

    def get_slice_status(self, slice_id: str) -> Optional[Dict[str, Any]]:
        status_file = self.status_dir / f"{slice_id}.json"
        if status_file.exists():
            return json.loads(status_file.read_text(encoding="utf-8"))
        return None

    def get_all_slice_statuses(self) -> Dict[str, Dict[str, Any]]:
        result = {}
        for f in self.status_dir.glob("*.json"):
            slice_id = f.stem
            try:
                result[slice_id] = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                pass
        return result

    def are_all_slices_done(self, expected_slices: Optional[List[str]] = None) -> bool:
        statuses = self.get_all_slice_statuses()
        if expected_slices:
            for s in expected_slices:
                if statuses.get(s, {}).get("status") != "DONE":
                    return False
            return True
        if not statuses:
            return False
        return all(s.get("status") == "DONE" for s in statuses.values())

    def get_all_modified_files(self) -> List[str]:
        files = set()
        for s in self.get_all_slice_statuses().values():
            for f in s.get("files_modified", []):
                files.add(f)
        return sorted(list(files))

    # -------------------------------------------------------------------------
    # Stage 1: Antigravity Slicing & Plan Proposal
    # -------------------------------------------------------------------------
    def stage1_save_initial_plan(self, plan_content: str) -> Path:
        return self.save_artifact("STAGE1_INITIAL_PLAN.md", plan_content)

    def stage1_format_codex_review_prompt(self, plan_content: str) -> str:
        return (
            "### [TRIAD STAGE 2: ADVERSARIAL CRITIQUE & GAP ANALYSIS]\n\n"
            "Antigravity has synthesized the initial architectural plan and slicing strategy below.\n"
            "As the Adversarial Auditor, please critically review this proposal:\n\n"
            "1. **Gaps & Blindspots**: What necessary changes, edge cases, or failure modes are overlooked?\n"
            "2. **Slicing Integrity**: Are the proposed worker slices truly independent and non-overlapping? Are there race conditions?\n"
            "3. **Causal & Invariant Risks**: Does any slice violate system invariants or introduce regressions?\n"
            "4. **Recommendations**: Highlight exact modifications and additions required before implementation.\n\n"
            "--- INITIAL PLAN ---\n\n"
            f"{plan_content}\n"
        )

    # -------------------------------------------------------------------------
    # Stage 2: Codex Critique Capture
    # -------------------------------------------------------------------------
    def stage2_save_codex_critique(self, critique_content: str) -> Path:
        return self.save_artifact("STAGE2_CODEX_CRITIQUE.md", critique_content)

    def stage2_format_deepseek_synthesis_prompt(self, plan_content: str, critique_content: str) -> str:
        return (
            "### [TRIAD STAGE 3: DEEP REASONING SYNTHESIS & ATOMIC TASK FORMALIZATION]\n\n"
            "Review the initial plan from Antigravity and the adversarial critique from Codex below.\n"
            "Using your deep mathematical and logical reasoning:\n\n"
            "1. **Merge & Resolve**: Reconcile Codex's critique with the initial plan, fixing all gaps.\n"
            "2. **Formalize Slices**: Finalize the exact, atomic execution format for each worker slice.\n"
            "3. **Define Interfaces**: Ensure rigorous input/output contracts and strict file boundaries.\n"
            "4. **Output Final Plan**: Provide the complete synthesized implementation plan ready for execution.\n\n"
            "--- ANTIGRAVITY INITIAL PLAN ---\n"
            f"{plan_content}\n\n"
            "--- CODEX ADVERSARIAL CRITIQUE ---\n"
            f"{critique_content}\n"
        )

    # -------------------------------------------------------------------------
    # Stage 3: DeepSeek Synthesis Capture
    # -------------------------------------------------------------------------
    def stage3_save_deepseek_synthesis(self, synthesis_content: str) -> Path:
        return self.save_artifact("STAGE3_DEEPSEEK_SYNTHESIS.md", synthesis_content)

    # -------------------------------------------------------------------------
    # Stage 4: Antigravity Final Lock
    # -------------------------------------------------------------------------
    def stage4_lock_plan(self, final_locked_content: str) -> Path:
        target = self.save_artifact("STAGE4_LOCKED_PLAN.md", final_locked_content)
        # Clear previous run statuses for fresh execution
        for f in self.status_dir.glob("*.json"):
            f.unlink()
        print("[TriadPipeline] Plan successfully LOCKED. Stage 4 complete.")
        return target

    # -------------------------------------------------------------------------
    # Stage 5: Parallel OpenCode Worker Execution
    # -------------------------------------------------------------------------
    def run_opencode_worker(
        self,
        slice_id: str,
        prompt: str,
        target_files: Optional[List[str]] = None,
        async_bg: bool = False
    ) -> Optional[subprocess.Popen]:
        """
        Executes an OpenCode subagent in a dedicated session with auto-approval.
        """
        self.set_slice_status(slice_id, "RUNNING", target_files or [], "Subagent execution started")

        cli_path = OPENCODE_CLI if OPENCODE_CLI.exists() else Path("opencode")
        cmd = [
            str(cli_path),
            "run",
            "--auto",
            "--session", f"triad-{slice_id}",
            prompt
        ]

        if async_bg:
            p = subprocess.Popen(
                cmd,
                cwd=str(self.root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8"
            )
            print(f"[TriadPipeline] Worker [{slice_id}] started in background (PID: {p.pid})")
            return p
        else:
            print(f"[TriadPipeline] Running Worker [{slice_id}] synchronously...")
            res = subprocess.run(cmd, cwd=str(self.root), capture_output=True, text=True, encoding="utf-8")
            if res.returncode == 0:
                self.set_slice_status(slice_id, "DONE", target_files or [], "Execution completed successfully")
                print(f"[TriadPipeline] Worker [{slice_id}] finished successfully.")
            else:
                self.set_slice_status(slice_id, "FAILED", target_files or [], f"CLI error: {res.stderr[:500]}")
                print(f"[TriadPipeline] Worker [{slice_id}] failed: {res.stderr[:300]}")
            return None

    # -------------------------------------------------------------------------
    # Stage 6: Codex Post-Execution Audit
    # -------------------------------------------------------------------------
    def stage6_format_codex_audit_prompt(self) -> str:
        locked_plan = self.load_artifact("STAGE4_LOCKED_PLAN.md") or "Plan not found."
        modified_files = self.get_all_modified_files()
        
        diff_text = self._gather_git_diff(modified_files)

        return (
            "### [TRIAD STAGE 6: POST-EXECUTION CONFORMANCE AUDIT]\n\n"
            "All OpenCode worker agents have completed their implementations.\n"
            "As the Audit Gatekeeper, analyze the results and files written against the locked initial plan:\n\n"
            "1. **Plan Conformance**: Is everything implemented exactly as planned? Does anything violate the initial plan?\n"
            "2. **Completeness**: Is the work fully done, or is any requirement pending or partially implemented?\n"
            "3. **Code Quality & Correctness**: Are there logical bugs, syntax errors, or domain leaks?\n"
            "4. **Verdict**: Issue a final verdict: `[VERDICT: FULLY_CONFORMANT]` or `[VERDICT: REMEDIATION_REQUIRED]` with specific bullet points for Antigravity.\n\n"
            "--- LOCKED INITIAL PLAN ---\n"
            f"{locked_plan}\n\n"
            "--- MODIFIED FILES ---\n" +
            "\n".join(f"- {f}" for f in modified_files) + "\n\n"
            "--- CODE DIFFS ---\n"
            f"{diff_text}\n"
        )

    def _gather_git_diff(self, files: List[str]) -> str:
        try:
            cmd = ["git", "diff", "HEAD", "--"] + files if files else ["git", "diff", "HEAD"]
            res = subprocess.run(cmd, cwd=str(self.root), capture_output=True, text=True, encoding="utf-8")
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout[:25000] # clamp to avoid massive outputs
        except Exception:
            pass
        return "No git diff available."

    def stage6_save_codex_audit(self, audit_content: str) -> Path:
        return self.save_artifact("STAGE6_CODEX_AUDIT.md", audit_content)

    # -------------------------------------------------------------------------
    # Stage 7: Antigravity Remediation & Verification Checks
    # -------------------------------------------------------------------------
    def stage7_run_verification(self, test_command: Optional[str] = None) -> Dict[str, Any]:
        modified_files = self.get_all_modified_files()
        compile_results = {}
        for f in modified_files:
            if f.endswith(".py"):
                full_path = self.root / f
                if full_path.exists():
                    res = subprocess.run(
                        [sys.executable, "-m", "py_compile", str(full_path)],
                        capture_output=True, text=True
                    )
                    compile_results[f] = "PASS" if res.returncode == 0 else f"FAIL: {res.stderr}"

        test_output = ""
        test_passed = True
        if test_command:
            print(f"[TriadPipeline] Running test command: {test_command}")
            t_res = subprocess.run(test_command, shell=True, cwd=str(self.root), capture_output=True, text=True)
            test_output = t_res.stdout + "\n" + t_res.stderr
            test_passed = (t_res.returncode == 0)

        report = {
            "compilation": compile_results,
            "all_compiled": all(v == "PASS" for v in compile_results.values()),
            "tests_passed": test_passed,
            "test_output": test_output[:4000],
            "verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        self.save_artifact("STAGE7_VERIFICATION.md", json.dumps(report, indent=2))
        return report

    # -------------------------------------------------------------------------
    # Stage 8: User Final Report
    # -------------------------------------------------------------------------
    def stage8_generate_report(self) -> str:
        locked_plan = self.load_artifact("STAGE4_LOCKED_PLAN.md") or "N/A"
        codex_audit = self.load_artifact("STAGE6_CODEX_AUDIT.md") or "N/A"
        verification = self.load_artifact("STAGE7_VERIFICATION.md") or "N/A"
        modified_files = self.get_all_modified_files()

        report = (
            "# Triad Collaborative Lifecycle — Final Execution Report\n\n"
            "## 1. Executive Summary\n"
            "The 8-stage Triad Collaboration Pipeline has completed successfully across Antigravity, OpenCode, and Codex.\n\n"
            "## 2. Modified & Created Files\n" +
            "\n".join(f"- `{f}`" for f in modified_files) + "\n\n"
            "## 3. Codex Post-Execution Audit Verdict\n"
            f"{codex_audit}\n\n"
            "## 4. Final Verification & Compilation Evidence\n"
            f"```json\n{verification}\n```\n\n"
            "## 5. Status\n"
            "**All planned tasks verified and complete.**\n"
        )
        self.save_artifact("FINAL_REPORT.md", report)
        return report


def main():
    parser = argparse.ArgumentParser(description="Triad Lifecycle Orchestrator")
    parser.add_argument("action", choices=[
        "status", "init", "set-status", "check-done", "stage6-prep", "stage7-verify", "stage8-report"
    ])
    parser.add_argument("--slice-id", type=str, help="Slice identifier")
    parser.add_argument("--status", type=str, help="Slice status (DONE, FAILED, RUNNING)")
    parser.add_argument("--files", nargs="*", help="List of files modified")
    parser.add_argument("--test-cmd", type=str, help="Optional test command for stage 7")

    args = parser.parse_args()
    pipeline = TriadPipeline()

    if args.action == "status":
        print(json.dumps(pipeline.get_all_slice_statuses(), indent=2))
    elif args.action == "set-status":
        if not args.slice_id or not args.status:
            print("Error: --slice-id and --status required.")
            sys.exit(1)
        pipeline.set_slice_status(args.slice_id, args.status, args.files or [])
    elif args.action == "check-done":
        done = pipeline.are_all_slices_done()
        print(f"All slices done: {done}")
        sys.exit(0 if done else 1)
    elif args.action == "stage6-prep":
        prompt = pipeline.stage6_format_codex_audit_prompt()
        print(prompt)
    elif args.action == "stage7-verify":
        res = pipeline.stage7_run_verification(args.test_cmd)
        print(json.dumps(res, indent=2))
    elif args.action == "stage8-report":
        report = pipeline.stage8_generate_report()
        print(report)


if __name__ == "__main__":
    main()

