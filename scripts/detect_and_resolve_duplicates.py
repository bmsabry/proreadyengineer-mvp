"""
detect_and_resolve_duplicates.py

Run in Render shell:
  cd /opt/render/project/src && python deploy/scripts/detect_and_resolve_duplicates.py

Flags:
  --dry-run     (default) Show duplicates, recommend which to keep, no changes
  --resolve     Actually delete duplicates (keeps the one with most relationships)
"""
import asyncio
import sys
import os

DRY_RUN = '--resolve' not in sys.argv

async def main():
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import text

    db_url = os.environ.get('DATABASE_URL', '')
    if not db_url:
        from app.core.config import settings
        db_url = str(settings.DATABASE_URL)
    # asyncpg driver
    if db_url.startswith('postgresql://'):
        db_url = db_url.replace('postgresql://', 'postgresql+asyncpg://', 1)

    engine = create_async_engine(db_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        # ── Step 1: Detect duplicates by firm_name + city + state ──
        dup_sql = text("""
            SELECT
                LOWER(TRIM(firm_name)) as key_name,
                LOWER(TRIM(COALESCE(city,''))) as key_city,
                LOWER(TRIM(COALESCE(state,''))) as key_state,
                COUNT(*) as cnt,
                array_agg(id ORDER BY id) as ids,
                array_agg(firm_name ORDER BY id) as names
            FROM providers
            WHERE firm_name IS NOT NULL AND firm_name != ''
            GROUP BY LOWER(TRIM(firm_name)),
                     LOWER(TRIM(COALESCE(city,''))),
                     LOWER(TRIM(COALESCE(state,'')))
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC, LOWER(TRIM(firm_name))
        """)
        result = await db.execute(dup_sql)
        groups = result.fetchall()

        if not groups:
            print('✅ No duplicates found in PostgreSQL providers table.')
            await engine.dispose()
            return

        total_dups = sum(row[3] - 1 for row in groups)
        print(f'Found {len(groups)} duplicate groups ({total_dups} extra records to remove):')
        print('')

        to_delete = []

        for row in groups:
            key_name, key_city, key_state, cnt, ids, names = row
            print(f'--- Group: "{names[0]}" ({key_city}, {key_state}) — {cnt} records ---')

            # For each ID in the group, check relationship count
            scores = {}  # id -> relationship count
            for pid in ids:
                rel_sql = text("""
                    SELECT
                        (SELECT COUNT(*) FROM provider_memberships WHERE provider_id = :pid) +
                        (SELECT COUNT(*) FROM rfq_unlocks WHERE provider_id = :pid) +
                        (SELECT COUNT(*) FROM quotes WHERE provider_id = :pid) +
                        (SELECT COUNT(*) FROM rfq_matches WHERE provider_id = :pid) +
                        (SELECT COUNT(*) FROM rfq_provider_dispatches WHERE provider_id = :pid) +
                        (SELECT COUNT(*) FROM provider_claim_requests WHERE provider_id = :pid)
                    as score
                """)
                r = await db.execute(rel_sql, {'pid': pid})
                scores[pid] = r.scalar() or 0

            # Keep the one with most relationships; tiebreak: lowest id
            keep_id = max(scores.items(), key=lambda x: (x[1], -x[0]))[0]

            for pid in ids:
                rel_info = f'rels={scores[pid]}'
                if pid == keep_id:
                    print(f'  KEEP   id={pid} {rel_info} ← winner')
                else:
                    print(f'  DELETE id={pid} {rel_info}')
                    to_delete.append((pid, names[ids.index(pid)], keep_id))
            print('')

        print(f'Summary: {len(to_delete)} records will be deleted, keeping the one with most relationships.')

        if DRY_RUN:
            print('')
            print('DRY RUN — no changes made.')
            print('Run with --resolve flag to actually delete duplicates:')
            print('  python deploy/scripts/detect_and_resolve_duplicates.py --resolve')
        else:
            print('')
            print('RESOLVING duplicates...')

            # Cascade-safe tables (just logs/snapshots)
            cascade_tables = ['rfq_matches', 'rfq_provider_dispatches']
            # Blocking tables — move to keep_id instead of deleting
            move_tables = [
                ('rfq_unlocks', 'provider_id'),
                ('quotes', 'provider_id'),
                ('provider_memberships', 'provider_id'),
                ('provider_claim_requests', 'provider_id'),
                ('tier_evaluation_requests', 'provider_id'),
            ]

            deleted = 0
            for del_id, del_name, keep_id in to_delete:
                print(f'  Processing delete id={del_id} "{del_name}" → keep id={keep_id}')

                # 1. Move blocking relationships to keep_id
                for tbl, col in move_tables:
                    r = await db.execute(
                        text(f'UPDATE {tbl} SET {col} = :keep WHERE {col} = :del'),
                        {'keep': keep_id, 'del': del_id}
                    )
                    if r.rowcount > 0:
                        print(f'    Moved {r.rowcount} rows in {tbl} to id={keep_id}')

                # 2. Delete cascade-safe snapshots
                for tbl in cascade_tables:
                    await db.execute(
                        text(f'DELETE FROM {tbl} WHERE provider_id = :del'),
                        {'del': del_id}
                    )

                # 3. Delete the duplicate provider record
                await db.execute(text('DELETE FROM providers WHERE id = :del'), {'del': del_id})
                deleted += 1
                print(f'  ✅ Deleted provider id={del_id}')

            await db.commit()
            print(f'')
            print(f'✅ Done. Deleted {deleted} duplicate provider records.')
            print(f'   All relationships moved to the winning record.')

    await engine.dispose()

asyncio.run(main())
