"""Service de génération : signe les billets et produit QR codes et PDF.

C'est le seul service qui détient la clé privée. Le back lui demande une
signature à l'émission d'un billet ; le navigateur lui demande l'image du QR.
"""

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

from . import rendu, signature


class Settings(BaseSettings):
    service_token: str = "dev-service-token"
    cle_privee_fichier: str = "/data/cle-ed25519.pem"
    cors_origins: str = "http://localhost:8080"


settings = Settings()
etat: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    etat["cle"] = signature.charger_cle(settings.cle_privee_fichier)
    yield


app = FastAPI(
    title="CinetINT, génération des billets",
    lifespan=lifespan,
    docs_url="/qr/docs",
    openapi_url="/qr/openapi.json",
)
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_methods=["GET"],
    )


def service_interne(x_service_token: Annotated[str | None, Header()] = None) -> None:
    if x_service_token != settings.service_token:
        raise HTTPException(403, "Accès réservé aux services")


class BilletASigner(BaseModel):
    id: str
    seance_id: int
    place: str = Field(max_length=8)


class DemandeSignature(BaseModel):
    billets: list[BilletASigner] = Field(min_length=1, max_length=50)


class BilletImprime(BaseModel):
    jeton: str
    place: str
    tarif: str
    prix: str


class DemandePdf(BaseModel):
    reference: str
    film: str
    date: str
    salle: str
    version: str
    evenement: str | None = None
    billets: list[BilletImprime] = Field(min_length=1, max_length=50)


@app.post("/internal/signer", dependencies=[Depends(service_interne)], include_in_schema=False)
def signer(data: DemandeSignature):
    cle = etat["cle"]
    return {"jetons": [signature.signer(cle, b.id, b.seance_id, b.place) for b in data.billets]}


@app.post("/internal/pdf", dependencies=[Depends(service_interne)], include_in_schema=False)
def pdf(data: DemandePdf):
    return Response(rendu.pdf_billets(data.model_dump()), media_type="application/pdf")


@app.get("/qr/cle-publique", response_class=PlainTextResponse)
def cle_publique():
    """Clé publique Ed25519 : de quoi vérifier un billet sans pouvoir en fabriquer."""
    return signature.cle_publique_pem(etat["cle"])


@app.get("/qr/sante")
def sante():
    return {"statut": "ok"}


@app.get("/qr/{jeton}.svg")
def image_qr(jeton: str):
    # on ne dessine que nos propres billets : pas de générateur de QR ouvert à tous
    if not signature.est_authentique(etat["cle"], jeton):
        raise HTTPException(404, "Billet inconnu")
    return Response(
        rendu.qr_svg(jeton),
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400, immutable"},
    )
