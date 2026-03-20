#!/usr/bin/env python3
"""
SQLite to PostgreSQL Migration Script
Migrates 6,766 engineering providers from engineering_directory.db to PostgreSQL
"""

import asyncio
import json
import sys
import os
from datetime import datetime
from decimal import Decimal

# Add backend to Python path - works both locally and on Render
script_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(script_dir, '../../backend'))
sys.path.insert(0, backend_dir)
print(f"Backend path: {backend_dir}")

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from app.db.session import AsyncSessionLocal
from app.models.provider import Provider
import sqlite3


def find_sqlite_db():
    """Find the engineering_directory.db file."""
    candidates = [
        # Render deployment: project root
        '/opt/render/project/src/engineering_directory.db',
        # Local dev
        '/a0/usr/projects/website_for_engineering_directory/engineering_directory.db',
        # Relative to script location (../../engineering_directory.db from deploy/scripts/)
        os.path.abspath(os.path.join(script_dir, '../../engineering_directory.db')),
        # Current working directory
        os.path.join(os.getcwd(), 'engineering_directory.db'),
        # Parent of cwd
        os.path.join(os.path.dirname(os.getcwd()), 'engineering_directory.db'),
    ]
    for path in candidates:
        if os.path.exists(path):
            print(f"Found SQLite DB at: {path}")
            return path
    raise FileNotFoundError(f"Cannot find engineering_directory.db. Tried: {candidates}")


def parse_json_field(value):
    """Parse JSON string, return Python object or None"""
    if not value:
        return None
    try:
        return json.loads(value)
    except:
        # Handle string lists like '["item1", "item2"]' or plain strings
        if isinstance(value, str) and value.strip():
            return [value]  # Wrap single string in list
        return None


def parse_decimal(value):
    """Parse decimal value"""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except:
        return None


async def migrate_data():
    print("=" * 60)
    print("SQLite to PostgreSQL Migration")
    print("=" * 60)

    SQLITE_DB = find_sqlite_db()
    print(f"Source: {SQLITE_DB}")

    # Connect to SQLite
    sqlite_conn = sqlite3.connect(SQLITE_DB)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()

    # Count total rows
    sqlite_cursor.execute("SELECT COUNT(*) FROM companies")
    total_rows = sqlite_cursor.fetchone()[0]
    print(f"Found {total_rows} companies in SQLite")

    if total_rows == 0:
        print("ERROR: No companies found in SQLite database!")
        sqlite_conn.close()
        return 0, 1

    # Fetch all companies
    sqlite_cursor.execute("SELECT * FROM companies")
    companies = sqlite_cursor.fetchall()

    # Find max existing ID to assign to null-ID rows (avoids PostgreSQL sequence conflicts)
    sqlite_cursor.execute("SELECT COALESCE(MAX(id), 0) FROM companies")
    max_existing_id = sqlite_cursor.fetchone()[0]
    null_id_counter = max_existing_id
    print(f"Max SQLite ID: {max_existing_id} - null-ID rows will be assigned IDs above this")

    # Get column names
    sqlite_cursor.execute("PRAGMA table_info(companies)")
    columns_info = sqlite_cursor.fetchall()
    column_names = [c[1] for c in columns_info]
    print(f"Columns: {len(column_names)}")

    async with AsyncSessionLocal() as session:
        # Check existing providers
        result = await session.execute(select(func.count()).select_from(Provider))
        existing = result.scalar()
        print(f"Existing providers in PostgreSQL: {existing}")

        # Always clear existing providers before fresh migration
        # This ensures idempotent re-runs without duplicate key errors
        if existing > 0:
            print(f"Clearing {existing} existing providers for fresh migration...")
            # Delete dependent tables first (FK constraints)
            print("Clearing dependent tables...")
            await session.execute(text("DELETE FROM rfq_matches"))
            await session.execute(text("DELETE FROM rfq_unlocks"))
            await session.execute(text("DELETE FROM rfq_provider_dispatches"))
            await session.execute(text("DELETE FROM quotes"))
            await session.execute(text("DELETE FROM tier_evaluation_requests"))
            await session.execute(text("DELETE FROM provider_memberships"))
            await session.execute(text("DELETE FROM provider_claim_requests"))
            await session.execute(text("DELETE FROM providers"))
            await session.commit()
            print("Cleared. Starting fresh migration...")
        else:
            print("No existing providers. Starting migration...")
        batch_size = 100
        inserted = 0
        errors = []

        print(f"\nMigrating {total_rows} providers...")

        for i, row in enumerate(companies):
            try:
                row_dict = dict(row)

                # Ensure name and firm_name are never NULL
                name = row_dict.get('name') or row_dict.get('firm_name') or f'Provider {row_dict.get("id", i)}'

                # Map SQLite row to Provider model
                provider = Provider(
                    id=(row_dict.get('id') or (null_id_counter := null_id_counter + 1) or null_id_counter),
                    name=name,
                    firm_name=row_dict.get('firm_name') or name,
                    website=row_dict.get('website'),
                    phone=row_dict.get('phone'),
                    address=row_dict.get('address'),
                    city=row_dict.get('city'),
                    state=row_dict.get('state'),
                    postal_code=row_dict.get('postal_code'),
                    rating=parse_decimal(row_dict.get('rating')),
                    review_count=int(row_dict['review_count']) if row_dict.get('review_count') else 0,
                    place_id=row_dict.get('place_id'),
                    search_query=row_dict.get('search_query'),
                    search_city=row_dict.get('search_city'),
                    is_engineering_service=1 if row_dict.get('is_engineering_service') else 0,
                    is_mechanical_focus=1 if row_dict.get('is_mechanical_focus') else 0,
                    classification_confidence=row_dict.get('classification_confidence'),
                    classification_reasoning=row_dict.get('classification_reasoning'),
                    primary_specialty=row_dict.get('primary_specialty'),
                    secondary_specialties=parse_json_field(row_dict.get('secondary_specialties')),
                    homepage_crawl_status=row_dict.get('homepage_crawl_status'),
                    homepage_file=row_dict.get('homepage_file'),
                    homepage_content_size=row_dict.get('homepage_content_size'),
                    deep_crawl_status=row_dict.get('deep_crawl_status'),
                    deep_crawl_page_count=row_dict.get('deep_crawl_page_count'),
                    deep_crawl_content_size=row_dict.get('deep_crawl_content_size'),
                    business_description=row_dict.get('business_description'),
                    capabilities=parse_json_field(row_dict.get('capabilities')),
                    specialties=parse_json_field(row_dict.get('specialties')),
                    software_tools=parse_json_field(row_dict.get('software_tools')),
                    notable_clients=row_dict.get('notable_clients'),
                    email_addresses=parse_json_field(row_dict.get('email_addresses')),
                    certifications=parse_json_field(row_dict.get('certifications')),
                    equipment=parse_json_field(row_dict.get('equipment')),
                    business_evaluation_tier=row_dict.get('business_evaluation_tier'),
                    business_evaluation_years_in_business=row_dict.get('business_evaluation_years_in_business'),
                    business_evaluation_employee_count=row_dict.get('business_evaluation_employee_count'),
                    proven_experience_project_count=row_dict.get('proven_experience_project_count'),
                    proven_experience_case_studies=parse_json_field(row_dict.get('proven_experience_case_studies')),
                    proven_experience_industries_served=parse_json_field(row_dict.get('proven_experience_industries_served')),
                    proven_experience_years_in_business=row_dict.get('proven_experience_years_in_business'),
                    proven_experience_notable_projects=parse_json_field(row_dict.get('proven_experience_notable_projects')),
                    online_presence_youtube_channel=row_dict.get('online_presence_youtube_channel'),
                    online_presence_linkedin_url=row_dict.get('online_presence_linkedin_url'),
                    online_presence_yelp_url=row_dict.get('online_presence_yelp_url'),
                    online_presence_review_count=row_dict.get('online_presence_review_count'),
                    online_presence_average_rating=parse_decimal(row_dict.get('online_presence_average_rating')),
                    online_presence_reputation_summary=row_dict.get('online_presence_reputation_summary'),
                    team_members=parse_json_field(row_dict.get('team_members')),
                    team_summary=row_dict.get('team_summary'),
                    projects=parse_json_field(row_dict.get('projects')),
                    created_at=datetime.fromisoformat(row_dict['created_at']) if row_dict.get('created_at') else datetime.utcnow(),
                    updated_at=datetime.fromisoformat(row_dict['updated_at']) if row_dict.get('updated_at') else datetime.utcnow(),
                    # MVP fields - not in SQLite source
                    claim_status=None,
                    claimed_by_user_id=None,
                )

                session.add(provider)
                inserted += 1

                if inserted % batch_size == 0:
                    await session.commit()
                    print(f"   Progress: {inserted}/{total_rows} ({inserted/total_rows*100:.1f}%)")

            except Exception as e:
                errors.append(f"Row {i+1} (ID {row_dict.get('id', '?')}): {str(e)[:100]}")
                if len(errors) > 50:
                    print(f"   Too many errors ({len(errors)}), stopping migration batch...")
                    break

        # Final commit
        if inserted % batch_size != 0:
            await session.commit()
        # Reset PostgreSQL sequence so NULL-id rows get IDs above existing max
        # This is critical when SQLite rows have NULL ids (auto-inserted rows)
        await session.execute(text("SELECT setval('providers_id_seq', (SELECT COALESCE(MAX(id), 1) FROM providers))"))
        await session.commit()
        print("PostgreSQL sequence reset to MAX(id) - new rows will get correct IDs")


        # Summary
        print("\n" + "=" * 60)
        print("Migration Complete!")
        print("=" * 60)
        print(f"Inserted: {inserted} providers")
        if errors:
            print(f"Errors: {len(errors)}")
            print("\nFirst errors:")
            for err in errors[:3]:
                print(f"   {err}")

    sqlite_conn.close()

    return inserted, len(errors)


if __name__ == "__main__":
    inserted, errors = asyncio.run(migrate_data())
    print(f"\nMigration finished!")
    if errors > 0:
        print(f"WARNING: Migration completed with {errors} errors - check logs above")
        print("Server startup will NOT be blocked by migration errors.")
    else:
        print("Migration completed successfully with 0 errors.")
