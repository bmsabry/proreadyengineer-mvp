#!/usr/bin/env python3
"""
SQLite to PostgreSQL Migration Script
Migrates 6,766 engineering providers from engineering_directory.db to PostgreSQL
"""

import asyncio
import json
import sys
from datetime import datetime
from decimal import Decimal

# Add backend to path
sys.path.insert(0, '/a0/usr/projects/website_for_engineering_directory/backend')

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.session import AsyncSessionLocal
from app.models.provider import Provider
import sqlite3

# Source SQLite database
# Detect environment and use correct path
import os
if os.path.exists('/opt/render/project/src/engineering_directory.db'):
    SQLITE_DB = '/opt/render/project/src/engineering_directory.db'
elif os.path.exists('/a0/usr/projects/engineering_services_directory_v2/engineering_directory.db'):
    SQLITE_DB = '/a0/usr/projects/engineering_services_directory_v2/engineering_directory.db'
else:
    # Try current directory
    SQLITE_DB = 'engineering_directory.db'  # Should be in same folder on Render


def parse_json_field(value):
    """Parse JSON string, return Python object or None"""
    if not value:
        return None
    try:
        return json.loads(value)
    except:
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
    print(f"Source: {SQLITE_DB}")

    # Connect to SQLite
    sqlite_conn = sqlite3.connect(SQLITE_DB)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()

    # Count total rows
    sqlite_cursor.execute("SELECT COUNT(*) FROM companies")
    total_rows = sqlite_cursor.fetchone()[0]
    print(f"📊 Found {total_rows} companies in SQLite")

    # Fetch all companies
    sqlite_cursor.execute("SELECT * FROM companies")
    companies = sqlite_cursor.fetchall()

    # Get column names
    sqlite_cursor.execute("PRAGMA table_info(companies)")
    columns_info = sqlite_cursor.fetchall()
    column_names = [c[1] for c in columns_info]
    print(f"📋 Columns: {len(column_names)}")

    async with AsyncSessionLocal() as session:
        # Check existing providers
        result = await session.execute(select(func.count()).select_from(Provider))
        existing = result.scalar()
        print(f"📊 Existing providers in PostgreSQL: {existing}")

        if existing > 0:
            print("\n⚠️  Providers already exist. Skipping migration.")
            print("   To re-migrate, delete existing providers first.")
            return 0, 0

        # Insert providers
        batch_size = 50
        inserted = 0
        errors = []

        print(f"\n🚀 Migrating {total_rows} providers...")

        for i, row in enumerate(companies):
            try:
                # Map SQLite row to Provider model
                provider = Provider(
                    id=row['id'],  # Keep same ID
                    name=row['name'] or row['firm_name'] or 'Unknown',
                    firm_name=row['firm_name'],
                    website=row['website'],
                    phone=row['phone'],
                    address=row['address'],
                    city=row['city'],
                    state=row['state'],
                    postal_code=row['postal_code'],
                    rating=parse_decimal(row['rating']),
                    review_count=int(row['review_count']) if row['review_count'] else 0,
                    place_id=row['place_id'],
                    search_query=row['search_query'],
                    search_city=row['search_city'],
                    is_engineering_service=1 if row['is_engineering_service'] else 0,
                    is_mechanical_focus=1 if row['is_mechanical_focus'] else 0,
                    classification_confidence=row['classification_confidence'],
                    classification_reasoning=row['classification_reasoning'],
                    primary_specialty=row['primary_specialty'],
                    secondary_specialties=parse_json_field(row['secondary_specialties']),
                    homepage_crawl_status=row['homepage_crawl_status'],
                    homepage_file=row['homepage_file'],
                    homepage_content_size=row['homepage_content_size'],
                    deep_crawl_status=row['deep_crawl_status'],
                    deep_crawl_page_count=row['deep_crawl_page_count'],
                    deep_crawl_content_size=row['deep_crawl_content_size'],
                    business_description=row['business_description'],
                    capabilities=parse_json_field(row['capabilities']),
                    specialties=parse_json_field(row['specialties']),
                    software_tools=parse_json_field(row['software_tools']),
                    notable_clients=row['notable_clients'],
                    email_addresses=parse_json_field(row['email_addresses']),
                    certifications=parse_json_field(row['certifications']),
                    equipment=parse_json_field(row['equipment']),
                    business_evaluation_tier=row['business_evaluation_tier'],
                    business_evaluation_years_in_business=row['business_evaluation_years_in_business'],
                    business_evaluation_employee_count=row['business_evaluation_employee_count'],
                    proven_experience_project_count=row['proven_experience_project_count'],
                    proven_experience_case_studies=parse_json_field(row['proven_experience_case_studies']),
                    proven_experience_industries_served=parse_json_field(row['proven_experience_industries_served']),
                    proven_experience_years_in_business=row['proven_experience_years_in_business'],
                    proven_experience_notable_projects=parse_json_field(row['proven_experience_notable_projects']),
                    online_presence_youtube_channel=row['online_presence_youtube_channel'],
                    online_presence_linkedin_url=row['online_presence_linkedin_url'],
                    online_presence_yelp_url=row['online_presence_yelp_url'],
                    online_presence_review_count=row['online_presence_review_count'],
                    online_presence_average_rating=parse_decimal(row['online_presence_average_rating']),
                    online_presence_reputation_summary=row['online_presence_reputation_summary'],
                    team_members=parse_json_field(row['team_members']),
                    team_summary=row['team_summary'],
                    projects=parse_json_field(row['projects']),
                    created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else datetime.utcnow(),
                    updated_at=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else datetime.utcnow(),
                    # MVP fields
                    claim_status=None,
                    claimed_by_user_id=None,
                )

                session.add(provider)
                inserted += 1

                if inserted % batch_size == 0:
                    await session.commit()
                    print(f"   Progress: {inserted}/{total_rows} ({inserted/total_rows*100:.1f}%)")

            except Exception as e:
                errors.append(f"Row {i+1} (ID {row.get('id', '?')}): {str(e)[:100]}")
                if len(errors) > 5:
                    print(f"   ⚠️  Too many errors, stopping...")
                    break

        # Final commit
        if inserted % batch_size != 0:
            await session.commit()

        # Summary
        print("\n" + "=" * 60)
        print("Migration Complete!")
        print("=" * 60)
        print(f"✓ Inserted: {inserted} providers")
        if errors:
            print(f"✗ Errors: {len(errors)}")
            print("\nFirst errors:")
            for err in errors[:3]:
                print(f"   {err}")

    sqlite_conn.close()

    return inserted, len(errors)


if __name__ == "__main__":
    inserted, errors = asyncio.run(migrate_data())
    print(f"\n🎉 Migration finished!")
    sys.exit(0 if errors == 0 else 1)
