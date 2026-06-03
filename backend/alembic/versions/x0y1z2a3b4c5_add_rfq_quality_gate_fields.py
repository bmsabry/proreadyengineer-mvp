"""add rfq quality gate fields

Revision ID: x0y1z2a3b4c5
Revises: w9x0y1z2a3b4
Create Date: 2026-06-03 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'x0y1z2a3b4c5'
down_revision: Union[str, None] = 'w9x0y1z2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Count of times the RFQ failed the completeness gate (still incomplete) and whether it
    # has been terminally blocked after exceeding the allowed attempts.
    op.add_column('rfqs', sa.Column('quality_attempts', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('rfqs', sa.Column('quality_blocked', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column('rfqs', 'quality_blocked')
    op.drop_column('rfqs', 'quality_attempts')
