"""Redis : connexion partagée et diffusion des évènements temps réel.

Chaque instance de l'API garde UNE seule connexion pub/sub vers Redis et
redistribue les messages aux clients SSE qu'elle sert. Ainsi un siège réservé
via l'instance A apparaît aussi chez un client connecté à l'instance B.
"""

import asyncio
import contextlib
import json
import logging
from collections import defaultdict

import redis.asyncio as aioredis

from .config import settings

log = logging.getLogger(__name__)

redis = aioredis.from_url(settings.redis_url, decode_responses=True)


def canal_seance(seance_id: int) -> str:
    return f"seance:{seance_id}"


CANAL_REMPLISSAGE = "remplissage"


async def publier(canal: str, donnees: dict) -> None:
    await redis.publish(canal, json.dumps(donnees))


class Diffuseur:
    def __init__(self) -> None:
        self.abonnes: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._tache: asyncio.Task | None = None

    async def demarrer(self) -> None:
        self._tache = asyncio.create_task(self._boucle())

    async def arreter(self) -> None:
        if self._tache:
            self._tache.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._tache

    async def _boucle(self) -> None:
        while True:
            pubsub = redis.pubsub()
            try:
                await pubsub.psubscribe("seance:*", CANAL_REMPLISSAGE)
                async for message in pubsub.listen():
                    if message["type"] != "pmessage":
                        continue
                    for file in list(self.abonnes.get(message["channel"], ())):
                        # un client trop lent ne doit pas bloquer les autres
                        if not file.full():
                            file.put_nowait(message["data"])
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("abonnement redis perdu, nouvelle tentative")
                await asyncio.sleep(1)
            finally:
                with contextlib.suppress(Exception):
                    await pubsub.aclose()

    @contextlib.asynccontextmanager
    async def abonner(self, canal: str):
        file: asyncio.Queue = asyncio.Queue(maxsize=200)
        self.abonnes[canal].add(file)
        try:
            yield file
        finally:
            self.abonnes[canal].discard(file)
            if not self.abonnes[canal]:
                del self.abonnes[canal]


diffuseur = Diffuseur()


async def flux(canal: str):
    """Générateur pour les routes SSE : un message JSON par évènement."""
    async with diffuseur.abonner(canal) as file:
        while True:
            yield json.loads(await file.get())
