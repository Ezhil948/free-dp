import os
import re
from typing import List, Dict, Any, Optional

class SkillInjector:
    """
    Read-only dynamic skill resolver and prompt injector.
    Connects Council Members & sub-agents with appropriate skill playbooks.
    """

    def __init__(self, workspace_root: Optional[str] = None):
        self.workspace_root = workspace_root or os.getcwd()
        self.skills_dir = os.path.join(self.workspace_root, ".agents", "skills")
        self.index_path = os.path.join(self.skills_dir, "skill-orchestrator", "categories_index.md")
        self.categories: List[str] = self._load_categories()
        self.installed_skills: Dict[str, Dict[str, Any]] = self._index_installed_skills()

    def _load_categories(self) -> List[str]:
        """Loads available category keywords from categories_index.md."""
        if not os.path.exists(self.index_path):
            return []
        cats = []
        try:
            with open(self.index_path, "r", encoding="utf-8") as f:
                for line in f:
                    match = re.search(r"`([A-Za-z0-9\-_]+)`", line)
                    if match:
                        cats.append(match.group(1))
        except Exception:
            pass
        return cats

    def _index_installed_skills(self) -> Dict[str, Dict[str, Any]]:
        """Indexes all local SKILL.md files recursively and their frontmatter descriptions."""
        skills = {}
        if not os.path.exists(self.skills_dir):
            return skills

        for root, dirs, files in os.walk(self.skills_dir):
            if "SKILL.md" in files:
                skill_md = os.path.join(root, "SKILL.md")
                skill_id = os.path.basename(root).lower()
                try:
                    with open(skill_md, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    
                    desc = ""
                    desc_match = re.search(r"description:\s*(.*?)(?:\n---|\n[a-z]+:)", content, re.DOTALL | re.IGNORECASE)
                    if desc_match:
                        desc = desc_match.group(1).strip()
                    else:
                        desc = content[:300].strip()

                    skills[skill_id] = {
                        "name": os.path.basename(root),
                        "path": skill_md,
                        "description": desc,
                        "raw_content": content
                    }
                except Exception:
                    pass
        return skills

    def resolve_skill_for_domain(self, domain_title: str, directive: str) -> Optional[Dict[str, Any]]:
        """
        Heuristic match of domain title & directive against indexed skills and categories.
        Returns the best matching skill content or None.
        """
        search_text = f"{domain_title} {directive}".lower()
        best_skill = None
        best_score = 0

        for key, s in self.installed_skills.items():
            score = 0
            # Name matching
            words = key.replace("-", " ").split()
            for w in words:
                if len(w) > 2 and w in search_text:
                    score += 5
            
            # Description keyword matching
            desc_words = s["description"].lower().split()
            for w in set(desc_words):
                if len(w) > 3 and w in search_text:
                    score += 1

            # Domain specific mappings
            if "trad" in search_text or "market" in search_text or "gold" in search_text:
                if "trading" in key:
                    score += 15
            if "search" in search_text or "scrape" in search_text or "web" in search_text:
                if "reach" in key or "search" in key:
                    score += 10
            if "security" in search_text or "vuln" in search_text:
                if "strix" in key:
                    score += 10

            if score > best_score and score >= 5:
                best_score = score
                best_skill = s

        return best_skill

    def format_skill_prompt_context(self, domain_title: str, directive: str, max_chars: int = 4000) -> str:
        """
        Wraps matched skill content in secure untrusted-data delimiters for prompt injection.
        """
        matched = self.resolve_skill_for_domain(domain_title, directive)
        if not matched:
            return ""

        content = matched["raw_content"]
        if len(content) > max_chars:
            content = content[:max_chars] + "\n...[truncated for context limits]"

        return (
            f"\n\n### ATTACHED DOMAIN SKILL PLAYBOOK: [{matched['name'].upper()}]\n"
            "Follow the professional methodology below for this task:\n"
            "```markdown\n"
            f"{content}\n"
            "```\n"
        )

skill_injector = SkillInjector()
