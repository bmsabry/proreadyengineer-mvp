#!/usr/bin/env python3
"""
Generate embeddings for all providers using DeepInfra BAAI/bge-large-en-v1.5.

Model: BAAI/bge-large-en-v1.5 (1024 dimensions)
API:   DeepInfra OpenAI-compatible endpoint

Usage:
    python generate_embeddings.py --api-key YOUR_DEEPINFRA_KEY
    python generate_embeddings.py --api-key KEY --batch-size 20
    python generate_embeddings.py --api-key KEY --all   # re-embed all providers
"""
import argparse
import asyncio
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate provider embeddings via DeepInfra")
    p.add_argument("--api-key", required=True, help="DeepInfra API key")
    p.add_argument(
        "--model",
        default="BAAI/bge-large-en-v1.5",
        help="Embedding model (default: BAAI/bge-large-en-v1.5)",
    )
    p.add_argument(
        "--batch-size", type=int, default=10,
        help="Providers per API call (default: 10)",
    )
    p.add_argument(
        "--rate-limit-sleep", type=float, default=1.0,
        help="Seconds to sleep between batches (default: 1.0)",
    )
    p.add_argument(
        "--all",
        dest="only_missing",
        action="store_false",
        help="Re-embed ALL providers (default: only embed missing)",
    )
    p.set_defaults(only_missing=True)
    p.add_argument("--db-url", default=None, help="Database URL (overrides .env)")
    p.add_argument(
        "--deepinfra-base",
        default="https://api.deepinfra.com/v1/openai",
        help="DeepInfra API base URL",
    )
    p.add_argument("--dry-run", action="store_true", help="List providers without calling API")
    return p.parse_args()


async def embed_texts(
    texts: List[str],
    model: str,
    api_key: str,
    base_url: str,
    timeout: float = 60.0,
) -> List[List[float]]:
    """Call DeepInfra embeddings endpoint; return list of vectors."""
    url = base_url.rstrip("/") + "/embeddings"
    headers = {
        "Authorization": "Bearer " + api_key,
        "Content-Type": "application/json",
    }
    payload = {"model": model, "input": texts}
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    return [item["embedding"] for item in data["data"]]


def get_db_url(override: Optional[str]) -> str:
    if override:
        return override
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("DATABASE_URL") and "=" in line and not line.startswith("#"):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if val:
                    return val
    import os
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        raise ValueError("No DATABASE_URL found. Pass --db-url or set DATABASE_URL in .env")
    return db_url


def print_progress(done: int, total: int, errors: int, label: str = "") -> None:
    pct = done / total * 100 if total else 0.0
    bar_len = 40
    filled = int(bar_len * done / total) if total else 0
    bar = "#" * filled + "-" * (bar_len - filled)
    line = "\r[" + bar + "] " + str(done) + "/" + str(total) + " (" + format(pct, ".1f") + "%) errors=" + str(errors) + "  " + label
    print(line, end="", flush=True)
    if done == total:
        print()


async def run(args: argparse.Namespace) -> None:
    db_url = get_db_url(args.db_url)

    if db_url.startswith("sqlite:///") and "+aiosqlite" not in db_url:
        db_url = db_url.replace("sqlite:///", "sqlite+aiosqlite:///")
    elif db_url.startswith("postgresql://") and "+asyncpg" not in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")

    from sqlalchemy import select, update
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_async_engine(db_url, echo=False)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    sys.path.insert(0, str(Path(__file__).parent))
    from app.models.provider import Provider

    async with AsyncSessionLocal() as db:
        if args.only_missing:
            stmt = select(Provider).where(Provider.embedding.is_(None))
            log.info("Querying providers without embeddings...")
        else:
            stmt = select(Provider)
            log.info("Querying ALL providers for re-embedding...")

        result = await db.execute(stmt)
        providers = result.scalars().all()
        total = len(providers)
        log.info("Found " + str(total) + " providers to embed.")

        if args.dry_run:
            log.info("DRY RUN - no API calls will be made.")
            for p in providers[:10]:
                preview = (p.business_description or "")[:80].replace("\n", " ")
                print("  [" + str(p.id) + "] " + str(p.name or p.firm_name) + ": " + preview + "...")
            if total > 10:
                print("  ... and " + str(total - 10) + " more providers")
            return

        if total == 0:
            log.info("Nothing to do. All providers already have embeddings.")
            return

        done = 0
        errors = 0
        skipped = 0
        start_time = time.time()

        for batch_start in range(0, total, args.batch_size):
            batch = providers[batch_start: batch_start + args.batch_size]

            texts = []
            valid_providers = []
            for p in batch:
                parts = [
                    p.name or p.firm_name or "",
                    p.primary_specialty or "",
                    p.business_description or "",
                ]
                if p.capabilities:
                    if isinstance(p.capabilities, list):
                        parts.append(" ".join(p.capabilities))
                    else:
                        parts.append(str(p.capabilities))
                combined = " ".join(filter(None, parts)).strip()
                if not combined:
                    log.warning("Provider " + str(p.id) + " has no text content, skipping.")
                    skipped += 1
                    continue
                texts.append(combined[:2048])
                valid_providers.append(p)

            if not texts:
                done += len(batch)
                print_progress(done, total, errors)
                continue

            embeddings = None
            for attempt in range(3):
                try:
                    embeddings = await embed_texts(
                        texts,
                        model=args.model,
                        api_key=args.api_key,
                        base_url=args.deepinfra_base,
                    )
                    break
                except httpx.HTTPStatusError as exc:
                    log.error("HTTP " + str(exc.response.status_code) + " on batch " + str(batch_start) + ": " + str(exc))
                    if exc.response.status_code == 429:
                        log.warning("Rate limited – sleeping 5 seconds")
                        await asyncio.sleep(5)
                    elif attempt == 2:
                        log.error("Skipping batch " + str(batch_start) + " after 3 failures")
                        errors += len(texts)
                        break
                except Exception as exc:
                    log.error("Error on batch " + str(batch_start) + " attempt " + str(attempt + 1) + ": " + str(exc))
                    if attempt == 2:
                        errors += len(texts)
                        break
                    await asyncio.sleep(2 ** attempt)

            if embeddings is None:
                done += len(batch)
                print_progress(done, total, errors)
                continue

            for provider, embedding in zip(valid_providers, embeddings):
                try:
                    await db.execute(
                        update(Provider)
                        .where(Provider.id == provider.id)
                        .values(
                            embedding=embedding,
                            embedding_model=args.model,
                            embedding_generated_at=datetime.utcnow(),
                            embedding_version="1",
                        )
                    )
                except Exception as exc:
                    log.error("DB update failed for provider " + str(provider.id) + ": " + str(exc))
                    errors += 1

            await db.commit()
            done += len(batch)

            elapsed = time.time() - start_time
            rate = done / elapsed if elapsed > 0 else 0
            eta = (total - done) / rate if rate > 0 else 0
            label = "rate=" + format(rate, ".1f") + "/s eta=" + format(eta, ".0f") + "s"
            print_progress(done, total, errors, label)

            if batch_start + args.batch_size < total:
                await asyncio.sleep(args.rate_limit_sleep)

    elapsed_total = time.time() - start_time
    log.info(
        "Done! Embedded " + str(done - errors - skipped) + "/" + str(total) +
        " providers in " + format(elapsed_total, ".1f") + "s. " +
        "Errors=" + str(errors) + ", Skipped(no text)=" + str(skipped)
    )


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(run(args))
