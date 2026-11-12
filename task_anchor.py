import os
import re
import json
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional

@dataclass
class TaskAnchor:
    """
    Immutable typed task anchor passed to every prompt and audit gate in Council v3.
    Extracts core goals, entities, deliverables, exclusions, and domain intent
    to prevent semantic drift across multi-agent handoffs.
    """
    raw_prompt: str
    target_domain: str
    core_question: str
    required_deliverables: List[str] = field(default_factory=list)
    eligible_entities: List[str] = field(default_factory=list)
    prohibited_drift: List[str] = field(default_factory=list)
    intent_mode: str = "general_fact"  # "api_catalog" | "quantitative_data" | "academic_theory" | "general_fact"
    harvest_academic_papers: bool = False
    script_execution_required: bool = False
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskAnchor":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def format_prompt_header(self) -> str:
        """
        Renders an unyielding context header injected at the top of every phase,
        worker, deliberation room, and audit prompt.
        """
        entities_str = ", ".join(self.eligible_entities) if self.eligible_entities else "Any relevant to the core question"
        drift_str = ", ".join(self.prohibited_drift) if self.prohibited_drift else "Off-topic subjects, unrelated domains"
        deliverables_str = "\n".join(f"  - {d}" for d in self.required_deliverables) if self.required_deliverables else "  - Complete, grounded factual answers"

        return (
            "================================================================================\n"
            "CRITICAL TASK ANCHOR (IMMUTABLE MISSION GOAL - NEVER DEVIATE OR SUBSTITUTE):\n"
            f"Target Domain:       {self.target_domain}\n"
            f"Core User Question:  {self.core_question}\n"
            f"Eligible Entities:   {entities_str}\n"
            f"Prohibited Drift:    {drift_str}\n"
            f"Intent Mode:         {self.intent_mode.upper()}\n"
            "Required Deliverables:\n"
            f"{deliverables_str}\n"
            "================================================================================\n"
        )

    def validate_query(self, query: str) -> bool:
        """
        Determines whether a proposed search query stays within the task anchor
        and does not stray into prohibited drift topics.
        """
        q_lower = query.lower()
        # Check against prohibited drift phrases and individual drift tokens
        for drift in self.prohibited_drift:
            d_lower = drift.lower()
            # Check full phrase match
            has_drift_phrase = d_lower in q_lower
            # Check individual tokens (words with > 3 chars like 'terraform', 'cloudwatch', 'alarms')
            drift_words = [w for w in re.findall(r'\w+', d_lower) if len(w) > 4 and w not in {"cloud", "about", "their", "under"}]
            has_drift_word = any(dw in q_lower for dw in drift_words)

            if has_drift_phrase or has_drift_word:
                # If target domain keyword is not present to anchor it, reject
                domain_tokens = [w for w in re.findall(r'\w+', self.target_domain.lower()) if len(w) > 3]
                if not any(dt in q_lower for dt in domain_tokens):
                    return False
        return True


def build_fallback_task_anchor(user_prompt: str) -> TaskAnchor:
    """Deterministic fallback anchor if LLM extraction fails or is offline."""
    prompt_lower = user_prompt.lower()
    
    # Classify intent mode
    is_api = any(k in prompt_lower for k in ["api", "endpoint", "free tier", "rate limit", "token", "tpm", "rpm", "model list"])
    is_academic = any(k in prompt_lower for k in [
        "paper", "arxiv", "theorem", "proof", "literature", "academic", "journal", 
        "cite", "citation", "peer-reviewed", "biochemistry", "molecular", "pdb", 
        "physics", "plasma", "tokamak", "mhd", "regulatory", "basel", "frtb", 
        "mechanism", "mechanics", "formal", "inhibition", "clinical", "biology", "scientific",
        "snark", "stark", "zero-knowledge", "plonk", "cryptography", "post-quantum", "kyber",
        "dilithium", "lattice", "contagion", "liquidity cascade", "erasure coding", "quorum",
        "allosteric", "enzyme", "cooperativity", "hill equation", "michaelis", "eisenberger"
    ])
    is_data = any(k in prompt_lower for k in ["dataset", "parquet", "csv", "sql", "backtest", "metrics", "gold", "xauusd", "vpin", "quantitative"])

    if is_academic:
        intent = "academic_theory"
        harvest_papers = True
        scripts_req = bool(is_data)
        prohibited = ["Informal blog posts", "Marketing copy", "Unverified opinion pieces"]
    elif is_api:
        intent = "api_catalog"
        harvest_papers = False
        scripts_req = False
        prohibited = ["Cloud billing infrastructure", "AWS/GCP cost budgets", "Terraform alarms", "Idle CPU metrics"]
    elif is_data:
        intent = "quantitative_data"
        harvest_papers = True if any(k in prompt_lower for k in ["cite", "literature", "easley", "kyle", "paper"]) else False
        scripts_req = True
        prohibited = ["Unverified qualitative opinions", "Speculative trading claims"]
    else:
        intent = "general_fact"
        harvest_papers = False
        scripts_req = False
        prohibited = ["Unrelated tangential topics"]

    # Extract target domain from first significant nouns
    words = [w for w in re.findall(r'[a-zA-Z0-9_\-]+', user_prompt) if len(w) > 3 and w.lower() not in {"what", "which", "where", "there", "about", "could", "would", "should"}]
    domain = " ".join(words[:4]) if words else "Target Research Subject"

    return TaskAnchor(
        raw_prompt=user_prompt,
        target_domain=domain,
        core_question=user_prompt.strip(),
        required_deliverables=["Comprehensive factual analysis addressing all aspects of the user prompt."],
        eligible_entities=[],
        prohibited_drift=prohibited,
        intent_mode=intent,
        harvest_academic_papers=harvest_papers,
        script_execution_required=scripts_req
    )
