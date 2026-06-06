"""
Generation pipeline.

Combines retrieval + Claude generation into a single streaming interface.
Used by the chat route.  The Vapi route uses retriever.py directly
(OpenAI-compatible endpoint handles its own streaming).
"""

from __future__ import annotations

import json
import logging
import time
from typing import AsyncGenerator

import anthropic

from app.agents.system_prompts import build_chat_system_prompt
from app.config import get_settings
from app.models import Message, Role
from app.rag import retriever

logger = logging.getLogger(__name__)
settings = get_settings()


# ── Session store (in-memory; swap for Redis in heavier deployments) ──────────

_sessions: dict[str, list[dict]] = {}


def get_history(session_id: str) -> list[dict]:
    return _sessions.get(session_id, [])


def append_history(session_id: str, role: str, content: str) -> None:
    history = _sessions.setdefault(session_id, [])
    history.append({"role": role, "content": content})
    # Keep only last N message pairs
    max_messages = settings.HISTORY_WINDOW * 2
    if len(history) > max_messages:
        _sessions[session_id] = history[-max_messages:]


def clear_history(session_id: str) -> None:
    _sessions.pop(session_id, None)


# ── Streaming generation ───────────────────────────────────────────────────────

async def stream_response(
    user_message: str,
    session_id: str = "default",
) -> AsyncGenerator[dict, None]:
    """
    Full RAG → Generate pipeline.

    Yields dicts:
      {"type": "sources", "data": [...]}     — emitted first
      {"type": "token",   "data": "..."}     — streamed tokens
      {"type": "done",    "data": {...}}      — final metadata
      {"type": "error",   "data": "..."}     — on failure
    """
    start = time.monotonic()
    history = get_history(session_id)

    # ── 1. Retrieve ────────────────────────────────────────────────────────
    try:
        context_texts, sources, confidence = await retriever.get_context_for_prompt(
            user_message, history=history
        )
    except Exception as exc:
        logger.error("Retrieval failed: %s", exc)
        context_texts, sources, confidence = [], [], 0.0

    yield {"type": "sources", "data": sources, "confidence": confidence}

    # ── 2. Build messages ─────────────────────────────────────────────────
    system_prompt = build_chat_system_prompt(context_texts)

    messages: list[dict] = list(history)   # copy
    messages.append({"role": "user", "content": user_message})

    # ── 3. Stream from Claude ─────────────────────────────────────────────
    full_reply = ""
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    try:
        async with client.messages.stream(
            model=settings.CLAUDE_MODEL,
            max_tokens=settings.CLAUDE_MAX_TOKENS,
            system=system_prompt,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                full_reply += text
                yield {"type": "token", "data": text}

    except anthropic.APIError as exc:
        logger.error("Claude API error: %s", exc)
        yield {"type": "error", "data": str(exc)}
        return

    # ── 4. Update history ─────────────────────────────────────────────────
    append_history(session_id, "user", user_message)
    append_history(session_id, "assistant", full_reply)

    elapsed_ms = int((time.monotonic() - start) * 1000)

    yield {
        "type": "done",
        "data": {
            "reply": full_reply,
            "session_id": session_id,
            "sources": sources,
            "confidence": confidence,
            "latency_ms": elapsed_ms,
        },
    }


async def complete_response(
    user_message: str,
    session_id: str = "default",
) -> dict:
    """Non-streaming variant. Used by evals and Vapi tool calls."""
    full_reply = ""
    metadata = {}

    async for event in stream_response(user_message, session_id):
        if event["type"] == "token":
            full_reply += event["data"]
        elif event["type"] == "done":
            metadata = event["data"]

    return metadata or {
        "reply": full_reply,
        "session_id": session_id,
        "sources": [],
        "confidence": 0.0,
        "latency_ms": 0,
    }
