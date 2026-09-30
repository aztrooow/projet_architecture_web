"""Back-office du gérant : programmation, tarifs, remplissage, remboursements."""

import uuid
from collections.abc import AsyncIterable
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.sse import EventSourceResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select

from .. import parametres, remplissage
from ..auth import gerant
from ..config import settings
from ..models import (
    Billet,
    Categorie,
    Commande,
    Controle,
    Evenement,
    Film,
    Parametre,
    RegleTarifaire,
    Salle,
    Seance,
    Siege,
)
from ..temps_reel import CANAL_REMPLISSAGE, flux
from .commandes import detail_commande, rembourser
from .commun import Session, film_json, maintenant

router = APIRouter(prefix="/api/admin", tags=["back-office"], dependencies=[Depends(gerant)])

TypeProduction = Literal["standard", "3d", "art_essai"]


def debut_du_jour() -> datetime:
    local = datetime.now(ZoneInfo(settings.fuseau))
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


# ---------- remplissage


@router.get("/resume")
async def resume(session: Session):
    """Les chiffres du jour affichés en tête du tableau de bord."""
    jour = debut_du_jour()
    fin = jour + timedelta(days=1)
    vendus_jour, recette = (
        await session.execute(
            select(func.count(), func.coalesce(func.sum(Billet.prix_centimes), 0)).where(
                Billet.emis_le >= jour, Billet.emis_le < fin, Billet.statut != "rembourse"
            )
        )
    ).one()
    seances_jour = list(
        await session.execute(
            select(Seance.id, Salle.capacite).join(Salle).where(Seance.debut >= jour, Seance.debut < fin)
        )
    )
    comptes = await remplissage.vendus(session, [s for s, _ in seances_jour])
    capacite = sum(c for _, c in seances_jour)
    entrees = await session.scalar(
        select(func.count()).select_from(Controle).where(Controle.cree_le >= jour, Controle.resultat == "accepte")
    )
    return {
        "billets_vendus": vendus_jour,
        "recette_centimes": recette,
        "seances": len(seances_jour),
        "taux_remplissage": round(100 * sum(comptes.values()) / capacite, 1) if capacite else 0,
        "entrees": entrees,
    }


@router.get("/remplissage")
async def tableau_remplissage(session: Session, jours: int = Query(2, ge=1, le=14)):
    debut = maintenant() - timedelta(hours=3)
    lignes = (
        await session.execute(
            select(Seance, Film, Salle, Evenement)
            .join(Film, Film.id == Seance.film_id)
            .join(Salle, Salle.id == Seance.salle_id)
            .outerjoin(Evenement, Evenement.id == Seance.evenement_id)
            .where(Seance.debut > debut, Seance.debut < debut_du_jour() + timedelta(days=jours))
            .order_by(Seance.debut, Salle.id)
        )
    ).all()
    vendus = await remplissage.vendus(session, [s.id for s, *_ in lignes])
    return [
        {
            "seance_id": s.id,
            "debut": s.debut.isoformat(),
            "film": f.titre,
            "salle": salle.nom,
            "version": s.version,
            "evenement": e.nom if e else None,
            "capacite": salle.capacite,
            "vendus": vendus.get(s.id, 0),
        }
        for s, f, salle, e in lignes
    ]


@router.get("/flux", response_class=EventSourceResponse)
async def flux_remplissage() -> AsyncIterable[dict]:
    async for evenement in flux(CANAL_REMPLISSAGE):
        yield evenement


@router.post("/remplissage/recalcul")
async def recalcul(session: Session):
    ids = list(await session.scalars(select(Seance.id).where(Seance.debut > maintenant() - timedelta(days=1))))
    return {"seances": len(await remplissage.recalculer(session, ids))}


# ---------- films


class FilmIn(BaseModel):
    titre: str = Field(min_length=1, max_length=120)
    realisation: str = ""
    annee: int | None = Field(None, ge=1890, le=2100)
    duree_min: int = Field(ge=1, le=600)
    genre: str = ""
    synopsis: str = ""
    type_production: TypeProduction = "standard"
    couleur: str = Field("#8f1d21", pattern=r"^#[0-9a-fA-F]{6}$")


@router.get("/films")
async def films(session: Session):
    return [film_json(f) | {"actif": f.actif} for f in await session.scalars(select(Film).order_by(Film.titre))]


@router.post("/films", status_code=201)
async def creer_film(data: FilmIn, session: Session):
    film = Film(**data.model_dump())
    session.add(film)
    await session.commit()
    return film_json(film)


@router.put("/films/{film_id}")
async def modifier_film(film_id: int, data: FilmIn, session: Session):
    film = await session.get(Film, film_id)
    if not film:
        raise HTTPException(404, "Film introuvable")
    for champ, valeur in data.model_dump().items():
        setattr(film, champ, valeur)
    film.actif = True
    await session.commit()
    return film_json(film)


@router.delete("/films/{film_id}")
async def retirer_film(film_id: int, session: Session):
    # on retire le film de l'affiche sans effacer l'historique des billets
    film = await session.get(Film, film_id)
    if not film:
        raise HTTPException(404, "Film introuvable")
    film.actif = False
    await session.commit()
    return {"ok": True}


# ---------- salles et séances


@router.get("/salles")
async def salles(session: Session):
    return [{"id": s.id, "nom": s.nom, "capacite": s.capacite} for s in await session.scalars(select(Salle).order_by(Salle.id))]


class SeanceIn(BaseModel):
    film_id: int
    salle_id: int
    debut: datetime
    version: Literal["VF", "VOST"] = "VF"
    evenement_id: int | None = None

    @field_validator("debut")
    @classmethod
    def heure_de_paris(cls, valeur: datetime) -> datetime:
        return valeur if valeur.tzinfo else valeur.replace(tzinfo=ZoneInfo(settings.fuseau))


@router.get("/seances")
async def seances(session: Session, jours: int = Query(14, ge=1, le=60)):
    return await tableau_remplissage(session, jours)


@router.post("/seances", status_code=201)
async def creer_seance(data: SeanceIn, session: Session):
    film = await session.get(Film, data.film_id)
    salle = await session.get(Salle, data.salle_id)
    if not film or not salle:
        raise HTTPException(404, "Film ou salle introuvable")
    if data.evenement_id and not await session.get(Evenement, data.evenement_id):
        raise HTTPException(404, "Évènement introuvable")
    fin = data.debut + timedelta(minutes=film.duree_min + 20)
    # la salle doit être libre, ménage compris
    autres = await session.execute(
        select(Seance.debut, Film.duree_min).join(Film).where(
            Seance.salle_id == data.salle_id,
            Seance.debut < fin,
            Seance.debut > data.debut - timedelta(hours=6),
        )
    )
    for debut, duree in autres:
        if debut + timedelta(minutes=duree + 20) > data.debut:
            raise HTTPException(409, f"{salle.nom} est déjà occupée sur ce créneau")
    seance = Seance(**data.model_dump())
    session.add(seance)
    await session.commit()
    return {"id": seance.id}


@router.delete("/seances/{seance_id}")
async def supprimer_seance(seance_id: int, session: Session):
    vendus = await session.scalar(
        select(func.count())
        .select_from(Billet)
        .where(Billet.seance_id == seance_id, Billet.statut.in_(remplissage.BILLETS_OCCUPANT))
    )
    if vendus:
        raise HTTPException(409, "Des billets sont vendus pour cette séance, remboursez-les d'abord")
    await session.execute(delete(Seance).where(Seance.id == seance_id))
    await session.commit()
    return {"ok": True}


# ---------- évènements


class EvenementIn(BaseModel):
    nom: str = Field(min_length=1, max_length=120)
    description: str = ""


@router.get("/evenements")
async def evenements(session: Session):
    return [
        {"id": e.id, "nom": e.nom, "description": e.description}
        for e in await session.scalars(select(Evenement).order_by(Evenement.id))
    ]


@router.post("/evenements", status_code=201)
async def creer_evenement(data: EvenementIn, session: Session):
    evenement = Evenement(**data.model_dump())
    session.add(evenement)
    await session.commit()
    return {"id": evenement.id, **data.model_dump()}


@router.put("/evenements/{evenement_id}")
async def modifier_evenement(evenement_id: int, data: EvenementIn, session: Session):
    evenement = await session.get(Evenement, evenement_id)
    if not evenement:
        raise HTTPException(404, "Évènement introuvable")
    evenement.nom, evenement.description = data.nom, data.description
    await session.commit()
    return {"id": evenement.id, **data.model_dump()}


# ---------- tarifs


class RegleIn(BaseModel):
    libelle: str = Field(min_length=1, max_length=80)
    prix_centimes: int = Field(ge=0, le=100_000)
    priorite: int = 0
    jours: list[int] | None = None
    type_production: TypeProduction | None = None
    categorie: str | None = None
    evenement_id: int | None = None
    actif: bool = True

    @field_validator("jours")
    @classmethod
    def jours_valides(cls, valeur):
        if valeur is None or not valeur:
            return None
        if any(j < 0 or j > 6 for j in valeur):
            raise ValueError("jours de 0 (lundi) à 6 (dimanche)")
        return sorted(set(valeur))


def regle_json(r: RegleTarifaire) -> dict:
    return {
        "id": r.id,
        "libelle": r.libelle,
        "prix_centimes": r.prix_centimes,
        "priorite": r.priorite,
        "jours": r.jours,
        "type_production": r.type_production,
        "categorie": r.categorie,
        "evenement_id": r.evenement_id,
        "actif": r.actif,
    }


@router.get("/tarifs")
async def regles(session: Session):
    lignes = await session.scalars(select(RegleTarifaire).order_by(RegleTarifaire.priorite.desc(), RegleTarifaire.id))
    return [regle_json(r) for r in lignes]


@router.post("/tarifs", status_code=201)
async def creer_regle(data: RegleIn, session: Session):
    regle = RegleTarifaire(**data.model_dump())
    session.add(regle)
    await session.commit()
    return regle_json(regle)


@router.put("/tarifs/{regle_id}")
async def modifier_regle(regle_id: int, data: RegleIn, session: Session):
    regle = await session.get(RegleTarifaire, regle_id)
    if not regle:
        raise HTTPException(404, "Règle introuvable")
    for champ, valeur in data.model_dump().items():
        setattr(regle, champ, valeur)
    await session.commit()
    return regle_json(regle)


@router.delete("/tarifs/{regle_id}")
async def supprimer_regle(regle_id: int, session: Session):
    await session.execute(delete(RegleTarifaire).where(RegleTarifaire.id == regle_id))
    await session.commit()
    return {"ok": True}


class CategorieIn(BaseModel):
    code: str = Field(pattern=r"^[a-z_]{2,20}$")
    libelle: str = Field(min_length=1, max_length=60)
    ordre: int = 0
    actif: bool = True


@router.get("/categories")
async def categories(session: Session):
    return [
        {"code": c.code, "libelle": c.libelle, "ordre": c.ordre, "actif": c.actif}
        for c in await session.scalars(select(Categorie).order_by(Categorie.ordre))
    ]


@router.put("/categories/{code}")
async def enregistrer_categorie(code: str, data: CategorieIn, session: Session):
    categorie = await session.get(Categorie, code)
    if categorie:
        categorie.libelle, categorie.ordre, categorie.actif = data.libelle, data.ordre, data.actif
    else:
        session.add(Categorie(**data.model_dump()))
    await session.commit()
    return data.model_dump()


# ---------- paramètres


@router.get("/parametres")
async def lire_parametres(session: Session):
    valeurs = await parametres.lire(session)
    return [{"cle": k, "valeur": valeurs[k], "libelle": libelle} for k, (_, libelle) in parametres.DEFAUTS.items()]


@router.put("/parametres")
async def enregistrer_parametres(data: dict[str, int], session: Session):
    for cle, valeur in data.items():
        if cle not in parametres.DEFAUTS:
            raise HTTPException(422, f"Paramètre inconnu : {cle}")
        if valeur < 0 or valeur > 10_000:
            raise HTTPException(422, f"Valeur hors limites pour {cle}")
        if cle == "places_max" and valeur < 1:
            raise HTTPException(422, "Au moins une place par commande")
        existant = await session.get(Parametre, cle)
        if existant:
            existant.valeur = valeur
        else:
            session.add(Parametre(cle=cle, valeur=valeur, libelle=parametres.DEFAUTS[cle][1]))
    await session.commit()
    return await lire_parametres(session)


# ---------- billets et contrôles


@router.get("/commandes")
async def chercher_commande(session: Session, reference: str):
    commande = await session.scalar(select(Commande).where(Commande.reference == reference.strip().upper()))
    if not commande:
        raise HTTPException(404, "Aucune commande avec cette référence")
    return await detail_commande(session, commande.id)


@router.post("/billets/{billet_id}/remboursement")
async def rembourser_billet(billet_id: uuid.UUID, session: Session):
    # le gérant peut rembourser hors délai, mais jamais un billet déjà scanné
    billet = await session.scalar(select(Billet).where(Billet.id == billet_id).with_for_update())
    if not billet:
        raise HTTPException(404, "Billet introuvable")
    await rembourser(session, billet, controler_delai=False)
    return await detail_commande(session, billet.commande_id)


@router.get("/controles")
async def controles(session: Session, limite: int = Query(40, ge=1, le=200)):
    lignes = await session.execute(
        select(Controle, Billet, Siege, Film)
        .outerjoin(Billet, Billet.id == Controle.billet_id)
        .outerjoin(Siege, Siege.id == Billet.siege_id)
        .outerjoin(Seance, Seance.id == Billet.seance_id)
        .outerjoin(Film, Film.id == Seance.film_id)
        .order_by(Controle.id.desc())
        .limit(limite)
    )
    return [
        {
            "id": c.id,
            "moment": c.cree_le.isoformat(),
            "resultat": c.resultat,
            "poste": c.poste,
            "film": f.titre if f else None,
            "place": f"{s.rang}{s.numero}" if s else None,
            "reference_billet": str(b.id)[:8] if b else None,
        }
        for c, b, s, f in lignes
    ]
