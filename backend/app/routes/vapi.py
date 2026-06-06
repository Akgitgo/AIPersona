"""
Vapi voice agent integration.

Two endpoints:
  POST /api/vapi/webhook   — receives Vapi lifecycle events (tool calls, call reports)
  POST /api/vapi/llm       — custom LLM endpoint (OpenAI-compatible) called by Vapi
                             for every conversational turn. We inject RAG context here.

Architecture note:
  Vapi handles STT (Deepgram), TTS (ElevenLabs), and conversation management.
  We only handle the LLM + retrieval piece. This keeps voice latency well below 2s
  because:
    - Qdrant retrieval: ~50ms
    - First Claude token: ~250ms
    - Network overhead: ~100ms
    - Total to first audio: ~400ms (Vapi starts TTS on first sentence)
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, AsyncGenerator

import anthropic
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.agents.system_prompts import build_voice_system_prompt
from app.config import get_settings
from app.integrations import calcom
from app.models import BookingRequest, OAIRequest
from app.rag import retriever

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()


# ── Vapi assistant config ─────────────────────────────────────────────────────
# This is returned by /api/vapi/webhook on "assistant-request" events.
# You can also hardcode this in the Vapi dashboard instead.

def _build_assistant_config(call_id: str) -> dict:
    base_url = settings.API_BASE_URL
    return {
        "name": "AI Persona",
        "model": {
            "provider": "custom-llm",
            "url": f"{base_url}/api/vapi/llm",
            "model": "claude-sonnet",
            "temperature": 0.7,
            "maxTokens": 350,
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "get_availability",
                        "description": (
                            "Get available meeting slots from the candidate's calendar. "
                            "Call this when the user asks about scheduling or availability."
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "days_ahead": {
                                    "type": "integer",
                                    "description": "How many days to look ahead. Default 7.",
                                    "default": 7,
                                }
                            },
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "book_meeting",
                        "description": "Book a confirmed meeting slot.",
                        "parameters": {
                            "type": "object",
                            "required": ["name", "email", "start_time"],
                            "properties": {
                                "name": {"type": "string", "description": "Caller's name"},
                                "email": {"type": "string", "description": "Caller's email"},
                                "start_time": {
                                    "type": "string",
                                    "description": "ISO 8601 start time of the chosen slot",
                                },
                                "notes": {
                                    "type": "string",
                                    "description": "Optional notes about the meeting",
                                },
                            },
                        },
                    },
                },
            ],
        },
        "voice": {
            "provider": "11labs",
            "voiceId": "21m00Tcm4TlvDq8ikWAM",   # Rachel — swap in Vapi dashboard
            "stability": 0.5,
            "similarityBoost": 0.75,
            "speed": 1.0,
        },
        "firstMessage": (
            "Hi there! I'm the AI assistant set up by the candidate to represent them "
            "during this screening. I can answer questions about their background, skills, "
            "and fit for the role — and I can also check availability and book an interview "
            "slot right now. What would you like to know?"
        ),
        "transcriber": {
            "provider": "deepgram",
            "model": "nova-2",
            "language": "en-IN",
        },
        "silenceTimeoutSeconds": 20,
        "maxDurationSeconds": 1200,
        "backgroundSound": "off",
        "backchannelingEnabled": False,
        "endCallFunctionEnabled": True,
    }


# ── Webhook handler ───────────────────────────────────────────────────────────

@router.post("/webhook")
async def vapi_webhook(request: Request):
    """Handle all Vapi lifecycle events."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    message = body.get("message", {})
    msg_type = message.get("type", "")

    logger.info("Vapi webhook: type=%s", msg_type)

    if msg_type == "assistant-request":
        call_id = message.get("call", {}).get("id", "unknown")
        return JSONResponse({"assistant": _build_assistant_config(call_id)})

    elif msg_type == "function-call":
        return await _handle_function_call(message)

    elif msg_type == "end-of-call-report":
        await _handle_call_report(message)
        return JSONResponse({"received": True})

    elif msg_type == "status-update":
        status = message.get("status", "")
        logger.info("Call status: %s", status)
        return JSONResponse({"received": True})

    elif msg_type == "hang":
        logger.info("Call hung up")
        return JSONResponse({"received": True})

    return JSONResponse({"received": True})


async def _handle_function_call(message: dict) -> JSONResponse:
    """Execute tool calls (calendar)."""
    fn = message.get("functionCall", {})
    fn_name = fn.get("name", "")
    params = fn.get("parameters", {})

    logger.info("Tool call: %s(%s)", fn_name, params)

    if fn_name == "get_availability":
        days_ahead = params.get("days_ahead", 7)
        slots = await calcom.get_available_slots(days_ahead=days_ahead)
        if not slots:
            result = "I don't see any available slots in the next week. Please check back later."
        else:
            slot_list = "\n".join(f"• {s.formatted}" for s in slots[:5])
            result = f"Here are the available slots:\n{slot_list}\n\nWhich one works for you?"
        return JSONResponse({"result": result})

    elif fn_name == "book_meeting":
        try:
            booking = await calcom.create_booking(
                BookingRequest(
                    name=params.get("name", "Interviewer"),
                    email=params.get("email", ""),
                    start_time=params.get("start_time", ""),
                    notes=params.get("notes"),
                )
            )
            return JSONResponse({"result": booking.confirmation_message})
        except Exception as exc:
            logger.error("Booking failed: %s", exc)
            return JSONResponse({"result": "I had trouble booking that slot. Let me try again — could you confirm your email?"})

    return JSONResponse({"result": f"Unknown function: {fn_name}"})


async def _handle_call_report(message: dict) -> None:
    """Log end-of-call data for eval tracking."""
    call = message.get("call", {})
    duration = message.get("durationSeconds", 0)
    transcript = message.get("transcript", "")
    summary = message.get("summary", "")

    logger.info(
        "Call completed: id=%s duration=%ds summary=%s",
        call.get("id", ""),
        duration,
        summary[:100] if summary else "N/A",
    )
    # In production: save to DB for eval tracking
    # await db.save_call_report(call_id=call.get("id"), ...)


# ── Custom LLM endpoint (OpenAI-compatible) ───────────────────────────────────

@router.post("/llm")
async def vapi_llm(request: Request):
    """
    OpenAI-compatible endpoint called by Vapi for every conversational turn.

    Flow:
      1. Extract conversation from Vapi's request
      2. Identify last user message
      3. Run RAG retrieval against our Qdrant store
      4. Inject retrieved context into the system prompt
      5. Stream Claude's response back in OpenAI SSE format
    """
    try:
        body = await request.json()
        oai_req = OAIRequest(**body)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Extract last user message for retrieval
    user_message = ""
    history = []
    for msg in oai_req.messages:
        if msg.role == "user":
            user_message = msg.content
        if msg.role in ("user", "assistant"):
            history.append({"role": msg.role, "content": msg.content})

    # Retrieve context
    try:
        context_texts, _, _ = await retriever.get_context_for_prompt(
            user_message, history=history[:-1]  # exclude current message
        )
    except Exception:
        context_texts = []

    # Build Vapi-aware system prompt with injected context
    system_prompt = build_voice_system_prompt(context_texts)

    # Build messages for Claude (strip the original system, inject ours)
    claude_messages = [
        {"role": m.role, "content": m.content}
        for m in oai_req.messages
        if m.role in ("user", "assistant")
    ]

    if oai_req.stream:
        return StreamingResponse(
            _stream_openai_format(system_prompt, claude_messages, oai_req),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    else:
        return await _complete_openai_format(system_prompt, claude_messages, oai_req)


async def _stream_openai_format(
    system: str,
    messages: list[dict],
    req: OAIRequest,
) -> AsyncGenerator[str, None]:
    """Stream Claude response in OpenAI SSE format (what Vapi expects)."""
    import uuid

    chat_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())

    # Opening chunk
    yield _oai_chunk(chat_id, created, {"role": "assistant"}, finish_reason=None)

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    try:
        async with client.messages.stream(
            model=settings.CLAUDE_MODEL,
            max_tokens=req.max_tokens or 350,
            system=system,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield _oai_chunk(chat_id, created, {"content": text}, finish_reason=None)
    except Exception as exc:
        logger.error("Claude stream error in Vapi LLM: %s", exc)
        yield _oai_chunk(chat_id, created, {"content": " [error] "}, finish_reason="stop")
        yield "data: [DONE]\n\n"
        return

    yield _oai_chunk(chat_id, created, {}, finish_reason="stop")
    yield "data: [DONE]\n\n"


def _oai_chunk(chat_id: str, created: int, delta: dict, finish_reason: str | None) -> str:
    payload = {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": settings.CLAUDE_MODEL,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
    }
    return f"data: {json.dumps(payload)}\n\n"


async def _complete_openai_format(
    system: str,
    messages: list[dict],
    req: OAIRequest,
) -> JSONResponse:
    """Non-streaming completion (fallback)."""
    import uuid

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = await client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=req.max_tokens or 350,
        system=system,
        messages=messages,
    )
    content = response.content[0].text if response.content else ""

    return JSONResponse({
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "model": settings.CLAUDE_MODEL,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": response.usage.input_tokens,
            "completion_tokens": response.usage.output_tokens,
            "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
        },
    })
