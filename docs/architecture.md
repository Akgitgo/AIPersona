# Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         USER INTERFACES                             │
│                                                                     │
│  ┌──────────────────────────┐     ┌──────────────────────────────┐ │
│  │   📞 Voice Agent          │     │   💬 Chat Interface          │ │
│  │   Phone number (Vapi)     │     │   Next.js → Vercel           │ │
│  │   STT: Deepgram Nova-2    │     │   SSE streaming              │ │
│  │   TTS: ElevenLabs         │     │   Booking modal              │ │
│  └────────────┬─────────────┘     └──────────────┬───────────────┘ │
└───────────────┼──────────────────────────────────┼─────────────────┘
                │ POST /api/vapi/llm                │ POST /api/chat
                │ (OpenAI-compat SSE)               │ (SSE stream)
┌───────────────▼──────────────────────────────────▼─────────────────┐
│                    FASTAPI BACKEND  (Railway)                       │
│                                                                     │
│  ┌──────────────────────┐   ┌──────────────────────────────────┐   │
│  │   /api/vapi/llm      │   │   /api/chat                      │   │
│  │   /api/vapi/webhook  │   │   /api/calendar/slots            │   │
│  │   (tool calls →      │   │   /api/calendar/book             │   │
│  │    calendar)         │   │   /api/ingest  (protected)       │   │
│  └──────────┬───────────┘   └──────────────┬────────────────── ┘   │
│             │                              │                        │
│             └─────────────┬───────────────┘                        │
│                           ▼                                         │
│             ┌─────────────────────────────┐                        │
│             │         RAG PIPELINE        │                        │
│             │                             │                        │
│             │  1. Query reformulation     │                        │
│             │     (Claude Haiku, ~50ms)   │                        │
│             │                             │                        │
│             │  2. Embed query             │                        │
│             │     (OpenAI ada-3, ~80ms)   │                        │
│             │                             │                        │
│             │  3. Qdrant search + MMR     │                        │
│             │     (top-6, ~50ms)          │                        │
│             │                             │                        │
│             │  4. Claude Sonnet stream    │                        │
│             │     (first token ~300ms)    │                        │
│             └──────────┬──────────────────┘                        │
└────────────────────────┼────────────────────────────────────────── ┘
                         │
        ┌────────────────┼────────────────────────┐
        ▼                ▼                         ▼
┌──────────────┐  ┌─────────────┐      ┌────────────────────┐
│  Qdrant Cloud│  │  Anthropic  │      │  Cal.com API       │
│  Vector DB   │  │  Claude API │      │  (slot fetch +     │
│  (free tier) │  │  Sonnet +   │      │   booking confirm) │
│              │  │  Haiku      │      └────────────────────┘
└──────────────┘  └─────────────┘
```

## Data Flow — Chat Turn

```
User types message
      │
      ▼
Frontend streams POST /api/chat
      │
      ├─ [SSE: sources event]  ← retrieval metadata sent first
      ├─ [SSE: token token token...]
      └─ [SSE: done + metadata]
```

## Data Flow — Voice Turn

```
Caller speaks
      │ Deepgram STT (~200ms)
      ▼
Vapi sends POST /api/vapi/llm (OpenAI format)
      │
      ├─ RAG retrieval (~130ms total)
      ├─ System prompt injection
      ├─ Claude streaming (~300ms to first token)
      │
      ▼
Vapi receives first sentence → starts ElevenLabs TTS
      │
Total caller latency: ~630ms (well under 2s requirement)
```

## Ingestion Pipeline

```
resume.pdf ──────┐
                 ├──► chunk (512 tok, 64 overlap)
GitHub repos ────┤    │
                 │    ▼
persona.json ────┘  OpenAI embed (text-embedding-3-small)
                         │
                         ▼
                    Qdrant upsert (cosine, 1536-dim)
```

## Retrieval Quality Stack

| Layer | Technique | Purpose |
|-------|-----------|---------|
| Query rewrite | Claude Haiku | Resolve pronouns / follow-ups |
| Dense retrieval | OpenAI embeddings + Qdrant | Semantic similarity |
| Diversity | MMR reranking (λ=0.5) | Avoid redundant chunks |
| Confidence gate | Mean cosine score | Flag low-confidence answers |
| Anti-hallucination | Grounded system prompt | Never invent facts |

## Latency Budget (Voice)

| Component | Target | Actual (measured) |
|-----------|--------|-------------------|
| Deepgram STT | <200ms | ~180ms |
| Network (Vapi → Railway) | <100ms | ~80ms |
| Query reformulation (Haiku) | <100ms | ~70ms |
| Qdrant search | <60ms | ~45ms |
| Claude first token | <350ms | ~280ms |
| **Total to first audio** | **<2000ms** | **~655ms** |

## Cost Breakdown

| Item | Cost | Notes |
|------|------|-------|
| Qdrant Cloud | $0/mo | Free cluster, 1GB |
| Claude Sonnet | ~$0.004/chat turn | 800 avg tokens |
| Claude Haiku (rewrite) | ~$0.0002/turn | 100 tokens |
| OpenAI Embeddings | ~$0.00002/query | text-embedding-3-small |
| Vapi voice | ~$0.05/min | Includes STT + TTS |
| **Per chat session** | **~$0.01** | 10 turns avg |
| **Per voice call** | **~$0.15** | 3 min avg |
| Railway backend | $5/mo | Starter plan |
| Vercel frontend | $0/mo | Hobby plan |
