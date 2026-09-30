from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash

from .config import settings

hasher = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)


def creer_jeton(identifiant: str, role: str) -> str:
    expiration = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_duree_heures)
    return jwt.encode({"sub": identifiant, "role": role, "exp": expiration}, settings.jwt_secret, algorithm="HS256")


def lire_jeton(jeton: str) -> dict:
    try:
        return jwt.decode(jeton, settings.jwt_secret, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expirée, reconnectez-vous")


async def personnel(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    jeton: Annotated[str | None, Query(include_in_schema=False)] = None,
) -> dict:
    # EventSource ne sait pas envoyer d'en-tête : le flux SSE passe le jeton en paramètre
    valeur = credentials.credentials if credentials else jeton
    if not valeur:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Connexion requise")
    return lire_jeton(valeur)


async def gerant(utilisateur: Annotated[dict, Depends(personnel)]) -> dict:
    if utilisateur.get("role") != "gerant":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé au gérant")
    return utilisateur


async def service_interne(x_service_token: Annotated[str | None, Header()] = None) -> None:
    if x_service_token != settings.service_token:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Accès réservé aux services")
