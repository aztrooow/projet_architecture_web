from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from ..auth import creer_jeton, hasher
from ..models import Compte
from .commun import Session

router = APIRouter(prefix="/api/auth", tags=["personnel"])

# comparé même quand l'identifiant n'existe pas, pour ne pas le trahir par le temps de réponse
_HASH_FACTICE = hasher.hash("mot-de-passe-factice")


class Identifiants(BaseModel):
    identifiant: str
    mot_de_passe: str


@router.post("/connexion")
async def connexion(data: Identifiants, session: Session):
    compte = await session.scalar(select(Compte).where(Compte.identifiant == data.identifiant.strip().lower()))
    valide = hasher.verify(data.mot_de_passe, compte.mot_de_passe if compte else _HASH_FACTICE)
    if not compte or not valide:
        raise HTTPException(401, "Identifiant ou mot de passe incorrect")
    return {"jeton": creer_jeton(compte.identifiant, compte.role), "role": compte.role, "identifiant": compte.identifiant}
