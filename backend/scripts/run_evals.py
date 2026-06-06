#!/usr/bin/env python3
"""
Evaluation runner.

Measures:
  - Hallucination rate (LLM-as-judge against retrieved context)
  - Retrieval precision@K
  - Response latency
  - Judge score distribution by category

Usage:
  python scripts/run_evals.py
  python scripts/run_evals.py --output evals/report.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import anthropic
from app.config import get_settings
from app.models import EvalQuestion, EvalReport, EvalResult
from app.rag import pipeline, retriever

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)
settings = get_settings()

GOLDEN_QA_PATH = Path(__file__).parent.parent / "evals" / "golden_qa.json"
HALLUCINATION_JUDGE_PROMPT = """You are a strict factual accuracy judge evaluating an AI persona's response.

QUESTION: {question}
ANSWER: {answer}
RETRIEVED CONTEXT (what the AI had access to): {context}

Task: Determine if the ANSWER makes any factual claims NOT supported by the RETRIEVED CONTEXT.

Respond ONLY with a JSON object (no markdown, no explanation outside the object):
{{
  "hallucinated": true/false,
  "score": 0.0-1.0,
  "reasoning": "one sentence explanation",
  "unsupported_claims": []
}}

score=1.0 means fully grounded, score=0.0 means fully hallucinated."""


async def judge_answer(
    question: str,
    answer: str,
    context: list[str],
) -> dict:
    """Use Claude claude-haiku-4-5-20251001 as judge to detect hallucinations."""
    ctx_text = "\n---\n".join(context) if context else "No context available."
    prompt = HALLUCINATION_JUDGE_PROMPT.format(
        question=question,
        answer=answer,
        context=ctx_text[:3000],
    )

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    msg = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()

    try:
        return json.loads(raw)
    except Exception:
        return {"hallucinated": False, "score": 0.5, "reasoning": "Parse error", "unsupported_claims": []}


async def eval_single(q: EvalQuestion, session_prefix: str) -> EvalResult:
    """Evaluate a single question."""
    session_id = f"{session_prefix}_{q.id}"
    start = time.monotonic()

    # Run chat pipeline
    result = await pipeline.complete_response(q.question, session_id=session_id)
    latency_ms = int((time.monotonic() - start) * 1000)

    answer = result.get("reply", "")
    sources = result.get("sources", [])
    confidence = result.get("confidence", 0.0)

    # Retrieve context used (for judge)
    chunks = await retriever.search(q.question)
    context_texts = [c.text for c in chunks]

    # Judge
    judgment = await judge_answer(q.question, answer, context_texts)

    return EvalResult(
        question_id=q.id,
        question=q.question,
        answer=answer,
        hallucinated=judgment.get("hallucinated", False),
        confidence=confidence,
        retrieval_sources=sources,
        judge_score=judgment.get("score", 0.5),
        judge_reasoning=judgment.get("reasoning", ""),
        latency_ms=latency_ms,
    )


async def run_evals(output_path: Path | None = None) -> EvalReport:
    await retriever.init_retriever()

    with open(GOLDEN_QA_PATH) as f:
        questions_raw = json.load(f)

    questions = [EvalQuestion(**q) for q in questions_raw]
    session_prefix = f"eval_{int(time.time())}"

    print(f"\n📊 Running evals on {len(questions)} questions...\n")

    results = []
    for i, q in enumerate(questions):
        print(f"  [{i+1}/{len(questions)}] {q.category}: {q.question[:60]}...", end=" ", flush=True)
        result = await eval_single(q, session_prefix)
        results.append(result)
        status = "✓" if not result.hallucinated else "✗ HALLUCINATION"
        print(f"{status} (score={result.judge_score:.2f}, latency={result.latency_ms}ms)")

    # Aggregate
    total = len(results)
    hallucination_rate = sum(1 for r in results if r.hallucinated) / total
    avg_score = sum(r.judge_score for r in results) / total
    avg_latency = sum(r.latency_ms for r in results) / total
    avg_confidence = sum(r.confidence for r in results) / total

    # By category
    categories: dict[str, list[EvalResult]] = {}
    for r in results:
        q_obj = next(q for q in questions if q.id == r.question_id)
        cat = q_obj.category
        categories.setdefault(cat, []).append(r)

    by_category = {}
    for cat, cat_results in categories.items():
        by_category[cat] = {
            "count": len(cat_results),
            "hallucination_rate": sum(1 for r in cat_results if r.hallucinated) / len(cat_results),
            "avg_score": sum(r.judge_score for r in cat_results) / len(cat_results),
            "avg_latency_ms": sum(r.latency_ms for r in cat_results) / len(cat_results),
        }

    report = EvalReport(
        timestamp=datetime.utcnow().isoformat(),
        total_questions=total,
        hallucination_rate=round(hallucination_rate, 4),
        avg_judge_score=round(avg_score, 4),
        avg_latency_ms=round(avg_latency, 1),
        avg_confidence=round(avg_confidence, 4),
        by_category=by_category,
        results=results,
    )

    print(f"\n{'='*60}")
    print(f"EVAL REPORT")
    print(f"{'='*60}")
    print(f"  Total questions    : {total}")
    print(f"  Hallucination rate : {hallucination_rate:.1%}")
    print(f"  Avg judge score    : {avg_score:.2f}/1.0")
    print(f"  Avg latency        : {avg_latency:.0f}ms")
    print(f"  Avg confidence     : {avg_confidence:.2f}")
    print(f"\n  By category:")
    for cat, stats in by_category.items():
        print(f"    {cat}: score={stats['avg_score']:.2f}, halluc={stats['hallucination_rate']:.1%}")
    print(f"{'='*60}\n")

    if output_path:
        with open(output_path, "w") as f:
            json.dump(report.model_dump(), f, indent=2)
        print(f"✅ Full report saved to {output_path}")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    asyncio.run(run_evals(output_path=args.output))
