"""
Document ingestion pipeline.

Sources:
  1. Resume PDF  → /data/resume.pdf
  2. GitHub repos → README, top-level .py/.ts files, commit messages
  3. persona_config.json → structured persona facts (seed data)

Chunking strategy:
  - Resume: semantic sections (experience, education, projects) → 512 tok chunks, 64 overlap
  - GitHub: README full text + file summaries → 256 tok chunks, 32 overlap
  - Persona JSON: flattened key facts, one fact per chunk
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

import httpx
import tiktoken
from openai import AsyncOpenAI
from pypdf import PdfReader
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import (
    Distance,
    PointStruct,
    VectorParams,
)

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Encoding for token counting
_enc = tiktoken.get_encoding("cl100k_base")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _count_tokens(text: str) -> int:
    return len(_enc.encode(text))


def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split text into overlapping token-bounded chunks."""
    tokens = _enc.encode(text)
    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        chunk = _enc.decode(tokens[start:end])
        chunks.append(chunk.strip())
        if end == len(tokens):
            break
        start += chunk_size - overlap
    return [c for c in chunks if c]


async def _embed(texts: list[str]) -> list[list[float]]:
    """Batch embed texts with OpenAI. Max 2048 texts per call."""
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    embeddings = []
    batch_size = 100
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        response = await client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=batch,
        )
        embeddings.extend([item.embedding for item in response.data])
    return embeddings


async def _upsert_chunks(
    client: AsyncQdrantClient,
    chunks: list[dict[str, Any]],
) -> int:
    """Upsert text chunks into Qdrant. Returns number of points upserted."""
    if not chunks:
        return 0

    texts = [c["text"] for c in chunks]
    vectors = await _embed(texts)

    points = [
        PointStruct(
            id=abs(hash(c["text"] + c.get("source", ""))) % (2**63),
            vector=vectors[i],
            payload={
                "text": c["text"],
                "source": c.get("source", "unknown"),
                "repo": c.get("repo", ""),
                "file_path": c.get("file_path", ""),
                "chunk_type": c.get("chunk_type", "text"),
            },
        )
        for i, c in enumerate(chunks)
    ]

    await client.upsert(
        collection_name=settings.QDRANT_COLLECTION,
        points=points,
    )
    return len(points)


# ── Qdrant collection initialisation ─────────────────────────────────────────

async def ensure_collection(client: AsyncQdrantClient) -> None:
    """Create collection if it doesn't exist."""
    collections = await client.get_collections()
    names = [c.name for c in collections.collections]
    if settings.QDRANT_COLLECTION not in names:
        await client.create_collection(
            collection_name=settings.QDRANT_COLLECTION,
            vectors_config=VectorParams(
                size=settings.EMBEDDING_DIMENSIONS,
                distance=Distance.COSINE,
            ),
        )
        logger.info("Created Qdrant collection: %s", settings.QDRANT_COLLECTION)


# ── Resume ingestion ──────────────────────────────────────────────────────────

async def ingest_resume(client: AsyncQdrantClient, pdf_path: Path) -> int:
    """Parse resume PDF and upsert semantic chunks."""
    if not pdf_path.exists():
        logger.warning("Resume not found at %s — skipping", pdf_path)
        return 0

    reader = PdfReader(str(pdf_path))
    full_text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
    full_text = re.sub(r"\n{3,}", "\n\n", full_text).strip()

    chunks_raw = _chunk_text(full_text, settings.RAG_CHUNK_SIZE, settings.RAG_CHUNK_OVERLAP)
    chunks = [
        {"text": c, "source": "resume", "chunk_type": "resume_section"}
        for c in chunks_raw
    ]

    count = await _upsert_chunks(client, chunks)
    logger.info("Ingested resume: %d chunks", count)
    return count


# ── GitHub ingestion ──────────────────────────────────────────────────────────

async def _fetch_github_files(
    username: str,
    repo: str,
    token: str,
) -> list[dict[str, str]]:
    """Fetch README + notable source files from a public GitHub repo."""
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    files = []
    base_url = f"https://api.github.com/repos/{username}/{repo}"

    async with httpx.AsyncClient(headers=headers, timeout=30) as http:
        # README
        try:
            r = await http.get(f"{base_url}/readme")
            if r.status_code == 200:
                import base64
                content = base64.b64decode(r.json()["content"]).decode("utf-8", errors="replace")
                files.append({"path": "README.md", "content": content})
        except Exception:
            pass

        # Repo metadata
        try:
            r = await http.get(base_url)
            if r.status_code == 200:
                meta = r.json()
                desc = meta.get("description", "")
                topics = ", ".join(meta.get("topics", []))
                lang = meta.get("language", "")
                stars = meta.get("stargazers_count", 0)
                meta_text = (
                    f"Repository: {username}/{repo}\n"
                    f"Description: {desc}\n"
                    f"Primary language: {lang}\n"
                    f"Topics: {topics}\n"
                    f"Stars: {stars}"
                )
                files.append({"path": "_meta.txt", "content": meta_text})
        except Exception:
            pass

        # Top-level source files (Python, TypeScript, JS — skip binary)
        try:
            r = await http.get(f"{base_url}/contents")
            if r.status_code == 200:
                interesting_exts = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".md"}
                for item in r.json():
                    if item["type"] == "file" and Path(item["name"]).suffix in interesting_exts:
                        if item.get("size", 0) < 50_000:  # skip huge files
                            fr = await http.get(item["download_url"])
                            if fr.status_code == 200:
                                files.append({"path": item["path"], "content": fr.text})
        except Exception:
            pass

    return files


async def ingest_github(client: AsyncQdrantClient, username: str, repos: list[str]) -> int:
    """Ingest GitHub repositories into vector store."""
    if not username:
        logger.warning("No GitHub username configured — skipping")
        return 0

    token = settings.GITHUB_TOKEN
    total = 0

    for repo in repos:
        logger.info("Ingesting GitHub repo: %s/%s", username, repo)
        try:
            files = await _fetch_github_files(username, repo, token)
            chunks = []
            for f in files:
                raw_chunks = _chunk_text(
                    f["content"],
                    chunk_size=256,
                    overlap=32,
                )
                for c in raw_chunks:
                    chunks.append({
                        "text": c,
                        "source": f"github:{repo}",
                        "repo": repo,
                        "file_path": f["path"],
                        "chunk_type": "code" if not f["path"].endswith(".md") else "readme",
                    })
            n = await _upsert_chunks(client, chunks)
            total += n
            logger.info("Repo %s: %d chunks", repo, n)
            await asyncio.sleep(0.5)   # be polite to GitHub API
        except Exception as exc:
            logger.error("Failed to ingest %s: %s", repo, exc)

    logger.info("GitHub ingestion total: %d chunks", total)
    return total


# ── Persona config ingestion ──────────────────────────────────────────────────

def _flatten_persona(persona: dict, prefix: str = "") -> list[str]:
    """Flatten nested persona JSON into readable fact strings."""
    facts = []

    def _recurse(obj: Any, path: str) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                _recurse(v, f"{path}.{k}" if path else k)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                if isinstance(item, (dict, list)):
                    _recurse(item, f"{path}[{i}]")
                else:
                    facts.append(f"{path}: {item}")
        else:
            facts.append(f"{path}: {obj}")

    _recurse(persona, prefix)
    return facts


async def ingest_persona_config(client: AsyncQdrantClient, config_path: Path) -> int:
    """Ingest structured persona config as seed facts."""
    if not config_path.exists():
        logger.warning("persona_config.json not found at %s", config_path)
        return 0

    with open(config_path) as f:
        persona = json.load(f)

    facts = _flatten_persona(persona)

    # Group facts into 10-fact chunks for better retrieval context
    chunks = []
    batch_size = 10
    for i in range(0, len(facts), batch_size):
        batch = facts[i : i + batch_size]
        chunks.append({
            "text": "\n".join(batch),
            "source": "persona",
            "chunk_type": "structured_fact",
        })

    # Also add a rich prose summary if present
    if "summary" in persona:
        chunks.append({
            "text": persona["summary"],
            "source": "persona",
            "chunk_type": "bio_summary",
        })

    count = await _upsert_chunks(client, chunks)
    logger.info("Persona config: %d chunks", count)
    return count


# ── Main ingest orchestrator ──────────────────────────────────────────────────

async def run_full_ingestion(sources: list[str] | None = None) -> dict:
    """Run the full ingestion pipeline. Returns stats."""
    sources = sources or ["resume", "github", "persona"]
    start = time.monotonic()

    client = AsyncQdrantClient(
        url=settings.QDRANT_URL,
        api_key=settings.QDRANT_API_KEY,
    )
    await ensure_collection(client)

    data_dir = Path(__file__).parent.parent.parent / "data"
    stats = {"sources": [], "chunks_added": 0}

    if "resume" in sources:
        n = await ingest_resume(client, data_dir / "resume.pdf")
        stats["chunks_added"] += n
        stats["sources"].append("resume")

    if "github" in sources and settings.GITHUB_USERNAME:
        persona_path = data_dir / "persona_config.json"
        repos = []
        if persona_path.exists():
            with open(persona_path) as f:
                pc = json.load(f)
                repos = pc.get("github_repos", [])
        n = await ingest_github(client, settings.GITHUB_USERNAME, repos)
        stats["chunks_added"] += n
        stats["sources"].append("github")

    if "persona" in sources:
        n = await ingest_persona_config(client, data_dir / "persona_config.json")
        stats["chunks_added"] += n
        stats["sources"].append("persona")

    stats["elapsed_seconds"] = round(time.monotonic() - start, 2)
    logger.info("Ingestion complete: %s", stats)
    return stats
