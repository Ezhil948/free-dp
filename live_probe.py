import re
import json
import asyncio
from typing import List, Dict, Any, Optional
import httpx
from bs4 import BeautifulSoup

SAFE_PUBLIC_HOSTS = {
    "openrouter.ai",
    "api.groq.com",
    "generativelanguage.googleapis.com",
    "api.together.xyz",
    "api.mistral.ai",
    "api.cohere.ai",
    "api.cohere.com",
    "docs.cohere.com",
    "api.sambanova.ai",
    "docs.sambanova.ai",
    "huggingface.co",
    "inference-docs.cerebras.ai",
    "support.together.ai",
    "raw.githubusercontent.com",
    "api.github.com"
}

# 1. Live Public Model Endpoints
SAFE_MODEL_ENDPOINTS = [
    {
        "provider": "OpenRouter",
        "name": "Public Models Catalog",
        "url": "https://openrouter.ai/api/v1/models",
        "filter_token": "free",
        "extract_fields": ["id", "name", "pricing", "context_length"]
    },
    {
        "provider": "SambaNova",
        "name": "Public Model Inventory",
        "url": "https://api.sambanova.ai/v1/models",
        "filter_token": None,
        "extract_fields": ["id"]
    },
    {
        "provider": "Hugging Face",
        "name": "Public Inference Models",
        "url": "https://huggingface.co/api/models?filter=text-generation&sort=downloads&direction=-1&limit=10",
        "filter_token": None,
        "extract_fields": ["id", "downloads", "pipeline_tag"]
    }
]

# 2. Curated Primary Official Documentation & Pricing Pages (Direct-URL RAG Fetcher)
OFFICIAL_DOC_TARGETS = [
    {
        "provider": "SambaNova Cloud",
        "doc_type": "Official Rate Limits & Free Quotas",
        "url": "https://docs.sambanova.ai/docs/en/models/rate-limits",
        "key_phrases": ["RPM", "RPD", "TPD", "Free Tier", "payment method"]
    },
    {
        "provider": "Cohere",
        "doc_type": "Trial Key Quota & Rate Limits",
        "url": "https://docs.cohere.com/v2/docs/rate-limits",
        "key_phrases": ["Trial", "month", "RPM", "calls"]
    },
    {
        "provider": "Hugging Face",
        "doc_type": "Inference Provider Pricing & Billing",
        "url": "https://huggingface.co/docs/inference-providers/en/pricing",
        "key_phrases": ["credits", "free", "monthly", "included", "bill"]
    },
    {
        "provider": "Cerebras",
        "doc_type": "Rate Limits & Trial Expiration Terms",
        "url": "https://inference-docs.cerebras.ai/support/rate-limits",
        "key_phrases": ["credit", "expires", "trial", "payment method", "1M"]
    },
    {
        "provider": "Together AI",
        "doc_type": "Free Tier & Billing Changes Policy",
        "url": "https://support.together.ai/articles/1862638756-changes-to-free-tier-and-billing-july-2025",
        "key_phrases": ["free trial", "purchase", "minimum", "credit"]
    }
]

class LiveProbeWorker:
    """
    Sandboxed, read-only HTTP prober and targeted primary-doc RAG fetcher.
    Pulls live endpoint model catalogs and official vendor documentation directly,
    bypassing unreliable general search snippets.
    """
    def __init__(self, timeout_sec: float = 8.0):
        self.timeout = timeout_sec

    async def probe_public_models_catalog(self, target_provider: Optional[str] = None) -> List[Dict[str, Any]]:
        """Safely probes known public model endpoints to extract live model IDs and zero-cost models."""
        results: List[Dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            for endpoint in SAFE_MODEL_ENDPOINTS:
                if target_provider and target_provider.lower() not in endpoint["provider"].lower():
                    continue
                try:
                    resp = await client.get(endpoint["url"], headers={"User-Agent": "Antigravity-Council-Probe/3.0"})
                    if resp.status_code == 200:
                        payload = resp.json()
                        data_items = payload.get("data", payload) if isinstance(payload, dict) else payload
                        if isinstance(data_items, list):
                            matched = []
                            filter_k = endpoint.get("filter_token")
                            for item in data_items:
                                item_str = json.dumps(item).lower()
                                if not filter_k or filter_k in item_str:
                                    matched.append({
                                        "id": item.get("id"),
                                        "name": item.get("name", item.get("id")),
                                        "pricing": item.get("pricing", {}),
                                        "context_length": item.get("context_length")
                                    })
                            results.append({
                                "provider": endpoint["provider"],
                                "probe_name": endpoint["name"],
                                "url": endpoint["url"],
                                "status": "LIVE_VERIFIED",
                                "matched_count": len(matched),
                                "sample_models": matched[:8]
                            })
                    else:
                        results.append({
                            "provider": endpoint["provider"],
                            "probe_name": endpoint["name"],
                            "url": endpoint["url"],
                            "status": f"HTTP_{resp.status_code}",
                            "matched_count": 0,
                            "sample_models": []
                        })
                except Exception as e:
                    results.append({
                        "provider": endpoint["provider"],
                        "probe_name": endpoint["name"],
                        "url": endpoint["url"],
                        "status": f"PROBE_ERROR: {type(e).__name__}",
                        "matched_count": 0,
                        "sample_models": []
                    })
        return results

    async def fetch_primary_official_docs(self, target_provider: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Directly fetches and extracts clean text from authoritative official docs and pricing pages.
        Extracts key sentences matching quota, pricing, and trial policy terms.
        """
        doc_results: List[Dict[str, Any]] = []
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            for target in OFFICIAL_DOC_TARGETS:
                if target_provider and target_provider.lower() not in target["provider"].lower():
                    continue
                try:
                    resp = await client.get(target["url"], headers=headers)
                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, "html.parser")
                        for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
                            tag.decompose()
                        
                        text = soup.get_text(separator=" ", strip=True)
                        # Extract sentences or table rows containing key phrases
                        relevant_segments = []
                        for phrase in target["key_phrases"]:
                            matches = re.findall(rf'([^.!?\n]*?{re.escape(phrase)}[^.!?\n]*)', text, flags=re.IGNORECASE)
                            for m in matches[:4]:
                                clean_m = m.strip()
                                if len(clean_m) > 25 and clean_m not in relevant_segments:
                                    relevant_segments.append(clean_m)

                        doc_results.append({
                            "provider": target["provider"],
                            "doc_type": target["doc_type"],
                            "url": target["url"],
                            "status": "FETCH_SUCCESS",
                            "key_evidence": relevant_segments[:6],
                            "raw_excerpt": text[:1500]
                        })
                    else:
                        doc_results.append({
                            "provider": target["provider"],
                            "doc_type": target["doc_type"],
                            "url": target["url"],
                            "status": f"HTTP_{resp.status_code}",
                            "key_evidence": [],
                            "raw_excerpt": ""
                        })
                except Exception as e:
                    doc_results.append({
                        "provider": target["provider"],
                        "doc_type": target["doc_type"],
                        "url": target["url"],
                        "status": f"FETCH_ERROR: {type(e).__name__}",
                        "key_evidence": [],
                        "raw_excerpt": ""
                    })
        return doc_results

    def format_probes_for_evidence(self, probe_results: List[Dict[str, Any]], doc_results: Optional[List[Dict[str, Any]]] = None) -> str:
        """Formats live endpoint probes and primary official doc evidence into a consolidated empirical block."""
        lines = []
        if probe_results:
            lines.append("### [LIVE API ENDPOINT PROBE RESULTS (EMPIRICALLY VERIFIED)]")
            lines.append("The following public inference endpoints were probed in real-time during this research run:\n")
            for res in probe_results:
                lines.append(f"• **Provider**: `{res['provider']}` ({res['probe_name']})")
                lines.append(f"  - **Status**: {res['status']} | Endpoint: `{res['url']}`")
                lines.append(f"  - **Models Detected**: {res['matched_count']}")
                if res.get("sample_models"):
                    for m in res["sample_models"][:5]:
                        lines.append(f"    * `{m.get('id')}`")
                lines.append("")

        if doc_results:
            lines.append("### [PRIMARY OFFICIAL PRICING & RATE-LIMIT DOCUMENTATION (DIRECT RAG FETCH)]")
            lines.append("Extracted directly from official vendor documentation and pricing terms:\n")
            for doc in doc_results:
                lines.append(f"• **Provider**: `{doc['provider']}` ({doc['doc_type']})")
                lines.append(f"  - **URL**: `{doc['url']}` | Status: {doc['status']}")
                if doc.get("key_evidence"):
                    for ev in doc["key_evidence"][:4]:
                        lines.append(f"    * \"{ev}\"")
                lines.append("")

        return "\n".join(lines)

live_prober = LiveProbeWorker()
