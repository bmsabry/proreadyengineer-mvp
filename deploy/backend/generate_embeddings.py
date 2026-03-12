#!/usr/bin/env python3
"""
Generate embeddings for all providers using DeepInfra BAAI/bge-large-en-v1.5.

Model: BAAI/bge-large-en-v1.5 (1024 dimensions)
API:   DeepInfra OpenAI-compatible endpoint

Usage on Render shell:
    cd /opt/render/project/src/deploy/backend
    python generate_embeddings.py --api-key YOUR_DEEPINFRA_KEY
    python generate_embeddings.py --api-key KEY --all   # re-embed ALL (v3 update)

KEY DIFFERENCE from old script:
  - NO app imports (avoids .env SQLite override)
  - Reads DATABASE_URL directly from OS environment (Render injects it)
  - Uses raw asyncpg for direct PostgreSQL access
  - Detects and rejects SQLite URLs immediately
"""
import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import List

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
    p.add_argument("--model", default="BAAI/bge-large-en-v1.5")
    p.add_argument("--batch-size", type=int, default=10)
    p.add_argument("--rate-limit-sleep", type=float, default=1.0)
    p.add_argument(
        "--all", dest="only_missing", action="store_false",
        help="Re-embed ALL providers (default: only missing)",
    )
    p.set_defaults(only_missing=True)
    p.add_argument("--deepinfra-base", default="https://api.deepinfra.com/v1/openai")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def get_postgres_url() -> str:
    """Get PostgreSQL URL from OS environment.

    IMPORTANT: Reads ONLY from os.environ, NOT from .env file.
    On Render, DATABASE_URL is injected into the process environment automatically.
    The .env file contains a SQLite fallback that must NOT be used here.
    """
    db_url = os.environ.get("DATABASE_URL", "").strip()

    if not db_url:
        log.error("="*60)
        log.error("ERROR: DATABASE_URL is not set in environment!")
        log.error("On Render shell, this should be automatic.")
        log.error("Verify with: echo $DATABASE_URL")
        log.error("It should look like: postgresql://user:pass@host/dbname")
        log.error("="*60)
        sys.exit(1)

    if "sqlite" in db_url.lower():
        log.error("="*60)
        log.error(f"ERROR: DATABASE_URL is SQLite: {db_url}")
        log.error("This script requires PostgreSQL on Render.")
        log.error("The .env file has a SQLite fallback that should not be used.")
        log.error("Make sure the Render environment variable DATABASE_URL is set.")
        log.error("="*60)
        sys.exit(1)

    # Normalize URL for asyncpg (needs plain postgresql://)
    if db_url.startswith("postgres://"):
        db_url = "postgresql://" + db_url[len("postgres://"):]
    # Remove asyncpg driver prefix if present (asyncpg uses plain postgresql://)
    if "+asyncpg" in db_url:
        db_url = db_url.replace("+asyncpg", "")

    log.info(f"Using database: {db_url[:50]}...")
    return db_url


async def embed_texts(
    texts: List[str],
    model: str,
    api_key: str,
    base_url: str,
    timeout: float = 60.0,
) -> List[List[float]]:
    url = base_url.rstrip("/") + "/embeddings"
    headers = {"Authorization": "Bearer " + api_key, "Content-Type": "application/json"}
    payload = {"model": model, "input": texts}
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    return [item["embedding"] for item in data["data"]]


def safe_json_to_text(val) -> str:
    if not val:
        return ""
    if isinstance(val, list):
        return " ".join(str(x) for x in val if x)
    if isinstance(val, str):
        val = val.strip()
        if val.startswith("[") or val.startswith("{"):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, list):
                    return " ".join(str(x) for x in parsed if x)
                elif isinstance(parsed, dict):
                    return " ".join(str(v) for v in parsed.values() if v)
            except Exception:
                pass
        return val
    return str(val)


def build_embedding_text(row: dict) -> str:
    """Build v3 embedding text. Includes projects & case studies."""
    parts = []
    name = row.get("name") or row.get("firm_name") or ""
    if name:
        parts.append(name)
    if row.get("primary_specialty"):
        parts.append(row["primary_specialty"])
    if row.get("business_description"):
        parts.append(row["business_description"])
    for field in ["specialties", "capabilities", "software_tools"]:
        t = safe_json_to_text(row.get(field))
        if t:
            parts.append(t)
    # v3 additions
    t = safe_json_to_text(row.get("proven_experience_notable_projects"))
    if t:
        parts.append(t)
    t = safe_json_to_text(row.get("proven_experience_case_studies"))
    if t:
        parts.append(t)
    return " ".join(filter(None, parts)).strip()[:4096]


def print_progress(done: int, total: int, errors: int, label: str = "") -> None:
    pct = done / total * 100 if total else 0.0
    bar_len = 40
    filled = int(bar_len * done / total) if total else 0
    bar = "#" * filled + "-" * (bar_len - filled)
    line = f"\r[{bar}] {done}/{total} ({pct:.1f}%) errors={errors}  {label}"
    print(line, end="", flush=True)
    if done == total:
        print()


async def run(args: argparse.Namespace) -> None:
    db_url = get_postgres_url()

    try:
        import asyncpg
    except ImportError:
        log.error("asyncpg not installed. Run: pip install asyncpg")
        sys.exit(1)

    log.info("Connecting to PostgreSQL...")
    try:
        conn = await asyncpg.connect(db_url)
    except Exception as e:
        log.error(f"Failed to connect: {e}")
        sys.exit(1)
    log.info("Connected.")

    # Verify providers table exists
    table_exists = await conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='providers')"
    )
    if not table_exists:
        log.error("Table 'providers' does not exist! Run migration first.")
        log.error("  cd /opt/render/project/src/deploy/scripts && python3 migrate_providers.py")
        await conn.close()
        sys.exit(1)

    total_count = await conn.fetchval("SELECT COUNT(*) FROM providers")
    embed_count = await conn.fetchval("SELECT COUNT(*) FROM providers WHERE embedding IS NOT NULL")
    log.info(f"Providers: {total_count} total, {embed_count} already have embeddings")

    if total_count == 0:
        log.error("No providers found! Run migration first.")
        await conn.close()
        sys.exit(1)

    if args.only_missing:
        rows = await conn.fetch("""
            SELECT id, name, firm_name, primary_specialty, business_description,
                   specialties, capabilities, software_tools,
                   proven_experience_notable_projects, proven_experience_case_studies
            FROM providers WHERE embedding IS NULL ORDER BY id
        """)
        log.info(f"Found {len(rows)} providers WITHOUT embeddings.")
    else:
        rows = await conn.fetch("""
            SELECT id, name, firm_name, primary_specialty, business_description,
                   specialties, capabilities, software_tools,
                   proven_experience_notable_projects, proven_experience_case_studies
            FROM providers ORDER BY id
        """)
        log.info(f"Re-embedding ALL {len(rows)} providers (--all mode, v3 update).")

    total = len(rows)

    if args.dry_run:
        log.info(f"DRY RUN - first 10 of {total} providers:")
        for row in rows[:10]:
            t = build_embedding_text(dict(row))
            print(f"  [{row['id']}] {row['name'] or row['firm_name']}: {t[:80]}...")
        if total > 10:
            print(f"  ... and {total - 10} more")
        await conn.close()
        return

    if total == 0:
        log.info("Nothing to do - all providers already have embeddings.")
        await conn.close()
        return

    done = 0
    errors = 0
    skipped = 0
    start_time = time.time()

    for batch_start in range(0, total, args.batch_size):
        batch = rows[batch_start: batch_start + args.batch_size]
        texts = []
        valid_rows = []
        for row in batch:
            t = build_embedding_text(dict(row))
            if not t:
                skipped += 1
                continue
            texts.append(t)
            valid_rows.append(row)

        if not texts:
            done += len(batch)
            print_progress(done, total, errors)
            continue

        embeddings = None
        for attempt in range(3):
            try:
                embeddings = await embed_texts(
                    texts, model=args.model, api_key=args.api_key,
                    base_url=args.deepinfra_base,
                )
                break
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                log.error(f"HTTP {status} on batch {batch_start}: {exc}")
                if status == 401:
                    log.error("AUTHENTICATION FAILED - invalid API key or insufficient credits!")
                    await conn.close()
                    sys.exit(1)
                elif status == 429:
                    log.warning("Rate limited - sleeping 5s")
                    await asyncio.sleep(5)
                elif attempt == 2:
                    errors += len(texts)
                    break
            except Exception as exc:
                log.error(f"Error attempt {attempt+1}: {exc}")
                if attempt == 2:
                    errors += len(texts)
                    break
                await asyncio.sleep(2 ** attempt)

        if embeddings is None:
            done += len(batch)
            print_progress(done, total, errors)
            continue

        now = datetime.now(timezone.utc)
        for row, embedding in zip(valid_rows, embeddings):
            try:
                emb_list = embedding if isinstance(embedding, list) else list(embedding)
                await conn.execute(
                    """
                    UPDATE providers
                    SET embedding = $1::vector,
                        embedding_model = $2,
                        embedding_generated_at = $3,
                        embedding_version = '3'
                    WHERE id = $4
                    """,
                    str(emb_list), args.model, now, row["id"]
                )
            except Exception as exc:
                log.error(f"DB update failed for provider {row['id']}: {exc}")
                errors += 1

        done += len(batch)
        elapsed = time.time() - start_time
        rate = done / elapsed if elapsed > 0 else 0
        eta = (total - done) / rate if rate > 0 else 0
        print_progress(done, total, errors, f"rate={rate:.1f}/s eta={eta:.0f}s")

        if batch_start + args.batch_size < total:
            await asyncio.sleep(args.rate_limit_sleep)

    await conn.close()
    elapsed_total = time.time() - start_time
    log.info(
        f"Done! Embedded {done-errors-skipped}/{total} providers in {elapsed_total:.1f}s. "
        f"Errors={errors}, Skipped={skipped}"
    )


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(run(args))
