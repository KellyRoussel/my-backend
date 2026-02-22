"""add_profile_country_interests

Add country (ISO 3-letter) and interests (JSON text array) to investment_profiles.

Revision ID: c1d2e3f4a5b6
Revises: b3c4d5e6f7a8
Create Date: 2026-02-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('investment_profiles', sa.Column('country', sa.String(length=3), nullable=True))
    op.add_column('investment_profiles', sa.Column('interests', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('investment_profiles', 'interests')
    op.drop_column('investment_profiles', 'country')
