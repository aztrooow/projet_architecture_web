"""Routes appelées uniquement par les autres services (jamais exposées au public)."""

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select, update

from .. import formats
from ..auth import service_interne
from ..models import Billet, Controle, Film, Salle, Seance, Siege
from .commun import Session

router = APIRouter(prefix="/internal", dependencies=[Depends(service_interne)], include_in_schema=False)


class Passage(BaseModel):
    poste: str = ""


class Journal(BaseModel):
    resultat: str
    poste: str = ""


async def infos_billet(session, billet: Billet) -> dict:
    seance, film, salle, siege = (
        await session.execute(
            select(Seance, Film, Salle, Siege)
            .join(Film, Film.id == Seance.film_id)
            .join(Salle, Salle.id == Seance.salle_id)
            .join(Siege, Siege.id == billet.siege_id)
            .where(Seance.id == billet.seance_id)
        )
    ).one()
    return {
        "id": str(billet.id),
        "film": film.titre,
        "seance": formats.date_longue(seance.debut),
        "debut": seance.debut.isoformat(),
        "salle": salle.nom,
        "place": f"{siege.rang}{siege.numero}",
        "tarif": billet.libelle_tarif,
        "statut": billet.statut,
        "utilise_le": billet.utilise_le.isoformat() if billet.utilise_le else None,
    }


@router.post("/billets/{billet_id}/utiliser")
async def utiliser(billet_id: uuid.UUID, data: Passage, session: Session):
    """Passage atomique valide -> utilise. Une seconde présentation du même billet est refusée."""
    passe = (
        await session.execute(
            update(Billet)
            .where(Billet.id == billet_id, Billet.statut == "valide")
            .values(statut="utilise", utilise_le=func.now())
            .returning(Billet.id)
        )
    ).first() is not None
    billet = await session.get(Billet, billet_id, populate_existing=True)
    if passe:
        resultat = "accepte"
    elif billet is None:
        resultat = "inconnu"
    elif billet.statut == "utilise":
        resultat = "deja_utilise"
    else:
        resultat = "rembourse"
    session.add(Controle(billet_id=billet.id if billet else None, resultat=resultat, poste=data.poste))
    await session.commit()
    return {"resultat": resultat, "billet": await infos_billet(session, billet) if billet else None}


@router.post("/controles")
async def journaliser(data: Journal, session: Session):
    session.add(Controle(resultat=data.resultat, poste=data.poste))
    await session.commit()
    return {"ok": True}
