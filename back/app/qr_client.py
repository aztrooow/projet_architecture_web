"""Appels au service qr-generator (seul détenteur de la clé privée)."""

import httpx
from fastapi import HTTPException

from .config import settings

_client = httpx.AsyncClient(
    base_url=settings.qr_generator_url,
    headers={"X-Service-Token": settings.service_token},
    timeout=10,
)


async def signer(billets: list[dict]) -> list[str]:
    """billets : [{id, seance_id, place}] -> jetons signés, dans le même ordre."""
    try:
        reponse = await _client.post("/internal/signer", json={"billets": billets})
        reponse.raise_for_status()
    except httpx.HTTPError:
        raise HTTPException(503, "Service de génération des billets indisponible, réessayez")
    return reponse.json()["jetons"]


async def pdf(donnees: dict) -> bytes:
    try:
        reponse = await _client.post("/internal/pdf", json=donnees)
        reponse.raise_for_status()
    except httpx.HTTPError:
        raise HTTPException(503, "Service de génération des billets indisponible, réessayez")
    return reponse.content


async def fermer() -> None:
    await _client.aclose()
