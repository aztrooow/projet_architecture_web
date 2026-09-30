import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from . import qr_client
from .config import settings
from .db import engine
from .initialisation import entretien_periodique, initialiser
from .routes import admin, auth, catalogue, commandes, interne
from .temps_reel import diffuseur, redis

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await initialiser()
    await diffuseur.demarrer()
    entretien = asyncio.create_task(entretien_periodique())
    yield
    entretien.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await entretien
    await diffuseur.arreter()
    await qr_client.fermer()
    await redis.aclose()
    await engine.dispose()


app = FastAPI(
    title="CinetINT, API de billetterie",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_methods=["*"],
        allow_headers=["*"],
    )

for module in (catalogue, commandes, auth, admin, interne):
    app.include_router(module.router)


@app.get("/api/sante", tags=["supervision"])
async def sante():
    """Sonde de disponibilité (sert aussi aux probes Kubernetes)."""
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    await redis.ping()
    return {"statut": "ok"}
