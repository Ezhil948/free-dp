import os
import sys
import re
import json
import asyncio
import uuid
import time
import shutil
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from key_rotator import key_rotator
from model_client import model_caller
from search_worker import DeepWebResearcher, format_sources_for_prompt
from dataset_engine import dataset_engine
from dataset_catalog import dataset_catalog
from skill_injector import skill_injector
from worker_pool import worker_pool
from paper_harvester import paper_harvester
from task_anchor import TaskAnchor, build_fallback_task_anchor
from live_probe import live_prober

logger = logging.getLogger("council_orchestrator")

MATH_FORMAT_CONTRACT = (
    "MANDATORY MATHEMATICAL SPECIFICATIONS:\n"
    "1. Derive every governing equation from first principles using isolated LaTeX display blocks ($$ ... $$).\n"
    "2. Provide 3-5 intermediate algebraic steps between equations; do not jump to final closed forms.\n"
    "3. Define all variables immediately below their first displayed equation.\n"
    "4. Derive all results strictly within the domain of the research directive.\n"
)


def save_json_atomic(filepath: str, data: Dict[str, Any]):
    """Atomically saves JSON with Windows/OneDrive lock retry and graceful fallback."""
    tmp_path = f"{filepath}.{os.getpid()}.{time.time_ns()}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        # Retry atomic replace for temporary Windows / OneDrive file locks
        for attempt in range(5):
            try:
                os.replace(tmp_path, filepath)
                return
            except (PermissionError, OSError):
                time.sleep(0.05 * (attempt + 1))
        
        # If atomic replace still locked, copyfile overwrite fallback
        try:
            shutil.copyfile(tmp_path, filepath)
        except Exception:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


class CouncilEngine:
    """Multi-Agent Deliberation & Deep-Research Orchestrator."""

    def __init__(
        self,
        leader_model: str = "gemini-2.0-flash",
        member_model: str = "llama-3.3-70b-versatile",
        worker_model: str = "llama-3.3-70b-versatile",
        target_web_pages_per_domain: int = 35,
        max_workers: int = 8,
        room_stagger_sec: Optional[float] = None,
        execution_mode: str = "auto",
        conditional_empirical_audit: bool = True
    ):
        self.leader_model = leader_model
        self.member_model = member_model
        self.worker_model = worker_model
        self.target_pages = target_web_pages_per_domain
        self.max_workers = max_workers
        self.room_stagger_sec = room_stagger_sec if room_stagger_sec is not None else float(os.getenv("COUNCIL_ROOM_STAGGER_SEC", "1.5"))
        self.execution_mode = execution_mode
        self.conditional_empirical_audit = conditional_empirical_audit
        worker_pool.sem = asyncio.Semaphore(max_workers)
        self.researcher = DeepWebResearcher(max_concurrent_fetches=15, timeout_seconds=12.0)

    def _save_state(self, council_state: Dict[str, Any]):
        """Saves council state to both the run-specific directory and the root file."""
        run_dir = council_state.get("run_dir", ".")
        if run_dir and run_dir != ".":
            save_json_atomic(os.path.join(run_dir, "council_room.json"), council_state)
        save_json_atomic("council_room.json", council_state)

    # ─────────────────────────────────────────────────────────────
    # ROOM 1: Council Room Deliberation & Plan Synthesis
    # ─────────────────────────────────────────────────────────────

    async def run_phase_1_context_expansion(self, user_prompt: str, council_state: Dict[str, Any], run_id: str = "default") -> str:
        """Phase 1: Leader elaborates prompt, extracts immutable TaskAnchor, and adds domain context."""
        print("\n[Council Room] --- Phase 1: Context Elaboration & Task Anchor (Leader) ---")
        has_dataset_intent = any(k in user_prompt.lower() for k in ["dataset", "parquet", "xauusd", "gold", "market data", "tick", "csv", "sql table"])
        if has_dataset_intent and os.path.exists("data"):
            catalog_text = dataset_catalog.format_catalog_for_prompt()
        else:
            catalog_text = "(No local tabular datasets provided. The Council will conduct deep empirical web and literature research.)"

        # Build fallback anchor immediately
        base_anchor = build_fallback_task_anchor(user_prompt)

        prompt = (
            "You are the Council Leader. Convert the user request into an immutable, unambiguous research brief and typed task anchor.\n"
            "CRITICAL: Keep the core entity and question strictly aligned with the user prompt. Do NOT substitute off-topic domains or cloud infrastructure.\n\n"
            f"USER REQUEST:\n{user_prompt}\n\n"
            f"AVAILABLE DATASETS & SCHEMAS:\n{catalog_text}\n\n"
            "Return a clean JSON object with this exact structure:\n"
            "{\n"
            '  "target_domain": "concise domain title",\n'
            '  "core_question": "exact question to answer",\n'
            '  "expanded_context": "detailed narrative context",\n'
            '  "explicit_requirements": ["requirement 1", "requirement 2"],\n'
            '  "eligible_entities": ["entity 1", "entity 2"],\n'
            '  "prohibited_drift": ["off-topic area 1", "off-topic area 2"],\n'
            '  "intent_mode": "api_catalog" | "quantitative_data" | "academic_theory" | "general_fact",\n'
            '  "harvest_academic_papers": false,\n'
            '  "script_execution_required": false,\n'
            '  "assumptions": ["..."],\n'
            '  "unknowns": ["..."],\n'
            '  "success_criteria": ["..."]\n'
            "}"
        )
        resp = await model_caller.call_by_tier(
            tier="leader_standard",
            messages=[{"role": "user", "content": prompt}],
            stage_tag="phase1_context",
            max_tokens=2000,
            overall_deadline=50.0,
            run_id=run_id
        )
        data = model_caller.extract_json(resp, default_schema={
            "target_domain": base_anchor.target_domain,
            "core_question": base_anchor.core_question,
            "expanded_context": user_prompt,
            "explicit_requirements": [user_prompt],
            "eligible_entities": base_anchor.eligible_entities,
            "prohibited_drift": base_anchor.prohibited_drift,
            "intent_mode": base_anchor.intent_mode,
            "harvest_academic_papers": base_anchor.harvest_academic_papers,
            "script_execution_required": base_anchor.script_execution_required,
            "assumptions": [],
            "unknowns": [],
            "success_criteria": ["Rigorous multi-domain empirical analysis"]
        })

        if not isinstance(data, dict):
            data = {}
        data.setdefault("expanded_context", user_prompt)
        data.setdefault("explicit_requirements", [user_prompt])
        data.setdefault("target_domain", base_anchor.target_domain)
        data.setdefault("core_question", base_anchor.core_question)
        data.setdefault("eligible_entities", base_anchor.eligible_entities)
        data.setdefault("prohibited_drift", base_anchor.prohibited_drift)
        data.setdefault("intent_mode", base_anchor.intent_mode)
        data.setdefault("harvest_academic_papers", base_anchor.harvest_academic_papers)
        data.setdefault("script_execution_required", base_anchor.script_execution_required)

        # Construct and persist typed TaskAnchor
        anchor = TaskAnchor(
            raw_prompt=user_prompt,
            target_domain=data.get("target_domain", base_anchor.target_domain),
            core_question=data.get("core_question", base_anchor.core_question),
            required_deliverables=data.get("explicit_requirements", [user_prompt]),
            eligible_entities=data.get("eligible_entities", base_anchor.eligible_entities),
            prohibited_drift=data.get("prohibited_drift", base_anchor.prohibited_drift),
            intent_mode=data.get("intent_mode", base_anchor.intent_mode),
            harvest_academic_papers=bool(data.get("harvest_academic_papers", base_anchor.harvest_academic_papers)),
            script_execution_required=bool(data.get("script_execution_required", base_anchor.script_execution_required)),
            created_at=datetime.utcnow().isoformat()
        )
        council_state["task_anchor"] = anchor.to_dict()
        council_state["context"] = data
        council_state["status"] = "context_elaborated"
        council_state["updated_at"] = datetime.utcnow().isoformat()
        self._save_state(council_state)
        print(f"[Council Room] ✓ Task Anchor extracted: Domain='{anchor.target_domain}', Mode='{anchor.intent_mode}', Papers={anchor.harvest_academic_papers}.")
        return data.get("expanded_context", "")

    async def run_phase_2_initial_plan(self, council_state: Dict[str, Any], run_id: str = "default") -> Dict[str, Any]:
        """
        Phase 2: Leader drafts the initial strategy and debate agenda.
        Uses Premium Slot 1: gemini-3.8-flash (stage_tag='phase2_initial_plan').
        """
        print("\n[Council Room] --- Phase 2: Initial Plan & Discussion Framework (Leader [Premium Slot 1]) ---")
        ctx = council_state.get("context", {}).get("expanded_context", council_state.get("input", {}).get("user_prompt", ""))
        reqs = council_state.get("context", {}).get("explicit_requirements", [council_state.get("input", {}).get("user_prompt", "")])
        raw_anchor = council_state.get("task_anchor", {})
        anchor_header = TaskAnchor.from_dict(raw_anchor).format_prompt_header() if raw_anchor else ""

        prompt = (
            f"{anchor_header}\n"
            "You are the Council Leader. Create the initial strategic plan and debate agenda for the Council of Domain Specialists.\n"
            "Identify key failure modes, potential traps, and decompose the mission into 4 distinct, domain-specific research angles tailored directly to the subject matter:\n"
            "1. Domain 1 (e.g. Primary architecture, landscape discovery, and core mechanisms)\n"
            "2. Domain 2 (e.g. Empirical boundaries, limits, constraints, and risk factors)\n"
            "3. Domain 3 (e.g. Comparative alternatives, verification gates, and edge cases)\n"
            "4. Domain 4 (e.g. Operational execution, implementation rules, and false claim traps)\n\n"
            f"GLOBAL CONTEXT:\n{ctx}\n\n"
            f"REQUIREMENTS:\n{json.dumps(reqs)}\n\n"
            "Return a clean JSON object with this structure:\n"
            "{\n"
            '  "goal": "...",\n'
            '  "tasks": ["..."],\n'
            '  "domains": [\n'
            '    {"id": "cm1", "domain_title": "...", "scope": "..."},\n'
            '    {"id": "cm2", "domain_title": "...", "scope": "..."},\n'
            '    {"id": "cm3", "domain_title": "...", "scope": "..."},\n'
            '    {"id": "cm4", "domain_title": "...", "scope": "..."}\n'
            '  ],\n'
            '  "open_questions": ["..."]\n'
            "}"
        )
        resp = await model_caller.call_by_tier(
            tier="leader_premium",
            messages=[{"role": "user", "content": prompt}],
            stage_tag="phase2_initial_plan",
            max_tokens=2400,
            overall_deadline=120.0,
            run_id=run_id
        )
        words = [w for w in re.findall(r'\w+', ctx) if len(w) > 3][:6]
        topic_snip = " ".join(words) if words else "Subject Matter"
        dynamic_default_plan = {
            "goal": f"Rigorous empirical multi-domain research into: {topic_snip}",
            "tasks": ["Theoretical Foundations & Proofs", "Microstructural / Algorithmic Formulation", "Boundary Conditions & Invariants", "Numerical Verification & Synthesis"],
            "domains": [
                {"id": "cm1", "domain_title": f"Theoretical Foundations & Proofs: {topic_snip}", "scope": "Rigorous mathematical formulations, foundational theorems, and analytical proofs"},
                {"id": "cm2", "domain_title": f"Microstructural & Algorithmic Formulation: {topic_snip}", "scope": "Exact algorithms, discrete scaling, solvers, and estimator mechanics"},
                {"id": "cm3", "domain_title": f"Boundary Conditions & Invariants: {topic_snip}", "scope": "Asymptotics, martingale preservation, singularity resolution, and deliberate traps"},
                {"id": "cm4", "domain_title": f"Numerical Verification & Empirical Audit: {topic_snip}", "scope": "Discretization stabilities, finite-sample bias corrections, and verification"}
            ],
            "open_questions": [f"What are the precise mathematical and empirical bounds governing {topic_snip}?"]
        }
        plan = model_caller.extract_json(resp, default_schema=dynamic_default_plan)
        council_state["initial_plan"] = plan
        council_state["status"] = "initial_plan_drafted"
        council_state["updated_at"] = datetime.utcnow().isoformat()
        self._save_state(council_state)
        print("[Council Room] ✓ Initial plan drafted.")
        return plan

    async def run_council_deliberation_round(self, round_num: int, council_state: Dict[str, Any], run_id: str = "default") -> List[Dict[str, Any]]:
        """Phase 3 & 5: Sequential debate chain CM1 -> CM2 -> CM3 -> CM4 via council_member tier."""
        print(f"\n[Council Room] --- Deliberation Round {round_num} (CM1 -> CM2 -> CM3 -> CM4) ---")
        plan = council_state.get("revised_plan") if round_num == 2 else council_state["initial_plan"]
        ctx = council_state.get("context", {}).get("expanded_context", council_state.get("input", {}).get("user_prompt", ""))
        members = plan.get("domains") if isinstance(plan, dict) else None
        if not members or len(members) < 2 or not all(isinstance(m, dict) and (m.get("domain_title") or m.get("domain") or m.get("title")) for m in members):
            words = [w for w in re.findall(r'\w+', ctx) if len(w) > 3][:6]
            t_snip = " ".join(words) if words else "Subject Matter"
            members = [
                {"id": "cm1", "domain_title": f"Structural Architecture & Mechanics: {t_snip}"},
                {"id": "cm2", "domain_title": f"Empirical Boundaries & Performance Limits: {t_snip}"},
                {"id": "cm3", "domain_title": f"Verification, Edge Cases & Access Gating: {t_snip}"},
                {"id": "cm4", "domain_title": f"Implementation Guardrails & Operational Viability: {t_snip}"}
            ]
            if isinstance(plan, dict):
                plan["domains"] = members

        cached_reviews = council_state.get(f"temp_round_{round_num}_reviews", [])
        chain_reviews = list(cached_reviews)
        conversation_history = f"GLOBAL CONTEXT:\n{ctx}\n\nCURRENT PLAN:\n{json.dumps(plan, indent=2)}\n"

        # Re-populate conversation history from any cached reviews from previous runs
        for rev in chain_reviews:
            c_cm = rev.get("member_id", "cm")
            c_dom = rev.get("domain", "")
            c_crits = "\n".join(f"  - {c}" for c in rev.get("critiques", [])) or "  - None"
            c_blinds = "\n".join(f"  - {b}" for b in rev.get("blind_spots", [])) or "  - None"
            c_amends = "\n".join(f"  - {a}" for a in rev.get("proposed_amendments", [])) or "  - None"
            c_reb = rev.get("peer_rebuttal", "N/A")
            conversation_history += (
                f"\n\n--- DELIBERATION NOTES: {c_cm.upper()} ({c_dom}) ---\n"
                f"• Critiques:\n{c_crits}\n"
                f"• Blind Spots:\n{c_blinds}\n"
                f"• Proposed Amendments:\n{c_amends}\n"
                f"• Peer Rebuttal:\n  {c_reb}"
            )

        # In Round 2 (Phase 5), check for dispute ledger and round_2_assignments from Phase 4
        disputes_context = ""
        r2_assignments = {}
        if round_num == 2:
            syn_r1 = council_state.get("synthesis_round_1", {})
            disputes = syn_r1.get("dispute_ledger", [])
            r2_assignments = syn_r1.get("round_2_assignments", {})
            if disputes:
                disputes_context = f"\nACTIVE DISPUTE LEDGER FROM ROUND 1:\n{json.dumps(disputes, indent=2)}\n"

        for m_idx, m in enumerate(members):
            cm_id = m.get("id") or f"cm{m_idx+1}"
            domain = m.get("domain_title") or m.get("domain") or m.get("title") or f"Domain {m_idx+1}"

            # If already cached in this round, skip to next member
            if any(r.get("member_id") == cm_id for r in chain_reviews):
                print(f"  > Council Member {cm_id.upper()} ({domain}) review already cached. Skipping.")
                continue

            print(f"  > Council Member {cm_id.upper()} ({domain}) reviewing...")

            rebuttal_instruction = ""
            assigned_disputes = r2_assignments.get(cm_id, [])
            if round_num == 2:
                target_peer = members[(m_idx - 1) % len(members)]
                peer_id = target_peer.get("id") or f"cm{(m_idx - 1) % len(members) + 1}"
                peer_domain = target_peer.get("domain_title") or target_peer.get("domain") or target_peer.get("title") or "Peer Domain"
                rebuttal_instruction = (
                    f"5. Directly answer and resolve or challenge the critique raised by {peer_id.upper()} ({peer_domain}).\n"
                    f"6. Explicitly address your assigned disputes from the Dispute Ledger: {json.dumps(assigned_disputes)}.\n"
                )

            phase_num = 3 if round_num == 1 else 5
            prompt = (
                f"You are Council Member {cm_id.upper()}, specialized in '{domain}'.\n"
                f"You are participating in Deliberation Round {round_num}.\n\n"
                f"{conversation_history}\n"
                f"{disputes_context}\n"
                "YOUR TASK:\n"
                "1. Critique the current plan strictly through the lens of your domain.\n"
                "2. Identify concrete omissions, unsupported assumptions, blind spots, and likely failure modes.\n"
                "3. State what is already solid and practical.\n"
                "4. Propose actionable additions and specific research requirements for the execution phase.\n"
                f"{rebuttal_instruction}"
                "Return a clean JSON object:\n"
                "{\n"
                f'  "member_id": "{cm_id}",\n'
                f'  "domain": "{domain}",\n'
                '  "critiques": ["..."],\n'
                '  "blind_spots": ["..."],\n'
                '  "proposed_amendments": ["..."],\n'
                '  "required_research_angles": ["..."],\n'
                '  "peer_rebuttal": "..."\n'
                "}"
            )
            resp = await model_caller.call_by_tier(
                tier="council_member",
                messages=[{"role": "user", "content": prompt}],
                stage_tag=f"phase{phase_num}_r{round_num}_{cm_id}",
                max_tokens=1800,
                overall_deadline=90.0,
                run_id=run_id
            )
            review = model_caller.extract_json(resp, default_schema={
                "member_id": cm_id,
                "domain": domain,
                "critiques": [f"Need more granular data on {domain}"],
                "blind_spots": ["Overlooking tail risks"],
                "proposed_amendments": [f"Deep dive into {domain}"],
                "required_research_angles": [f"{domain} empirical parameters"],
                "peer_rebuttal": "Concur with prior observations."
            })
            chain_reviews.append(review)
            council_state[f"temp_round_{round_num}_reviews"] = chain_reviews
            self._save_state(council_state)

            critiques_list = review.get("critiques", [])
            blind_spots_list = review.get("blind_spots", [])
            amendments_list = review.get("proposed_amendments", [])
            rebuttal_text = review.get("peer_rebuttal", "")

            critiques_str = "\n".join(f"  - {c}" for c in critiques_list) if critiques_list else "  - None"
            blind_spots_str = "\n".join(f"  - {b}" for b in blind_spots_list) if blind_spots_list else "  - None"
            amendments_str = "\n".join(f"  - {a}" for a in amendments_list) if amendments_list else "  - None"

            conversation_history += (
                f"\n\n--- DELIBERATION NOTES: {cm_id.upper()} ({domain}) ---\n"
                f"• Critiques:\n{critiques_str}\n"
                f"• Blind Spots:\n{blind_spots_str}\n"
                f"• Proposed Amendments:\n{amendments_str}\n"
                f"• Peer Rebuttal:\n  {rebuttal_text if rebuttal_text else 'N/A'}"
            )

        if f"temp_round_{round_num}_reviews" in council_state:
            del council_state[f"temp_round_{round_num}_reviews"]

        if "rounds" not in council_state:
            council_state["rounds"] = []
        council_state["rounds"].append({
            "round": round_num,
            "reviews": chain_reviews
        })
        council_state["updated_at"] = datetime.utcnow().isoformat()
        self._save_state(council_state)
        print(f"[Council Room] ✓ Round {round_num} reviews completed by all members.")
        return chain_reviews

    async def run_phase_4_leader_synthesis(self, council_state: Dict[str, Any], run_id: str = "default") -> Dict[str, Any]:
        """Phase 4: Leader synthesizes Round 1 critiques into an updated plan and dispute ledger."""
        print("\n[Council Room] --- Phase 4: Leader Synthesis & Dispute Ledger ---")
        ctx = council_state.get("context", {}).get("expanded_context", council_state.get("input", {}).get("user_prompt", ""))
        init_plan = council_state["initial_plan"]
        r1_reviews = council_state["rounds"][0]["reviews"]

        prompt = (
            "You are the Council Leader. Synthesize Round 1 feedback from all 4 Council Members.\n"
            "Reconcile disagreements, accept valid blind-spot warnings, reject unfeasible suggestions with reasons,\n"
            "construct a formal DISPUTE LEDGER enumerating active technical disagreements, assign specific disputes to each member for Round 2, and establish the updated plan.\n\n"
            f"CONTEXT:\n{ctx}\n\n"
            f"INITIAL PLAN:\n{json.dumps(init_plan, indent=2)}\n\n"
            f"ROUND 1 REVIEWS:\n{json.dumps(r1_reviews, indent=2)}\n\n"
            "Return a clean JSON object:\n"
            "{\n"
            '  "accepted_improvements": ["..."],\n'
            '  "rejected_suggestions": [{"suggestion": "...", "reason": "..."}],\n'
            '  "dispute_ledger": [\n'
            '    {"dispute_id": "DISP-01", "topic": "...", "member_a": "cm1", "member_b": "cm2", "tension": "..."}\n'
            '  ],\n'
            '  "round_2_assignments": {\n'
            '    "cm1": ["DISP-01"],\n'
            '    "cm2": ["DISP-01"],\n'
            '    "cm3": ["DISP-01"],\n'
            '    "cm4": ["DISP-01"]\n'
            '  },\n'
            '  "revised_plan": {\n'
            '    "goal": "...",\n'
            '    "domains": [\n'
            '      {"id": "cm1", "domain_title": "...", "scope": "..."},\n'
            '      {"id": "cm2", "domain_title": "...", "scope": "..."},\n'
            '      {"id": "cm3", "domain_title": "...", "scope": "..."},\n'
            '      {"id": "cm4", "domain_title": "...", "scope": "..."}\n'
            '    ],\n'
            '    "refined_tasks": ["..."]\n'
            '  },\n'
            '  "round_2_focus_agenda": ["..."]\n'
            "}"
        )
        resp = await model_caller.call_by_tier(
            tier="leader_standard",
            messages=[{"role": "user", "content": prompt}],
            stage_tag="phase4_dispute_synthesis",
            max_tokens=2400,
            overall_deadline=150.0,
            run_id=run_id
        )
        synthesis = model_caller.extract_json(resp, default_schema={
            "accepted_improvements": ["Incorporate empirical stress testing", "Include quantitative boundary verification"],
            "rejected_suggestions": [],
            "dispute_ledger": [
                {"dispute_id": "DISP-01", "topic": "Operational stress thresholds", "member_a": "cm2", "member_b": "cm3", "tension": "Disagreement on throughput limits vs failure boundary calibration"}
            ],
            "round_2_assignments": {
                "cm1": ["DISP-01"],
                "cm2": ["DISP-01"],
                "cm3": ["DISP-01"],
                "cm4": ["DISP-01"]
            },
            "revised_plan": init_plan,
            "round_2_focus_agenda": ["Empirical validation", "Execution bottlenecks"]
        })
        if "round_2_assignments" not in synthesis:
            synthesis["round_2_assignments"] = {"cm1": ["DISP-01"], "cm2": ["DISP-01"], "cm3": ["DISP-01"], "cm4": ["DISP-01"]}
        council_state["synthesis_round_1"] = synthesis
        council_state["revised_plan"] = synthesis.get("revised_plan", init_plan)
        council_state["status"] = "plan_revised"
        council_state["updated_at"] = datetime.utcnow().isoformat()
        self._save_state(council_state)
        print("[Council Room] ✓ Leader synthesis and Dispute Ledger complete.")
        return synthesis

    async def run_phase_6_final_plan_generation(self, council_state: Dict[str, Any], run_id: str = "default") -> Dict[str, Any]:
        """
        Phase 6: Leader generates Final Plan JSON with dynamic member assignments.
        Uses Premium Slot 2: gemini-3.8-flash (stage_tag='phase6_final_plan').
        Dynamically selects execution_mode ('focused' | 'bimodal' | 'comprehensive')
        and allocates K in [1..4] domain rooms based on task scope.
        """
        print("\n[Council Room] --- Phase 6: Final Confirmed Plan JSON (Leader [Premium Slot 2]) ---")
        ctx = council_state.get("context", {}).get("expanded_context", council_state.get("input", {}).get("user_prompt", ""))
        r2_reviews = council_state["rounds"][-1]["reviews"]
        revised_plan = council_state.get("revised_plan", council_state["initial_plan"])
        catalog_text = dataset_catalog.format_catalog_for_prompt()

        target_mode_hint = ""
        if self.execution_mode and self.execution_mode.lower() != "auto":
            target_mode_hint = f"\nUSER DIRECTIVE OVERRIDE: Enforce execution_mode='{self.execution_mode.lower()}'.\n"

        raw_anchor = council_state.get("task_anchor", {})
        anchor_header = TaskAnchor.from_dict(raw_anchor).format_prompt_header() if raw_anchor else ""

        prompt = (
            f"{anchor_header}\n"
            "You are the Council Leader. Formulate the FINAL CONFIRMED PLAN JSON.\n"
            f"{target_mode_hint}"
            "Assess the scope, complexity, and structural requirements of the research directive:\n"
            "- 'focused' mode (K=1): For targeted lookups, fact verification, single-topic empirical research, or bounded queries. Allocate exactly 1 comprehensive execution room ('cm1') covering all evidence in a single unified context without fracturing memory.\n"
            "- 'bimodal' mode (K=2): For two-sided questions, comparative architectures, or bifurcated domains (e.g. architectural design vs empirical validation, free-tier vs enterprise). Allocate 2 distinct domain rooms ('cm1', 'cm2').\n"
            "- 'comprehensive' mode (K=3 or 4): For multi-pillar institutional system design or broad market studies requiring 3 to 4 distinct domain specializations ('cm1'..'cm4').\n\n"
            "CRITICAL: Keep all member assignments strictly anchored to the specific candidate providers (e.g., SambaNova, Cohere, OpenRouter, SiliconFlow, Cerebras, Together AI).\n"
            "Do NOT assign member domains to abstract inference serving architectures or GPU kernels (like DeepInfer or vLLM). Every member must audit specific real-world providers and their actual rate limits and quotas.\n\n"
            "You must output:\n"
            "1. 'execution_mode': 'focused' | 'bimodal' | 'comprehensive'\n"
            "2. 'scope_rationale': Concise explanation of why this execution mode and K domains were selected.\n"
            "3. 'common_context': Global project brief and background shared across execution.\n"
            "4. 'member_assignments': Array of K distinct, decoupled assignments.\n"
            "Each assignment must detail: member_id ('cm1', ...), domain, mission_directive, task_types, search_queries, deliverables, and max_workers.\n"
            "Do NOT overlap scopes. Return clean JSON only.\n\n"
            f"CONTEXT:\n{ctx}\n\n"
            f"AVAILABLE DATASETS & SCHEMAS:\n{catalog_text}\n\n"
            f"REVISED PLAN:\n{json.dumps(revised_plan, indent=2)}\n\n"
            f"ROUND 2 DELIBERATIONS:\n{json.dumps(r2_reviews, indent=2)}\n\n"
            "Return JSON format:\n"
            "{\n"
            '  "execution_mode": "focused",\n'
            '  "scope_rationale": "Single-topic investigation optimal for 1 unified deep-dive room...",\n'
            '  "common_context": "exhaustive global background...",\n'
            '  "member_assignments": [\n'
            '    {\n'
            '      "member_id": "cm1",\n'
            '      "domain": "...",\n'
            '      "mission_directive": "...",\n'
            '      "task_types": ["web"],\n'
            '      "search_queries": ["query 1", "query 2", "query 3"],\n'
            '      "deliverables": ["..."],\n'
            '      "max_workers": 5\n'
            '    }\n'
            '  ]\n'
            "}"
        )
        resp = await model_caller.call_by_tier(
            tier="leader_premium",
            messages=[{"role": "user", "content": prompt}],
            stage_tag="phase6_final_plan",
            max_tokens=2500,
            overall_deadline=180.0,
            run_id=run_id
        )

        words = [w for w in re.findall(r'\w+', ctx) if len(w) > 3][:6]
        kw_base = " ".join(words) if words else "Research Domain"
        default_assignments_4 = [
            {"member_id": "cm1", "domain": "Theoretical Foundations & Proofs", "mission_directive": f"Analyze core proofs, theorems, and mathematical derivations for: {kw_base}", "task_types": ["web", "paper"], "search_queries": [f"{kw_base} theoretical proof", f"{kw_base} foundation theorems"], "deliverables": ["Mathematical derivations", "Formal proofs"]},
            {"member_id": "cm2", "domain": "Microstructural & Algorithmic Mechanics", "mission_directive": f"Formulate exact algorithms, scaling limits, and estimators for: {kw_base}", "task_types": ["web", "paper"], "search_queries": [f"{kw_base} algorithm formulation", f"{kw_base} numerical solver"], "deliverables": ["Algorithmic specifications", "Estimator formulations"]},
            {"member_id": "cm3", "domain": "Boundary Conditions & Trap Falsification", "mission_directive": f"Evaluate asymptotic limits, boundary conditions, and deliberate traps for: {kw_base}", "task_types": ["web", "paper"], "search_queries": [f"{kw_base} boundary conditions", f"{kw_base} asymptotic proof"], "deliverables": ["Asymptotic analyses", "Trap resolutions"]},
            {"member_id": "cm4", "domain": "Numerical Stabilities & Empirical Verification", "mission_directive": f"Design discretization schemes, convergence order tests, and noise filters for: {kw_base}", "task_types": ["web", "paper"], "search_queries": [f"{kw_base} convergence order", f"{kw_base} discretization scheme"], "deliverables": ["Numerical validation", "Empirical protocol"]}
        ]
        default_assignment_1 = [
            {"member_id": "cm1", "domain": "Unified Empirical Deep-Dive", "mission_directive": f"Conduct exhaustive research, verification, and empirical audit for: {kw_base}", "task_types": ["web", "paper"], "search_queries": [f"{kw_base} proofs", f"{kw_base} algorithms", f"{kw_base} boundaries", f"{kw_base} verification"], "deliverables": ["Mathematical proofs", "Algorithmic specifications", "Boundary audit", "Empirical verification"]}
        ]
        default_assignment_2 = [
            {"member_id": "cm1", "domain": "Theoretical Foundations & Mechanics", "mission_directive": f"Audit mathematical foundations, proofs, and specifications for: {kw_base}", "task_types": ["web", "paper"], "search_queries": [f"{kw_base} foundations", f"{kw_base} models"], "deliverables": ["Foundational theory", "Formal specification"]},
            {"member_id": "cm2", "domain": "Boundary Limits & Empirical Verification", "mission_directive": f"Audit asymptotic limits, boundary conditions, and empirical viability for: {kw_base}", "task_types": ["web", "paper"], "search_queries": [f"{kw_base} boundary limits", f"{kw_base} empirical verification"], "deliverables": ["Boundary analysis", "Verification ledger"]}
        ]

        # Determine target mode: explicit override on engine takes precedence
        target_mode = self.execution_mode.lower() if self.execution_mode and self.execution_mode.lower() != "auto" else None

        final_plan = model_caller.extract_json(resp, default_schema={
            "execution_mode": target_mode or "focused",
            "scope_rationale": "Default assignment based on query scope.",
            "common_context": ctx,
            "member_assignments": default_assignment_1 if (target_mode == "focused") else default_assignments_4
        })

        if target_mode:
            final_plan["execution_mode"] = target_mode
        elif not final_plan.get("execution_mode"):
            assign_count = len(final_plan.get("member_assignments", []))
            if assign_count <= 1:
                final_plan["execution_mode"] = "focused"
            elif assign_count == 2:
                final_plan["execution_mode"] = "bimodal"
            else:
                final_plan["execution_mode"] = "comprehensive"

        mode = final_plan["execution_mode"]
        if target_mode == "focused" and len(final_plan.get("member_assignments", [])) > 1:
            final_plan["member_assignments"] = final_plan["member_assignments"][:1]
        elif target_mode == "bimodal" and len(final_plan.get("member_assignments", [])) != 2:
            final_plan["member_assignments"] = final_plan.get("member_assignments", [])[:2] or default_assignment_2

        if not final_plan.get("member_assignments"):
            if mode == "focused":
                final_plan["member_assignments"] = default_assignment_1
            elif mode == "bimodal":
                final_plan["member_assignments"] = default_assignment_2
            else:
                final_plan["member_assignments"] = default_assignments_4

        if not final_plan.get("common_context"):
            final_plan["common_context"] = ctx

        council_state["final_plan"] = final_plan
        council_state["status"] = "final_plan_approved"
        council_state["updated_at"] = datetime.utcnow().isoformat()
        self._save_state(council_state)
        print(f"[Council Room] ✓ Final Plan JSON generated in '{mode.upper()}' mode with {len(final_plan['member_assignments'])} member allocation(s).")
        return final_plan

    # ─────────────────────────────────────────────────────────────
    # ROOM 2: Council Member Rooms (Domain Execution & Deep Search)
    # ─────────────────────────────────────────────────────────────

    async def run_council_member_room(
        self,
        assignment: Dict[str, Any],
        common_context: str,
        run_dir: str = ".",
        run_id: str = "latest",
        execution_mode: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Phase 7: Isolated Council Member Room.
        Orchestrates Dynamic Empirical (Web + Paper) + Dynamic Analytical Dual-Pool System.
        """
        cm_id = assignment["member_id"]
        domain = assignment["domain"]
        directive = assignment.get("mission_directive", "")
        deliverables = assignment.get("deliverables", [])
        room_file = os.path.join(run_dir, f"cm_room_{cm_id}.json")
        cm_state = None
        if os.path.exists(room_file):
            try:
                with open(room_file, "r", encoding="utf-8") as f:
                    existing_state = json.load(f)
                if existing_state.get("status") == "report_ready" and existing_state.get("report"):
                    print(f"[Room 2: {cm_id.upper()}] ✓ Domain Report already completed in checkpoint. Skipping execution.")
                    return existing_state["report"]
                cm_state = existing_state
            except Exception as e:
                print(f"[Room 2: {cm_id.upper()}] Note loading checkpoint room file: {e}")

        print(f"\n[Room 2: {cm_id.upper()}] === Launching Domain Orchestrator for '{domain}' ===")

        skill_context = skill_injector.format_skill_prompt_context(domain, directive)
        if skill_context:
            print(f"[{cm_id.upper()}] Dynamically attached specialized skill playbook.")

        seen_web_urls: set = set()
        seen_paper_ids: set = set()
        used_web_keywords: set = set()
        used_paper_keywords: set = set()
        active_memory_pool: str = (cm_state.get("memory_pool") or cm_state.get("memory_pool_preview") or "") if cm_state else ""
        all_harvested_sources: List[Dict[str, Any]] = cm_state.get("sources", []) if cm_state else []
        all_harvested_papers: List[Dict[str, Any]] = cm_state.get("papers", []) if cm_state else []
        worker_task_records: List[Dict[str, Any]] = cm_state.get("worker_tasks", []) if cm_state else []
        last_audit_packet: Dict[str, Any] = cm_state.get("report", {}).get("domain_audit_packet", {}) if cm_state else {}

        if not cm_state:
            cm_state = {
                "schema_version": "2.0",
                "run_id": run_id,
                "member_id": cm_id,
                "domain": domain,
                "status": "executing",
                "common_context": common_context,
                "assignment": assignment,
                "created_at": datetime.utcnow().isoformat(),
                "iterations_run": 0,
                "worker_tasks": [],
                "sources": [],
                "papers": [],
                "memory_pool": "",
                "report": {}
            }
            save_json_atomic(room_file, cm_state)

        max_room_iterations = 2
        start_iter = cm_state.get("iterations_run", 0) + 1

        # Extract Task Anchor rules for retrieval from assignment or council_room.json
        raw_anchor = assignment.get("task_anchor")
        if not raw_anchor and os.path.exists(os.path.join(run_dir, "council_room.json")):
            try:
                with open(os.path.join(run_dir, "council_room.json"), "r", encoding="utf-8") as rf:
                    c_data = json.load(rf)
                    raw_anchor = c_data.get("task_anchor", {})
            except Exception:
                raw_anchor = {}
        task_anchor = TaskAnchor.from_dict(raw_anchor) if raw_anchor else None
        should_harvest_papers = task_anchor.harvest_academic_papers if task_anchor else False
        anchor_header = task_anchor.format_prompt_header() if task_anchor else ""

        # If Iteration 1 is already completed with substantial memory pool, proceed directly to report synthesis
        if cm_state.get("iterations_run", 0) >= 1 and len(active_memory_pool) > 3000:
            print(f"[{cm_id.upper()}] ✓ Checkpointed Iteration 1 complete ({len(active_memory_pool)} pool chars, {len(all_harvested_papers)} papers). Moving to Final Domain Synthesis.")
            start_iter = max_room_iterations + 1
        elif len(active_memory_pool) < 1000:
            # Prior iteration yielded minimal memory pool; ensure iteration executes
            start_iter = 1

        for iteration in range(start_iter, max_room_iterations + 1):
            print(f"\n[{cm_id.upper()}] >>> Starting Room Iteration {iteration}/{max_room_iterations} <<<")

            if iteration == 1:
                kw_prompt = (
                    f"{anchor_header}\n"
                    f"You are Council Member {cm_id.upper()}, Orchestrator of '{domain}'.\n"
                    f"Directive: {directive}\n"
                    f"Deliverables: {json.dumps(deliverables)}\n\n"
                    "Formulate highly targeted empirical search keywords tailored strictly to the directive and domain:\n"
                    "1. 3 Web Research Keywords (for real-world documentation, API specifications, benchmarks, implementation guides).\n"
                    "2. 5 Academic Research Paper Keywords (for arXiv, OpenAlex, formal models, empirical studies).\n\n"
                    "CRITICAL: Search terms must stay strictly focused on the Target Domain. Do NOT drift into off-topic infrastructure.\n\n"
                    "Output JSON ONLY:\n"
                    "{\n"
                    '  "web_keywords": ["keyword 1", "keyword 2", "keyword 3"],\n'
                    '  "paper_keywords": ["paper kw 1", "paper kw 2", "paper kw 3", "paper kw 4", "paper kw 5"]\n'
                    "}"
                )
            else:
                kw_prompt = (
                    f"{anchor_header}\n"
                    f"You are Council Member {cm_id.upper()} in Iteration 2.\n"
                    f"Prior Audited Memory Pool Preview:\n{active_memory_pool[:2000]}\n\n"
                    f"Previously used web keywords: {list(used_web_keywords)}\n"
                    f"Previously used paper keywords: {list(used_paper_keywords)}\n\n"
                    "Generate NEW, non-duplicate search keywords to address remaining gaps:\n"
                    "1. 3 NEW Web Research Keywords.\n"
                    "2. 5 NEW Academic Research Paper Keywords.\n\n"
                    "CRITICAL: Search terms must stay strictly focused on the Target Domain. Do NOT drift into off-topic infrastructure.\n\n"
                    "Output JSON ONLY:\n"
                    "{\n"
                    '  "web_keywords": ["new kw 1", "new kw 2", "new kw 3"],\n'
                    '  "paper_keywords": ["new paper kw 1", "new paper kw 2", "new paper kw 3", "new paper kw 4", "new paper kw 5"]\n'
                    "}"
                )

            kw_resp = await model_caller.call_by_tier(
                tier="council_member",
                messages=[{"role": "user", "content": kw_prompt}],
                stage_tag=f"room2_{cm_id}_iter{iteration}_keywords",
                max_tokens=900,
                overall_deadline=60.0,
                run_id=run_id
            )
            kw_data = model_caller.extract_json(kw_resp, default_schema={
                "web_keywords": [f"{domain} specifications", f"{domain} empirical limits", f"{domain} benchmarks"],
                "paper_keywords": [f"{domain} theoretical model", f"{domain} empirical analysis", f"{domain} structural bounds", f"{domain} formal specification", f"{domain} statistical verification"]
            })

            raw_web_kws = kw_data.get("web_keywords", [])[:3]
            raw_paper_kws = kw_data.get("paper_keywords", [])[:5]

            current_web_kws = [k for k in raw_web_kws if k.lower() not in used_web_keywords]
            if not current_web_kws:
                current_web_kws = [f"{domain} empirical evidence {iteration}", f"{domain} operational specifications {iteration}", f"{domain} benchmark metrics {iteration}"]
            for k in current_web_kws:
                used_web_keywords.add(k.lower())

            current_paper_kws = [k for k in raw_paper_kws if k.lower() not in used_paper_keywords]
            if not current_paper_kws:
                current_paper_kws = [f"{domain} theoretical paper {iteration}", f"{domain} empirical analysis {iteration}", f"{domain} boundary conditions {iteration}", f"{domain} formal model {iteration}", f"{domain} statistical test {iteration}"]
            for k in current_paper_kws:
                used_paper_keywords.add(k.lower())

            # A. Web Search
            if len(all_harvested_sources) >= 10:
                print(f"[{cm_id.upper()}] Reusing {len(all_harvested_sources)} checkpointed web research sources.")
                new_web_sources = all_harvested_sources
                formatted_web_evidence = format_sources_for_prompt(all_harvested_sources, max_chars_per_source=3000)
            else:
                print(f"[{cm_id.upper()}] Fetching 12 web research sources...")
                web_res = await worker_pool.execute_task({
                    "task_id": f"{cm_id}_web_iter{iteration}",
                    "task_type": "web",
                    "queries": current_web_kws,
                    "target_pages": 12,
                    "start_index": len(all_harvested_sources) + 1,
                    "intent_mode": task_anchor.intent_mode if task_anchor else "general_fact"
                }, cm_id=cm_id)
                new_web_sources = [s for s in web_res.get("sources", []) if s.get("url") not in seen_web_urls]
                for s in new_web_sources:
                    if s.get("url"):
                        seen_web_urls.add(s.get("url"))
                all_harvested_sources.extend(new_web_sources)
                formatted_web_evidence = web_res.get("formatted_evidence", "")

            # B. Academic Paper Harvesting (Intent-Conditional)
            new_papers = []
            if should_harvest_papers:
                if len(all_harvested_papers) >= 8:
                    print(f"[{cm_id.upper()}] Reusing {len(all_harvested_papers)} checkpointed academic research papers.")
                    new_papers = all_harvested_papers
                else:
                    print(f"[{cm_id.upper()}] Harvesting 10 academic research papers via arXiv & OpenAlex...")
                    new_papers = await paper_harvester.harvest_papers_for_keywords(
                        keywords=current_paper_kws,
                        target_papers_per_keyword=2,
                        total_target=10,
                        known_blacklist_ids=seen_paper_ids,
                        id_prefix=f"PAP-{cm_id.upper()}",
                        start_index=len(all_harvested_papers) + 1
                    )
                    for p in new_papers:
                        pid = p.get("paper_id", "")
                        if pid:
                            seen_paper_ids.add(paper_harvester._normalize_id(pid))
                    all_harvested_papers.extend(new_papers)
            else:
                print(f"[{cm_id.upper()}] Skipping academic paper harvesting (TaskAnchor intent_mode: {task_anchor.intent_mode if task_anchor else 'non-academic'}).")

            # B2. Live Endpoint Probing & Primary Docs RAG Indexing
            live_probe_evidence = ""
            official_doc_sources = []
            if task_anchor and task_anchor.intent_mode == "api_catalog" and iteration == 1:
                print(f"[{cm_id.upper()}] Executing live public endpoint probing & primary official docs fetch...")
                try:
                    probe_results = await live_prober.probe_public_models_catalog()
                    doc_results = await live_prober.fetch_primary_official_docs()
                    live_probe_evidence = live_prober.format_probes_for_evidence(probe_results, doc_results)
                    print(f"[{cm_id.upper()}] ✓ Live endpoint probes & official docs complete ({len(probe_results)} endpoints, {len(doc_results)} doc targets).")

                    # Convert primary vendor docs into first-class research sources so workers receive them directly
                    for v_name, v_data in doc_results.items():
                        if isinstance(v_data, dict) and v_data.get("content"):
                            official_doc_sources.append({
                                "ref_id": f"SRC-PRIMARY-{v_name.upper()}",
                                "title": f"Official {v_name.capitalize()} Primary Documentation",
                                "url": v_data.get("url", ""),
                                "content": v_data.get("content", ""),
                                "snippet": v_data.get("content", "")[:300],
                                "domain": f"{v_name}.ai",
                                "provenance_score": 5.0,
                                "is_verified": True
                            })
                except Exception as pe:
                    print(f"[{cm_id.upper()}] Live probe warning: {pe}")

            # Prepend official doc sources so empirical workers ALWAYS have primary vendor documentation in their bins
            if official_doc_sources:
                new_web_sources = official_doc_sources + new_web_sources

            # Merge live probe evidence into web evidence
            if live_probe_evidence:
                formatted_web_evidence = live_probe_evidence + "\n\n" + formatted_web_evidence

            # C. Dataset Query
            dataset_summary = ""
            dataset_task = assignment.get("dataset_query")
            if dataset_task:
                print(f"[{cm_id.upper()}] Querying DuckDB dataset...")
                d_task = {**dataset_task, "task_id": f"{cm_id}_dataset_iter{iteration}", "task_type": "dataset"}
                d_res = await worker_pool.execute_task(d_task)
                dataset_summary = f"\n\n### DATASET QUERY RESULTS:\n```json\n{json.dumps(d_res.get('result', {}), indent=2, default=str)}\n```"

            # D. Dual-Pool Workflow
            eff_mode = execution_mode or self.execution_mode or "auto"
            print(f"[{cm_id.upper()}] Executing Dynamic Dual-Pool [Mode: {eff_mode.upper()}] (Iter {iteration}/2)...")
            chain_res = await worker_pool.execute_dual_pool_workflow(
                directive=directive,
                deliverables=deliverables,
                domain=domain,
                cm_id=cm_id,
                skill_context=skill_context,
                web_sources=new_web_sources,
                paper_dossiers=new_papers,
                evidence_corpus=formatted_web_evidence,
                dataset_summary=dataset_summary,
                worker_model=self.worker_model,
                current_iteration=iteration,
                prior_memory_pool=active_memory_pool,
                run_id=run_id,
                execution_mode=eff_mode,
                conditional_empirical_audit=self.conditional_empirical_audit
            )

            active_memory_pool = chain_res.get("memory_pool", "")
            last_audit_packet = chain_res.get("domain_audit_packet", {})
            cm_state["iterations_run"] = iteration
            cm_state["data_pool_preview"] = (chain_res.get("data_pool", "")[:1200] + "...") if chain_res.get("data_pool") else ""
            cm_state["memory_pool_preview"] = (active_memory_pool[:1200] + "...") if active_memory_pool else ""
            cm_state["sources"] = all_harvested_sources
            cm_state["papers"] = [{"title": p.get("title"), "id": p.get("paper_id"), "year": p.get("year")} for p in all_harvested_papers]
            worker_task_records.append({
                "iteration": iteration,
                "manifest_path": chain_res.get("manifest_path", ""),
                "audit_packet": last_audit_packet,
                "status": "completed"
            })
            cm_state["worker_tasks"] = worker_task_records
            save_json_atomic(room_file, cm_state)

            if iteration < max_room_iterations:
                print(f"[{cm_id.upper()}] Evaluating Memory Pool quality against directive deliverables...")
                eval_prompt = (
                    f"You are Council Member {cm_id.upper()}, evaluating Iteration 1 results.\n"
                    f"Directive: {directive}\n"
                    f"Target Deliverables: {json.dumps(deliverables)}\n\n"
                    f"Current Audited Memory Pool:\n{active_memory_pool[:3000]}\n\n"
                    "Evaluate if all deliverables are satisfied with verified empirical evidence.\n"
                    "Output JSON ONLY:\n"
                    "{\n"
                    '  "status": "SATISFIED" or "NEEDS_REFINEMENT",\n'
                    '  "gaps": ["gap 1", "gap 2"]\n'
                    "}"
                )
                eval_resp = await model_caller.call_by_tier(
                    tier="council_member",
                    messages=[{"role": "user", "content": eval_prompt}],
                    stage_tag=f"room2_{cm_id}_iter{iteration}_loop_gate",
                    max_tokens=600,
                    overall_deadline=60.0,
                    run_id=run_id
                )
                eval_data = model_caller.extract_json(eval_resp, default_schema={"status": "NEEDS_REFINEMENT"})
                if eval_data.get("status") == "SATISFIED":
                    print(f"[{cm_id.upper()}] ✓ CM Quality Gate: Deliverables satisfied in Iteration 1! Skipping Iteration 2.")
                    break
                else:
                    print(f"[{cm_id.upper()}] ↺ CM Quality Gate: Gaps detected ({eval_data.get('gaps', [])}). Proceeding to Iteration 2...")

        # ─── 5. FINAL DOMAIN REPORT SYNTHESIS ─────────────────────────────────
        print(f"\n[{cm_id.upper()}] Synthesizing Final Domain Report from Complete Audited Memory Pool...")
        cm_synthesis_prompt = (
            f"You are Council Member {cm_id.upper()}, Orchestrator of '{domain}'.\n"
            f"You have conducted rigorous multi-iteration empirical research across {len(all_harvested_sources)} web sources and {len(all_harvested_papers)} academic research papers.\n\n"
            f"ASSIGNMENT DIRECTIVE:\n{directive}\n\n"
            f"TARGET DELIVERABLES:\n{json.dumps(deliverables, indent=2)}\n\n"
            f"COMPLETE AUDITED MEMORY POOL:\n{active_memory_pool[:25000]}\n\n"
            "Produce your FINAL DOMAIN REPORT for the Council Leader. It must be:\n"
            "- Exhaustive, fully articulated, and authoritative, directly answering the assignment directive.\n"
            "- Structured with clear, domain-appropriate sections: 1. Core Technical / Architectural Specifications & Operational Mechanics, 2. Empirical Evidence, Verified Limits & Quantitative Metrics, 3. Audited Hypotheses & Status Matrix, 4. Edge Cases, Failure Boundaries & Deceptive Traps, 5. Actionable Implementation Recommendations & Guardrails.\n"
            "- Grounded with explicit citations to sources, papers, empirical numbers, and parameters.\n"
        )

        domain_report_text = await model_caller.call_by_tier(
            tier="council_member",
            messages=[{"role": "user", "content": cm_synthesis_prompt}],
            stage_tag=f"room2_{cm_id}_domain_report",
            max_tokens=3500,
            overall_deadline=180.0,
            run_id=run_id
        )
        if not domain_report_text or not domain_report_text.strip():
            domain_report_text = active_memory_pool

        cm_state["report"] = {
            "member_id": cm_id,
            "domain": domain,
            "full_text": domain_report_text,
            "web_sources_count": len(all_harvested_sources),
            "academic_papers_count": len(all_harvested_papers),
            "iterations_completed": cm_state["iterations_run"],
            "domain_audit_packet": last_audit_packet,
            "papers": all_harvested_papers,
            "sources": all_harvested_sources,
            "completed_at": datetime.utcnow().isoformat()
        }
        cm_state["memory_pool"] = active_memory_pool
        cm_state["status"] = "report_ready"
        save_json_atomic(room_file, cm_state)
        save_json_atomic(f"cm_room_{cm_id}.json", cm_state)
        print(f"[{cm_id.upper()}] ✓ Domain Report generated ({len(domain_report_text)} chars) across {len(all_harvested_sources)} web sources & {len(all_harvested_papers)} academic papers.")
        return cm_state["report"]

    # ─────────────────────────────────────────────────────────────
    # Back to ROOM 1: Leader Quality Audit & Targeted Remediation
    # ─────────────────────────────────────────────────────────────

    async def run_phase_7_leader_audit_gate(
        self,
        council_state: Dict[str, Any],
        domain_reports: List[Dict[str, Any]],
        run_dir: str = ".",
        run_id: str = "latest",
        max_remediation_rounds: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Phase 7.5: Leader Quality Audit Gate.
        Uses Premium Slot 3: gemini-3.8-flash (stage_tag='phase75_quality_audit').
        Ingests the structured domain_audit_packet from each CM.
        Defaults to 'NEEDS_REVISION' if reports or audit packets fail verification.
        """
        final_plan = council_state.get("final_plan", {})
        assignments = {a["member_id"]: a for a in final_plan.get("member_assignments", [])}
        common_context = final_plan.get("common_context", "")

        reports_map: Dict[str, Dict[str, Any]] = {}
        for idx, rep in enumerate(domain_reports):
            m_id = rep.get("member_id", f"cm{idx+1}")
            reports_map[m_id] = rep

        audit_history = []
        remediation_round = 0

        while remediation_round < max_remediation_rounds:
            remediation_round += 1
            print(f"\n[Council Room] --- Phase 7.5: Leader Quality Audit Gate (Round {remediation_round}/{max_remediation_rounds} [Premium Slot 3]) ---")

            eval_payload = []
            for m_id, assign in assignments.items():
                rep = reports_map.get(m_id, {})
                packet = rep.get("domain_audit_packet", {})
                eval_payload.append({
                    "member_id": m_id,
                    "domain": assign.get("domain", ""),
                    "mission_directive": assign.get("mission_directive", ""),
                    "target_deliverables": assign.get("deliverables", []),
                    "domain_audit_packet": packet,
                    "report_length_chars": len(rep.get("full_text", "")),
                    "report_excerpt": rep.get("full_text", "")[:3500]
                })

            raw_anchor = council_state.get("task_anchor", {})
            anchor_header = TaskAnchor.from_dict(raw_anchor).format_prompt_header() if raw_anchor else ""

            audit_prompt = (
                f"{anchor_header}\n"
                "You are the Council Leader. Perform a rigorous Quality Audit on the Domain Reports and Audit Packets submitted by the Council Members.\n"
                "CRITICAL: Compare each member's submitted Domain Report and empirical packet against both the IMMUTABLE TASK ANCHOR and their required deliverables.\n"
                "Reject any report that strayed into prohibited drift topics (e.g. cloud billing or unrelated infrastructure).\n\n"
                f"AUDIT EVALUATION DATA:\n{json.dumps(eval_payload, indent=2)}\n\n"
                "AUDIT CRITERIA:\n"
                "1. Has the Council Member answered the actual user question and required deliverables without topic drift?\n"
                "2. Check domain_audit_packet: ensure claims are supported by concrete citations ([SOURCE_ID] or live probes). In fact_verification mode, structured tables are accepted.\n"
                "3. If satisfied: assign status 'SATISFIED' and remediation_directive null.\n"
                "4. If deficient or off-topic: assign status 'NEEDS_REVISION' and provide an explicit remediation_directive.\n\n"
                "Return a clean JSON object:\n"
                "{\n"
                '  "all_satisfied": true/false,\n'
                '  "audit_summary": "Assessment of council report completeness...",\n'
                '  "evaluations": [\n'
                '    {\n'
                '      "member_id": "cm1",\n'
                '      "status": "SATISFIED" or "NEEDS_REVISION",\n'
                '      "deliverable_scores": [{"deliverable": "...", "status": "MET" or "MISSING", "notes": "..."}],\n'
                '      "remediation_directive": "Exact remediation instructions if NEEDS_REVISION, else null"\n'
                '    }\n'
                '  ]\n'
                "}"
            )

            # In Round 1 of audit, use Premium Slot 3; in subsequent remediation rounds, use leader_standard
            tier = "leader_premium" if remediation_round == 1 else "leader_standard"
            stage_tag = "phase75_quality_audit" if remediation_round == 1 else f"phase75_quality_audit_r{remediation_round}"

            resp = await model_caller.call_by_tier(
                tier=tier,
                messages=[{"role": "user", "content": audit_prompt}],
                stage_tag=stage_tag,
                max_tokens=2500,
                overall_deadline=120.0,
                run_id=run_id
            )

            # Default fallback strictly sets all_satisfied: False and flags all members for revision
            audit = model_caller.extract_json(resp, default_schema={
                "all_satisfied": False,
                "audit_summary": "Automated audit failed to parse report completeness - flag for review.",
                "evaluations": [{"member_id": m_id, "status": "NEEDS_REVISION", "remediation_directive": "Re-verify empirical deliverables and provide missing claim verifications."} for m_id in assignments]
            })

            evals = audit.get("evaluations", [])
            evals_by_member = {ev.get("member_id"): ev for ev in evals if isinstance(ev, dict)}

            # Mechanical Audit Pre-Check on each member's report & domain_audit_packet
            for m_id in assignments:
                rep = reports_map.get(m_id, {})
                full_txt = rep.get("full_text", "") or ""
                pkt = rep.get("domain_audit_packet", {}) or {}
                mech_reasons = []
                if len(full_txt.strip()) < 20:
                    mech_reasons.append("Domain report text is empty or below minimum substantive length.")
                if pkt:
                    if pkt.get("total_evidence_sources", 1) <= 0 and pkt.get("empirical_agents_verified", 1) <= 0:
                        mech_reasons.append("domain_audit_packet contains 0 evidence sources and 0 verified empirical agents.")
                    if pkt.get("total_claims_generated", 0) > 0 and pkt.get("claims_verified_count", 0) <= 0:
                        mech_reasons.append("domain_audit_packet shows 0 verified claims across generated hypotheses.")
                if mech_reasons:
                    existing_ev = evals_by_member.get(m_id, {"member_id": m_id})
                    existing_ev["status"] = "NEEDS_REVISION"
                    existing_ev["remediation_directive"] = (
                        existing_ev.get("remediation_directive") or " ".join(mech_reasons)
                    )
                    evals_by_member[m_id] = existing_ev
                    if existing_ev not in evals:
                        evals.append(existing_ev)

            # Verification rule: ALL assigned members must exist in evaluations and have status SATISFIED
            all_members_evaluated_satisfied = all(
                evals_by_member.get(m_id, {}).get("status") == "SATISFIED"
                for m_id in assignments
            )
            gate_passed = bool(audit.get("all_satisfied", False)) and all_members_evaluated_satisfied

            audit_entry = {
                "round": remediation_round,
                "all_satisfied": gate_passed,
                "raw_all_satisfied": audit.get("all_satisfied", False),
                "summary": audit.get("audit_summary", ""),
                "evaluations": evals
            }
            audit_history.append(audit_entry)

            if gate_passed:
                print(f"[Council Leader] ✓ Quality Audit PASSED! All {len(assignments)} Council Member deliverables verified.")
                council_state["audit_disposition"] = "VERIFIED_PASS"
                break

            # If not passed, find all members that need revision
            remediation_candidates = []
            for m_id in assignments:
                ev = evals_by_member.get(m_id)
                if not ev or ev.get("status") != "SATISFIED":
                    directive = ev.get("remediation_directive") if ev else None
                    if not directive:
                        directive = f"Re-verify empirical deliverables and substantiate all unverified claims for member {m_id}."
                    remediation_candidates.append({
                        "member_id": m_id,
                        "remediation_directive": directive
                    })

            print(f"[Council Leader] ⚠️ Quality Audit NOT satisfied: {len(remediation_candidates)} deficient report(s) identified:")
            for cand in remediation_candidates:
                print(f"  • {cand.get('member_id', '').upper()}: {cand.get('remediation_directive', '')[:120]}...")

            if remediation_round >= max_remediation_rounds:
                print(f"[Council Leader] Notice: Maximum remediation rounds ({max_remediation_rounds}) reached. Gate remains UNRESOLVED.")
                council_state["audit_disposition"] = "INSUFFICIENT_EVIDENCE_REVISION_UNRESOLVED"
                break

            remediation_tasks = []
            remediated_ids = []
            remediation_assignments = []
            for cand in remediation_candidates:
                m_id = cand["member_id"]
                if m_id in assignments:
                    remediated_ids.append(m_id)
                    # Invalidate cached completed room file so Room 2 actually re-executes remediation
                    room_file = os.path.join(run_dir, f"cm_room_{m_id}.json")
                    if os.path.exists(room_file):
                        try:
                            with open(room_file, "r", encoding="utf-8") as rf:
                                r_data = json.load(rf)
                            r_data["status"] = "remediating"
                            r_data["iterations_run"] = 0
                            if "report" in r_data:
                                r_data["report"]["full_text"] = ""
                            save_json_atomic(room_file, r_data)
                        except Exception:
                            pass

                    augmented_assign = dict(assignments[m_id])
                    original_directive = augmented_assign.get("mission_directive", "")
                    augmented_assign["mission_directive"] = (
                        f"{original_directive}\n\n"
                        f"LEADER QUALITY AUDIT REMEDIATION DIRECTIVE (Round {remediation_round}):\n"
                        f"{cand['remediation_directive']}"
                    )
                    remediation_tasks.append(
                        self.run_council_member_room(augmented_assign, common_context, run_dir=run_dir, run_id=run_id)
                    )
                    remediation_assignments.append(augmented_assign)

            print(f"[Council Leader] Re-invoking Room 2 for member(s): {', '.join(remediated_ids)}...")
            raw_remediation_reports = await asyncio.gather(*remediation_tasks, return_exceptions=True)
            remediated_reports = []
            for r_idx, r_result in enumerate(raw_remediation_reports):
                if isinstance(r_result, BaseException):
                    failed_assign = remediation_assignments[r_idx]
                    failed_id = failed_assign.get(
                        "member_id",
                        remediated_ids[r_idx] if r_idx < len(remediated_ids) else f"cm{r_idx + 1}"
                    )
                    logger.error(f"[Council Leader] Remediation room {failed_id} failed: {r_result}")
                    remediated_reports.append({
                        "member_id": failed_id,
                        "domain": failed_assign.get("domain", f"Domain {r_idx + 1}"),
                        "full_text": f"[DEGRADED REMEDIATION REPORT] Room execution failed: {r_result}",
                        "web_sources_count": 0,
                        "academic_papers_count": 0,
                        "iterations_completed": 0,
                        "domain_audit_packet": {},
                        "papers": [],
                        "sources": [],
                        "completed_at": datetime.utcnow().isoformat(),
                        "degraded": True
                    })
                else:
                    remediated_reports.append(r_result)

            for updated_rep in remediated_reports:
                m_id = updated_rep.get("member_id")
                if m_id:
                    reports_map[m_id] = updated_rep

        council_state["leader_audits"] = audit_history
        self._save_state(council_state)
        return [reports_map.get(m_id, {}) for m_id in assignments]

    # ─────────────────────────────────────────────────────────────
    # Back to ROOM 1: Lossless Stitching & Audit
    # ─────────────────────────────────────────────────────────────

    async def run_phase_8_lossless_stitching(
        self,
        council_state: Dict[str, Any],
        domain_reports: List[Dict[str, Any]],
        run_dir: str = ".",
        run_id: str = "default"
    ) -> str:
        """
        Phase 8: Lossless Dossier Stitching & Master Synthesis.
        Uses Premium Slot 4: gemini-3.8-flash (stage_tag='phase8_master_synthesis').
        Outputs both final_dossier.md and FINAL_VERDICT.md.
        """
        print("\n[Council Room] --- Phase 8: Lossless Dossier Stitching & Final Verdict (Leader [Premium Slot 4]) ---")
        prompt_text = council_state["input"]["user_prompt"]
        context_text = council_state.get("context", {}).get("expanded_context", council_state.get("input", {}).get("user_prompt", ""))
        plan = council_state["final_plan"]

        dossier_sections = [
            f"# COMPREHENSIVE RESEARCH DOSSIER & MULTI-AGENT COUNCIL REPORT\n",
            f"**Research Directive**: {prompt_text}\n",
            f"**Run ID**: {run_id}\n",
            f"**Generated**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n",
            f"**Architecture**: 2-Room / 3-Tier Multi-Agent Engine (Gemini 3.8 Flash + Llama 3.3 70B)\n",
            f"---\n",
            f"## 1. Executive Context & Problem Decomposition\n",
            f"{context_text}\n\n",
            f"---\n",
            f"## 2. Master Council Deliberation Plan\n",
            f"**Common Objective**: {plan.get('common_context', '')}\n\n"
        ]

        # Append each domain report in full (NO compression)
        for idx, rep in enumerate(domain_reports, 1):
            domain_name = rep.get("domain", f"Domain {idx}")
            sources_count = rep.get("web_sources_count", 0)
            papers_count = rep.get("academic_papers_count", 0)
            full_text = rep.get("full_text", "")
            dossier_sections.append(
                f"---\n"
                f"## 3.{idx} Domain {idx}: {domain_name}\n"
                f"*Analyzed across {sources_count} in-depth web sources and {papers_count} academic papers.*\n\n"
                f"{full_text}\n\n"
            )

        # Leader Master Synthesis across all 4 Domain Reports & Structured Audit Packets
        domain_evidence_blocks = []
        for idx, r in enumerate(domain_reports, 1):
            dom = r.get("domain", f"Domain {idx}")
            full = r.get("full_text", "")
            packet = r.get("domain_audit_packet", {})
            v_claims = packet.get("verified_claims", [])
            r_claims = packet.get("refuted_claims", [])
            emp_runs = packet.get("empirical_runs", [])
            
            domain_evidence_blocks.append(
                f"### Domain {idx}: {dom}\n"
                f"• Verified Claims ({len(v_claims)}): {', '.join([c.get('claim_id', '') + ': ' + str(c.get('statement', c.get('claim_statement', '')))[:80] for c in v_claims[:5]])}\n"
                f"• Refuted Claims ({len(r_claims)}): {', '.join([c.get('claim_id', '') for c in r_claims[:3]]) if r_claims else 'None'}\n"
                f"• Empirical Runs: {len(emp_runs)} scripts executed\n"
                f"• Substantive Report Findings:\n{full[:3000]}\n"
            )

        raw_anchor = council_state.get("task_anchor", {})
        anchor_obj = TaskAnchor.from_dict(raw_anchor) if raw_anchor else None
        anchor_header = anchor_obj.format_prompt_header() if anchor_obj else ""
        intent_mode = anchor_obj.intent_mode if anchor_obj else "general_fact"

        if intent_mode == "api_catalog":
            domain_specific_instructions = (
                "2. STRICT EXCLUSIONS: Completely exclude Google AI Studio, Groq, Cloudflare Workers AI, and GitHub Models from your recommended alternatives and matrix. Focus exclusively on verified alternatives: SambaNova, Cohere, Cerebras, Hugging Face, OpenRouter, Together AI.\n"
                "3. CONCRETE OPERATIONAL METRICS: State exact verified numerical values for RPM, RPD, TPM, TPD, and monthly free credits.\n"
                "4. ONBOARDING & VERIFICATION FRICTION: For each provider, state whether Credit Card / SMS / KYC is required and whether API keys are instant.\n"
                "5. FINAL COMPARATIVE MATRIX: Output a clean markdown table with columns:\n"
                "   | Provider | Primary Free Models | RPM / RPD Limits | TPM / Token Limits | Credit Card Required? | Free Data Trained on? | Primary Doc Citation URL |\n"
            )
        elif intent_mode in ("academic_theory", "quantitative_data"):
            domain_specific_instructions = (
                "2. MATHEMATICAL & THEORETICAL RIGOR: Provide exact mathematical formulations, equations, theorems, and proofs directly answering the core user question. Use formal LaTeX equations (e.g. \\frac, \\sum, \\ge, \\le, quorums, bounds) with explicit definitions for all individual variables (e.g. define symbols explicitly such as N = total nodes, T = latency, K = capacity, v = velocity, S = substrate).\n"
                "3. DOMAIN-SPECIFIC QUANTITATIVE OBJECTS:\n"
                "   - Distributed Systems: State concrete latency-throughput trade-off curves, network round trips, and failure quorum bounds (f < n/3 or f < n/2).\n"
                "   - Regulatory Capital: Trace PLA test breaches (Spearman correlation and Kolmogorov-Smirnov test), traffic-light zone transitions (Green -> Amber -> Red), and NMRF Stressed Expected Shortfall (SES) capital add-ons.\n"
                "   - Biochemistry / Kinetics: Detail explicit rate and binding models (e.g. Michaelis-Menten v = \\frac{V_{max}[S]}{K_m + [S]} or Hill equation v = \\frac{V_{max}[S]^n}{K_{0.5}^n + [S]^n}) with each parameter explicitly defined.\n"
                "   - Cryptography & ZK: Detail polynomial commitment schemes (KZG vs FRI), proof sizes in bytes, arithmetic circuit size N, prover complexity O(N \\log N), verifier time, and post-quantum security bits.\n"
                "4. EMPIRICAL PARAMETERS & THRESHOLD BOUNDARIES: Detail exact numerical ranges, critical thresholds, failure boundaries, and falsification criteria.\n"
                "5. EXPLICIT LIMITATIONS & VULNERABILITIES: Disclose concrete failure modes, operational risks, counterexamples, and edge-case vulnerabilities for each evaluated approach.\n"
                "6. CROSS-FACTOR TRADE-OFFS & INTERACTION DYNAMICS: Detail explicit cross-factor trade-offs, architecture interaction dynamics, cascade vulnerabilities, and asymmetric regime shifts.\n"
                "7. FORMAL PRIMARY CITATIONS: Formally cite at least 4 primary academic papers, author names, publication years, and permanent DOI / arXiv identifiers / journal / proceedings publication venues.\n"
                "8. FINAL COMPARATIVE MATRIX: Output a clean markdown table comparing the core models, regimes, frameworks, or entities evaluated in the research directive with columns:\n"
                "   | Paradigm / Entity | Core Mechanism / Invariant | Mathematical Formulation | Critical Threshold / Boundary | Falsification / Failure Condition | Primary Literature Reference (with DOI/arXiv) |\n"
            )
        else:
            domain_specific_instructions = (
                "2. FACTUAL PRECISION: Deliver grounded, verifiable factual findings directly answering the prompt. Use formal LaTeX equations where relevant.\n"
                "3. EXPLICIT LIMITATIONS & VULNERABILITIES: Disclose failure modes, counterexamples, operational risks, and trade-offs.\n"
                "4. COMPARATIVE MATRIX: Output a structured markdown table comparing key entities, trade-offs, and specifications.\n"
                "5. PRIMARY CITATIONS: Formally cite specific official documentation, primary papers, and verifiable URLs with publication years.\n"
            )

        # Collect verified papers and primary sources across all domain rooms
        verified_citations = []
        for r in domain_reports:
            for p in r.get("papers", []):
                if isinstance(p, dict):
                    p_title = p.get("title", "")
                    p_id = p.get("id", "")
                    p_yr = p.get("year", "2023")
                    p_url = p.get("url", "") or (f"https://arxiv.org/abs/{p_id.replace('arxiv:', '')}" if p_id else "")
                    if p_title and p_title not in [c.get("title") for c in verified_citations]:
                        verified_citations.append({"type": "academic_paper", "title": p_title, "ref": p_id, "year": p_yr, "url": p_url})
            for s in r.get("sources", []):
                if isinstance(s, dict):
                    s_title = s.get("title", "")
                    s_url = s.get("url", "")
                    s_dom = s.get("domain", "")
                    IGNORED_DOMAINS = {"abebooks.com", "amazon.com", "magersandquinn.com", "ebay.com", "walmart.com", "books.google.com"}
                    if any(ign in s_dom.lower() for ign in IGNORED_DOMAINS):
                        continue
                    if s_url and s_url not in [c.get("url") for c in verified_citations]:
                        verified_citations.append({"type": "web_source", "title": s_title, "ref": s_dom, "year": "2024", "url": s_url})

        # Parse user prompt into discrete core problem obligations
        problem_splits = re.split(r'\n(?=###?\s*\d+\.|\bProblem\s*\d+:)', prompt_text)
        sub_problems = []
        if len(problem_splits) > 1:
            for sp in problem_splits:
                sp_clean = sp.strip()
                if sp_clean and any(sp_clean.startswith(prefix) for prefix in ["#", "Problem", "1.", "2.", "3.", "4.", "5."]):
                    sub_problems.append(sp_clean)
        
        if not sub_problems or len(sub_problems) < 2:
            # Fallback: treat each domain as a problem obligation
            sub_problems = [r.get("domain", f"Obligation {i+1}") + "\n" + r.get("full_text", "")[:500] for i, r in enumerate(domain_reports)]

        print(f"[Council Room] Decomposed mission into {len(sub_problems)} discrete problem obligations for modular synthesis.")

        synthesized_sections = []

        # Call 8.1: Executive Summary & Comprehensive Claim Audit Table
        table_prompt = (
            f"{anchor_header}\n"
            "You are the Council Leader. Synthesize the 'Executive Summary & Comprehensive Claim Audit Table'.\n"
            "MANDATORY REQUIREMENTS:\n"
            "1. Deliver an executive synthesis directly addressing the core research directive with zero hand-waving.\n"
            "2. Construct a publication-grade Claim Audit Table / Evidence Ledger with columns:\n"
            "   | Claim / Hypothesis | Exact Mathematical Assumptions Required | Governing Primary Citations (Author, Year, Journal/DOI/arXiv ID) | Precise Theorem / Proof Result (Distinguish Proven Theorem vs Extrapolation) | Critical Boundary Caveats / Falsification Conditions |\n"
            "3. Ground each row in an exact theorem or empirical finding from the foundational literature. Avoid overgeneralizations.\n"
            "4. Cover all key claims across the problem obligations and reconcile at least 8 primary academic references.\n\n"
            f"HARVESTED EVIDENCE & DOMAIN REPORTS:\n"
            + "\n".join(domain_evidence_blocks[:2])
        )
        sec_claim_table = await model_caller.call_by_tier(
            tier="leader_premium",
            messages=[{"role": "user", "content": table_prompt}],
            stage_tag="phase8_claim_table",
            max_tokens=3500,
            overall_deadline=120.0,
            run_id=run_id
        )
        synthesized_sections.append(f"## 1. Executive Summary & Claim Audit Table\n\n{sec_claim_table}\n")

        # Calls 8.2 to 8.(K+1): Dedicated Section per Core Problem Obligation
        for p_idx, prob_text in enumerate(sub_problems, 1):
            prob_title_match = re.match(r'^(?:###?\s*\d+\.?\s*|Problem\s*\d+:?\s*)([^\n]+)', prob_text)
            prob_title = prob_title_match.group(1).strip() if prob_title_match else f"Problem {p_idx} In-Depth Derivation"

            print(f"[Council Room] Synthesizing Section {p_idx+1}: {prob_title[:60]} (Dedicated 4096-token call)...")
            
            # Detect whether this problem obligation requires code from generic directive
            # keywords only. Domain-specific finance/physics phrases previously hardcoded
            # code/no-code decisions for unrelated prompts.
            prob_lower = prob_text.lower()
            wants_code = any(kw in prob_lower for kw in [
                "pseudocode", "python", "code block", "code deliverable", "solver",
                "numerical discretization", "numerical simulation", "estimator implementation",
                "algorithm implementation", "reference implementation", "reproducible script"
            ]) and not any(kw in prob_lower for kw in ["no code", "without code", "pure theoretical proof only"])

            if wants_code:
                code_directive = (
                    "7. MANDATORY PYTHON CODE DELIVERABLE:\n"
                    "   - Provide a complete, self-contained, syntactically valid Python implementation in a single ```python ... ``` block.\n"
                    "   - Implement the primary numerical algorithm specified in the problem directive above. Keep the script compact and concise (under 80 lines) so it never truncates.\n"
                    "   - Use standard library `math`, `numpy`, `scipy`, or another approved scientific package. DO NOT use deprecated APIs.\n"
                    "   - Include full type annotations and docstrings.\n"
                    "   - Include a self-contained test harness under `if __name__ == '__main__':` with realistic parameters and explicit numerical assertions.\n"
                    "   - Complete all lines, brackets, and fences. NEVER leave incomplete lines or pass placeholders.\n"
                    "   - Deterministic Verification Output: The test harness MUST explicitly print verification results upon completing all assertions, including 'PASS' or 'PASSED: ... violations: 0' to stdout."
                )
            else:
                code_directive = (
                    "7. STRICT PROHIBITION ON CODE: DO NOT write any Python code, pseudocode blocks, or scripts in this section. "
                    "Dedicate 100% of your output tokens to exhaustive step-by-step mathematical derivations, formal LaTeX proofs, "
                    "exact scaling exponents, and theoretical boundary resolutions. Zero code blocks."
                )

            section_prompt = (
                f"{anchor_header}\n"
                f"You are the Council Leader. Provide the exhaustive mathematical and algorithmic resolution for:\n\n"
                f"--- PROBLEM DIRECTIVE ---\n{prob_text}\n-------------------------\n\n"
                "RIGID MATHEMATICAL & ALGORITHMIC REQUIREMENTS:\n"
                f"{MATH_FORMAT_CONTRACT}"
                "5. Directly address every sub-question (a), (b), (c) in full detail. Check dimensions and scaling exponents.\n"
                "6. Actively identify and resolve any deliberate theoretical traps or boundary failures mentioned in the directive.\n"
                f"{code_directive}\n"
                "8. Cite primary foundational literature (author, year, paper title, permanent arXiv ID / DOI).\n\n"
                f"HARVESTED EVIDENCE ACROSS COUNCIL ROOMS:\n"
                + "\n".join([f"Evidence Block {i+1}:\n" + r.get("full_text", "")[:2500] for i, r in enumerate(domain_reports)])
            )

            sec_content = await model_caller.call_by_tier(
                tier="leader_premium",
                messages=[{"role": "user", "content": section_prompt}],
                stage_tag=f"phase8_section_{p_idx}",
                max_tokens=4096,
                overall_deadline=180.0,
                run_id=run_id
            )

            # Enforce code fence parity immediately
            if sec_content.count("```") % 2 != 0:
                print(f"[Council Room] Section {p_idx+1} has unclosed code fence. Balancing cleanly...")
                sec_content += "\n```\n"

            # If this section was strictly prohibited from code, but an incomplete python fence leaked, clean it
            if not wants_code and "```python" in sec_content:
                # Remove unrequested code blocks in pure theory sections to avoid token waste
                clean_sec = re.sub(r'```python.*?```', '', sec_content, flags=re.DOTALL)
                if len(clean_sec.strip()) > 300:
                    sec_content = clean_sec

            synthesized_sections.append(f"## {p_idx+1}. {prob_title}\n\n{sec_content}\n")

        # Call 8.K+2: Unresolved Problems & Non-Identifiable Parameter Bounds
        unresolved_domain = anchor_obj.target_domain if anchor_obj else "the research directive"
        unresolved_prompt = (
            f"{anchor_header}\n"
            "You are the Council Leader. Formulate the concluding section on:\n"
            "'Unresolved Problems, Non-Identifiable Parameter Bounds & Critical Research Frontiers'.\n"
            f"Apply every requirement strictly to the research directive and target domain: {unresolved_domain}.\n"
            "MANDATORY REQUIREMENTS:\n"
            "1. Structural Calibration Bottlenecks: Explicitly analyze the ill-posed inverse problem or parameter-estimation bottleneck specific to this domain, including optimization-landscape geometry and sensitivity to noisy or incomplete inputs.\n"
            "2. Non-Identifiability & Degeneracy Under Discrete Observations: Provide concrete mathematical parameter bounds showing how sampling resolution, measurement noise, or observation gaps limit identifiability, and identify the exact likelihood flatness or degeneracy between coupled parameters.\n"
            "3. Real-World Execution Friction: Detail how finite sampling, measurement error, resource constraints, and feedback effects within the directive's domain bound practical performance.\n"
            "4. Empirical Falsification Boundaries: Formulate exact, falsifiable statistical hypotheses derived from the directive's governing equations, including the observable signatures that would refute them.\n"
            "Cite primary foundational literature for each point. Avoid qualitative filler or generic rhetoric."
        )
        sec_unresolved = await model_caller.call_by_tier(
            tier="leader_premium",
            messages=[{"role": "user", "content": unresolved_prompt}],
            stage_tag="phase8_unresolved",
            max_tokens=3500,
            overall_deadline=100.0,
            run_id=run_id
        )
        synthesized_sections.append(f"## {len(sub_problems)+2}. Unresolved Problems & Non-Identifiable Parameter Bounds\n\n{sec_unresolved}\n")

        # Code Extraction, AST Validation & Execution-Driven Self-Repair
        execution_certificates = []
        from script_runner import SandboxedScriptRunner, validate_script_ast
        runner = SandboxedScriptRunner()
        total_code_blocks = 0

        for s_idx, sec_text in enumerate(synthesized_sections):
            py_blocks = re.findall(r'```python\s*(.*?)\s*```', sec_text, re.DOTALL)
            for orig_block in py_blocks:
                clean_block = orig_block.strip()
                if not clean_block or not any(k in clean_block for k in ["def ", "class ", "import ", "assert ", "="]):
                    continue

                total_code_blocks += 1
                b_idx = total_code_blocks
                print(f"[Code Sandbox] Inspecting Code Block {b_idx} for syntax and runtime validity...")

                is_passed = False
                last_error = ""
                final_exec_res = {}
                max_repair_attempts = 3

                for attempt in range(1, max_repair_attempts + 1):
                    # 1. AST syntax validation
                    ast_errs = validate_script_ast(clean_block)
                    if ast_errs:
                        last_error = f"SyntaxError / AST Issue: {ast_errs[0]}"
                    else:
                        # 2. Sandboxed execution in scrubbed subprocess
                        try:
                            exec_res = await runner.execute_script(
                                script_id=f"verify_block_{b_idx}_att_{attempt}",
                                code_str=clean_block,
                                timeout_seconds=15.0
                            )
                            final_exec_res = exec_res
                            if exec_res.get("success"):
                                is_passed = True
                                print(f"[Code Sandbox] ✓ Block {b_idx} executed cleanly (EXIT_CODE_0 in {exec_res.get('runtime_seconds', 0.0):.2f}s).")
                                break
                            else:
                                err_diag = exec_res.get("stderr", "").strip() or str(exec_res.get("errors", "")).strip() or "Runtime error / non-zero exit code"
                                last_error = f"Runtime Crash:\n{err_diag}"
                        except Exception as ex:
                            last_error = f"Execution Exception: {ex}"

                    print(f"[Code Sandbox] ⚠️ Block {b_idx} attempt {attempt}/{max_repair_attempts} failed:\n{last_error[:250]}\nInitiating automated Gemini self-repair...")

                    # 3. Targeted Gemini Repair Pass
                    repair_prompt = (
                        "You are an expert Python engineer and quantitative researcher.\n"
                        "The following Python code failed execution in our sandboxed test runner with this runtime error:\n\n"
                        f"```\n{last_error[:1200]}\n```\n\n"
                        f"Failing Code:\n```python\n{clean_block}\n```\n\n"
                        "CRITICAL FIX REQUIREMENTS:\n"
                        "1. Fix the root cause of the error. Resolve all TypeErrors, NameErrors, indexing bugs, or failed assertions.\n"
                        "2. Ensure all data structures have consistent types (e.g. if checking membership with 'in', ensure the variable is a set/list/dict, NOT an int or primitive).\n"
                        "3. Ensure the test harness executes completely to exit code 0 when run with Python 3.12/3.13.\n"
                        "4. Output ONLY the complete, corrected, executable Python code inside a single ```python ... ``` block. No markdown conversation.\n"
                    )

                    try:
                        repaired_resp = await model_caller.call_by_tier(
                            tier="council_member",
                            messages=[{"role": "user", "content": repair_prompt}],
                            max_tokens=4096,
                            run_id=run_id
                        )
                        fixed_match = re.search(r'```python\s*(.*?)\s*```', repaired_resp, re.DOTALL)
                        if fixed_match and fixed_match.group(1).strip():
                            clean_block = fixed_match.group(1).strip()
                    except Exception as e:
                        logger.warning(f"Repair call attempt {attempt} failed: {e}")

                # If code was improved or changed, update the actual synthesized section!
                if clean_block != orig_block.strip():
                    if f"```python\n{orig_block}\n```" in synthesized_sections[s_idx]:
                        synthesized_sections[s_idx] = synthesized_sections[s_idx].replace(f"```python\n{orig_block}\n```", f"```python\n{clean_block}\n```")
                    elif orig_block in synthesized_sections[s_idx]:
                        synthesized_sections[s_idx] = synthesized_sections[s_idx].replace(orig_block, clean_block)
                    print(f"[Code Sandbox] ✓ Section text updated with repaired Block {b_idx} (Passed: {is_passed}).")

                import hashlib
                code_hash = hashlib.sha256(clean_block.encode('utf-8')).hexdigest()[:12]
                first_line = clean_block.splitlines()[0] if clean_block.splitlines() else "Python Block"
                code_title = first_line.replace('"""', '').replace("'''", "").strip() or f"Block {b_idx}"

                if is_passed:
                    stdout_clean = final_exec_res.get("stdout", "").strip()[:800]
                    execution_certificates.append(
                        f"#### Sandbox Execution Certificate (Block {b_idx}: `{code_title[:50]}`, Hash: `{code_hash}`)\n"
                        f"- **AST Status**: `VALID_SYNTAX`\n"
                        f"- **Execution Status**: `EXIT_CODE_0` (Runtime: {final_exec_res.get('runtime_seconds', 0.0):.2f}s)\n"
                        f"- **Execution Output**:\n```\n{stdout_clean}\n```\n"
                    )
                else:
                    execution_certificates.append(
                        f"#### Sandbox Execution Audit (Block {b_idx}: `{code_title[:50]}`, Hash: `{code_hash}`)\n"
                        f"- **Execution Status**: ⚠️ `RUNTIME_EXCEPTION`\n"
                        f"- **Diagnostics**: `{last_error[:300]}`\n"
                    )

        if execution_certificates:
            synthesized_sections.append(
                f"## {len(sub_problems)+3}. Sandboxed Empirical Code Verification & Execution Certificates\n\n"
                + "\n\n".join(execution_certificates) + "\n"
            )

        # Primary Harvested Citations Block
        citation_block = "\n\n### Primary Literature & Verifiable Citations (Harvested Ground Truth)\n"
        if verified_citations:
            for i, c in enumerate(verified_citations[:12], 1):
                if c["type"] == "academic_paper":
                    ref_str = f" (`{c['ref']}`)" if c['ref'] else ""
                    url_str = f" | [Primary Paper URL]({c['url']})" if c['url'] else ""
                    citation_block += f"{i}. **{c['title']}** ({c['year']}){ref_str}{url_str}\n"
                else:
                    citation_block += f"{i}. **{c['title']}** (Domain: `{c['ref']}`) | [Primary Source URL]({c['url']})\n"
        synthesized_sections.append(citation_block)

        leader_synthesis = "\n\n".join(synthesized_sections)

        audit_disp = council_state.get("audit_disposition", "UNKNOWN")
        if audit_disp != "VERIFIED_PASS":
            warning_block = (
                f"> [!WARNING]\n"
                f"> **LEADER AUDIT GATE DISPOSITION**: `{audit_disp}`\n"
                f"> Notice: One or more domain deliverables or claim verifications did not reach verified status during the automated audit gate.\n\n"
            )
            dossier_sections.insert(4, warning_block)

        telemetry_table = model_caller.get_telemetry_markdown_table(run_id=run_id)
        dossier_sections.append(
            f"---\n"
            f"## 4. Master Modular Synthesis & Cross-Domain Decision Matrix (Leader Audit)\n\n"
            f"{leader_synthesis}\n\n"
            f"---\n"
            f"## 5. Provider & Model Execution Telemetry\n\n"
            f"{telemetry_table}\n"
        )

        final_dossier = "\n".join(dossier_sections)

        # Save final_dossier.md inside run directory and root mirror
        run_dossier_path = os.path.join(run_dir, "final_dossier.md")
        with open(run_dossier_path, "w", encoding="utf-8") as f:
            f.write(final_dossier)
        with open("final_dossier.md", "w", encoding="utf-8") as f:
            f.write(final_dossier)

        # Also generate standalone FINAL_VERDICT.md for executive review
        audit_badge = f"**Audit Disposition**: `{audit_disp}`" if audit_disp == "VERIFIED_PASS" else f"**Audit Disposition**: ⚠️ `{audit_disp}`"
        verdict_content = (
            f"# INSTITUTIONAL VERDICT & STRATEGIC RECOMMENDATION\n\n"
            f"**Run ID**: {run_id} | **Date**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
            f"{audit_badge}\n\n"
            f"{leader_synthesis}\n\n"
            f"---\n"
            f"*Generated by Council v5 Multi-Agent Engine with Modular Synthesis & Sandboxed AST Code Verification.*"
        )
        run_verdict_path = os.path.join(run_dir, "FINAL_VERDICT.md")
        with open(run_verdict_path, "w", encoding="utf-8") as f:
            f.write(verdict_content)
        with open("FINAL_VERDICT.md", "w", encoding="utf-8") as f:
            f.write(verdict_content)

        final_status = "completed" if audit_disp == "VERIFIED_PASS" else "completed_with_audit_warnings"
        council_state["status"] = final_status
        council_state["execution"] = {
            "completed_at": datetime.utcnow().isoformat(),
            "dossier_file": run_dossier_path,
            "verdict_file": run_verdict_path,
            "audit_disposition": audit_disp,
            "dossier_length_chars": len(final_dossier)
        }
        print(f"[Council Leader] ✓ Final Dossier ({len(final_dossier)} chars) and FINAL_VERDICT.md generated with status '{final_status}'.")
        return final_dossier

    # ─────────────────────────────────────────────────────────────
    # Full Orchestration Pipeline
    # ─────────────────────────────────────────────────────────────

    async def execute(self, user_prompt: str, resume_dir: Optional[str] = None) -> str:
        """Executes the complete dual-room deliberation & deep execution pipeline with optional resumption."""
        if resume_dir and os.path.isdir(resume_dir) and os.path.exists(os.path.join(resume_dir, "council_room.json")):
            run_dir = resume_dir
            council_room_path = os.path.join(run_dir, "council_room.json")
            with open(council_room_path, "r", encoding="utf-8") as f:
                council_state = json.load(f)
            run_uuid = council_state.get("run_id", "resumed")
            print("================================================================")
            print("    RESUMING MULTI-AGENT COUNCIL FROM CHECKPOINTED STATE        ")
            print("================================================================")
            print(f"• Resumed Run Directory: {run_dir}")
            print(f"• Run UUID: {run_uuid}")
            print(f"• Checkpointed Status: {council_state.get('status')}")
        else:
            run_timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            run_uuid = str(uuid.uuid4())[:8]
            run_dir = os.path.join("runs", f"run_{run_timestamp}_{run_uuid}")
            os.makedirs(run_dir, exist_ok=True)
            council_room_path = os.path.join(run_dir, "council_room.json")

            print("================================================================")
            print("    STARTING MULTI-AGENT COUNCIL DELIBERATION & DEEP RESEARCH   ")
            print("================================================================")
            print(f"• Run Directory: {run_dir}")
            print(f"• Run UUID: {run_uuid}")
            print(f"• Target Sources per Domain: {self.target_pages}")

            council_state = {
                "schema_version": "2.0",
                "run_id": run_uuid,
                "run_dir": run_dir,
                "status": "initializing",
                "created_at": datetime.utcnow().isoformat(),
                "input": {
                    "user_prompt": user_prompt,
                    "requested_output": "Comprehensive Multi-Domain Deep Dossier"
                }
            }
            save_json_atomic(council_room_path, council_state)

        # Reset 4-call premium budget tracker for this run
        key_rotator.reset_for_run(run_uuid, force=False)
        key_rotator.print_status()

        # Room 1: Deliberation Tier
        if "context" not in council_state or not council_state.get("context", {}).get("expanded_context"):
            await self.run_phase_1_context_expansion(user_prompt, council_state, run_id=run_uuid)
            save_json_atomic(council_room_path, council_state)
        else:
            print("[Council Room] ✓ Phase 1 already completed in checkpoint. Skipping.")

        if "initial_plan" not in council_state:
            await self.run_phase_2_initial_plan(council_state, run_id=run_uuid)
            save_json_atomic(council_room_path, council_state)
        else:
            print("[Council Room] ✓ Phase 2 (Initial Plan) already completed in checkpoint. Skipping.")

        rounds = council_state.get("rounds", [])
        if len(rounds) < 1:
            await self.run_council_deliberation_round(round_num=1, council_state=council_state, run_id=run_uuid)
            save_json_atomic(council_room_path, council_state)
        else:
            print("[Council Room] ✓ Deliberation Round 1 already completed in checkpoint. Skipping.")

        if "synthesis_round_1" not in council_state:
            await self.run_phase_4_leader_synthesis(council_state, run_id=run_uuid)
            save_json_atomic(council_room_path, council_state)
        else:
            print("[Council Room] ✓ Phase 4 (Leader Synthesis) already completed in checkpoint. Skipping.")

        rounds = council_state.get("rounds", [])
        if len(rounds) < 2:
            await self.run_council_deliberation_round(round_num=2, council_state=council_state, run_id=run_uuid)
            save_json_atomic(council_room_path, council_state)
        else:
            print("[Council Room] ✓ Deliberation Round 2 already completed in checkpoint. Skipping.")

        if "final_plan" not in council_state:
            final_plan = await self.run_phase_6_final_plan_generation(council_state, run_id=run_uuid)
            save_json_atomic(council_room_path, council_state)
        else:
            final_plan = council_state["final_plan"]
            print("[Council Room] ✓ Phase 6 (Final Plan) already completed in checkpoint. Skipping.")

        # Room 2: Domain Orchestrators & Worker Pools (Run in parallel with optional room stagger!)
        common_context = final_plan.get("common_context", "")
        assignments = final_plan.get("member_assignments", [])
        eff_mode = final_plan.get("execution_mode", self.execution_mode)

        print("\n================================================================")
        print(f"  LAUNCHING {len(assignments)} DOMAIN ORCHESTRATOR ROOM(S) CONCURRENTLY [{eff_mode.upper()}]   ")
        print("================================================================")

        async def _launch_staggered_room(idx: int, assign: Dict[str, Any]) -> Dict[str, Any]:
            if idx > 0 and self.room_stagger_sec > 0:
                await asyncio.sleep(idx * self.room_stagger_sec)
            return await self.run_council_member_room(assign, common_context, run_dir=run_dir, run_id=run_uuid, execution_mode=eff_mode)

        tasks = [_launch_staggered_room(idx, assign) for idx, assign in enumerate(assignments)]
        raw_domain_reports = await asyncio.gather(*tasks, return_exceptions=True)
        domain_reports = []
        for r_idx, r_result in enumerate(raw_domain_reports):
            if isinstance(r_result, BaseException):
                failed_assign = assignments[r_idx]
                failed_id = failed_assign.get("member_id", f"cm{r_idx + 1}")
                logger.error(f"[Council Room] Domain room {failed_id} failed: {r_result}")
                domain_reports.append({
                    "member_id": failed_id,
                    "domain": failed_assign.get("domain", f"Domain {r_idx + 1}"),
                    "full_text": (
                        f"[DEGRADED DOMAIN REPORT] Room execution failed after retries: {r_result}. "
                        "No empirical evidence or claims were produced for this domain."
                    ),
                    "web_sources_count": 0,
                    "academic_papers_count": 0,
                    "iterations_completed": 0,
                    "domain_audit_packet": {},
                    "papers": [],
                    "sources": [],
                    "completed_at": datetime.utcnow().isoformat(),
                    "degraded": True
                })
            else:
                domain_reports.append(r_result)

        # Room 1 Leader Quality Audit Gate & Targeted Remediation Loopback
        audited_reports = await self.run_phase_7_leader_audit_gate(
            council_state=council_state,
            domain_reports=domain_reports,
            run_dir=run_dir,
            run_id=run_uuid,
            max_remediation_rounds=2
        )

        # Back to Room 1: Final Lossless Stitching & Final Verdict
        final_dossier = await self.run_phase_8_lossless_stitching(council_state, audited_reports, run_dir=run_dir, run_id=run_uuid)

        self._save_state(council_state)
        return final_dossier


council_engine = CouncilEngine()
