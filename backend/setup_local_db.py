#!/usr/bin/env python3
"""Setup local SQLite database - patches pgvector for SQLite compat."""
import asyncio, sys, os, json
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./proready.db")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import Text
import sqlalchemy.types as sat

class _SQLiteVector(sat.TypeDecorator):
    impl = sat.Text
    cache_ok = True
    def __init__(self, dim=None, *a, **kw): super().__init__()
    def process_bind_param(self, v, d): return json.dumps(list(v)) if isinstance(v,(list,tuple)) else v
    def process_result_value(self, v, d):
        try: return json.loads(v) if v else v
        except: return v

try:
    import pgvector.sqlalchemy as _pv; _pv.Vector = _SQLiteVector
    print("[OK] Patched pgvector.Vector")
except ImportError:
    import types as _t
    _m = _t.ModuleType("pgvector"); _ms = _t.ModuleType("pgvector.sqlalchemy")
    _ms.Vector = _SQLiteVector
    sys.modules["pgvector"] = _m; sys.modules["pgvector.sqlalchemy"] = _ms
    print("[OK] Created pgvector stub")

print("[..] Importing app...")
from app.db.session import async_engine
from app.db.base import Base
import app.models
print("[OK] Models imported")

async def main():
    from sqlalchemy import text
    async with async_engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
        await conn.run_sync(Base.metadata.create_all)
    async with async_engine.connect() as conn:
        r = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"))
        tables = [row[0] for row in r.fetchall()]
    print(f"[OK] Created {len(tables)} tables:")
    for t in tables: print(f"     {t}")

asyncio.run(main())
print("[DONE]")
