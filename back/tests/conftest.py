"""Les tests tournent contre un vrai PostgreSQL et un vrai Redis (docker compose,
profil « tests »), sur une base dédiée qui est vidée au début de la session."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import asyncpg
import httpx
import pytest
from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal, engine
from app.initialisation import creer_donnees_demo
from app.main import app
from app.models import Base, Film, Salle, Seance
from app.temps_reel import redis

PARIS = ZoneInfo("Europe/Paris")


async def creer_base_de_test() -> None:
    url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    serveur, nom = url.rsplit("/", 1)
    conn = await asyncpg.connect(serveur + "/postgres")
    try:
        if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", nom):
            await conn.execute(f'CREATE DATABASE "{nom}"')
    finally:
        await conn.close()


@pytest.fixture(scope="session")
async def client():
    await creer_base_de_test()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await redis.flushdb()
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
