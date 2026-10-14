"""Chargement des fixtures au démarrage du conteneur (après les migrations).

Données de référence : salles et sièges, catégories de spectateurs, règles
tarifaires, évènement du samedi, réglages par défaut, comptes du personnel.
Le chargement est idempotent : relancé, il ne crée aucun doublon. Les salles,
les tarifs et les réglages ne sont créés que sur une base vide (le gérant les
modifie ensuite depuis le back-office et on ne doit pas écraser son travail) ;
les mots de passe du personnel, eux, suivent la configuration à chaque démarrage.

Lancement : python -m app.fixtures
"""

import asyncio
import logging

from sqlalchemy import func, select, text

from .config import settings
from .db import SessionLocal, engine
from .initialisation import VERROU_INIT, creer_comptes, creer_donnees_demo
from .models import Salle

log = logging.getLogger("fixtures")


async def charger_fixtures() -> None:
    async with SessionLocal() as session:
        # un seul conteneur charge à la fois, les autres attendent puis constatent que tout est là
        await session.execute(text("SELECT pg_advisory_xact_lock(:v)"), {"v": VERROU_INIT})
        await creer_comptes(session)
        if settings.donnees_demo and not await session.scalar(select(func.count()).select_from(Salle)):
            await creer_donnees_demo(session)
            log.info("fixtures chargées : salles, sièges, catégories, tarifs, réglages")
        else:
            log.info("fixtures déjà en place, rien à créer")
        await session.commit()


async def main() -> None:
    try:
        await charger_fixtures()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(main())
