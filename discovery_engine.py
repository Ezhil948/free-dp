"""
discovery_engine.py
Dynamic Canonical Root and Official Documentation Discovery Engine.
Integrates:
1. Wikidata P856 ('official website') structured entity property lookup (zero auth, 100% free)
2. Tavily AI Search API for agent-grade discovery and extraction
3. Dynamic query generation tailored to TaskAnchor domain/roles without hardcoding
4. tldextract domain normalization
"""

import os
import re
import json
import time
import shutil
import asyncio
import logging
import threading
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse
import httpx
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("DiscoveryEngine")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

try:
    import tldextract
except ImportError:
    tldextract = None

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None

SEARCH_CACHE_FILE = os.path.join("scratch", "search_cache.json")
MAX_TAVILY_CALLS_PER_RUN = int(os.getenv("MAX_TAVILY_CALLS_PER_RUN", "3"))

_cache_lock = threading.Lock()

# Global telemetry tracking for Tavily API calls
TAVILY_TELEMETRY: Dict[str, Any] = {
    "search_calls": 0,
    "extract_calls": 0,
    "cache_hits": 0,
    "blocked_by_budget": 0,
    "queries": []
}


def _load_cache() -> Dict[str, Any]:
    if os.path.exists(SEARCH_CACHE_FILE):
        try:
            with open(SEARCH_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_cache(cache: Dict[str, Any]):
    os.makedirs("scratch", exist_ok=True)
    tmp_path = f"{SEARCH_CACHE_FILE}.{os.getpid()}.{time.time_ns()}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
        for attempt in range(5):
            try:
                os.replace(tmp_path, SEARCH_CACHE_FILE)
                return
            except (PermissionError, OSError):
                time.sleep(0.05 * (attempt + 1))
        shutil.copyfile(tmp_path, SEARCH_CACHE_FILE)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def get_cached_search(provider: str, query: str, limit: int = 5) -> Optional[List[Dict[str, Any]]]:
    key = f"{provider}:{query.strip().lower()}:{limit}"
    with _cache_lock:
        cache = _load_cache()
        entry = cache.get(key)
        if entry and isinstance(entry, dict):
            return entry.get("results")
        return None


def set_cached_search(provider: str, query: str, limit: int, results: List[Dict[str, Any]]):
    key = f"{provider}:{query.strip().lower()}:{limit}"
    with _cache_lock:
        cache = _load_cache()
        cache[key] = {
            "timestamp": time.time(),
            "results": results
        }
        _save_cache(cache)



def normalize_domain(url: str) -> str:
    """Extract registered domain (e.g. 'docs.sambanova.ai' -> 'sambanova.ai')."""
    if not url:
        return ""
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    parsed = urlparse(url)
    hostname = parsed.netloc.lower().split(":")[0]
    if tldextract:
        ext = tldextract.extract(url)
        if ext.domain and ext.suffix:
            return f"{ext.domain}.{ext.suffix}".lower()
    parts = hostname.split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return hostname


async def discover_wikidata_roots(entity_name: str, client: Optional[httpx.AsyncClient] = None) -> List[Dict[str, Any]]:
    """
    Query Wikidata API for entity P856 ('official website').
    Completely open, free, zero API key required.
    """
    results = []
    own_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=10.0, headers={"User-Agent": "ResearchEngineCouncil/4.0 (contact@council.local)"})
        own_client = True

    try:
        search_url = "https://www.wikidata.org/w/api.php"
        search_params = {
            "action": "wbsearchentities",
            "search": entity_name,
            "language": "en",
            "format": "json",
            "limit": 3
        }
        resp = await client.get(search_url, params=search_params)
        if resp.status_code != 200:
            return []
        data = resp.json()
        search_items = data.get("search", [])
        if not search_items:
            return []

        for item in search_items[:2]:
            entity_id = item.get("id")
            label = item.get("label", "")
            description = item.get("description", "")
            
            # Fetch entity claims
            entity_url = f"https://www.wikidata.org/wiki/Special:EntityData/{entity_id}.json"
            ent_resp = await client.get(entity_url)
            if ent_resp.status_code != 200:
                continue
            ent_data = ent_resp.json()
            entities_dict = ent_data.get("entities", {})
            entity_obj = entities_dict.get(entity_id, {})
            claims = entity_obj.get("claims", {})
            
            # P856 is the 'official website' property in Wikidata
            p856_claims = claims.get("P856", [])
            for claim in p856_claims:
                mainsnak = claim.get("mainsnak", {})
                datavalue = mainsnak.get("datavalue", {})
                website_val = datavalue.get("value")
                if website_val and isinstance(website_val, str) and website_val.startswith("http"):
                    norm_dom = normalize_domain(website_val)
                    results.append({
                        "entity": entity_name,
                        "label": label,
                        "description": description,
                        "url": website_val,
                        "domain": norm_dom,
                        "source": "wikidata_p856",
                        "confidence": 0.95
                    })
    except Exception as e:
        logger.debug(f"Wikidata lookup failed for {entity_name}: {e}")
    finally:
        if own_client:
            await client.aclose()

    return results


def search_tavily_sync(
    query: str,
    api_key: Optional[str] = None,
    search_depth: str = "advanced",
    max_results: int = 5,
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Execute AI-native web search via Tavily API with persistent disk caching
    and strict per-run quota throttling (MAX_TAVILY_CALLS_PER_RUN).
    """
    # 1. Check persistent disk cache first (Zero credit cost)
    cached = get_cached_search("tavily", query, max_results)
    if cached is not None:
        with _cache_lock:
            TAVILY_TELEMETRY["cache_hits"] += 1
            if query not in TAVILY_TELEMETRY["queries"]:
                TAVILY_TELEMETRY["queries"].append(f"{query} [CACHE HIT]")
        logger.info(f"[Tavily Cache] Hit for query '{query}' (0 credits consumed).")
        return cached

    # 2. Check total Tavily budget for this run
    with _cache_lock:
        total_calls = TAVILY_TELEMETRY["search_calls"] + TAVILY_TELEMETRY["extract_calls"]
        if total_calls >= MAX_TAVILY_CALLS_PER_RUN:
            TAVILY_TELEMETRY["blocked_by_budget"] += 1
            logger.warning(
                f"[Tavily Throttler] Run quota cap reached ({total_calls}/{MAX_TAVILY_CALLS_PER_RUN} calls used). "
                f"Skipping network call for query '{query}' to conserve user credits."
            )
            return []

    key = api_key or os.getenv("TAVILY_API_KEY")
    if not key:
        logger.warning("TAVILY_API_KEY missing from environment.")
        return []

    try:
        with _cache_lock:
            TAVILY_TELEMETRY["search_calls"] += 1
            TAVILY_TELEMETRY["queries"].append(query)
        client = TavilyClient(api_key=key)
        kwargs: Dict[str, Any] = {
            "query": query,
            "search_depth": search_depth,
            "max_results": max_results,
            "include_raw_content": False,
            "include_answer": False
        }
        if include_domains:
            kwargs["include_domains"] = include_domains
        if exclude_domains:
            kwargs["exclude_domains"] = exclude_domains

        res = client.search(**kwargs)
        raw_items = res.get("results", [])
        cleaned = []
        for item in raw_items:
            url = item.get("url", "")
            cleaned.append({
                "title": item.get("title", ""),
                "url": url,
                "domain": normalize_domain(url),
                "snippet": item.get("content", ""),
                "score": item.get("score", 0.0),
                "source": "tavily"
            })
        
        # Save to persistent disk cache
        set_cached_search("tavily", query, max_results, cleaned)
        return cleaned
    except Exception as e:
        logger.error(f"Tavily search failed for query '{query}': {e}")
        return []


async def search_tavily(
    query: str,
    api_key: Optional[str] = None,
    search_depth: str = "advanced",
    max_results: int = 5,
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """Async wrapper around Tavily search."""
    return await asyncio.to_thread(
        search_tavily_sync,
        query=query,
        api_key=api_key,
        search_depth=search_depth,
        max_results=max_results,
        include_domains=include_domains,
        exclude_domains=exclude_domains
    )


def extract_tavily_sync(urls: List[str], api_key: Optional[str] = None) -> List[Dict[str, Any]]:
    """Directly extract clean markdown for URLs using Tavily's extract API with quota limits."""
    key = api_key or os.getenv("TAVILY_API_KEY")
    if not key or not urls:
        return []

    # Check budget
    with _cache_lock:
        total_calls = TAVILY_TELEMETRY["search_calls"] + TAVILY_TELEMETRY["extract_calls"]
        if total_calls >= MAX_TAVILY_CALLS_PER_RUN:
            TAVILY_TELEMETRY["blocked_by_budget"] += 1
            logger.warning(
                f"[Tavily Throttler] Run quota cap reached ({total_calls}/{MAX_TAVILY_CALLS_PER_RUN}). "
                f"Skipping Tavily extract for {len(urls)} URLs."
            )
            return []

    try:
        with _cache_lock:
            TAVILY_TELEMETRY["extract_calls"] += 1
        client = TavilyClient(api_key=key)
        res = client.extract(urls=urls)
        results = res.get("results", [])
        return [{
            "url": r.get("url", ""),
            "raw_content": r.get("raw_content", ""),
            "domain": normalize_domain(r.get("url", ""))
        } for r in results if r.get("raw_content")]
    except Exception as e:
        logger.error(f"Tavily extract failed for {len(urls)} URLs: {e}")
        return []


async def extract_tavily(urls: List[str], api_key: Optional[str] = None) -> List[Dict[str, Any]]:
    """Async wrapper around Tavily extract."""
    return await asyncio.to_thread(extract_tavily_sync, urls=urls, api_key=api_key)


async def dynamic_canonical_discovery(
    entities: List[str],
    domain_category: str = "software_api",
    max_candidates_per_entity: int = 4
) -> List[Dict[str, Any]]:
    """
    Topic-agnostic canonical root discovery:
    1. Wikidata P856 property lookup for each entity (100% free).
    2. Skip Tavily if Wikidata found the official site.
    3. Aggregation and domain deduplication.
    """
    candidates: List[Dict[str, Any]] = []
    seen_domains = set()

    async with httpx.AsyncClient(timeout=12.0) as http_client:
        for entity in entities:
            clean_name = entity.strip()
            if not clean_name:
                continue

            # Step 1: Query Wikidata P856 (Zero credit cost)
            wiki_roots = await discover_wikidata_roots(clean_name, client=http_client)
            for w in wiki_roots:
                dom = w["domain"]
                if dom and dom not in seen_domains:
                    seen_domains.add(dom)
                    candidates.append({
                        "entity": clean_name,
                        "canonical_url": w["url"],
                        "domain": dom,
                        "discovery_path": "wikidata_p856",
                        "initial_trust_score": 3.0,
                        "description": w.get("description", "")
                    })

            # Step 2: Query Tavily ONLY if Wikidata found nothing AND we have budget
            with _cache_lock:
                total_calls = TAVILY_TELEMETRY["search_calls"] + TAVILY_TELEMETRY["extract_calls"]
            
            if not wiki_roots and total_calls < MAX_TAVILY_CALLS_PER_RUN:
                if domain_category == "software_api":
                    queries = [
                        f'"{clean_name}" official documentation API rate limits'
                    ]
                elif domain_category == "financial_regulation":
                    queries = [
                        f'"{clean_name}" official regulatory guidance statute'
                    ]
                elif domain_category == "biological_mechanism":
                    queries = [
                        f'"{clean_name}" official mechanism study clinical trial'
                    ]
                else:
                    queries = [
                        f'"{clean_name}" official documentation technical specifications'
                    ]

                for q in queries:
                    tav_results = await search_tavily(q, max_results=3)
                    for r in tav_results:
                        url = r["url"]
                        dom = r["domain"]
                        if not dom:
                            continue
                        
                        existing = next((c for c in candidates if c["domain"] == dom), None)
                        if existing:
                            existing["initial_trust_score"] += 2.0
                            existing["consensus_citations"] = existing.get("consensus_citations", 1) + 1
                        elif dom not in seen_domains:
                            seen_domains.add(dom)
                            candidates.append({
                                "entity": clean_name,
                                "canonical_url": url,
                                "domain": dom,
                                "discovery_path": "tavily_search_consensus",
                                "initial_trust_score": 2.0,
                                "snippet": r.get("snippet", ""),
                                "consensus_citations": 1
                            })

    return candidates

