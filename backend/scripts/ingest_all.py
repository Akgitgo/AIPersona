#!/usr/bin/env python3
"""
Standalone ingestion script.

Usage (from backend/ directory):
  python scripts/ingest_all.py                      # ingest everything
  python scripts/ingest_all.py --sources resume     # only resume
  python scripts/ingest_all.py --sources github persona
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Add parent to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from app.rag.ingest import run_full_ingestion

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


async def main():
    parser = argparse.ArgumentParser(description="Ingest documents into vector store")
    parser.add_argument(
        "--sources",
        nargs="+",
        choices=["resume", "github", "persona"],
        default=["resume", "github", "persona"],
        help="Which sources to ingest",
    )
    args = parser.parse_args()

    print(f"\n🔄 Starting ingestion: {args.sources}\n")
    result = await run_full_ingestion(sources=args.sources)
    print(f"\n✅ Done!")
    print(f"   Sources processed : {result['sources']}")
    print(f"   Chunks added      : {result['chunks_added']}")
    print(f"   Time elapsed      : {result['elapsed_seconds']}s\n")


if __name__ == "__main__":
    asyncio.run(main())
