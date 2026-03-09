#!/usr/bin/env python3
"""
SQLite to PostgreSQL Migration Script
Migrates 6,766 engineering providers from engineering_directory.db to PostgreSQL
"""

import sqlite3
import json
import asyncio
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

# Source SQLite database
SQLITE_DB = '/a0/usr/projects/engineering_services_directory_v2/engineering_directory.db'

# Target PostgreSQL - use local SQLite for testing if PostgreSQL unavailable
import os
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite+aiosqlite:///./proready_migrated.db')

# Column mapping from SQLite to PostgreSQL providers table
COLUMN_MAPPING = {
    'id': 'legacy_id',
    'name': 'name',
    'firm_name': 'firm_name',
    'website': 'website',
    'phone': 'phone',
    'address': 'address',
    'city': 'city',
    'state': 'state',
    'postal_code': 'postal_code',
    'rating': 'rating',
    'review_count': 'review_count',
    'place_id': 'place_id',
    'search_query': 'search_query',
    'search_city': 'search_city',
    'is_engineering_service': 'is_engineering_service',
    'is_mechanical_focus': 'is_mechanical_focus',
    'classification_confidence': 'classification_confidence',
    'classification_reasoning': 'classification_reasoning',
    'primary_specialty': 'primary_specialty',
    'secondary_specialties': 'secondary_specialties',  # JSON
    'business_description': 'business_description',
    'capabilities': 'capabilities',  # JSON
    'specialties': 'specialties',  # JSON
    'software_tools': 'software_tools',  # JSON
    'notable_clients': 'notable_clients',  # JSON
    'email_addresses': 'email_addresses',  # JSON
    'certifications': 'certifications',  # JSON
    'equipment': 'equipment',  # JSON
    'business_evaluation_tier': 'tier',
    'business_evaluation_years_in_business': 'years_in_business',
    'business_evaluation_employee_count': 'employee_count',
    'proven_experience_project_count': 'project_count',
    'proven_experience_case_studies': 'case_studies',  # JSON
    'proven_experience_industries_served': 'industries_served',  # JSON
    'team_members': 'team_members',  # JSON
    'team_summary': 'team_summary',
    'projects': 'projects',  # JSON
    'created_at': 'created_at',
    'updated_at': 'updated_at',
    # Computed/generated fields
    'is_claimed': False,
    'claim_status': None,
}

# JSON columns that need parsing
JSON_COLUMNS = [
    'secondary_specialties', 'capabilities', 'specialties', 'software_tools',
    'notable_clients', 'email_addresses', 'certifications', 'equipment',
    'case_studies', 'industries_served', 'team_members', 'projects'
]

async def migrate_data():
    print("=" * 60)
    print("SQLite to PostgreSQL Migration")
    print("=" * 60)

    # Connect to SQLite
    sqlite_conn = sqlite3.connect(SQLITE_DB)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()

    # Count total rows
    sqlite_cursor.execute("SELECT COUNT(*) FROM companies")
    total_rows = sqlite_cursor.fetchone()[0]
    print(f"\n📊 Source: {total_rows} companies in SQLite")

    # Connect to PostgreSQL
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Clear existing providers (optional - for fresh migration)
        print("\n🧹 Clearing existing providers...")
        await session.execute(text("DELETE FROM provider_memberships"))
        await session.execute(text("DELETE FROM provider_claim_requests"))
        await session.execute(text("DELETE FROM providers"))
        await session.commit()
        print("   ✓ Cleared")

        # Fetch all companies
        sqlite_cursor.execute("SELECT * FROM companies")
        companies = sqlite_cursor.fetchall()

        # Insert in batches
        batch_size = 100
        inserted = 0
        errors = []

        print(f"\n🚀 Migrating {total_rows} providers...")

        for i, row in enumerate(companies):
            try:
                # Build insert data
                data = {
                    'id': f"prov_{row['id']}",  # Generate UUID-style ID
                    'legacy_id': str(row['id']),
                    'name': row['name'] or row['firm_name'] or 'Unknown',
                    'firm_name': row['firm_name'],
                    'website': row['website'],
                    'phone': row['phone'],
                    'address': row['address'],
                    'city': row['city'],
                    'state': row['state'],
                    'postal_code': row['postal_code'],
                    'rating': row['rating'],
                    'review_count': int(row['review_count']) if row['review_count'] else 0,
                    'place_id': row['place_id'],
                    'search_query': row['search_query'],
                    'search_city': row['search_city'],
                    'is_engineering_service': bool(row['is_engineering_service']),
                    'is_mechanical_focus': bool(row['is_mechanical_focus']),
                    'classification_confidence': row['classification_confidence'],
                    'classification_reasoning': row['classification_reasoning'],
                    'primary_specialty': row['primary_specialty'],
                    'secondary_specialties': parse_json(row['secondary_specialties']),
                    'business_description': row['business_description'],
                    'capabilities': parse_json(row['capabilities']),
                    'specialties': parse_json(row['specialties']),
                    'software_tools': parse_json(row['software_tools']),
                    'notable_clients': parse_json(row['notable_clients']),
                    'email_addresses': parse_json(row['email_addresses']),
                    'certifications': parse_json(row['certifications']),
                    'equipment': parse_json(row['equipment']),
                    'tier': row['business_evaluation_tier'],
                    'years_in_business': row['business_evaluation_years_in_business'],
                    'employee_count': str(row['business_evaluation_employee_count']) if row['business_evaluation_employee_count'] else None,
                    'project_count': row['proven_experience_project_count'],
                    'case_studies': parse_json(row['proven_experience_case_studies']),
                    'industries_served': parse_json(row['proven_experience_industries_served']),
                    'team_members': parse_json(row['team_members']),
                    'team_summary': row['team_summary'],
                    'projects': parse_json(row['projects']),
                    'created_at': row['created_at'] or datetime.utcnow(),
                    'updated_at': row['updated_at'] or datetime.utcnow(),
                    'is_claimed': False,
                    'is_active': True,
                    'view_count': 0,
                }

                # Build SQL
                columns = ', '.join(data.keys())
                placeholders = ', '.join([f':{k}' for k in data.keys()])

                sql = f"INSERT INTO providers ({columns}) VALUES ({placeholders})"
                await session.execute(text(sql), data)

                inserted += 1

                if (i + 1) % batch_size == 0:
                    await session.commit()
                    print(f"   Progress: {i+1}/{total_rows} ({(i+1)/total_rows*100:.1f}%)")

            except Exception as e:
                errors.append(f"Row {i+1} (ID {row['id']}): {str(e)}")
                if len(errors) > 10:
                    break

        # Final commit
        await session.commit()

        # Summary
        print("\n" + "=" * 60)
        print("Migration Complete!")
        print("=" * 60)
        print(f"✓ Inserted: {inserted} providers")
        print(f"✗ Errors: {len(errors)}")

        if errors:
            print("\nFirst 5 errors:")
            for err in errors[:5]:
                print(f"   {err}")

    sqlite_conn.close()
    await engine.dispose()

    return inserted, len(errors)

def parse_json(value):
    """Parse JSON string or return empty list/dict"""
    if not value:
        return '[]'
    try:
        # Validate it's valid JSON
        parsed = json.loads(value)
        return value  # Return original if valid
    except:
        return '[]'

if __name__ == "__main__":
    inserted, errors = asyncio.run(migrate_data())
    print(f"\n🎉 Migration finished: {inserted} providers migrated")
