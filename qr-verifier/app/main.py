"""Service de vérification des billets au contrôle d'entrée.

Il ne détient que la clé publique : il peut dire si un billet vient bien de
nous, jamais en fabriquer un. Le contrôle se fait en deux temps :
  1. la signature, vérifiée ici sans appel réseau ;
  2. l'usage unique, demandé au back (passage atomique valide -> utilisé).
Si le back ne répond plus, on accepte sur la seule signature (mode dégradé
prévu par la spec) et on rejoue le passage dès que le back revient.
"""

import asyncio
import base64
import contextlib
import json
import logging
from collections import deque
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
import jwt
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

log = logging.getLogger("qr-verifier")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


class Settings(BaseSettings):
    back_url: str = "http://back:8000"
    qr_generator_url: str = "http://qr-generator:8001"
    # PEM de la clé publique ; vide = on la demande au service de génération
    cle_publique: str = ""
    service_token: str = "dev-service-token"
    jwt_secret: str = "dev-jwt-secret-a-changer-en-production"
    cors_origins: str = "http://localhost:8080"


settings = Settings()
etat: dict = {"cle": None}
# passages acceptés pendant une panne du back, à rejouer
en_attente: deque = deque(maxlen=5000)
acceptes_hors_ligne: set[str] = set()

client = httpx.AsyncClient(timeout=3, headers={"X-Service-Token": settings.service_token})


async def cle_publique():
    if etat["cle"] is None:
        pem = settings.cle_publique
        if not pem:
            reponse = await client.get(f"{settings.qr_generator_url}/qr/cle-publique")
            reponse.raise_for_status()
            pem = reponse.text
        etat["cle"] = serialization.load_pem_public_key(pem.encode())
    return etat["cle"]


def _b64(texte: str) -> bytes:
    return base64.urlsafe_b64decode(texte + "=" * (-len(texte) % 4))


def lire_jeton(cle, jeton: str) -> dict | None:
    """Contenu du billet si la signature est bonne, None sinon."""
    try:
        prefixe, contenu, signature = jeton.strip().split(".")
        if prefixe != "CIN1":
            return None
        donnees = _b64(contenu)
        cle.verify(_b64(signature), donnees)
        return json.loads(donnees)
    except (ValueError, InvalidSignature):
        return None


async def rejouer_passages() -> None:
    while True:
        await asyncio.sleep(10)
        while en_attente:
            billet_id, poste = en_attente[0]
            try:
                reponse = await client.post(
                    f"{settings.back_url}/internal/billets/{billet_id}/utiliser", json={"poste": poste}
                )
            except httpx.TransportError:
                break
            if reponse.status_code >= 500:
                break
            en_attente.popleft()
            acceptes_hors_ligne.discard(billet_id)
            if reponse.status_code >= 400 or reponse.json()["resultat"] != "accepte":
                log.warning("double entrée détectée après coup pour le billet %s", billet_id)


@asynccontextmanager
async def lifespan(app: FastAPI):
    with contextlib.suppress(Exception):
        await cle_publique()
    tache = asyncio.create_task(rejouer_passages())
    yield
    tache.cancel()
    await client.aclose()


app = FastAPI(
    title="CinetINT, vérification des billets",
    lifespan=lifespan,
    docs_url="/verification/docs",
    openapi_url="/verification/openapi.json",
)
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_methods=["POST", "GET"],
        allow_headers=["Authorization", "Content-Type"],
    )

bearer = HTTPBearer(auto_error=False)


def controleur(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> dict:
    if not credentials:
        raise HTTPException(401, "Connexion requise")
    try:
        utilisateur = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Session expirée, reconnectez-vous")
    if utilisateur.get("role") not in ("controleur", "gerant"):
        raise HTTPException(403, "Réservé au personnel de contrôle")
    return utilisateur


class Scan(BaseModel):
    jeton: str = Field(max_length=600)
    poste: str = Field("", max_length=40)


MOTIFS = {
    "accepte": "Bonne séance",
    "deja_utilise": "Billet déjà utilisé",
    "rembourse": "Billet remboursé",
    "inconnu": "Billet inconnu",
}


@app.post("/verification")
async def verifier(scan: Scan, utilisateur: Annotated[dict, Depends(controleur)]):
    try:
        cle = await cle_publique()
    except httpx.HTTPError:
        raise HTTPException(503, "Clé de vérification indisponible")
    poste = scan.poste or utilisateur["sub"]

    contenu = lire_jeton(cle, scan.jeton)
    if contenu is None:
        with contextlib.suppress(httpx.HTTPError):
            await client.post(
                f"{settings.back_url}/internal/controles", json={"resultat": "signature_invalide", "poste": poste}
            )
        return {"verdict": "refuse", "code": "signature_invalide", "motif": "Faux billet ou code illisible"}

    billet_id = contenu["b"]
    try:
        reponse = await client.post(
            f"{settings.back_url}/internal/billets/{billet_id}/utiliser", json={"poste": poste}
        )
    except httpx.TransportError:
        reponse = None
    if reponse is None or reponse.status_code >= 500:
        # billetterie injoignable : on se fie à la signature, en refusant quand même
        # un billet déjà accepté par ce poste pendant la panne
        if billet_id in acceptes_hors_ligne:
            return {"verdict": "refuse", "code": "deja_utilise", "motif": "Billet déjà présenté (mode dégradé)"}
        acceptes_hors_ligne.add(billet_id)
        en_attente.append((billet_id, poste))
        return {
            "verdict": "accepte",
            "code": "hors_ligne",
            "motif": "Signature valide, statut vérifié plus tard",
            "billet": {"place": contenu["p"], "seance_id": contenu["s"]},
        }
    if reponse.status_code >= 400:
        return {"verdict": "refuse", "code": "inconnu", "motif": MOTIFS["inconnu"]}

    resultat = reponse.json()
    return {
        "verdict": "accepte" if resultat["resultat"] == "accepte" else "refuse",
        "code": resultat["resultat"],
        "motif": MOTIFS.get(resultat["resultat"], "Billet refusé"),
        "billet": resultat["billet"],
    }


@app.get("/verification/sante")
async def sante():
    return {"statut": "ok", "cle_chargee": etat["cle"] is not None, "passages_a_rejouer": len(en_attente)}
