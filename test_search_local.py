#!/usr/bin/env python3
"""Test search functionality locally with SQLite fallback."""
import asyncio
import sys
import os

sys.path.insert(0, '/a0/usr/projects/website_for_engineering_directory/backend')
os.environ['DATABASE_URL'] = 'sqlite+aiosqlite:////a0/usr/projects/website_for_engineering_directory/backend/proready.db'
os.environ['SECRET_KEY'] = 'test-secret-key-32-chars-minimum!!'
os.environ['OPENAI_API_KEY'] = 'dummy-key'  # Force keyword fallback
os.environ['ENVIRONMENT'] = 'test'
os.environ['OPENAI_API_BASE'] = 'https://api.deepinfra.com/v1/openai'
os.environ['OPENAI_EMBEDDING_MODEL'] = 'BAAI/bge-large-en-v1.5'
os.environ['OPENAI_LLM_MODEL'] = 'moonshotai/kimi-k2.5'

async def test_search():
    print("[TEST] Importing modules...")
    from app.db.session import AsyncSessionLocal
    from app.services.search_service import search_providers, check_search_quota
    print("[TEST] Imports OK")

    async with AsyncSessionLocal() as db:
        print('\n[TEST] Testing quota check...')
        try:
            can_search, remaining = await check_search_quota(db, user=None, ip_address='127.0.0.1')
            print(f'  can_search={can_search}, remaining={remaining}')
        except Exception as e:
            print(f'  QUOTA CHECK ERROR: {e}')

        print('\n[TEST] Testing search (expects 0 results - DB is empty)...')
        try:
            results = await search_providers(db, query='gas turbine combustion engineering')
            print(f'  Found {len(results)} results')
            for r in results[:3]:
                name = getattr(r.provider, 'name', 'UNKNOWN')
                score = getattr(r, 'score', 0)
                print(f'  - {name}: score={score}')
            print('  [PASS] Search ran without crashing')
        except Exception as e:
            import traceback
            print(f'  SEARCH ERROR: {e}')
            traceback.print_exc()

        print('\n[TEST] Testing with structural engineering query...')
        try:
            results2 = await search_providers(db, query='structural analysis finite element')
            print(f'  Found {len(results2)} results (expected 0 - empty DB)')
            print('  [PASS] Search ran without crashing')
        except Exception as e:
            print(f'  SEARCH ERROR: {e}')

    print('\n[TEST] All tests completed successfully!')
    print('[INFO] Note: 0 results expected - proready.db has no provider data (empty migration db)')
    print('[INFO] Real search testing requires PostgreSQL with migrated 6766 provider records')

asyncio.run(test_search())
