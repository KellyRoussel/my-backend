"""widen_profile_country_column

Widen investment_profiles.country from VARCHAR(3) to VARCHAR(100)
to support full country names (e.g. "France") in addition to ISO codes.

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-02-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2e3f4a5b6c7'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'investment_profiles',
        'country',
        existing_type=sa.String(length=3),
        type_=sa.String(length=100),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        'investment_profiles',
        'country',
        existing_type=sa.String(length=100),
        type_=sa.String(length=3),
        existing_nullable=True,
    )
