import os
import re
import sys
import json
import httpx
import asyncio
import urllib.parse
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional, Set

class AcademicPaperHarvester:
    """
    High-speed, resilient research paper harvester querying arXiv, OpenAlex, 
    and CrossRef with bounded timeouts, PDF parsing, and strict deduplication.
    """

    def __init__(self, cache_dir: str = "scratch/papers_cache"):
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)
        self.seen_identifiers: Set[str] = set()

    def _normalize_id(self, text: str) -> str:
        """Normalizes DOIs, titles, or IDs to detect duplicates."""
        return re.sub(r'[^a-z0-9]', '', (text or "").lower())

    async def search_arxiv(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Queries arXiv API for preprints matching the query with encoded URL."""
        encoded_q = urllib.parse.quote(query)
        url = f"https://export.arxiv.org/api/query?search_query=all:{encoded_q}&start=0&max_results={limit}&sortBy=relevance&sortOrder=descending"
        papers = []
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return []
                root = ET.fromstring(resp.text)
                ns = {'atom': 'http://www.w3.org/2005/Atom'}

                for entry in root.findall('atom:entry', ns):
                    title_elem = entry.find('atom:title', ns)
                    summary_elem = entry.find('atom:summary', ns)
                    id_elem = entry.find('atom:id', ns)
                    published_elem = entry.find('atom:published', ns)

                    if title_elem is None:
                        continue

                    title = " ".join(title_elem.text.split())
                    abstract = " ".join(summary_elem.text.split()) if summary_elem is not None else ""
                    raw_id = id_elem.text.strip() if id_elem is not None else ""
                    # Extract arxiv ID from URL
                    arxiv_id = raw_id.split('/abs/')[-1] if '/abs/' in raw_id else raw_id
                    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf" if arxiv_id else ""
                    year = published_elem.text[:4] if published_elem is not None and published_elem.text else ""

                    authors = []
                    for auth in entry.findall('atom:author', ns):
                        name_elem = auth.find('atom:name', ns)
                        if name_elem is not None and name_elem.text:
                            authors.append(name_elem.text.strip())

                    papers.append({
                        "source": "arxiv",
                        "title": title,
                        "paper_id": f"arxiv:{arxiv_id}",
                        "arxiv_id": arxiv_id,
                        "doi": "",
                        "year": year,
                        "authors": authors[:5],
                        "abstract": abstract,
                        "pdf_url": pdf_url
                    })
        except Exception as e:
            print(f"[arXiv Search Warning] Query '{query}' failed: {e}")
        return papers

    async def search_openalex(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Queries OpenAlex API for open-access papers."""
        url = f"https://api.openalex.org/works?search={query}&per-page={limit}&filter=has_fulltext:true"
        papers = []
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return []
                data = resp.json()
                for item in data.get("results", []):
                    title = item.get("title", "")
                    if not title:
                        continue
                    doi = item.get("doi", "") or ""
                    year = str(item.get("publication_year", ""))
                    authors = [a.get("author", {}).get("display_name", "") for a in item.get("authorships", []) if a.get("author")]
                    
                    # Reconstruct abstract from inverted index if present
                    abstract = ""
                    inv_index = item.get("abstract_inverted_index")
                    if inv_index:
                        try:
                            word_positions = []
                            for word, positions in inv_index.items():
                                for pos in positions:
                                    word_positions.append((pos, word))
                            word_positions.sort()
                            abstract = " ".join([w for _, w in word_positions])
                        except Exception:
                            abstract = ""

                    pdf_url = ""
                    best_oa = item.get("best_oa_location") or {}
                    if best_oa.get("pdf_url"):
                        pdf_url = best_oa["pdf_url"]
                    elif item.get("primary_location", {}).get("pdf_url"):
                        pdf_url = item["primary_location"]["pdf_url"]

                    papers.append({
                        "source": "openalex",
                        "title": title,
                        "paper_id": doi or f"openalex:{item.get('id', '')}",
                        "arxiv_id": "",
                        "doi": doi,
                        "year": year,
                        "authors": authors[:5],
                        "abstract": abstract,
                        "pdf_url": pdf_url
                    })
        except Exception as e:
            print(f"[OpenAlex Search Warning] Query '{query}' failed: {e}")
        return papers

    async def search_crossref(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Queries CrossRef REST API for verified publisher DOIs & bibliographic metadata."""
        encoded_q = urllib.parse.quote(query)
        url = f"https://api.crossref.org/works?query={encoded_q}&rows={limit}"
        papers = []
        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True, headers={"User-Agent": "CouncilResearch/5.0 (mailto:council@research.local)"}) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return []
                data = resp.json()
                items = data.get("message", {}).get("items", [])
                for item in items:
                    title_list = item.get("title", [])
                    title = title_list[0] if title_list else ""
                    if not title:
                        continue
                    doi = item.get("DOI", "")
                    year = ""
                    published = item.get("published-print") or item.get("published-online") or item.get("created")
                    if published and published.get("date-parts"):
                        year = str(published["date-parts"][0][0])

                    authors = []
                    for a in item.get("author", [])[:5]:
                        name = f"{a.get('given', '')} {a.get('family', '')}".strip()
                        if name:
                            authors.append(name)

                    container = item.get("container-title", [])
                    journal = container[0] if container else ""

                    papers.append({
                        "source": "crossref",
                        "title": title,
                        "paper_id": f"doi:{doi}" if doi else f"crossref:{self._normalize_id(title)[:20]}",
                        "arxiv_id": "",
                        "doi": doi,
                        "year": year,
                        "authors": authors,
                        "abstract": f"Published in {journal}. DOI: {doi}" if journal else f"DOI: {doi}",
                        "pdf_url": f"https://doi.org/{doi}" if doi else ""
                    })
        except Exception as e:
            print(f"[CrossRef Search Warning] Query '{query}' failed: {e}")
        return papers

    async def harvest_papers_for_keywords(
        self,
        keywords: List[str],
        target_papers_per_keyword: int = 2,
        total_target: int = 10,
        known_blacklist_ids: Optional[Set[str]] = None,
        id_prefix: str = "PAP",
        start_index: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Coordinates multi-source search across keywords, skips duplicates, 
        and downloads up to total_target papers via arXiv, OpenAlex, and CrossRef.
        """
        blacklist = known_blacklist_ids or set()
        candidates: List[Dict[str, Any]] = []

        print(f"[Paper Harvester] Searching arXiv, OpenAlex & CrossRef for {len(keywords)} keywords (target: {total_target} papers)...")
        for kw in keywords:
            # Query arXiv, OpenAlex, and CrossRef in parallel
            arxiv_res, openalex_res, crossref_res = await asyncio.gather(
                self.search_arxiv(kw, limit=target_papers_per_keyword + 2),
                self.search_openalex(kw, limit=target_papers_per_keyword + 2),
                self.search_crossref(kw, limit=target_papers_per_keyword + 2)
            )
            combined = arxiv_res + openalex_res + crossref_res

            for p in combined:
                norm_id = self._normalize_id(p["paper_id"])
                norm_title = self._normalize_id(p["title"])
                if norm_id in blacklist or norm_title in blacklist or norm_id in self.seen_identifiers or norm_title in self.seen_identifiers:
                    continue  # Deduplicated!
                self.seen_identifiers.add(norm_id)
                self.seen_identifiers.add(norm_title)
                candidates.append(p)
                if len(candidates) >= total_target * 2:
                    break
            if len(candidates) >= total_target * 2:
                break

        print(f"[Paper Harvester] Found {len(candidates)} candidate papers. Downloading & extracting up to {total_target}...")
        results: List[Dict[str, Any]] = []
        for p in candidates:
            if len(results) >= total_target:
                break
            extracted = await self.download_and_extract_paper(p)
            if extracted.get("usable", False):
                extracted["ref_id"] = f"{id_prefix}-{start_index + len(results):03d}"
                results.append(extracted)

        print(f"[Paper Harvester] Completed ingestion: {len(results)}/{total_target} usable papers harvested.")
        return results

    async def download_and_extract_paper(self, paper: Dict[str, Any], timeout: float = 12.0) -> Dict[str, Any]:
        """Downloads PDF and runs hybrid section parser to produce structured academic dossier."""
        title = paper.get("title", "Untitled")
        pdf_url = paper.get("pdf_url", "")
        abstract = paper.get("abstract", "")
        paper_id = paper.get("paper_id", "")

        extracted_text = ""
        equations = []
        tables_summary = []
        methodology = ""
        parse_status = "abstract_only"

        if pdf_url:
            clean_fname = re.sub(r'[^a-zA-Z0-9]', '_', title[:40]) + ".pdf"
            cache_path = os.path.join(self.cache_dir, clean_fname)

            # 1. Download PDF if not cached
            if not os.path.exists(cache_path):
                try:
                    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                        resp = await client.get(pdf_url)
                        if resp.status_code == 200 and len(resp.content) > 5000 and len(resp.content) < 18 * 1024 * 1024:
                            with open(cache_path, "wb") as f:
                                f.write(resp.content)
                except Exception as e:
                    print(f"[PDF Download Notice] Failed to download {pdf_url}: {e}")

            # 2. Extract sections via PyMuPDF (fitz) if file exists
            if os.path.exists(cache_path):
                try:
                    import fitz  # PyMuPDF
                    doc = fitz.open(cache_path)
                    pages_text = []
                    # Read first 8 pages max to avoid huge PDFs
                    for page_num in range(min(len(doc), 8)):
                        page = doc[page_num]
                        p_text = page.get_text("text")
                        if p_text:
                            pages_text.append(p_text)

                    full_pdf_text = "\n".join(pages_text)
                    
                    # Heuristic section extraction
                    math_matches = re.findall(r'(?:[A-Za-z]\s*=\s*[^;\n]{3,60}|E\[[^\]]+\]|Var\([^\)]+\)|\b\d+\.\d+\s*%)', full_pdf_text)
                    if math_matches:
                        equations = list(set([m.strip() for m in math_matches[:8]]))

                    # Look for methodology/model headers
                    meth_match = re.search(r'(?:methodology|model specification|empirical framework|econometric model)[\s\S]{100,1200}?(?=\n[A-Z0-9\.\s]{3,20}\n)', full_pdf_text, re.IGNORECASE)
                    if meth_match:
                        methodology = meth_match.group(0)[:800]

                    # Look for table excerpts
                    tab_match = re.findall(r'(?:Table\s+\d+[\s\S]{50,400}?(?=\n\n))', full_pdf_text, re.IGNORECASE)
                    if tab_match:
                        tables_summary = [t.strip() for t in tab_match[:3]]

                    parse_status = "full_pdf_extracted"
                    extracted_text = full_pdf_text[:3000]
                    doc.close()
                except Exception as pe:
                    # Fallback to pure abstract
                    parse_status = f"pdf_parse_failed_using_abstract ({pe})"

        # 3. Format structured academic dossier
        dossier = (
            f"### [RESEARCH PAPER: {title.upper()}]\n"
            f"- **Identifiers:** {paper_id} | Year: {paper.get('year', 'N/A')} | Source: {paper.get('source', '').upper()}\n"
            f"- **Authors:** {', '.join(paper.get('authors', []))}\n"
            f"- **Extraction Status:** [{parse_status}]\n\n"
            f"#### 1. ABSTRACT & CORE CLAIMS:\n{abstract if abstract else 'No abstract available.'}\n\n"
        )
        if methodology:
            dossier += f"#### 2. METHODOLOGY & STRUCTURAL MODEL:\n{methodology}\n\n"
        if equations:
            dossier += f"#### 3. KEY MATHEMATICAL SPECIFICATIONS & EQUATIONS:\n" + "\n".join([f"  * {eq}" for eq in equations]) + "\n\n"
        if tables_summary:
            dossier += f"#### 4. EMPIRICAL PARAMETER TABLES:\n" + "\n\n".join(tables_summary) + "\n\n"

        return {
            "usable": True,
            "title": title,
            "paper_id": paper_id,
            "year": paper.get("year", ""),
            "authors": paper.get("authors", []),
            "parse_status": parse_status,
            "structured_dossier": dossier,
            "raw_abstract": abstract
        }

paper_harvester = AcademicPaperHarvester()
