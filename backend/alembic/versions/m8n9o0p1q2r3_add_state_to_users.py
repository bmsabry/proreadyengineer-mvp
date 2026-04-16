from alembic import op
import sqlalchemy as sa

revision = 'm8n9o0p1q2r3'
down_revision = 'l7m8n9o0p1q2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('state', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('users', 'state')
