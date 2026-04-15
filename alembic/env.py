from __future__ import annotations

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def _normalize_sqlalchemy_dsn(raw_dsn: str) -> str:
    if raw_dsn.startswith("postgresql://"):
        return "postgresql+psycopg://" + raw_dsn[len("postgresql://") :]
    if raw_dsn.startswith("postgres://"):
        return "postgresql+psycopg://" + raw_dsn[len("postgres://") :]
    return raw_dsn


def _resolve_dsn() -> str:
    x_args = context.get_x_argument(as_dictionary=True)
    dsn = x_args.get("dsn")
    if dsn:
        return _normalize_sqlalchemy_dsn(dsn)

    env_dsn = os.getenv("CHANNEL_POLICY_ROUTER_MIGRATOR_DSN") or os.getenv(
        "CHANNEL_POLICY_ROUTER_POSTGRES_DSN"
    )
    if env_dsn:
        return _normalize_sqlalchemy_dsn(env_dsn)

    return _normalize_sqlalchemy_dsn(config.get_main_option("sqlalchemy.url"))


def run_migrations_offline() -> None:
    url = _resolve_dsn()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _resolve_dsn()

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
