"""drop_report_step_columns

Remove per-step analysis storage from investment_reports.
The save_analysis_step tool is no longer used — only final_recommendation is kept.

Revision ID: b3c4d5e6f7a8
Revises: a1b2c3d4e5f6
Create Date: 2026-02-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('investment_reports', 'step1_portfolio_review')
    op.drop_column('investment_reports', 'step2_macro_context')
    op.drop_column('investment_reports', 'step3_shortlist')
    op.drop_column('investment_reports', 'step4_decision')


def downgrade() -> None:
    op.add_column('investment_reports', sa.Column('step4_decision', sa.Text(), nullable=True))
    op.add_column('investment_reports', sa.Column('step3_shortlist', sa.Text(), nullable=True))
    op.add_column('investment_reports', sa.Column('step2_macro_context', sa.Text(), nullable=True))
    op.add_column('investment_reports', sa.Column('step1_portfolio_review', sa.Text(), nullable=True))
