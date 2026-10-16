"""bobobidou_schema

Isolate the Bobobidou data in a dedicated `bobobidou` schema, with a
`bobobidou_app` Postgres role that only has access to this schema.

- creates the schema, the role (NOLOGIN: its password is set by hand, out of git)
  and the tables: users, refresh_tokens, auth_states, photo_quotas, subscriptions
- copies the Bobobidou users and their active refresh tokens from `public`
  (the `public` rows are left untouched: they are cleaned up later, by hand)

Revision ID: b0b1d0a1c2d3
Revises: a7b8c9d0e1f2
Create Date: 2026-10-16 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'b0b1d0a1c2d3'
down_revision = 'a7b8c9d0e1f2'
branch_labels = None
depends_on = None

SCHEMA = "bobobidou"
ROLE = "bobobidou_app"

# Users and tokens tables are shared by all the apps, with no column telling which
# app a user comes from. A Bobobidou user is a Google user with no data in the
# personal features (Instagram, investment, push notifications).
# Check the list with this query before upgrading; a user missing from it just
# has to log in again in the app.
BOBOBIDOU_USERS_SELECT = """
    SELECT u.id FROM public.users u
    WHERE u.primary_provider = 'GOOGLE'
      AND NOT EXISTS (SELECT 1 FROM public.instagram_tokens t WHERE t.user_id = u.id)
      AND NOT EXISTS (SELECT 1 FROM public.investment_profiles t WHERE t.user_id = u.id)
      AND NOT EXISTS (SELECT 1 FROM public.investments t WHERE t.user_id = u.id)
      AND NOT EXISTS (SELECT 1 FROM public.investment_watchlist t WHERE t.user_id = u.id)
      AND NOT EXISTS (SELECT 1 FROM public.investment_reports t WHERE t.user_id = u.id)
      AND NOT EXISTS (SELECT 1 FROM public.device_tokens t WHERE t.user_id = u.id)
"""

auth_provider = postgresql.ENUM("GOOGLE", "INSTAGRAM", name="authprovider", schema=SCHEMA, create_type=False)


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    op.execute(f"CREATE TYPE {SCHEMA}.authprovider AS ENUM ('GOOGLE', 'INSTAGRAM')")

    op.create_table(
        'users',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('username', sa.String(), nullable=True),
        sa.Column('display_name', sa.String(), nullable=True),
        sa.Column('profile_picture_url', sa.String(), nullable=True),
        sa.Column('primary_provider', auth_provider, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        schema=SCHEMA,
    )
    op.create_index('ix_bobobidou_users_email', 'users', ['email'], schema=SCHEMA)

    op.create_table(
        'refresh_tokens',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('access_token', sa.Text(), nullable=False),
        sa.Column('token_type', sa.String(), nullable=True),
        sa.Column('expires_in', sa.Integer(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('scope', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], [f'{SCHEMA}.users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        schema=SCHEMA,
    )
    op.create_index('ix_bobobidou_refresh_tokens_user_id', 'refresh_tokens', ['user_id'], schema=SCHEMA)

    op.create_table(
        'auth_states',
        sa.Column('state', sa.String(), nullable=False),
        sa.Column('app_name', sa.String(), nullable=False),
        sa.Column('provider', auth_provider, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('state'),
        schema=SCHEMA,
    )

    op.create_table(
        'photo_quotas',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('period_start', sa.Date(), nullable=False),
        sa.Column('used_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], [f'{SCHEMA}.users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'period_start', name='uq_photo_quotas_user_period'),
        schema=SCHEMA,
    )
    op.create_index('ix_bobobidou_photo_quotas_user_id', 'photo_quotas', ['user_id'], schema=SCHEMA)

    op.create_table(
        'subscriptions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('platform', sa.String(length=10), nullable=False),
        sa.Column('product_id', sa.String(), nullable=False),
        sa.Column('purchase_token', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='active'),
        sa.Column('auto_renewing', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], [f'{SCHEMA}.users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('purchase_token', name='uq_subscriptions_purchase_token'),
        schema=SCHEMA,
    )
    op.create_index('ix_bobobidou_subscriptions_user_id', 'subscriptions', ['user_id'], schema=SCHEMA)

    # Copy the Bobobidou users and their still valid refresh tokens
    op.execute(f"""
        INSERT INTO {SCHEMA}.users
            (id, email, username, display_name, profile_picture_url, primary_provider, created_at, updated_at)
        SELECT id, email, username, display_name, profile_picture_url,
               primary_provider::text::{SCHEMA}.authprovider, created_at, updated_at
        FROM public.users
        WHERE id IN ({BOBOBIDOU_USERS_SELECT})
    """)
    op.execute(f"""
        INSERT INTO {SCHEMA}.refresh_tokens
            (user_id, access_token, token_type, expires_in, expires_at, scope, created_at, updated_at, is_active)
        SELECT user_id, access_token, token_type, expires_in, expires_at, scope, created_at, updated_at, is_active
        FROM public.my_backend_tokens
        WHERE user_id IN ({BOBOBIDOU_USERS_SELECT})
          AND token_type = 'refresh'
          AND is_active = 'true'
          AND (expires_at IS NULL OR expires_at > now() AT TIME ZONE 'utc')
    """)

    # Dedicated role: read/write on the bobobidou tables only, no DDL (the
    # migrations run with the admin user). LOGIN and password are set by hand.
    op.execute(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{ROLE}') THEN
                CREATE ROLE {ROLE} NOLOGIN;
            END IF;
        END
        $$
    """)
    op.execute(f"REVOKE ALL ON SCHEMA {SCHEMA} FROM PUBLIC")
    op.execute(f"GRANT USAGE ON SCHEMA {SCHEMA} TO {ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {SCHEMA} TO {ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {SCHEMA} TO {ROLE}")
    # Same rights on the tables the next migrations will create
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {SCHEMA} GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {ROLE}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {SCHEMA} GRANT USAGE, SELECT ON SEQUENCES TO {ROLE}")
    op.execute(f"ALTER ROLE {ROLE} SET search_path = {SCHEMA}")


def downgrade() -> None:
    # The role is kept (it may hold a password set by hand): DROP ROLE by hand if needed
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {SCHEMA} REVOKE ALL ON TABLES FROM {ROLE}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {SCHEMA} REVOKE ALL ON SEQUENCES FROM {ROLE}")
    op.drop_table('subscriptions', schema=SCHEMA)
    op.drop_table('photo_quotas', schema=SCHEMA)
    op.drop_table('auth_states', schema=SCHEMA)
    op.drop_table('refresh_tokens', schema=SCHEMA)
    op.drop_table('users', schema=SCHEMA)
    op.execute(f"DROP TYPE {SCHEMA}.authprovider")
    op.execute(f"DROP SCHEMA {SCHEMA}")
