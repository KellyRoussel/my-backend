"""Alembic environment configuration."""
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

from models.database_models import (
    Base,
    User,
    InstagramToken,
    GoogleToken,
    MyBackendToken,
    AuthState,
    InvestmentProfile,
    Investment,
    InvestmentTransaction,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Schemas managed by these migrations (Supabase has others: auth, storage...).
# `bobobidou` is managed by the bobobidou_backend repo (own migrations, version
# table `bobobidou.alembic_version`): b0b1d0a1c2d3 and c2d3e4f5a6b7 stay here as
# history, new Bobobidou migrations go there
MANAGED_SCHEMAS = {None, "public"}


def include_name(name, type_, parent_names):
    if type_ == "schema":
        return name in MANAGED_SCHEMAS
    return True


def get_url():
    """Get database URL from environment or config."""
    return os.getenv("DATABASE_URL", config.get_main_option("sqlalchemy.url"))


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        include_name=include_name,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            include_schemas=True,
            include_name=include_name,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
