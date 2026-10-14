"""Une route JSON par table, avec toutes les lignes et toutes les colonnes."""

import pytest
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Base
from app.routes.donnees import SOURCES

from .conftest import connexion

PUBLIQUES = [s.nom for s in SOURCES if not s.protegee]
PROTEGEES = [s.nom for s in SOURCES if s.protegee]


def test_chaque_table_du_modele_a_sa_route():
    assert sorted(s.modele.__tablename__ for s in SOURCES) == sorted(Base.metadata.tables)


async def test_index_des_tables(client):
    reponse = await client.get("/api/donnees")
    assert reponse.status_code == 200
    tables = {t["nom"]: t for t in reponse.json()}
    assert set(tables) == {s.nom for s in SOURCES}
    assert tables["salles"]["total"] == 6
    assert tables["comptes"]["protegee"] is True


@pytest.mark.parametrize("nom", PUBLIQUES)
async def test_tables_publiques_renvoient_toutes_les_lignes(client, nom):
    source = next(s for s in SOURCES if s.nom == nom)
    reponse = await client.get(f"/api/donnees/{nom}")
    assert reponse.status_code == 200
    donnees = reponse.json()
    async with SessionLocal() as session:
        attendu = await session.scalar(select(func.count()).select_from(source.modele))
    assert donnees["total"] == attendu == len(donnees["lignes"])
    # toutes les colonnes du modèle, dans chaque ligne
    colonnes = [c.key for c in source.modele.__table__.columns]
    assert [c["nom"] for c in donnees["colonnes"]] == colonnes
    assert all(set(ligne) == set(colonnes) for ligne in donnees["lignes"])


@pytest.mark.parametrize("nom", PROTEGEES)
async def test_tables_sensibles_reservees_au_gerant(client, nom):
    assert (await client.get(f"/api/donnees/{nom}")).status_code == 401
    assert (await client.get(f"/api/donnees/{nom}/1")).status_code == 401
    controleur = await connexion(client, "controleur")
    assert (await client.get(f"/api/donnees/{nom}", headers=controleur)).status_code == 403
    gerant = await connexion(client, "gerant")
    assert (await client.get(f"/api/donnees/{nom}", headers=gerant)).status_code == 200


async def test_aucun_secret_dans_les_donnees(client):
    gerant = await connexion(client, "gerant")
    comptes = await client.get("/api/donnees/comptes", headers=gerant)
    assert comptes.json()["total"] == 2
    assert "$argon2" not in comptes.text
    assert {ligne["mot_de_passe"] for ligne in comptes.json()["lignes"]} == {"(masqué)"}
    billets = await client.get("/api/donnees/billets?limite=50", headers=gerant)
    for ligne in billets.json()["lignes"]:
        assert ligne["jeton"] is None or "…" in ligne["jeton"]
        assert ligne["jeton"] is None or len(ligne["jeton"]) < 30


async def test_pagination(client):
    page = (await client.get("/api/donnees/sieges?limite=10&decalage=5")).json()
    tout = (await client.get("/api/donnees/sieges")).json()
    assert page["limite"] == 10 and page["decalage"] == 5
    assert page["total"] == tout["total"] == len(tout["lignes"])
    assert page["lignes"] == tout["lignes"][5:15]


async def test_detail_d_une_ligne(client):
    salle = (await client.get("/api/donnees/salles/1")).json()
    assert salle["id"] == 1 and salle["nom"] == "Salle Lumière"
    # clé primaire textuelle
    assert (await client.get("/api/donnees/categories/etudiant")).json()["libelle"] == "Étudiant"
    assert (await client.get("/api/donnees/salles/9999")).status_code == 404
    assert (await client.get("/api/donnees/salles/pas-un-nombre")).status_code == 404
    gerant = await connexion(client, "gerant")
    assert (await client.get("/api/donnees/billets/pas-un-uuid", headers=gerant)).status_code == 404


async def test_table_inconnue(client):
    assert (await client.get("/api/donnees/voitures")).status_code == 404
