from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from app.config.settings import get_settings
from app.curated import curated_models  # noqa: F401 — register models
from app.data import raw_models  # noqa: F401 — register models
from app.db.base import Base
from app.evidence import audit as audit_models  # noqa: F401 — register models
from app.external import models as external_models  # noqa: F401 — register models
from sqlalchemy import engine_from_config, pool, text

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    return get_settings().database_url


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        autocommit = connection.execution_options(isolation_level="AUTOCOMMIT")
        autocommit.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
