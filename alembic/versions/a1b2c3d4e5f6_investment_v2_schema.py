"""investment_v2_schema

Revision ID: a1b2c3d4e5f6
Revises: 5c44cf40ccac
Create Date: 2026-02-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '5c44cf40ccac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- investment_profiles: 4 new columns ---
    op.add_column('investment_profiles', sa.Column('investment_horizon', sa.String(length=50), nullable=True))
    op.add_column('investment_profiles', sa.Column('ethical_exclusions', sa.Text(), nullable=True))
    op.add_column('investment_profiles', sa.Column('last_macro_context', sa.Text(), nullable=True))
    op.add_column('investment_profiles', sa.Column('last_macro_updated_at', sa.DateTime(), nullable=True))

    # --- investments: 4 new columns ---
    op.add_column('investments', sa.Column('investment_thesis', sa.Text(), nullable=True))
    op.add_column('investments', sa.Column('thesis_status', sa.String(length=20), nullable=True, server_default='valid'))
    op.add_column('investments', sa.Column('alert_threshold_pct', sa.Numeric(precision=5, scale=2), nullable=True))
    op.add_column('investments', sa.Column('account_type', sa.String(length=5), nullable=True))

    # --- new table: investment_watchlist ---
    op.create_table(
        'investment_watchlist',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('sector', sa.String(length=100), nullable=True),
        sa.Column('country', sa.String(length=3), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('source', sa.String(length=50), nullable=True),
        sa.Column('priority', sa.String(length=20), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_investment_watchlist_user_id'), 'investment_watchlist', ['user_id'], unique=False)

    # --- new table: investment_reports ---
    op.create_table(
        'investment_reports',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('report_date', sa.Date(), nullable=False),
        sa.Column('step1_portfolio_review', sa.Text(), nullable=True),
        sa.Column('step2_macro_context', sa.Text(), nullable=True),
        sa.Column('step3_shortlist', sa.Text(), nullable=True),
        sa.Column('step4_decision', sa.Text(), nullable=True),
        sa.Column('final_recommendation', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_investment_reports_user_id'), 'investment_reports', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_investment_reports_user_id'), table_name='investment_reports')
    op.drop_table('investment_reports')
    op.drop_index(op.f('ix_investment_watchlist_user_id'), table_name='investment_watchlist')
    op.drop_table('investment_watchlist')

    op.drop_column('investments', 'account_type')
    op.drop_column('investments', 'alert_threshold_pct')
    op.drop_column('investments', 'thesis_status')
    op.drop_column('investments', 'investment_thesis')

    op.drop_column('investment_profiles', 'last_macro_updated_at')
    op.drop_column('investment_profiles', 'last_macro_context')
    op.drop_column('investment_profiles', 'ethical_exclusions')
    op.drop_column('investment_profiles', 'investment_horizon')
