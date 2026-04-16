"""resize embedding vector from 1536 to 1024 for BAAI/bge-large-en-v1.5

Revision ID: abc123resize
Revises: a1b2c3d4e5f6
Create Date: 2026-03-09
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'abc123resize'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Only resize if vector extension exists and column exists
    op.execute("""
        DO $$
        BEGIN
            -- Check if pgvector extension exists
            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
                -- Alter column if it exists and is currently vector(1536)
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'providers' AND column_name = 'embedding'
                ) THEN
                    ALTER TABLE providers ALTER COLUMN embedding TYPE vector(1024) 
                    USING NULL;
                END IF;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'providers' AND column_name = 'embedding'
                ) THEN
                    ALTER TABLE providers ALTER COLUMN embedding TYPE vector(1536) 
                    USING NULL;
                END IF;
            END IF;
        END $$;
    """)
