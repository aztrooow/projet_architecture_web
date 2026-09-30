from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Parametre

# points laissés ouverts par la spec (§8), réglables par le gérant
DEFAUTS = {
    "duree_verrou_min": (10, "Durée de blocage des places pendant le paiement (minutes)"),
    "places_max": (10, "Nombre maximum de places par commande"),
    "remboursement_limite_min": (60, "Remboursement possible jusqu'à ce nombre de minutes avant la séance"),
}


async def lire(session: AsyncSession) -> dict[str, int]:
    valeurs = {cle: defaut for cle, (defaut, _) in DEFAUTS.items()}
    for p in await session.scalars(select(Parametre)):
        valeurs[p.cle] = p.valeur
    return valeurs
