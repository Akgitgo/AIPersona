from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import time


# ── Chat ──────────────────────────────────────────────────────────────────────

class Role(str, Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


class Message(BaseModel):
    role: Role
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4096)
    session_id: str = Field(default="default")
    stream: bool = Field(default=True)


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    retrieval_sources: List[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    latency_ms: int = Field(default=0)


class RetrievedChunk(BaseModel):
    text: str
    source: str          # "resume" | "github:{repo}" | "persona"
    score: float
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ── Voice / Vapi ─────────────────────────────────────────────────────────────

class VapiMessage(BaseModel):
    role: str
    content: str
    time: Optional[float] = None
    secondsFromStart: Optional[float] = None


class VapiCall(BaseModel):
    id: str
    phoneNumberId: Optional[str] = None
    type: Optional[str] = None


class VapiFunctionCall(BaseModel):
    name: str
    parameters: Dict[str, Any] = Field(default_factory=dict)


class VapiWebhookPayload(BaseModel):
    message: Dict[str, Any]


# OpenAI-compatible LLM request (sent by Vapi to our custom LLM endpoint)
class OAIMessage(BaseModel):
    role: str
    content: str


class OAIRequest(BaseModel):
    model: str = "gpt-4"
    messages: List[OAIMessage]
    stream: bool = False
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 512
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Any] = None


# ── Calendar ─────────────────────────────────────────────────────────────────

class SlotRequest(BaseModel):
    days_ahead: int = Field(default=7, ge=1, le=30)
    timezone: str = Field(default="Asia/Kolkata")


class TimeSlot(BaseModel):
    start: str          # ISO 8601
    end: str
    formatted: str      # human-friendly


class SlotsResponse(BaseModel):
    slots: List[TimeSlot]
    timezone: str


class BookingRequest(BaseModel):
    name: str = Field(..., min_length=1)
    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    start_time: str     # ISO 8601
    notes: Optional[str] = None
    timezone: str = Field(default="Asia/Kolkata")


class BookingResponse(BaseModel):
    success: bool
    booking_id: Optional[str] = None
    meeting_url: Optional[str] = None
    calendar_link: Optional[str] = None
    confirmation_message: str


# ── Ingestion ────────────────────────────────────────────────────────────────

class IngestRequest(BaseModel):
    secret: str
    sources: List[str] = Field(default=["resume", "github", "persona"])


class IngestResponse(BaseModel):
    status: str
    chunks_added: int
    sources_processed: List[str]
    elapsed_seconds: float


# ── Evals ────────────────────────────────────────────────────────────────────

class EvalQuestion(BaseModel):
    id: str
    question: str
    expected_keywords: List[str] = Field(default_factory=list)
    ground_truth: Optional[str] = None
    category: str = "general"  # general | technical | adversarial | calendar


class EvalResult(BaseModel):
    question_id: str
    question: str
    answer: str
    hallucinated: bool
    confidence: float
    retrieval_sources: List[str]
    judge_score: float       # 0-1 from LLM judge
    judge_reasoning: str
    latency_ms: int


class EvalReport(BaseModel):
    timestamp: str
    total_questions: int
    hallucination_rate: float
    avg_judge_score: float
    avg_latency_ms: float
    avg_confidence: float
    by_category: Dict[str, Dict[str, float]]
    results: List[EvalResult]
