"""Le front est testé seul : l'API du back est simulée par un transport httpx."""

import httpx
import pytest

from server import main

GRILLE = [
    {"libelle": "Plein tarif semaine", "prix_centimes": 1050, "jours": [0, 1, 2, 3], "type_production": None,
     "categorie": None, "evenement": None},
    {"libelle": "Tarif étudiant", "prix_centimes": 790, "jours": None, "type_production": None,
     "categorie": "etudiant", "evenement": None},
    {"libelle": "Terminator grandeur nature, tarif unique", "prix_centimes": 2500, "jours": None,
     "type_production": None, "categorie": None, "evenement": "Terminator grandeur nature"},
]


def faux_back(disponible: bool):
    def reponse(requete: httpx.Request) -> httpx.Response:
        if not disponible:
            raise httpx.ConnectError("back arrêté", request=requete)
        if requete.url.path == "/api/tarifs":
            return httpx.Response(200, json=GRILLE)
        return httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(reponse), base_url="http://back:8000")


@pytest.fixture
def back_disponible(monkeypatch):
    monkeypatch.setattr(main, "client", faux_back(True))
    main._cache.clear()


@pytest.fixture
def back_arrete(monkeypatch):
    monkeypatch.setattr(main, "client", faux_back(False))
    main._cache.clear()


@pytest.fixture
async def navigateur():
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
