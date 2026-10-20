"""bobobidou_photo_usage

Daily counters of the photos analysed by OpenAI (per user and global), to limit
the number of photos per day. The rows are keyed by an HMAC of the user id and
have no foreign key to `users`, so that they survive an account deletion.
The `bobobidou_app` role gets its rights from the schema's default privileges.

Revision ID: c2d3e4f5a6b7
Revises: b0b1d0a1c2d3
Create Date: 2026-10-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'c2d3e4f5a6b7'
down_revision = 'b0b1d0a1c2d3'
branch_labels = None
depends_on = None

SCHEMA = "bobobidou"


def upgrade() -> None:
    op.create_table(
        'photo_usage',
        sa.Column('subject', sa.String(length=64), nullable=False),
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('count', sa.Integer(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('subject', 'day'),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table('photo_usage', schema=SCHEMA)
