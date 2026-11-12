"""
search_worker.py
Upgraded Council v4 Web Research Engine.
Integrates:
1. Tavily AI Search as primary search backend (replaces flaky DuckDuckGo scraping)
2. Provenance Engine for domain authority scoring and spam/listicle rejection
3. Multi-Tier Content Extractor (Trafilatura static + Jina Reader cloud JS fallback + bot-challenge gate)
4. Preserves backward-compatible ResearchSource interface.
"""

import os
import asyncio
import re
import logging
from typing import List, Dict, Any, Optional
import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from discovery_engine import search_tavily, normalize_domain
from provenance_engine import evaluate_domain_provenance, filter_verified_sources
from content_extractor import extract_clean_content, is_bot_challenge

load_dotenv()
logger = logging.getLogger("SearchWorker")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


class ResearchSource:
    def __init__(
        self,
        ref_id: str,
        url: str,
        title: str,
        snippet: str,
        content: str,
        domain: str = "",
        provenance_score: float = 5.0,
        is_verified: bool = True
    ):
        self.ref_id = ref_id
        self.url = url
        self.title = title
        self.snippet = snippet
        self.content = content
        self.domain = domain or normalize_domain(url)
        self.provenance_score = provenance_score
        self.is_verified = is_verified

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ref_id": self.ref_id,
            "url": self.url,
            "title": self.title,
            "snippet": self.snippet,
            "domain": self.domain,
            "provenance_score": self.provenance_score,
            "is_verified": self.is_verified,
            "content": self.content[:25000],
            "content_preview": self.content[:300] + ("..." if len(self.content) > 300 else ""),
            "length_chars": len(self.content)
        }


class DeepWebResearcher:
    """Council v4 High-Precision Web Research Engine."""

    def __init__(self, max_concurrent_fetches: int = 12, timeout_seconds: float = 12.0):
        self.max_concurrent_fetches = max_concurrent_fetches
        self.timeout = timeout_seconds

    async def search_candidates(
        self,
        queries: List[str],
        max_results_per_query: int = 6,
        intent_mode: str = "general_fact"
    ) -> List[Dict[str, Any]]:
        """Collect and evaluate candidate URLs using Tavily AI Search and Provenance scoring."""
        candidates = []
        seen_urls = set()

        has_tavily = bool(os.getenv("TAVILY_API_KEY"))
        if has_tavily:
            logger.info(f"[DeepResearch] Executing Tavily AI search across {len(queries)} query angles...")
            for q in queries:
                try:
                    tav_results = await search_tavily(q, max_results=max_results_per_query)
                    for r in tav_results:
                        url = r.get("url")
                        if url and url not in seen_urls and not url.endswith((".pdf", ".exe", ".zip", ".jpg", ".png")):
                            seen_urls.add(url)
                            # Evaluate provenance
                            prov = evaluate_domain_provenance(
                                url=url,
                                entity_name="",
                                discovery_path="tavily",
                                intent_mode=intent_mode
                            )
                            if prov["status"] != "REJECTED_EXCLUDED_VENDOR":
                                candidates.append({
                                    "url": url,
                                    "title": r.get("title", ""),
                                    "snippet": r.get("snippet", ""),
                                    "domain": prov["hostname"],
                                    "provenance_score": prov["score"],
                                    "is_verified": prov["is_verified"]
                                })
                except Exception as e:
                    logger.warning(f"Tavily search error on query '{q}': {e}")
        else:
            logger.warning("[DeepResearch] TAVILY_API_KEY not found. Falling back to DuckDuckGo...")
            try:
                from duckduckgo_search import DDGS
                ddgs = DDGS()
                for q in queries:
                    try:
                        res = list(ddgs.text(q, max_results=max_results_per_query))
                        for r in res:
                            url = r.get("href")
                            if url and url not in seen_urls and not url.endswith((".pdf", ".exe", ".zip", ".jpg", ".png")):
                                seen_urls.add(url)
                                prov = evaluate_domain_provenance(
                                    url=url,
                                    entity_name="",
                                    intent_mode=intent_mode
                                )
                                if prov["status"] != "REJECTED_EXCLUDED_VENDOR":
                                    candidates.append({
                                        "url": url,
                                        "title": r.get("title", ""),
                                        "snippet": r.get("body", ""),
                                        "domain": prov["hostname"],
                                        "provenance_score": prov["score"],
                                        "is_verified": prov["is_verified"]
                                    })
                    except Exception as de:
                        logger.debug(f"DDGS query error: {de}")
            except Exception as e:
                logger.error(f"Fallback search error: {e}")

        # Sort candidates so highest authority provenance candidates come first
        candidates.sort(key=lambda c: c.get("provenance_score", 0.0), reverse=True)
        return candidates

    async def fetch_page_content(
        self,
        client: httpx.AsyncClient,
        item: Dict[str, Any],
        sem: asyncio.Semaphore
    ) -> Optional[Dict[str, Any]]:
        """Extract clean readable content via Multi-Tier Extraction Cascade."""
        url = item["url"]
        async with sem:
            ext_res = await extract_clean_content(url, client=client, timeout=self.timeout)
            if ext_res["is_valid"] and ext_res["content"]:
                return {
                    "url": url,
                    "title": item.get("title") or url,
                    "snippet": item.get("snippet", ""),
                    "domain": item.get("domain") or normalize_domain(url),
                    "provenance_score": item.get("provenance_score", 5.0),
                    "is_verified": item.get("is_verified", True),
                    "content": ext_res["content"][:35000]
                }
            return None

    async def deep_research(
        self,
        queries: List[str],
        target_page_count: int = 15,
        id_prefix: str = "SRC-OFFICIAL",
        start_index: int = 1,
        intent_mode: str = "general_fact"
    ) -> List[ResearchSource]:
        """Conduct high-precision deep research using Tavily, Provenance scoring, and Extraction cascade."""
        print(f"[DeepResearch] Initiating AI-native primary source sweep across {len(queries)} queries...")
        candidates = await self.search_candidates(
            queries,
            max_results_per_query=max(5, target_page_count // len(queries) + 3),
            intent_mode=intent_mode
        )
        print(f"[DeepResearch] Discovered {len(candidates)} candidate primary sources. Extracting verified content...")

        to_scrape = candidates[:target_page_count + 10]
        sem = asyncio.Semaphore(self.max_concurrent_fetches)

        async with httpx.AsyncClient(limits=httpx.Limits(max_keepalive_connections=20, max_connections=40), follow_redirects=True) as client:
            tasks = [self.fetch_page_content(client, item, sem) for item in to_scrape]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        sources = []
        ref_counter = start_index
        for res in results:
            if isinstance(res, dict) and res.get("content"):
                source = ResearchSource(
                    ref_id=f"{id_prefix}-{ref_counter:03d}",
                    url=res["url"],
                    title=res["title"],
                    snippet=res["snippet"],
                    content=res["content"],
                    domain=res.get("domain", ""),
                    provenance_score=res.get("provenance_score", 5.0),
                    is_verified=res.get("is_verified", True)
                )
                sources.append(source)
                ref_counter += 1
                if len(sources) >= target_page_count:
                    break

        print(f"[DeepResearch] ✓ Successfully verified and extracted {len(sources)} authoritative primary sources.")
        return sources


def format_sources_for_prompt(sources: List[Any], max_chars_per_source: int = 4000) -> str:
    """Formats research sources into a dense evidence block with reference IDs for model consumption."""
    evidence_blocks = []
    for s in sources:
        ref_id = s.get("ref_id", "REF") if isinstance(s, dict) else getattr(s, "ref_id", "REF")
        title = s.get("title", "") if isinstance(s, dict) else getattr(s, "title", "")
        url = s.get("url", "") if isinstance(s, dict) else getattr(s, "url", "")
        content = s.get("content", "") if isinstance(s, dict) else getattr(s, "content", "")
        domain = s.get("domain", "") if isinstance(s, dict) else getattr(s, "domain", "")
        score = s.get("provenance_score", "") if isinstance(s, dict) else getattr(s, "provenance_score", "")
        evidence_blocks.append(
            f"--- BEGIN PRIMARY REFERENCE [{ref_id}] (Domain: {domain} | Trust: {score}) ---\n"
            f"TITLE: {title}\n"
            f"URL: {url}\n"
            f"CONTENT:\n{str(content)[:max_chars_per_source]}\n"
            f"--- END PRIMARY REFERENCE [{ref_id}] ---\n"
        )
    return "\n\n".join(evidence_blocks)
