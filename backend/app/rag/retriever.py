"""
Retriever module.

Responsibilities:
  - Query → embedding → Qdrant search
  - Conversation-aware query reformulation
  - MMR-style diversity reranking
  - Confidence scoring (used to gate uncertain answers)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import anthropic
from openai import AsyncOpenAI
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import Filter

from app.config import get_settings
from app.models import RetrievedChunk

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Module-level clients (initialised once on startup) ────────────────────────
_qdrant: Optional[AsyncQdrantClient] = None
_openai: Optional[AsyncOpenAI] = None


async def init_retriever() -> None:
    global _qdrant, _openai
    _qdrant = AsyncQdrantClient(
        url=settings.QDRANT_URL,
        api_key=settings.QDRANT_API_KEY,
    )
    _openai = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    logger.info("Retriever initialised (Qdrant + OpenAI)")


def _get_clients() -> tuple[AsyncQdrantClient, AsyncOpenAI]:
    if _qdrant is None or _openai is None:
        raise RuntimeError("Retriever not initialised. Call init_retriever() first.")
    return _qdrant, _openai


# ── Query reformulation ────────────────────────────────────────────────────────

async def reformulate_query(
    query: str,
    history: list[dict],
) -> str:
    """
    Use Claude to rewrite a follow-up question as a self-contained search query.
    Fast: uses claude-haiku for minimal latency.
    Falls back to original query on any error.
    """
    if not history or len(history) < 2:
        return query

    recent = history[-4:]   # last 2 turns (4 messages)
    history_text = "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in recent
    )

    prompt = (
        f"Conversation:\n{history_text}\n\n"
        f"Follow-up: {query}\n\n"
        "Rewrite the follow-up as a standalone search query. "
        "Return ONLY the query, nothing else."
    )

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=64,
            messages=[{"role": "user", "content": prompt}],
        )
        reformulated = msg.content[0].text.strip()
        logger.debug("Query reformulated: %r → %r", query, reformulated)
        return reformulated
    except Exception as exc:
        logger.warning("Query reformulation failed: %s", exc)
        return query


# ── Embedding ─────────────────────────────────────────────────────────────────

async def _embed_query(query: str) -> list[float]:
    _, oai = _get_clients()
    response = await oai.embeddings.create(
        model=settings.EMBEDDING_MODEL,
        input=query,
    )
    return response.data[0].embedding


# ── MMR diversity reranker ────────────────────────────────────────────────────

def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _mmr_rerank(
    query_vec: list[float],
    results: list[tuple[list[float], dict]],   # (vector, payload)
    top_k: int,
    lambda_: float = 0.5,
) -> list[dict]:
    """
    Maximal Marginal Relevance: balances relevance to query vs diversity.
    lambda_=1.0 → pure relevance; lambda_=0.0 → pure diversity.
    """
    if not results:
        return []

    selected = []
    remaining = list(results)

    while remaining and len(selected) < top_k:
        if not selected:
            # Pick highest relevance first
            best = max(remaining, key=lambda r: _cosine_sim(query_vec, r[0]))
        else:
            def _mmr_score(candidate):
                rel = _cosine_sim(query_vec, candidate[0])
                red = max(_cosine_sim(candidate[0], s[0]) for s in selected)
                return lambda_ * rel - (1 - lambda_) * red

            best = max(remaining, key=_mmr_score)

        selected.append(best)
        remaining.remove(best)

    return [item[1] for item in selected]


# ── Main search ───────────────────────────────────────────────────────────────

async def search(
    query: str,
    top_k: int | None = None,
    source_filter: str | None = None,   # e.g. "resume" or "github:my-repo"
    history: list[dict] | None = None,
) -> list[RetrievedChunk]:
    """
    Retrieve the most relevant chunks for a query.

    1. Reformulate query if conversation history is available
    2. Embed the query
    3. Search Qdrant
    4. MMR rerank for diversity
    5. Return RetrievedChunk objects with confidence scores
    """
    qdrant, _ = _get_clients()
    k = top_k or settings.RAG_TOP_K
    threshold = settings.RAG_SCORE_THRESHOLD

    # Step 1: Contextualise
    effective_query = await reformulate_query(query, history or [])

    # Step 2: Embed
    query_vec = await _embed_query(effective_query)

    # Step 3: Qdrant search (over-fetch for MMR)
    search_kwargs: dict = {
        "collection_name": settings.QDRANT_COLLECTION,
        "query_vector": query_vec,
        "limit": k * 2,
        "with_payload": True,
        "with_vectors": True,
        "score_threshold": threshold,
    }

    if source_filter:
        search_kwargs["query_filter"] = Filter(
            must=[{"key": "source", "match": {"value": source_filter}}]
        )

    try:
        hits = await qdrant.search(**search_kwargs)
    except Exception as exc:
        logger.error("Qdrant search failed: %s", exc)
        return []

    if not hits:
        return []

    # Step 4: MMR diversity reranking
    candidates = [(hit.vector, hit.payload) for hit in hits if hit.vector]
    reranked_payloads = _mmr_rerank(query_vec, candidates, top_k=k)

    # Fallback if vectors weren't returned
    if not reranked_payloads:
        reranked_payloads = [hit.payload for hit in hits[:k]]

    # Step 5: Build results
    chunks = []
    for i, payload in enumerate(reranked_payloads):
        # Approximate score from hit order (Qdrant already sorted by cosine)
        hit_score = hits[i].score if i < len(hits) else threshold
        chunks.append(
            RetrievedChunk(
                text=payload.get("text", ""),
                source=payload.get("source", "unknown"),
                score=round(hit_score, 4),
                metadata={
                    "repo": payload.get("repo", ""),
                    "file_path": payload.get("file_path", ""),
                    "chunk_type": payload.get("chunk_type", ""),
                },
            )
        )

    logger.debug(
        "Retrieved %d chunks for query=%r (reformulated=%r)",
        len(chunks),
        query[:60],
        effective_query[:60],
    )
    return chunks


async def get_context_for_prompt(
    query: str,
    history: list[dict] | None = None,
) -> tuple[list[str], list[str], float]:
    """
    Convenience wrapper: returns (context_texts, source_labels, avg_confidence).
    Used by the generation pipeline and Vapi endpoint.
    """
    chunks = await search(query, history=history)
    if not chunks:
        return [], [], 0.0

    texts = [c.text for c in chunks]
    sources = list({c.source for c in chunks})
    confidence = sum(c.score for c in chunks) / len(chunks)
    return texts, sources, round(confidence, 3)
