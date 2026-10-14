"""Environnement d'exécution d'Alembic (version asynchrone, pilote asyncpg).

Deux particularités par rapport au modèle fourni par Alembic :

* un verrou consultatif PostgreSQL (pg_advisory_lock) est pris avant de migrer.
  Sous Kubernetes, plusieurs répliques du back démarrent en même temps et
  lancent chacune « alembic upgrade head » : la première migre, les autres
  attendent le verrou puis constatent que la base est déjà à jour ;
* une base créée avant l'introduction d'Alembic (schéma produit par
  Base.metadata.create_all) est reconnue et simplement marquée à la révision
  initiale, sans rejouer la création des tables.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

# distinct des verrous de app/initialisation.py (856_700 et 856_701)
VERROU_MIGRATIONS = 856_690
REVISION_INITIALE = "0001"


def url_base() -> str:
    # une adresse passée explicitement (tests) prime sur la configuration de l'application
    return config.get_main_option("sqlalchemy.url") or settings.database_url


def run_migrations_offline() -> None:
    """Mode « --sql » : écrit le SQL sans se connecter à la base."""
    context.configure(
        url=url_base(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def schema_anterieur_a_alembic(connection: Connection) -> bool:
    tables = inspect(connection)
    return tables.has_table("salles") and not tables.has_table("alembic_version")


def do_run_migrations(connection: Connection) -> None:
    connection.execute(text("SELECT pg_advisory_lock(:cle)"), {"cle": VERROU_MIGRATIONS})
    connection.commit()
    try:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        herite = schema_anterieur_a_alembic(connection)
        connection.commit()
        with context.begin_transaction():
            if herite:
                # tables déjà là : on marque la base comme étant à la révision initiale
                context.get_context().stamp(ScriptDirectory.from_config(config), REVISION_INITIALE)
            context.run_migrations()
        connection.commit()
    finally:
        connection.execute(text("SELECT pg_advisory_unlock(:cle)"), {"cle": VERROU_MIGRATIONS})
        connection.commit()


async def run_async_migrations() -> None:
    moteur = create_async_engine(url_base(), poolclass=pool.NullPool)
    async with moteur.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await moteur.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
