import os
import sys
import re
import ast
import json
import asyncio
from typing import Dict, Any, List, Optional

# Prohibited dangerous modules/builtins for agent scripts
PROHIBITED_MODULES = {
    "os", "sys", "subprocess", "socket", "shutil", "urllib", "requests", 
    "http", "ftplib", "smtplib", "webbrowser", "ctypes", "winreg", "pickle"
}

ALLOWED_MODULES = {
    "duckdb", "polars", "pandas", "numpy", "scipy", "sympy", "torch", "jax",
    "sklearn", "skimage", "math", "statistics", "json", "re", "datetime",
    "collections", "itertools", "typing", "dataclasses", "enum", "abc", "time",
    "cmath", "functools", "warnings", "random", "__future__"
}


class ScriptSandboxValidator(ast.NodeVisitor):
    """AST validator to ensure generated Python scripts do not invoke forbidden operations."""
    def __init__(self):
        self.errors = []

    def visit_Import(self, node):
        for alias in node.names:
            root_mod = alias.name.split('.')[0]
            if root_mod in PROHIBITED_MODULES:
                self.errors.append(f"Prohibited module import: '{alias.name}'")
            elif root_mod not in ALLOWED_MODULES:
                self.errors.append(f"Unapproved module import: '{alias.name}'. Allowed: {sorted(list(ALLOWED_MODULES))}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module:
            root_mod = node.module.split('.')[0]
            if root_mod in PROHIBITED_MODULES:
                self.errors.append(f"Prohibited module import from: '{node.module}'")
            elif root_mod not in ALLOWED_MODULES:
                self.errors.append(f"Unapproved module import from: '{node.module}'. Allowed: {sorted(list(ALLOWED_MODULES))}")
        self.generic_visit(node)

    def visit_Call(self, node):
        # Prevent open(), eval(), exec(), compile(), __import__()
        if isinstance(node.func, ast.Name):
            if node.func.id in {"open", "eval", "exec", "__import__", "compile", "breakpoint"}:
                self.errors.append(f"Prohibited built-in call: '{node.func.id}()'")
        self.generic_visit(node)


def validate_script_ast(code: str) -> List[str]:
    """Parses code into AST and validates against the security whitelist."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"SyntaxError on line {e.lineno}: {e.msg}"]
    validator = ScriptSandboxValidator()
    validator.visit(tree)
    return validator.errors


class SandboxedScriptRunner:
    """Safely executes empirical test scripts against DuckDB datasets in a scrubbed subprocess."""

    def __init__(self, scratch_dir: str = "scratch/agent_scripts", project_root: Optional[str] = None):
        self.project_root = os.path.abspath(project_root or os.getcwd())
        # Keep the scratch sandbox absolute so path resolution never depends on the caller's cwd.
        self.scratch_dir = os.path.abspath(scratch_dir)
        os.makedirs(self.scratch_dir, exist_ok=True)

    def _absolutize_data_paths(self, code: str) -> str:
        """
        Rewrites repo-relative ``data/...`` string literals to absolute paths before execution.

        The sandbox deliberately runs from ``scratch/agent_scripts`` for file-system isolation.
        Generated DuckDB scripts, however, receive catalog paths such as
        ``data/xauusd/XAUUSD_M15.parquet`` from dataset_catalog. Resolving those paths against
        the project root (while keeping the isolated cwd) lets DuckDB find the files without
        weakening the sandbox.
        """
        def repl(m: re.Match) -> str:
            p = m.group(1).replace("\\", "/")
            if not os.path.isabs(p):
                p = os.path.abspath(os.path.join(self.project_root, p)).replace("\\", "/")
            return p

        return re.sub(r"(?<=['\"])(data[/\\][^'\"]+)(?=['\"])", repl, code)

    async def execute_script(
        self,
        script_id: str,
        code_str: str,
        dataset_path: str = "",
        timeout_seconds: float = 15.0,
        available_schema: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Executes a Python script in a sandboxed subprocess with an environment stripped of secrets.
        Returns captured stdout, stderr, execution status, and structured diagnostics on error.
        """
        # Sanitize script_id to prevent directory traversal
        safe_script_id = re.sub(r'[^a-zA-Z0-9_\-]', '', script_id)
        if not safe_script_id:
            safe_script_id = "agent_script_anon"

        clean_code = code_str.strip()
        if clean_code.startswith("```python"):
            clean_code = clean_code[9:]
        elif clean_code.startswith("```"):
            clean_code = clean_code[3:]
        if clean_code.endswith("```"):
            clean_code = clean_code[:-3]
        clean_code = clean_code.strip()

        # 0. Resolve relative data/... literals against the project root without changing cwd.
        clean_code = self._absolutize_data_paths(clean_code)

        # 1. AST Validation (blocks open, eval, exec, prohibited imports)
        ast_errors = validate_script_ast(clean_code)
        if ast_errors:
            return {
                "success": False,
                "script_id": safe_script_id,
                "category": "SECURITY_OR_SYNTAX_VIOLATION",
                "errors": ast_errors,
                "stdout": "",
                "stderr": "\n".join(ast_errors),
                "error_report": self._format_error_report(
                    category="SECURITY_OR_SYNTAX_VIOLATION",
                    exception_str="\n".join(ast_errors),
                    available_schema=available_schema
                )
            }

        # 2. Write script file
        script_file = os.path.join(self.scratch_dir, f"{safe_script_id}.py")
        with open(script_file, "w", encoding="utf-8") as f:
            f.write(clean_code)

        # 3. Environment Sanitization (Codex Fix 1: Scrub all secrets and API keys from subprocess environment)
        python_exe = sys.executable
        scrubbed_env = {}
        for k, v in os.environ.items():
            k_upper = k.upper()
            if any(term in k_upper for term in ["KEY", "TOKEN", "SECRET", "PASS", "CREDENTIAL", "AUTH", "API"]):
                continue  # Scrubbed!
            scrubbed_env[k] = v

        scrubbed_env["PYTHONDONTWRITEBYTECODE"] = "1"
        scrubbed_env["PYTHONUNBUFFERED"] = "1"

        try:
            proc = await asyncio.create_subprocess_exec(
                python_exe,
                os.path.abspath(script_file),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=scrubbed_env,
                cwd=os.path.abspath(self.scratch_dir)
            )

            try:
                stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
                stdout_str = stdout_b.decode("utf-8", errors="replace").strip()
                stderr_str = stderr_b.decode("utf-8", errors="replace").strip()
                return_code = proc.returncode

                if return_code == 0:
                    return {
                        "success": True,
                        "script_id": safe_script_id,
                        "script_file": script_file,
                        "stdout": stdout_str,
                        "stderr": stderr_str,
                        "return_code": 0
                    }
                else:
                    category = self._classify_error(stderr_str)
                    return {
                        "success": False,
                        "script_id": safe_script_id,
                        "script_file": script_file,
                        "category": category,
                        "return_code": return_code,
                        "stdout": stdout_str,
                        "stderr": stderr_str,
                        "error_report": self._format_error_report(
                            category=category,
                            exception_str=stderr_str,
                            available_schema=available_schema
                        )
                    }

            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except Exception:
                    pass
                return {
                    "success": False,
                    "script_id": safe_script_id,
                    "category": "TIMEOUT",
                    "return_code": -1,
                    "stdout": "",
                    "stderr": f"Script execution exceeded timeout limit of {timeout_seconds}s.",
                    "error_report": self._format_error_report(
                        category="TIMEOUT",
                        exception_str=f"Script execution exceeded wall-clock timeout of {timeout_seconds}s.",
                        available_schema=available_schema
                    )
                }

        except Exception as e:
            return {
                "success": False,
                "script_id": safe_script_id,
                "category": "SUBPROCESS_LAUNCH_ERROR",
                "return_code": -1,
                "stdout": "",
                "stderr": str(e),
                "error_report": self._format_error_report(
                    category="SUBPROCESS_LAUNCH_ERROR",
                    exception_str=str(e),
                    available_schema=available_schema
                )
            }

    def _classify_error(self, stderr_str: str) -> str:
        s = stderr_str.lower()
        if "syntaxerror" in s:
            return "SYNTAX_ERROR"
        elif "binder error" in s or "column" in s and "not found" in s or "keyerror" in s:
            return "SCHEMA_MISMATCH"
        elif "modulenotfounderror" in s or "importerror" in s:
            return "IMPORT_ERROR"
        elif "timeouterror" in s:
            return "TIMEOUT"
        elif "typeerror" in s or "valueerror" in s:
            return "DATA_TYPE_MISMATCH"
        else:
            return "RUNTIME_EXCEPTION"

    def _format_error_report(
        self,
        category: str,
        exception_str: str,
        available_schema: Optional[Dict[str, str]] = None
    ) -> str:
        """Constructs the structured diagnostic report required for Round 1.2 remediation."""
        schema_lines = []
        if available_schema:
            for col, dtype in available_schema.items():
                schema_lines.append(f"  - {col}: {dtype}")
        else:
            schema_lines.append("  (No schema provided - verify table columns before querying)")

        truncated_exc = exception_str[-1200:] if len(exception_str) > 1200 else exception_str

        return (
            f"[SCRIPT EXECUTION FAILURE REPORT]\n"
            f"Category: [{category}]\n"
            f"Traceback / Exception:\n{truncated_exc}\n\n"
            f"AVAILABLE DUCKDB SCHEMA & COLUMN TYPES:\n"
            + "\n".join(schema_lines) + "\n\n"
            f"REMEDIATION MANDATE:\n"
            f"Inspect the failure category and available columns above. In Round 1.2, you must write a corrected "
            f"script that references only valid column names and imports only permitted libraries (duckdb, polars, pandas, numpy, scipy, sympy, math, statistics)."
        )

    def format_error_for_agent(self, script_result: Dict[str, Any]) -> str:
        """Returns the pre-formatted error report or constructs one from result dict."""
        if "error_report" in script_result and script_result["error_report"]:
            return script_result["error_report"]
        return self._format_error_report(
            category=script_result.get("category", "RUNTIME_EXCEPTION"),
            exception_str=script_result.get("stderr") or script_result.get("error", "Unknown script error")
        )

    def cleanup_ephemeral_scripts(self, session_prefix: str = ""):
        """Deletes ephemeral Python script files created during a specific run session."""
        if not os.path.exists(self.scratch_dir):
            return
        for fname in os.listdir(self.scratch_dir):
            if fname.endswith(".py"):
                if not session_prefix or fname.startswith(session_prefix) or fname.startswith(f"script_{session_prefix}"):
                    fpath = os.path.join(self.scratch_dir, fname)
                    try:
                        os.remove(fpath)
                    except Exception:
                        pass


script_runner = SandboxedScriptRunner()
