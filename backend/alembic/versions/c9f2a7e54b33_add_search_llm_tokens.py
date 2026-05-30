"""add search_requests LLM token + cost columns

Per-search LLM token usage (intent + pass1 + pass2) so the Operating Cost panel can
show ACTUAL search/ranking spend instead of an estimate.

Revision ID: c9f2a7e54b33
Revises: b8e1f6c43d21
Create Date: 2026-05-30
"""
from alembic import op
import sqlalchemy as sa

revision = 'c9f2a7e54b33'
down_revision = 'b8e1f6c43d21'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = [c['name'] for c in insp.get_columns('search_requests')]
    if 'llm_prompt_tokens' not in cols:
        op.add_column('search_requests', sa.Column('llm_prompt_tokens', sa.Integer(), nullable=True))
    if 'llm_completion_tokens' not in cols:
        op.add_column('search_requests', sa.Column('llm_completion_tokens', sa.Integer(), nullable=True))
    if 'llm_cost_usd' not in cols:
        op.add_column('search_requests', sa.Column('llm_cost_usd', sa.Float(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = [c['name'] for c in insp.get_columns('search_requests')]
    for col in ('llm_cost_usd', 'llm_completion_tokens', 'llm_prompt_tokens'):
        if col in cols:
            op.drop_column('search_requests', col)
