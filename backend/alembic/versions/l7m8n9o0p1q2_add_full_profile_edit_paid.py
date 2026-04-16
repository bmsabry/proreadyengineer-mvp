from alembic import op
import sqlalchemy as sa

revision = 'l7m8n9o0p1q2'
down_revision = 'k6l7m8n9o0p1'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('providers', sa.Column('full_profile_edit_paid', sa.Boolean(), nullable=True, server_default='false'))

def downgrade():
    op.drop_column('providers', 'full_profile_edit_paid')
