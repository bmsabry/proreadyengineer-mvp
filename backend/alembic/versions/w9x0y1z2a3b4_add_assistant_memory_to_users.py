"""add assistant_memory to users

Revision ID: w9x0y1z2a3b4
Revises: u1v2w3x4y5z6
Create Date: 2026-06-01 23:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'w9x0y1z2a3b4'
down_revision: Union[str, None] = 'u1v2w3x4y5z6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Short, user-controlled notes the AI Help Assistant remembers across sessions
    # (the signed-in user's OWN stated preferences/context). Nullable; capped in app code.
    op.add_column(
        'users',
        sa.Column('assistant_memory', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('users', 'assistant_memory')
