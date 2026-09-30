import base64
import json
import os
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

CLE = Ed25519PrivateKey.generate()
os.environ["CLE_PUBLIQUE"] = CLE.public_key().public_bytes(
    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
).decode()
os.environ["JWT_SECRET"] = "secret-de-test-assez-long-pour-hs256"
os.environ["BACK_URL"] = "http://back"

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import main  # noqa: E402


def b64(donnees: bytes) -> str:
    return base64.urlsafe_b64encode(donnees).rstrip(b"=").decode()


def billet(billet_id: str, cle=CLE) -> str:
    contenu = json.dumps({"b": billet_id, "s": 1, "p": "G7", "e": 0}, separators=(",", ":")).encode()
    return f"CIN1.{b64(contenu)}.{b64(cle.sign(contenu))}"


def entete(role: str = "controleur") -> dict:
    jeton = jwt.encode(
        {"sub": role, "role": role, "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "secret-de-test-assez-long-pour-hs256",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {jeton}"}


class FauxBack:
    """Imite les routes internes du back : statut des billets en mémoire."""

    def __init__(self):
        self.statuts: dict[str, str] = {}
        self.en_panne = False

    def __call__(self, requete: httpx.Request) -> httpx.Response:
        if self.en_panne:
            raise httpx.ConnectError("back injoignable")
        if requete.url.path == "/internal/controles":
            return httpx.Response(200, json={"ok": True})
        billet_id = requete.url.path.split("/")[3]
        statut = self.statuts.get(billet_id)
        if statut is None:
            resultat = "inconnu"
        elif statut == "valide":
            self.statuts[billet_id] = "utilise"
            resultat = "accepte"
        else:
            resultat = "deja_utilise" if statut == "utilise" else "rembourse"
        return httpx.Response(200, json={"resultat": resultat, "billet": {"place": "G7"} if statut else None})


@pytest.fixture
def back():
    return FauxBack()


@pytest.fixture
def client(back, monkeypatch):
    monkeypatch.setattr(main, "client", httpx.AsyncClient(transport=httpx.MockTransport(back)))
    main.en_attente.clear()
    main.acceptes_hors_ligne.clear()
    with TestClient(main.app) as c:
        yield c
