"""
AI Persona API — main entry point.

Routes:
  GET  /health                   health check
  POST /api/chat                 streaming chat (SSE)
  POST /api/chat/slots           available calendar slots
  POST /api/chat/book            create booking
  POST /api/vapi/webhook         Vapi lifecycle events
  POST /api/vapi/llm             custom LLM for Vapi (OpenAI-compatible)
  POST /api/calendar/slots       calendar slots (standalone)
  POST /api/calendar/book        booking (standalone)
  POST /api/ingest               trigger knowledge ingestion (protected)
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.models import IngestRequest, IngestResponse
from app.rag.ingest import run_full_ingestion
from app.rag.retriever import init_retriever
from app.routes import calendar, chat, vapi

# ── Logging ───────────────────────────────────────────────────────────────────
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ]
)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = get_settings()


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AI Persona API (model=%s)", settings.CLAUDE_MODEL)
    await init_retriever()
    logger.info("Vector store ready: %s", settings.QDRANT_COLLECTION)
    yield
    logger.info("Shutting down")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="AI Persona API",
    description="RAG-grounded voice & chat persona for professional screening",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
)

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


# ── Request timing middleware ─────────────────────────────────────────────────

@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    start = time.monotonic()
    response = await call_next(request)
    elapsed = int((time.monotonic() - start) * 1000)
    response.headers["X-Response-Time-Ms"] = str(elapsed)
    return response


# ── Routes ────────────────────────────────────────────────────────────────────

app.include_router(chat.router,     prefix="/api/chat",     tags=["chat"])
app.include_router(vapi.router,     prefix="/api/vapi",     tags=["voice"])
app.include_router(calendar.router, prefix="/api/calendar", tags=["calendar"])


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["system"])
async def health():
    return {
        "status": "ok",
        "version": "1.0.0",
        "model": settings.CLAUDE_MODEL,
        "collection": settings.QDRANT_COLLECTION,
    }


# ── Ingestion endpoint (protected) ───────────────────────────────────────────

@app.post("/api/ingest", response_model=IngestResponse, tags=["system"])
async def trigger_ingest(req: IngestRequest):
    if req.secret != settings.INGEST_SECRET:
        raise HTTPException(status_code=403, detail="Invalid ingest secret")

    result = await run_full_ingestion(sources=req.sources)

    return IngestResponse(
        status="ok",
        chunks_added=result["chunks_added"],
        sources_processed=result["sources"],
        elapsed_seconds=result["elapsed_seconds"],
    )


# ── Root redirect ─────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root():
    return JSONResponse({"message": "AI Persona API — see /docs"})
