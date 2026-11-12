"""
content_extractor.py
Multi-Tier Content Extraction & Bot-Defense Cascade.
Flow:
1. HTTPX async GET with browser headers -> Trafilatura extraction (fast, clean markdown, strips boilerplate)
2. If status is 202/403/429 or Trafilatura returns <200 chars (JS hydration), pipe through Jina Reader (https://r.jina.ai/{url})
3. If still challenged or blocked, tag STATUS_INACCESSIBLE and discard immediately.
"""

import re
import asyncio
import logging
from typing import Dict, Any, Optional
import httpx
import trafilatura

logger = logging.getLogger("ContentExtractor")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

BOT_CHALLENGE_PATTERNS = [
    r"cloudflare", r"turnstile", r"just a moment\.\.\.", r"verify you are human",
    r"cf-chl-widget", r"access denied", r"attention required", r"ddos protection",
    r"robot check", r"captcha", r"please enable javascript"
]
BOT_CHALLENGE_REGEX = re.compile("|".join(BOT_CHALLENGE_PATTERNS), re.IGNORECASE)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache"
}


def is_bot_challenge(text: str) -> bool:
    """Detect if scraped text is a bot challenge or access block."""
    if not text:
        return True
    first_1000 = text[:1000].lower()
    matches = BOT_CHALLENGE_REGEX.findall(first_1000)
    # If text is extremely short and contains challenge terms
    if len(text) < 1500 and len(matches) >= 1:
        return True
    # If multiple distinct challenge terms appear
    if len(set(matches)) >= 2:
        return True
    return False


async def fetch_via_jina_reader(url: str, client: Optional[httpx.AsyncClient] = None) -> Optional[str]:
    """
    Fallback extraction using Jina Reader (https://r.jina.ai/{url}).
    Renders JavaScript in the cloud, strips noise, and returns clean Markdown.
    Completely free up to 20 RPM with zero API key!
    """
    jina_url = f"https://r.jina.ai/{url}"
    headers = {
        "User-Agent": "CouncilResearchBot/4.0",
        "X-Return-Format": "markdown"
    }
    own_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=15.0)
        own_client = True

    try:
        resp = await client.get(jina_url, headers=headers)
        if resp.status_code == 200:
            md = resp.text
            if md and not is_bot_challenge(md) and len(md.strip()) > 150:
                return md.strip()
    except Exception as e:
        logger.debug(f"Jina Reader fetch failed for {url}: {e}")
    finally:
        if own_client:
            await client.aclose()
    return None


async def extract_clean_content(
    url: str,
    client: Optional[httpx.AsyncClient] = None,
    timeout: float = 12.0
) -> Dict[str, Any]:
    """
    Execute the multi-tier extraction cascade for a given URL.
    Returns:
    {
        "url": url,
        "content": markdown_or_text,
        "extraction_method": "trafilatura" | "jina_reader" | "failed",
        "char_count": int,
        "is_valid": bool,
        "status": "SUCCESS" | "BOT_CHALLENGE" | "INACCESSIBLE"
    }
    """
    own_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=timeout, headers=DEFAULT_HEADERS, follow_redirects=True)
        own_client = True

    try:
        # Tier 1: Static Fast Path via HTTPX + Trafilatura
        resp = await client.get(url)
        status_code = resp.status_code

        # If HTTP 200, try Trafilatura
        if status_code == 200:
            html = resp.text
            if not is_bot_challenge(html):
                extracted = trafilatura.extract(
                    html,
                    output_format="markdown",
                    favor_precision=True,
                    include_comments=False,
                    include_tables=True,
                    include_links=True
                )
                if extracted and len(extracted.strip()) >= 200 and not is_bot_challenge(extracted):
                    return {
                        "url": url,
                        "content": extracted.strip(),
                        "extraction_method": "trafilatura",
                        "char_count": len(extracted.strip()),
                        "is_valid": True,
                        "status": "SUCCESS"
                    }

        # Tier 2: Cloud JS/Hydration Fallback via Jina Reader
        logger.info(f"Tier 1 insufficient for {url} (HTTP {status_code}). Escalating to Tier 2 (Jina Reader)...")
        jina_content = await fetch_via_jina_reader(url, client=client)
        if jina_content and len(jina_content) >= 200 and not is_bot_challenge(jina_content):
            return {
                "url": url,
                "content": jina_content,
                "extraction_method": "jina_reader",
                "char_count": len(jina_content),
                "is_valid": True,
                "status": "SUCCESS"
            }

        # Tier 3: Inaccessible / Challenged
        return {
            "url": url,
            "content": "",
            "extraction_method": "failed",
            "char_count": 0,
            "is_valid": False,
            "status": "BOT_CHALLENGE" if status_code in (403, 202) else "INACCESSIBLE"
        }

    except Exception as e:
        logger.debug(f"Extraction error for {url}: {e}")
        # Final emergency fallback to Jina Reader
        try:
            jina_content = await fetch_via_jina_reader(url, client=client)
            if jina_content and len(jina_content) >= 200 and not is_bot_challenge(jina_content):
                return {
                    "url": url,
                    "content": jina_content,
                    "extraction_method": "jina_reader_emergency",
                    "char_count": len(jina_content),
                    "is_valid": True,
                    "status": "SUCCESS"
                }
        except Exception:
            pass

        return {
            "url": url,
            "content": "",
            "extraction_method": "error",
            "char_count": 0,
            "is_valid": False,
            "status": "ERROR"
        }
    finally:
        if own_client:
            await client.aclose()


async def batch_extract_content(urls: list[str], max_concurrency: int = 6) -> list[Dict[str, Any]]:
    """Batch extract multiple URLs with concurrency bounding."""
    sem = asyncio.Semaphore(max_concurrency)
    async with httpx.AsyncClient(timeout=15.0, headers=DEFAULT_HEADERS, follow_redirects=True) as client:
        async def _worker(u):
            async with sem:
                return await extract_clean_content(u, client=client)
        tasks = [_worker(u) for u in urls]
        return await asyncio.gather(*tasks)

