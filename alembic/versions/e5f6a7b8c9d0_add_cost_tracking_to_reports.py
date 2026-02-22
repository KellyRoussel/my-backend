"""add_cost_tracking_to_reports

Revision ID: e5f6a7b8c9d0
Revises: c1d2e3f4a5b6
Create Date: 2026-02-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('investment_reports', sa.Column('tokens_input', sa.Integer(), nullable=True))
    op.add_column('investment_reports', sa.Column('tokens_cached', sa.Integer(), nullable=True))
    op.add_column('investment_reports', sa.Column('tokens_output', sa.Integer(), nullable=True))
    op.add_column('investment_reports', sa.Column('cost_usd', sa.Numeric(precision=10, scale=6), nullable=True))
    op.add_column('investment_reports', sa.Column('model_used', sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column('investment_reports', 'model_used')
    op.drop_column('investment_reports', 'cost_usd')
    op.drop_column('investment_reports', 'tokens_output')
    op.drop_column('investment_reports', 'tokens_cached')
    op.drop_column('investment_reports', 'tokens_input')
