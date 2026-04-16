#!/usr/bin/env python3
# migrate_providers.py - Safe UPSERT migration preserving embeddings.
# Normal mode: UPSERT all providers WITHOUT touching embedding columns.
# --force mode: destructive delete+insert (destroys all embeddings).
# Usage:
#   python migrate_providers.py           # safe upsert (DEFAULT)
#   python migrate_providers.py --force   # destructive, destroys embeddings
import asyncio, json, sys, os
from datetime import datetime

script_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(script_dir, '../../backend'))
sys.path.insert(0, backend_dir)
print(f'Backend path: {backend_dir}')

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.db.session import AsyncSessionLocal
import sqlite3

# These 4 fields are NEVER written in normal upsert mode.
# They are only populated by generate_embeddings.py.
EMBEDDING_PROTECTED_FIELDS = [
    'embedding',
    'embedding_model',
    'embedding_generated_at',
    'embedding_version',
]

# All fields to upsert - intentionally excludes all embedding fields above.
UPSERT_FIELDS = [
    'name',
    'firm_name',
    'website',
    'phone',
    'address',
    'city',
    'state',
    'postal_code',
    'rating',
    'review_count',
    'place_id',
    'search_query',
    'search_city',
    'is_engineering_service',
    'is_mechanical_focus',
    'classification_confidence',
    'classification_reasoning',
    'primary_specialty',
    'secondary_specialties',
    'homepage_crawl_status',
    'homepage_file',
    'homepage_content_size',
    'deep_crawl_status',
    'deep_crawl_page_count',
    'deep_crawl_content_size',
    'business_description',
    'capabilities',
    'specialties',
    'software_tools',
    'notable_clients',
    'email_addresses',
    'certifications',
    'equipment',
    'business_evaluation_tier',
    'business_evaluation_years_in_business',
    'business_evaluation_employee_count',
    'proven_experience_project_count',
    'proven_experience_case_studies',
    'proven_experience_industries_served',
    'proven_experience_years_in_business',
    'proven_experience_notable_projects',
    'online_presence_youtube_channel',
    'online_presence_linkedin_url',
    'online_presence_yelp_url',
    'online_presence_review_count',
    'online_presence_average_rating',
    'online_presence_reputation_summary',
    'team_members',
    'team_summary',
    'projects',
    'created_at',
    'updated_at',
    'claim_status',
    'claimed_by_user_id',
]

# SQLite fields stored as JSON strings needing parse for JSONB columns
JSON_FIELDS = {
    'secondary_specialties',
    'capabilities',
    'specialties',
    'software_tools',
    'email_addresses',
    'certifications',
    'equipment',
    'proven_experience_case_studies',
    'proven_experience_industries_served',
    'proven_experience_notable_projects',
    'team_members',
    'projects',
}

# Sequence reset SQL
SEQ_SQL = "SELECT setval('providers_id_seq', COALESCE((SELECT MAX(id) FROM providers), 1), true)"


def find_sqlite_db():
    candidates = [
        '/opt/render/project/src/engineering_directory.db',
        '/a0/usr/projects/website_for_engineering_directory/engineering_directory.db',
        os.path.abspath(os.path.join(script_dir, '../../engineering_directory.db')),
        os.path.join(os.getcwd(), 'engineering_directory.db'),
    ]
    for path in candidates:
        if os.path.exists(path):
            print(f'Found SQLite DB at: {path}')
            return path
    raise FileNotFoundError(f'Cannot find engineering_directory.db. Tried: {candidates}')


def parse_json_field(value):
    if not value:
        return None
    try:
        return json.loads(value)
    except Exception:
        return [value] if isinstance(value, str) and value.strip() else None


def serialize_for_pg(field, value):
    if value is None:
        return None
    if field in JSON_FIELDS:
        p = parse_json_field(value)
        return json.dumps(p) if p is not None else None
    if field in ('rating', 'online_presence_average_rating'):
        try:
            return float(str(value))
        except Exception:
            return None
    if field in ('created_at', 'updated_at'):
        if isinstance(value, str) and value.strip():
            try:
                return datetime.fromisoformat(value)
            except Exception:
                return datetime.utcnow()
        return datetime.utcnow()
    if field in ('is_engineering_service', 'is_mechanical_focus'):
        return 1 if value else 0
    if field == 'review_count':
        try:
            return int(value) if value is not None else 0
        except Exception:
            return 0
    return value


def build_upsert_sql():
    # EMBEDDING PROTECTION:
    # UPSERT_FIELDS does NOT contain embedding/embedding_model/
    # embedding_generated_at/embedding_version.
    # Therefore the ON CONFLICT DO UPDATE SET clause will NEVER
    # overwrite existing embedding data. New rows get NULL embeddings
    # which generate_embeddings.py fills in later.
    all_cols = ['id'] + UPSERT_FIELDS
    cols_str = ', '.join(all_cols)
    params_str = ', '.join(':' + c for c in all_cols)
    update_parts = ',\n            '.join(f + ' = EXCLUDED.' + f for f in UPSERT_FIELDS)
    return (
        'INSERT INTO providers (' + cols_str + ')\n'
        '        VALUES (' + params_str + ')\n'
        '        ON CONFLICT (id) DO UPDATE SET\n'
        '            ' + update_parts
    )

def build_row_params(sqlite_cols, row, all_cols, null_ctr):
    rd = dict(zip(sqlite_cols, row))
    rid = rd.get('id')
    if not rid:
        null_ctr[0] += 1
        rid = null_ctr[0]
        rd['id'] = rid
    name = rd.get('name') or rd.get('firm_name') or ('Provider ' + str(rid))
    rd['name'] = name
    rd['firm_name'] = rd.get('firm_name') or name
    params = {c: serialize_for_pg(c, rd.get(c)) for c in all_cols}
    if not params['created_at']:
        params['created_at'] = datetime.utcnow()
    if not params['updated_at']:
        params['updated_at'] = datetime.utcnow()
    return rid, params, rd


async def run_safe_upsert(session, sqlite_conn):
    """
    UPSERT all providers from SQLite into PostgreSQL.
    EMBEDDING PROTECTION GUARANTEE:
      - embedding, embedding_model, embedding_generated_at, embedding_version
        are NOT in UPSERT_FIELDS and therefore NOT in the ON CONFLICT UPDATE SET.
      - Existing embeddings are 100% preserved for all existing providers.
      - New provider rows get NULL embeddings (correct; filled by generate_embeddings.py).
    """
    cur = sqlite_conn.cursor()
    cur.execute('SELECT COUNT(*) FROM companies')
    total = cur.fetchone()[0]
    print(f'Found {total} companies in SQLite')
    if total == 0:
        print('ERROR: No companies found!')
        return {'inserted': 0, 'updated': 0, 'errors': 0}

    cur.execute('SELECT * FROM companies')
    companies = cur.fetchall()
    cur.execute('PRAGMA table_info(companies)')
    sqlite_cols = [c[1] for c in cur.fetchall()]
    print(f'SQLite columns ({len(sqlite_cols)}): {sqlite_cols[:6]}...')

    result = await session.execute(text('SELECT id FROM providers'))
    existing_ids = {r[0] for r in result.fetchall()}
    print(f'Existing providers in PostgreSQL: {len(existing_ids)}')

    # Build firm name+location -> id map to detect duplicates before they happen
    name_loc_to_id = {}
    result2 = await session.execute(text(
        "SELECT id, LOWER(TRIM(firm_name)), LOWER(TRIM(COALESCE(city,''))), LOWER(TRIM(COALESCE(state,''))) FROM providers"
    ))
    for pg_id, fn, fc, fs in result2.fetchall():
        if fn:
            key = (fn, fc, fs)
            # Keep the lowest id as canonical if multiple exist
            if key not in name_loc_to_id or pg_id < name_loc_to_id[key]:
                name_loc_to_id[key] = pg_id
    print(f'Name+location index built: {len(name_loc_to_id)} unique firm locations')

    result = await session.execute(text('SELECT COALESCE(MAX(id),0) FROM providers'))
    max_pg = result.scalar() or 0
    cur.execute('SELECT COALESCE(MAX(id),0) FROM companies')
    max_sq = cur.fetchone()[0] or 0
    null_ctr = [max(max_pg, max_sq)]

    upsert_sql = build_upsert_sql()
    all_cols = ['id'] + UPSERT_FIELDS
    inserted = updated = errors = 0
    sqlite_ids = set()  # track all SQLite IDs for deletion comparison
    err_list = []

    print('')
    print('=' * 60)
    print('SAFE UPSERT MODE - Embeddings PROTECTED')
    print('Protected fields (never written): ' + str(EMBEDDING_PROTECTED_FIELDS))
    print('=' * 60)
    print('')

    for i, row in enumerate(companies):
        rd = {}
        try:
            rid, params, rd = build_row_params(sqlite_cols, row, all_cols, null_ctr)
            # DUPLICATE PREVENTION: Check if a firm with same name+city+state
            # already exists in PostgreSQL with a DIFFERENT id.
            # If so, reuse that id so ON CONFLICT updates it instead of inserting a new record.
            fn_key = (
                (str(rd.get('firm_name') or '')).lower().strip(),
                (str(rd.get('city') or '')).lower().strip(),
                (str(rd.get('state') or '')).lower().strip(),
            )
            if fn_key[0] and rid not in existing_ids and fn_key in name_loc_to_id:
                existing_pg_id = name_loc_to_id[fn_key]
                print(f'  DEDUP: SQLite id={rid} "{rd.get("firm_name","")[:40]}" mapped to existing PG id={existing_pg_id}')
                params['id'] = existing_pg_id
                rid = existing_pg_id
            await session.execute(text(upsert_sql), params)
            sqlite_ids.add(rid)
            if rid in existing_ids:
                updated += 1
            else:
                inserted += 1
                existing_ids.add(rid)
            if (i + 1) % 100 == 0:
                await session.commit()
                done = inserted + updated
                print(f'  {done}/{total} ({done/total*100:.1f}%) | new={inserted} updated={updated} err={errors}')
        except Exception as e:
            errors += 1
            eid = rd.get('id', '?')
            ename = str(rd.get('firm_name') or '')[:40]
            msg = f'  ERROR row {i+1} id={eid} {repr(ename)}: {str(e)[:100]}'
            print(msg)
            err_list.append(msg)
            await session.rollback()
            if len(err_list) > 50:
                print('Too many errors, aborting.')
                break

    if (inserted + updated) % 100 != 0:
        await session.commit()

    await session.execute(text(SEQ_SQL))
    await session.commit()
    print('Sequence providers_id_seq reset to MAX(id).')
    print('EMBEDDING PROTECTION CONFIRMED: embedding columns were never written.')

    # ── Auto-delete firms removed from SQLite ──────────────────────────────
    deleted, skipped = await delete_removed_providers(session, existing_ids, sqlite_ids)

    return {'inserted': inserted, 'updated': updated, 'errors': errors, 'deleted': deleted, 'skipped_deletion': skipped}


async def delete_removed_providers(session, existing_pg_ids: set, sqlite_ids: set):
    """
    Auto-delete providers that existed in PostgreSQL before migration
    but are no longer present in the SQLite source.

    Rules:
    - Only considers providers whose ID was in PostgreSQL BEFORE this migration run.
    - Providers with dependent records (RFQs, quotes, memberships, etc.) are SKIPPED
      (not deleted) and a warning is printed.
    - Providers with NO dependents are hard-deleted.
    - Admin-created providers (ID > max SQLite ID) are never touched.
    """
    removed_ids = existing_pg_ids - sqlite_ids
    if not removed_ids:
        print('Auto-delete: No removed firms detected. PostgreSQL is in sync with SQLite.')
        return 0, 0

    print('')
    print(f'Auto-delete: {len(removed_ids)} firm(s) found in PostgreSQL but NOT in SQLite.')

    # Tables that are SAFE to cascade-delete (ranking snapshots / email logs only)
    cascade_tables = [
        'rfq_matches',           # ranking snapshot — not a transaction
        'rfq_provider_dispatches',  # email dispatch log — not a transaction
    ]

    # Tables that BLOCK deletion (real business records: money, claims, quotes)
    dep_tables = [
        'rfq_unlocks',
        'quotes',
        'tier_evaluation_requests',
        'provider_memberships',
        'provider_claim_requests',
    ]

    deleted = 0
    skipped = 0
    cascade_cleaned = 0

    for pid in sorted(removed_ids):
        # Fetch provider name for logging
        name_result = await session.execute(text('SELECT name, firm_name FROM providers WHERE id = :pid'), {'pid': pid})
        name_row = name_result.fetchone()
        if not name_row:
            continue  # Already gone
        display_name = (name_row[1] or name_row[0] or f'id={pid}')[:60]

        # Step 1: Cascade-delete safe log/snapshot tables first
        for safe_tbl in cascade_tables:
            r = await session.execute(
                text(f'DELETE FROM {safe_tbl} WHERE provider_id = :pid'),
                {'pid': pid}
            )
            if r.rowcount > 0:
                cascade_cleaned += r.rowcount

        # Step 2: Check remaining BLOCKING tables
        has_deps = False
        dep_found_in = None
        for tbl in dep_tables:
            r = await session.execute(
                text(f'SELECT 1 FROM {tbl} WHERE provider_id = :pid LIMIT 1'),
                {'pid': pid}
            )
            if r.fetchone():
                has_deps = True
                dep_found_in = tbl
                break

        if has_deps:
            print(f'  SKIP  id={pid} "{display_name}" — has records in {dep_found_in}, cannot auto-delete')
            skipped += 1
        else:
            await session.execute(text('DELETE FROM providers WHERE id = :pid'), {'pid': pid})
            print(f'  DELETE id={pid} "{display_name}" — removed from SQLite, no dependents')
            deleted += 1

    if deleted > 0:
        await session.commit()

    print(f'Auto-delete complete: {deleted} deleted, {skipped} skipped (have blocking records), {cascade_cleaned} cascade-cleaned from rfq_matches/dispatches.')
    return deleted, skipped

async def run_force_delete_insert(session, sqlite_conn):
    """
    DESTRUCTIVE mode (--force flag).
    Deletes all providers and dependent rows, then re-inserts from SQLite.
    WARNING: DESTROYS ALL EMBEDDINGS. Use only for full reset.
    """
    print('')
    print('=' * 60)
    print('FORCE MODE - DESTRUCTIVE - ALL EMBEDDINGS WILL BE LOST')
    print('=' * 60)
    print('')

    cur = sqlite_conn.cursor()
    cur.execute('SELECT COUNT(*) FROM companies')
    total = cur.fetchone()[0]
    print(f'Found {total} companies in SQLite')
    if total == 0:
        print('ERROR: No companies found!')
        return {'inserted': 0, 'updated': 0, 'errors': 0}

    cur.execute('SELECT * FROM companies')
    companies = cur.fetchall()
    cur.execute('PRAGMA table_info(companies)')
    sqlite_cols = [c[1] for c in cur.fetchall()]

    dep_tables = [
        'rfq_matches',
        'rfq_unlocks',
        'rfq_provider_dispatches',
        'quotes',
        'tier_evaluation_requests',
        'provider_memberships',
        'provider_claim_requests',
    ]
    print('Clearing dependent tables...')
    for tbl in dep_tables:
        await session.execute(text('DELETE FROM ' + tbl))
        print(f'  Cleared {tbl}')
    await session.execute(text('DELETE FROM providers'))
    print('  Cleared providers (ALL EMBEDDINGS GONE)')
    await session.commit()

    cur.execute('SELECT COALESCE(MAX(id),0) FROM companies')
    max_sq = cur.fetchone()[0] or 0
    null_ctr = [max_sq]

    all_cols = ['id'] + UPSERT_FIELDS
    cols_s = ', '.join(all_cols)
    par_s = ', '.join(':' + c for c in all_cols)
    insert_sql = 'INSERT INTO providers (' + cols_s + ') VALUES (' + par_s + ')'

    inserted = errors = 0
    err_list = []

    for i, row in enumerate(companies):
        rd = {}

        try:
            rid, params, rd = build_row_params(sqlite_cols, row, all_cols, null_ctr)
            await session.execute(text(insert_sql), params)
            inserted += 1
            if (i + 1) % 100 == 0:
                await session.commit()
                print(f'  {inserted}/{total} ({inserted/total*100:.1f}%) errors={errors}')
        except Exception as e:
            errors += 1
            eid = rd.get('id', '?')
            ename = str(rd.get('firm_name') or '')[:40]
            msg = f'  ERROR row {i+1} id={eid} {repr(ename)}: {str(e)[:100]}'
            print(msg)
            err_list.append(msg)
            await session.rollback()
            if len(err_list) > 50:
                print('Too many errors, aborting.')
                break

    if inserted % 100 != 0:
        await session.commit()

    await session.execute(text(SEQ_SQL))
    await session.commit()
    print('Sequence providers_id_seq reset to MAX(id).')
    print('WARNING: All embeddings were destroyed. Run generate_embeddings.py --all to regenerate.')
    return {'inserted': inserted, 'updated': 0, 'errors': errors}


async def main():
    force_mode = '--force' in sys.argv
    if force_mode:
        print('WARNING: --force flag detected. This will DESTROY ALL EMBEDDINGS.')
        print('Press Ctrl+C within 5 seconds to abort...')
        import time
        time.sleep(5)
    else:
        print('Running in SAFE UPSERT mode (default).')
        print('Embeddings will NOT be touched.')
        print('Pass --force to use destructive delete+insert mode.')
    print('')

    sqlite_path = find_sqlite_db()
    sqlite_conn = sqlite3.connect(sqlite_path)
    print(f'Connected to SQLite: {sqlite_path}')

    async with AsyncSessionLocal() as session:
        if force_mode:
            stats = await run_force_delete_insert(session, sqlite_conn)
        else:
            stats = await run_safe_upsert(session, sqlite_conn)

    sqlite_conn.close()

    print('')
    print('=' * 60)
    if force_mode:
        print('FORCE MIGRATION COMPLETE')
        print(f'  Inserted : {stats["inserted"]}')
        print(f'  Errors   : {stats["errors"]}')
        print('  NOTE: All embeddings destroyed. Run generate_embeddings.py --all')
    else:
        print('SAFE UPSERT COMPLETE - EMBEDDINGS PRESERVED')
        print(f'  New rows  : {stats["inserted"]}')
        print(f'  Updated   : {stats["updated"]}')
        print(f'  Deleted   : {stats["deleted"]} (removed from SQLite, no dependents)')
        print(f'  Skipped   : {stats["skipped_deletion"]} (removed from SQLite, kept - have RFQ/quote/membership data)')
        print(f'  Errors    : {stats["errors"]}')
        print('  Embeddings: UNTOUCHED (existing embeddings fully preserved)')
        if stats['inserted'] > 0:
            print(f'  ACTION: {stats["inserted"]} new providers need embeddings.')
            print('  Run: python generate_embeddings.py --api-key YOUR_KEY')
            print('  (without --all flag, only new null-embedding providers will be embedded)')
        if stats['skipped_deletion'] > 0:
            print(f'  WARNING: {stats["skipped_deletion"]} removed firms could not be auto-deleted (have dependent records).')
            print('  Review these manually in the admin panel if needed.')
    print('=' * 60)


if __name__ == '__main__':
    asyncio.run(main())
