from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import tarifs
from ..db import get_session
from ..models import Categorie, Evenement, Film, RegleTarifaire, Salle, Seance

Session = Annotated[AsyncSession, Depends(get_session)]


def maintenant() -> datetime:
    return datetime.now(timezone.utc)


def film_json(film: Film) -> dict:
    return {
        "id": film.id,
        "titre": film.titre,
        "realisation": film.realisation,
        "annee": film.annee,
        "duree_min": film.duree_min,
        "genre": film.genre,
        "synopsis": film.synopsis,
        "type_production": film.type_production,
        "couleur": film.couleur,
    }


def seance_json(seance: Seance, film: Film, salle: Salle, evenement: Evenement | None) -> dict:
    return {
        "id": seance.id,
        "debut": seance.debut.isoformat(),
        "version": seance.version,
        "film": film_json(film),
        "salle": {"id": salle.id, "nom": salle.nom, "capacite": salle.capacite},
        "evenement": {"id": evenement.id, "nom": evenement.nom, "description": evenement.description}
        if evenement
        else None,
    }


async def regles_actives(session: AsyncSession) -> list[RegleTarifaire]:
    return list(await session.scalars(select(RegleTarifaire).where(RegleTarifaire.actif)))


async def categories_actives(session: AsyncSession) -> list[Categorie]:
    return list(await session.scalars(select(Categorie).where(Categorie.actif).order_by(Categorie.ordre)))


def grille_seance(seance: Seance, film: Film, regles, categories) -> list[dict]:
    """Prix de la séance pour chaque catégorie de spectateur, tel qu'affiché avant paiement."""
    grille = []
    for c in categories:
        ctx = tarifs.contexte_seance(seance.debut, film.type_production, seance.evenement_id, c.code)
        regle = tarifs.choisir(regles, ctx)
        if regle:
            grille.append(
                {
                    "categorie": c.code,
                    "categorie_libelle": c.libelle,
                    "libelle": regle.libelle,
                    "prix_centimes": regle.prix_centimes,
                }
            )
    return grille
