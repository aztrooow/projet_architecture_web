"""Compteurs de places vendues par séance.

Le compteur Redis n'est qu'un cache : la vérité reste le nombre de billets
valides ou utilisés en base, et on peut toujours le recalculer.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Billet
from .temps_reel import CANAL_REMPLISSAGE, publier, redis

BILLETS_OCCUPANT = ("valide", "utilise")

# n'incrémente que si le compteur existe déjà, sinon il faut le recalculer
_AJUSTER = redis.register_script(
    """
    if redis.call('EXISTS', KEYS[1]) == 1 then
        return redis.call('INCRBY', KEYS[1], ARGV[1])
    end
    return false
    """
)


def cle(seance_id: int) -> str:
    return f"remplissage:{seance_id}"


async def compter_en_base(session: AsyncSession, seance_ids: list[int]) -> dict[int, int]:
    if not seance_ids:
        return {}
    lignes = await session.execute(
        select(Billet.seance_id, func.count())
        .where(Billet.seance_id.in_(seance_ids), Billet.statut.in_(BILLETS_OCCUPANT))
        .group_by(Billet.seance_id)
    )
    comptes = {s: 0 for s in seance_ids}
    comptes.update({s: n for s, n in lignes.all()})
    return comptes


async def vendus(session: AsyncSession, seance_ids: list[int]) -> dict[int, int]:
    if not seance_ids:
        return {}
    valeurs = await redis.mget([cle(s) for s in seance_ids])
    resultat = {s: int(v) for s, v in zip(seance_ids, valeurs) if v is not None}
    manquants = [s for s in seance_ids if s not in resultat]
    if manquants:
        recalcules = await compter_en_base(session, manquants)
        await redis.mset({cle(s): n for s, n in recalcules.items()})
        resultat.update(recalcules)
    return resultat


async def ajuster(session: AsyncSession, seance_id: int, delta: int) -> int:
    nouveau = await _AJUSTER(keys=[cle(seance_id)], args=[delta])
    if nouveau is None:
        nouveau = (await compter_en_base(session, [seance_id]))[seance_id]
        await redis.set(cle(seance_id), nouveau)
    await publier(CANAL_REMPLISSAGE, {"seance_id": seance_id, "vendus": int(nouveau)})
    return int(nouveau)


async def recalculer(session: AsyncSession, seance_ids: list[int]) -> dict[int, int]:
    comptes = await compter_en_base(session, seance_ids)
    if comptes:
        await redis.mset({cle(s): n for s, n in comptes.items()})
    return comptes
