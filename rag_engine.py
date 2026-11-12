"""
rag_engine.py
Local In-Process Hybrid RAG Engine using LanceDB and FlashRank Cross-Encoder.
Provides:
1. Semantic Markdown chunking with heading preservation.
2. In-process LanceDB storage and FTS indexing.
3. FlashRank TinyBERT cross-encoder reranking (pure CPU, ~15ms latency).
4. Evidence package generation with immutable citation tokens [SRC-OFFICIAL-XX].
"""

import os
import re
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
import lancedb
from flashrank import Ranker, RerankRequest

logger = logging.getLogger("RAGEngine")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


@dataclass
class DocumentChunk:
    chunk_id: str
    text: str
    source_url: str
    domain: str
    source_role: str
    provenance_score: float
    section_title: str


def chunk_markdown(
    text: str,
    source_url: str,
    domain: str,
    source_role: str = "official_documentation",
    provenance_score: float = 5.0,
    prefix_id: str = "SRC-OFFICIAL",
    target_chunk_chars: int = 1500
) -> List[DocumentChunk]:
    """
    Split markdown text into coherent semantic chunks preserving heading context.
    """
    if not text:
        return []

    chunks: List[DocumentChunk] = []
    # Split by markdown headers
    header_pattern = re.compile(r"^(#{1,4}\s+.+)$", re.MULTILINE)
    sections = header_pattern.split(text)
    
    current_title = "Overview"
    current_buffer = []
    current_len = 0
    chunk_idx = 1

    i = 0
    while i < len(sections):
        part = sections[i].strip()
        if not part:
            i += 1
            continue

        if header_pattern.match(part):
            current_title = part.lstrip("#").strip()
            i += 1
            continue

        # Split long section into paragraphs
        paragraphs = part.split("\n\n")
        for p in paragraphs:
            p_clean = p.strip()
            if not p_clean:
                continue

            if current_len + len(p_clean) > target_chunk_chars and current_buffer:
                # Flush chunk
                chunk_text = f"### Source: {domain} | Section: {current_title}\n" + "\n\n".join(current_buffer)
                cid = f"{prefix_id}-{chunk_idx:03d}"
                chunks.append(DocumentChunk(
                    chunk_id=cid,
                    text=chunk_text,
                    source_url=source_url,
                    domain=domain,
                    source_role=source_role,
                    provenance_score=provenance_score,
                    section_title=current_title
                ))
                chunk_idx += 1
                current_buffer = [p_clean]
                current_len = len(p_clean)
            else:
                current_buffer.append(p_clean)
                current_len += len(p_clean)

        i += 1

    # Flush final remaining buffer
    if current_buffer:
        chunk_text = f"### Source: {domain} | Section: {current_title}\n" + "\n\n".join(current_buffer)
        cid = f"{prefix_id}-{chunk_idx:03d}"
        chunks.append(DocumentChunk(
            chunk_id=cid,
            text=chunk_text,
            source_url=source_url,
            domain=domain,
            source_role=source_role,
            provenance_score=provenance_score,
            section_title=current_title
        ))

    return chunks


class ResearchRAGEngine:
    """
    Local hybrid retrieval and reranking engine.
    Stores chunks in LanceDB and executes fast CPU cross-encoder reranking via FlashRank.
    """
    def __init__(self, db_path: str = "scratch/research_index"):
        os.makedirs(db_path, exist_ok=True)
        self.db_path = db_path
        self.db = lancedb.connect(db_path)
        self.ranker = Ranker()
        self.chunks_memory: List[DocumentChunk] = []
        self.table = None

    def ingest_documents(self, documents: List[Dict[str, Any]]) -> int:
        """
        Ingest a list of extracted document dicts:
        [{ "url": ..., "domain": ..., "content": ..., "source_role": ..., "provenance_score": ... }]
        """
        all_chunks: List[DocumentChunk] = []
        doc_count = 0

        for doc in documents:
            url = doc.get("url", "")
            domain = doc.get("domain", "")
            content = doc.get("content", "")
            role = doc.get("source_role", "official_documentation")
            score = float(doc.get("provenance_score", 5.0))
            if not content:
                continue

            doc_chunks = chunk_markdown(
                text=content,
                source_url=url,
                domain=domain,
                source_role=role,
                provenance_score=score,
                prefix_id=f"SRC-DOC{doc_count+1:02d}"
            )
            all_chunks.extend(doc_chunks)
            doc_count += 1

        if not all_chunks:
            logger.warning("No chunks generated from documents.")
            return 0

        self.chunks_memory = all_chunks

        # Store in LanceDB
        data_records = [asdict(c) for c in all_chunks]
        try:
            self.table = self.db.create_table("research_corpus", data=data_records, mode="overwrite")
            try:
                self.table.create_fts_index("text", replace=True)
            except Exception as e:
                logger.debug(f"LanceDB FTS index warning: {e}")
            logger.info(f"Successfully indexed {len(all_chunks)} chunks across {doc_count} verified documents into LanceDB.")
        except Exception as e:
            logger.error(f"Failed to create LanceDB table: {e}")

        return len(all_chunks)

    def retrieve(self, subquestion: str, top_k: int = 6, min_score: float = 0.0) -> List[Dict[str, Any]]:
        """
        Retrieve and cross-encoder rerank chunks against a worker subquestion.
        Returns top_k ranked chunk records with immutable [SRC-ID] tokens.
        """
        if not self.chunks_memory:
            return []

        # If corpus is reasonably sized (<= 150 chunks), rerank directly across all chunks
        # FlashRank takes ~15ms for 50-100 chunks on CPU!
        candidate_pool = self.chunks_memory
        if len(candidate_pool) > 100 and self.table is not None:
            try:
                # Use FTS to prune candidate pool to top 60 first
                fts_results = self.table.search(subquestion, query_type="fts").limit(60).to_list()
                if fts_results:
                    fts_ids = {r["chunk_id"] for r in fts_results}
                    candidate_pool = [c for c in self.chunks_memory if c.chunk_id in fts_ids]
            except Exception as e:
                logger.debug(f"FTS prune fallback: {e}")
                candidate_pool = self.chunks_memory[:100]

        passages = [{"id": c.chunk_id, "text": c.text} for c in candidate_pool]
        req = RerankRequest(query=subquestion, passages=passages)
        ranked = self.ranker.rerank(req)

        # Map back to DocumentChunk objects
        chunk_map = {c.chunk_id: c for c in candidate_pool}
        results = []
        for r in ranked:
            cid = r["id"]
            score = float(r["score"])
            if score < min_score:
                continue
            chunk = chunk_map.get(cid)
            if chunk:
                results.append({
                    "chunk_id": chunk.chunk_id,
                    "text": chunk.text,
                    "source_url": chunk.source_url,
                    "domain": chunk.domain,
                    "source_role": chunk.source_role,
                    "provenance_score": chunk.provenance_score,
                    "section_title": chunk.section_title,
                    "relevance_score": round(score, 4)
                })
            if len(results) >= top_k:
                break

        return results

    def format_evidence_package(self, subquestion: str, top_k: int = 6) -> str:
        """
        Format retrieved evidence chunks into an authoritative Markdown package for agent workers.
        """
        ranked_chunks = self.retrieve(subquestion, top_k=top_k)
        if not ranked_chunks:
            return "NO_VERIFIED_PRIMARY_EVIDENCE_AVAILABLE: Missing primary documentation for this subquestion."

        lines = [
            f"### VERIFIED PRIMARY EVIDENCE CORPUS for Subquestion: '{subquestion}'",
            "CRITICAL INSTRUCTION: You must base all claims STRICTLY on the following cited chunks. Cite every fact with its [SRC-ID].",
            ""
        ]
        for c in ranked_chunks:
            lines.append(f"--- [{c['chunk_id']}] (Source: {c['domain']} | URL: {c['source_url']} | Trust: {c['provenance_score']} | Relevance: {c['relevance_score']}) ---")
            lines.append(c["text"])
            lines.append("")

        return "\n".join(lines)

