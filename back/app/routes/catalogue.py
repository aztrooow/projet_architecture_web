import uuid
from collections.abc import AsyncIterable
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Query
from fastapi.sse import EventSourceResponse
from sqlalchemy import select

from .. import parametres, remplissage, verrous
from ..models import Billet, Evenement, Film, Salle, Seance, Siege
from ..temps_reel import canal_seance, flux
from .commun import (
    Session,
    categories_actives,
    film_json,
    grille_seance,
    maintenant,
    regles_actives,
    seance_json,
)

router = APIRouter(prefix="/api", tags=["catalogue"])


def _requete_seances():
    return (
        select(Seance, Film, Salle, Evenement)
        .join(Film, Film.id == Seance.film_id)
        .join(Salle, Salle.id == Seance.salle_id)
        .outerjoin(Evenement, Evenement.id == Seance.evenement_id)
    )


@router.get("/programme")
async def programme(session: Session, jours: int = Query(7, ge=1, le=14)):
    """Films à l'affiche et leurs prochaines séances (sert aussi aux pages rendues par le front)."""
    debut = maintenant()
    lignes = (
        await session.execute(
            _requete_seances()
            .where(Seance.debut > debut, Seance.debut < debut + timedelta(days=jours), Film.actif)
            .order_by(Seance.debut)
        )
    ).all()
    vendus = await remplissage.vendus(session, [s.id for s, *_ in lignes])
    regles = await regles_actives(session)
    categories = await categories_actives(session)

    films: dict[int, dict] = {}
    evenements: dict[int, dict] = {}
    for seance, film, salle, evenement in lignes:
        fiche = films.setdefault(film.id, {**film_json(film), "seances": []})
        prix = [g["prix_centimes"] for g in grille_seance(seance, film, regles, categories)]
        infos = seance_json(seance, film, salle, evenement)
        del infos["film"]
        infos["vendus"] = vendus.get(seance.id, 0)
        infos["prix_min_centimes"] = min(prix) if prix else None
        fiche["seances"].append(infos)
        if evenement and evenement.id not in evenements:
            evenements[evenement.id] = {
                **infos["evenement"],
                "seance_id": seance.id,
                "debut": infos["debut"],
                "film": film_json(film),
                "salle": infos["salle"],
                "prix_centimes": infos["prix_min_centimes"],
                "vendus": infos["vendus"],
            }
    return {"films": list(films.values()), "evenements": list(evenements.values())}


@router.get("/films/{film_id}")
async def film(film_id: int, session: Session):
    fiche = await session.get(Film, film_id)
    if not fiche or not fiche.actif:
        raise HTTPException(404, "Film introuvable")
    lignes = (
        await session.execute(
            _requete_seances()
            .where(Seance.film_id == film_id, Seance.debut > maintenant())
            .order_by(Seance.debut)
            .limit(80)
        )
    ).all()
    vendus = await remplissage.vendus(session, [s.id for s, *_ in lignes])
    seances = []
    for seance, f, salle, evenement in lignes:
        infos = seance_json(seance, f, salle, evenement)
        del infos["film"]
        infos["vendus"] = vendus.get(seance.id, 0)
        seances.append(infos)
    return {**film_json(fiche), "seances": seances}


@router.get("/categories")
async def categories(session: Session):
    return [{"code": c.code, "libelle": c.libelle} for c in await categories_actives(session)]


@router.get("/seances/{seance_id}")
async def seance(seance_id: int, session: Session):
    ligne = (await session.execute(_requete_seances().where(Seance.id == seance_id))).first()
    if not ligne:
        raise HTTPException(404, "Séance introuvable")
    s, film, salle, evenement = ligne
    params = await parametres.lire(session)
    return {
        **seance_json(s, film, salle, evenement),
        "vendus": (await remplissage.vendus(session, [s.id]))[s.id],
        "tarifs": grille_seance(s, film, await regles_actives(session), await categories_actives(session)),
        "places_max": params["places_max"],
        "duree_verrou_min": params["duree_verrou_min"],
        "commencee": s.debut <= maintenant(),
    }


@router.get("/seances/{seance_id}/plan")
async def plan(seance_id: int, session: Session, commande: uuid.UUID | None = None):
    """État de chaque siège : libre, verrouille (paiement en cours), vendu, ou panier."""
    s = await session.get(Seance, seance_id)
    if not s:
        raise HTTPException(404, "Séance introuvable")
    sieges = list(await session.scalars(select(Siege).where(Siege.salle_id == s.salle_id).order_by(Siege.y, Siege.x)))
    occupes = set(
        await session.scalars(
            select(Billet.siege_id).where(Billet.seance_id == seance_id, Billet.statut.in_(remplissage.BILLETS_OCCUPANT))
        )
    )
    bloques = await verrous.proprietaires(seance_id, [x.id for x in sieges])
    mien = str(commande) if commande else None

    def etat(siege: Siege) -> str:
        if siege.id in occupes:
            return "vendu"
        if siege.id in bloques:
            return "panier" if bloques[siege.id] == mien else "verrouille"
        return "libre"

    return {
        "seance_id": seance_id,
        "largeur": max((x.x for x in sieges), default=0) + 1,
        "profondeur": max((x.y for x in sieges), default=0) + 1,
        "sieges": [
            {"id": x.id, "rang": x.rang, "numero": x.numero, "x": x.x, "y": x.y, "pmr": x.pmr, "etat": etat(x)}
            for x in sieges
        ],
    }


@router.get("/seances/{seance_id}/flux", response_class=EventSourceResponse)
async def flux_seance(seance_id: int) -> AsyncIterable[dict]:
    """Changements d'état des sièges poussés en direct au plan de salle."""
    async for evenement in flux(canal_seance(seance_id)):
        yield evenement
