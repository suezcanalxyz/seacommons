# SPDX-License-Identifier: AGPL-3.0-or-later
"""Alembic environment (docs/fixes.md Phase 2.2).

The URL comes from core.db.session.database_url() so migrations always target
the same database the app does; ``target_metadata`` is the live model
metadata so ``alembic revision --autogenerate`` works.
"""
from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from core.db.models import Base
from core.db.session import database_url

config = context.config
if config.config_file_name is not None:
    # disable_existing_loggers=False: when this env is driven embedded
    # (core.db.session.alembic_upgrade, the migration tests), fileConfig must
    # not silence the host process's / test runner's already-configured
    # loggers, which is its default behaviour.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# A caller (tests, a one-off command) may pin the URL explicitly; otherwise
# fall back to the same database the app uses.
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", database_url().replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # batch mode keeps ALTER TABLE working on SQLite (the pilot DB).
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
