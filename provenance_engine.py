"""
provenance_engine.py
Domain Provenance & Primary Source Verification Engine.
Evaluates candidate URLs against mathematical authority signals:
- Wikidata P856 match (+3)
- Root domain or official docs/api path (+3)
- Subdomain indicators (docs., developer., api., console.) (+2)
- Multi-query search consensus (+2)
- Aggregator / listicle / affiliate penalty (-4)
- Excluded vendor gate for API-catalog mode only (Google AI Studio, Groq, Cloudflare, GitHub) (-10)
Assigns: VERIFIED_OFFICIAL (>=5.0), POSSIBLY_OFFICIAL (3.0-4.9), UNVERIFIED (<3.0).
"""

import re
import logging
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger("ProvenanceEngine")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# Known consumer blog / content-farm / aggregator domains that must never be treated as primary sources
GENERIC_AGGREGATOR_DOMAINS = {
    "medium.com", "dev.to", "reddit.com", "quora.com", "geeksforgeeks.org",
    "towardsdatascience.com", "hackernoon.com", "techtarget.com", "zapier.com",
    "makeuseof.com", "freecodecamp.org", "wikipedia.org", "w3schools.com",
    "stackoverflow.com", "stackexchange.com", "youtube.com", "facebook.com",
    "twitter.com", "x.com", "linkedin.com", "pinterest.com", "tiktok.com"
}

# Strictly prohibited benchmarked providers for the current evaluation task
EXCLUDED_DOMAINS = {
    "aistudio.google.com", "groq.com", "cloudflare.com", "github.com",
    "ai.google.dev", "console.groq.com", "workers.cloudflare.com"
}


def evaluate_domain_provenance(
    url: str,
    entity_name: str,
    discovery_path: str = "search_consensus",
    consensus_citations: int = 1,
    initial_score: float = 0.0,
    domain_category: str = "software_api",
    intent_mode: str = "general_fact"
) -> Dict[str, Any]:
    """
    Score the authority and provenance of a candidate URL.

    ``EXCLUDED_DOMAINS`` only applies to API-catalog evaluation runs. Academic and quantitative
    research may legitimately depend on GitHub reference implementations, Cloudflare/Google
    documentation, and vendor engineering blogs.
    """
    parsed = urlparse(url)
    hostname = parsed.netloc.lower().split(":")[0]
    path = parsed.path.lower()
    
    score = initial_score
    reasons = []

    # 1. Excluded Vendor Check (scoped strictly to API-catalog evaluations)
    if intent_mode == "api_catalog":
        for ex in EXCLUDED_DOMAINS:
            if ex in hostname:
                return {
                    "url": url,
                    "hostname": hostname,
                    "score": -10.0,
                    "status": "REJECTED_EXCLUDED_VENDOR",
                    "reasons": [f"Matches strictly excluded provider: {ex}"]
                }

    # 2. Aggregator / Listicle Penalty
    for ag in GENERIC_AGGREGATOR_DOMAINS:
        if ag in hostname:
            score -= 4.0
            reasons.append(f"Penalty: Known aggregator / blog domain ({ag})")
            break

    # 3. Wikidata Official Website match
    if discovery_path == "wikidata_p856":
        score += 3.0
        reasons.append("Wikidata P856 structured official website match (+3)")

    # 4. Search consensus
    if consensus_citations >= 2:
        bonus = min(consensus_citations * 1.0, 3.0)
        score += bonus
        reasons.append(f"Search consensus agreement ({consensus_citations} hits, +{bonus:.1f})")

    # 5. Technical Documentation Path / Subdomain Indicators
    docs_subdomains = ("docs.", "developer.", "developers.", "api.", "console.", "platform.")
    if any(hostname.startswith(sub) for sub in docs_subdomains):
        score += 2.0
        reasons.append("Official developer/docs subdomain (+2)")

    docs_paths = ("/docs", "/documentation", "/api", "/reference", "/pricing", "/developer")
    if any(path.startswith(dp) or dp in path for dp in docs_paths):
        score += 2.0
        reasons.append(f"Primary documentation/pricing path ({path}) (+2)")

    # 6. Entity name matching domain
    clean_entity = re.sub(r"[^a-zA-Z0-9]", "", entity_name.lower())
    clean_host = re.sub(r"[^a-zA-Z0-9]", "", hostname)
    if clean_entity and clean_entity in clean_host:
        score += 1.5
        reasons.append(f"Entity name '{entity_name}' matches domain root (+1.5)")

    # Assign Trust Status
    if score >= 5.0:
        status = "VERIFIED_OFFICIAL"
    elif score >= 3.0:
        status = "POSSIBLY_OFFICIAL"
    else:
        status = "UNVERIFIED"

    return {
        "url": url,
        "hostname": hostname,
        "score": round(score, 2),
        "status": status,
        "is_verified": (status == "VERIFIED_OFFICIAL"),
        "reasons": reasons
    }


def filter_verified_sources(
    candidates: List[Dict[str, Any]],
    min_score: float = 4.5,
    intent_mode: str = "general_fact"
) -> List[Dict[str, Any]]:
    """Filter candidate sources to strictly keep verified and high-confidence sources."""
    verified = []
    for cand in candidates:
        url = cand.get("canonical_url") or cand.get("url")
        if not url:
            continue
        entity = cand.get("entity", "")
        disc_path = cand.get("discovery_path", "search_consensus")
        citations = cand.get("consensus_citations", 1)
        init_s = cand.get("initial_trust_score", 0.0)

        eval_res = evaluate_domain_provenance(
            url=url,
            entity_name=entity,
            discovery_path=disc_path,
            consensus_citations=citations,
            initial_score=init_s,
            intent_mode=intent_mode
        )
        if eval_res["score"] >= min_score and eval_res["status"] != "REJECTED_EXCLUDED_VENDOR":
            merged = dict(cand)
            merged.update(eval_res)
            verified.append(merged)
        else:
            logger.debug(f"Source rejected: {url} (Score {eval_res['score']}, Status: {eval_res['status']})")

    return verified

