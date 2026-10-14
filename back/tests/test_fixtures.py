"""Le chargement des fixtures est idempotent : le relancer ne crée aucun doublon."""

from sqlalchemy import func, select

from app.config import settings
from app.db import SessionLocal
from app.fixtures import charger_fixtures
from app.models import Categorie, Compte, Parametre, RegleTarifaire, Salle, Siege

from .conftest import connexion

TABLES = (Salle, Siege, Categorie, RegleTarifaire, Parametre, Compte)


async def compter(modele) -> int:
    async with SessionLocal() as session:
        return await session.scalar(select(func.count()).select_from(modele))


async def test_fixtures_rejouables_sans_doublon(client, monkeypatch):
    monkeypatch.setattr(settings, "donnees_demo", True)
    avant = [await compter(m) for m in TABLES]
    assert avant[0] == 6 and avant[5] == 2
    await charger_fixtures()
    await charger_fixtures()
    assert [await compter(m) for m in TABLES] == avant


async def test_mot_de_passe_du_personnel_suit_la_configuration(client, monkeypatch):
    monkeypatch.setattr(settings, "gerant_mot_de_passe", "nouveau-secret")
    await charger_fixtures()
    reponse = await client.post("/api/auth/connexion", json={"identifiant": "gerant", "mot_de_passe": "nouveau-secret"})
    assert reponse.status_code == 200
    monkeypatch.setattr(settings, "gerant_mot_de_passe", "gerant")
    await charger_fixtures()
    assert "Authorization" in await connexion(client, "gerant")
