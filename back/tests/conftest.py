"""Les tests tournent contre un vrai PostgreSQL et un vrai Redis (docker compose,
profil « tests »), sur une base dédiée qui est recréée au début de la session.

Le schéma vient des migrations Alembic, comme en production : un test qui passe
prouve donc aussi que la migration initiale est fidèle aux modèles."""

import asyncio
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import asyncpg
import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text

from app.config import settings
from app.db import SessionLocal, engine
from app.fixtures import charger_fixtures
from app.initialisation import creer_donnees_demo
from app.main import app
from app.models import Film, Salle, Seance
from app.temps_reel import redis

PARIS = ZoneInfo("Europe/Paris")
ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


def serveur_et_base(url: str) -> tuple[str, str]:
    """('postgresql://hote:5432', 'nom_de_la_base') à partir d'une URL SQLAlchemy asyncpg."""
    brut = url.replace("postgresql+asyncpg://", "postgresql://")
    serveur, nom = brut.rsplit("/", 1)
    return serveur, nom


async def creer_base(url: str) -> None:
    serveur, nom = serveur_et_base(url)
    conn = await asyncpg.connect(serveur + "/postgres")
    try:
        if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", nom):
            await conn.execute(f'CREATE DATABASE "{nom}"')
    finally:
        await conn.close()


def configuration_alembic(url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


@pytest.fixture(scope="session")
async def client():
    await creer_base(settings.database_url)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    # Alembic pilote sa propre boucle d'évènements : on l'exécute dans un fil
    await asyncio.to_thread(command.upgrade, configuration_alembic(settings.database_url), "head")
    await redis.flushdb()
    await charger_fixtures()
    async with app.router.lifespan_context(app):
        async with SessionLocal() as session:
            await creer_donnees_demo(session)
            await session.commit()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


FILM_EVENEMENT = "Terminator 2 : Le Jugement dernier"


async def nouvelle_seance(film_titre: str = FILM_EVENEMENT, jours: int = 2, evenement_id: int | None = None) -> int:
    async with SessionLocal() as session:
        film = await session.scalar(select(Film).where(Film.titre == film_titre))
        salle = await session.scalar(select(Salle).order_by(Salle.id).limit(1))
        debut = datetime.combine(datetime.now(PARIS).date() + timedelta(days=jours), time(20, 0), PARIS)
        seance = Seance(film_id=film.id, salle_id=salle.id, debut=debut, evenement_id=evenement_id)
        session.add(seance)
        await session.commit()
        return seance.id


@pytest.fixture
async def seance(client):
    return await nouvelle_seance()


async def connexion(client, identifiant: str) -> dict:
    reponse = await client.post("/api/auth/connexion", json={"identifiant": identifiant, "mot_de_passe": identifiant})
    return {"Authorization": f"Bearer {reponse.json()['jeton']}"}
