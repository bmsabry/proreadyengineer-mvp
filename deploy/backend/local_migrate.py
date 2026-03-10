#!/usr/bin/env python3
"""
Local dev migration: copies `companies` from engineering_directory.db
into `providers` in proready.db (local development database).

All column names match. New provider-only columns (claim_status, embedding, etc.)
are left NULL and will be populated later.
"""
import sqlite3, sys
from pathlib import Path

BASE = Path('/a0/usr/projects/website_for_engineering_directory')
SRC_DB  = BASE / 'engineering_directory.db'
DST_DB  = BASE / 'backend' / 'proready.db'

print(f'Source : {SRC_DB}')
print(f'Target : {DST_DB}')
assert SRC_DB.exists(), f'Source DB not found: {SRC_DB}'
assert DST_DB.exists(), f'Target DB not found: {DST_DB}'

src = sqlite3.connect(SRC_DB)
dst = sqlite3.connect(DST_DB)

# ---- column introspection ------------------------------------------------
src_cols = [r[1] for r in src.execute('PRAGMA table_info(companies)').fetchall()]
dst_cols = [r[1] for r in dst.execute('PRAGMA table_info(providers)').fetchall()]

# Columns that exist in BOTH tables (ordered by source)
common = [c for c in src_cols if c in dst_cols]
print(f'\nSource columns : {len(src_cols)}')
print(f'Target columns : {len(dst_cols)}')
print(f'Common columns : {len(common)}')
new_only = [c for c in dst_cols if c not in src_cols]
print(f'New (target-only): {new_only}')

# ---- check if already migrated -------------------------------------------
existing = dst.execute('SELECT count(*) FROM providers').fetchone()[0]
if existing > 0:
    print(f'\nTarget already has {existing} providers — skipping migration.')
    src.close(); dst.close(); sys.exit(0)

# ---- migrate ---------------------------------------------------------------
total = src.execute('SELECT count(*) FROM companies').fetchone()[0]
print(f'\nMigrating {total} rows from companies → providers...')

batch_size = 500
offset = 0
inserted = 0
errors = 0

col_list = ', '.join(common)
placeholders = ', '.join(['?' for _ in common])

while True:
    rows = src.execute(
        f'SELECT {col_list} FROM companies LIMIT {batch_size} OFFSET {offset}'
    ).fetchall()
    if not rows:
        break
    try:
        dst.executemany(
            f'INSERT INTO providers ({col_list}) VALUES ({placeholders})',
            rows
        )
        dst.commit()
        inserted += len(rows)
        print(f'  Inserted {inserted}/{total}...', end='\r')
    except Exception as e:
        print(f'\nBatch error at offset {offset}: {e}')
        errors += 1
        # Try row-by-row for this batch
        for row in rows:
            try:
                dst.execute(
                    f'INSERT INTO providers ({col_list}) VALUES ({placeholders})',
                    row
                )
                dst.commit()
                inserted += 1
            except Exception as e2:
                errors += 1
                if errors <= 5:
                    print(f'  Row error: {e2} | first fields: {row[:3]}')
    offset += batch_size

final = dst.execute('SELECT count(*) FROM providers').fetchone()[0]
print(f'\n\nMigration complete!')
print(f'  Inserted : {inserted}')
print(f'  Errors   : {errors}')
print(f'  Total in providers: {final}')

# Quick sanity check
samples = dst.execute(
    'SELECT id, name, primary_specialty, business_evaluation_tier FROM providers LIMIT 3'
).fetchall()
print('\nSample rows:')
for row in samples:
    print(f'  id={row[0]}  name={row[1]!r}  specialty={row[2]!r}  tier={row[3]!r}')

src.close(); dst.close()
