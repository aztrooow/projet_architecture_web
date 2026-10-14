"""La migration initiale produit exactement le schéma des modèles."""

import asyncio

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, pool, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.models import Base

from .conftest import configuration_alembic, creer_base, serveur_et_base

_, BASE_PRINCIPALE = serveur_et_base(settings.database_url)
URL = settings.database_url.rsplit("/", 1)[0] + "/" + BASE_PRINCIPALE + "_migrations"


async def base_vierge() -> None:
    await creer_base(URL)
    moteur = create_async_engine(URL, poolclass=pool.NullPool)
    async with moteur.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await moteur.dispose()


async def differences() -> list:
    moteur = create_async_engine(URL, poolclass=pool.NullPool)
    try:
        async with moteur.connect() as conn:

            def comparer(sync_conn):
                contexte = MigrationContext.configure(sync_conn, opts={"compare_type": True})
                return compare_metadata(contexte, Base.metadata)

            return await conn.run_sync(comparer)
    finally:
        await moteur.dispose()


async def tables() -> set[str]:
    moteur = create_async_engine(URL, poolclass=pool.NullPool)
    try:
        async with moteur.connect() as conn:
            return await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
    finally:
        await moteur.dispose()


async def test_migration_fidele_aux_modeles_et_reversible():
    await base_vierge()
    config = configuration_alembic(URL)
    await asyncio.to_thread(command.upgrade, config, "head")
    assert await tables() == set(Base.metadata.tables) | {"alembic_version"}
    assert await differences() == []
    # rejouer la migration sur une base à jour ne change rien
    await asyncio.to_thread(command.upgrade, config, "head")
    await asyncio.to_thread(command.downgrade, config, "base")
    assert await tables() == {"alembic_version"}


async def test_base_creee_avant_alembic_est_reconnue():
    """Une base produite par l'ancien create_all est marquée à la révision initiale, sans erreur."""
    await base_vierge()
    moteur = create_async_engine(URL, poolclass=pool.NullPool)
    async with moteur.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await moteur.dispose()
    await asyncio.to_thread(command.upgrade, configuration_alembic(URL), "head")
    assert "alembic_version" in await tables()
    assert await differences() == []
