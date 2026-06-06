"""
/api/chat  — streaming chat endpoint.

Emits Server-Sent Events (SSE) so the frontend can render tokens as they arrive.
Non-streaming fallback available via ?stream=false.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.models import BookingRequest, ChatRequest, SlotRequest
from app.rag import pipeline
from app.integrations import calcom

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


# ── Chat ──────────────────────────────────────────────────────────────────────

@router.post("")
async def chat(req: ChatRequest):
    """
    Main chat endpoint.

    - stream=true  (default): SSE stream of tokens
    - stream=false           : single JSON response
    """
    if not req.stream:
        result = await pipeline.complete_response(req.message, req.session_id)
        return JSONResponse(result)

    async def _event_stream():
        async for event in pipeline.stream_response(req.message, req.session_id):
            yield _sse(event)
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx buffering
        },
    )


# ── Availability ──────────────────────────────────────────────────────────────

@router.post("/slots")
async def get_slots(req: SlotRequest):
    slots = await calcom.get_available_slots(
        days_ahead=req.days_ahead,
        timezone_str=req.timezone,
    )
    return {"slots": [s.model_dump() for s in slots], "timezone": req.timezone}


# ── Booking ───────────────────────────────────────────────────────────────────

@router.post("/book")
async def book(req: BookingRequest):
    result = await calcom.create_booking(req)
    return result.model_dump()


# ── Session management ────────────────────────────────────────────────────────

@router.delete("/session/{session_id}")
async def clear_session(session_id: str):
    pipeline.clear_history(session_id)
    return {"cleared": session_id}
