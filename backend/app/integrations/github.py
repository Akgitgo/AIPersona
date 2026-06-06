"""
GitHub integration helpers (beyond what's in ingest.py).

Used by routes to fetch repo metadata on demand (for "tell me about repo X" questions).
"""

from __future__ import annotations

import logging
from functools import lru_cache

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def list_public_repos(username: str | None = None) -> list[dict]:
    """Fetch list of public repos for a user."""
    user = username or settings.GITHUB_USERNAME
    if not user:
        return []

    headers = {"Accept": "application/vnd.github.v3+json"}
    if settings.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {settings.GITHUB_TOKEN}"

    async with httpx.AsyncClient(headers=headers, timeout=15) as client:
        r = await client.get(
            f"https://api.github.com/users/{user}/repos",
            params={"sort": "updated", "per_page": 30, "type": "public"},
        )
        if r.status_code != 200:
            logger.error("GitHub API error: %s", r.status_code)
            return []

        repos = r.json()
        return [
            {
                "name": repo["name"],
                "description": repo.get("description", ""),
                "language": repo.get("language", ""),
                "stars": repo.get("stargazers_count", 0),
                "url": repo.get("html_url", ""),
                "topics": repo.get("topics", []),
                "updated_at": repo.get("updated_at", ""),
            }
            for repo in repos
            if not repo.get("fork")   # skip forks
        ]
