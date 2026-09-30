import asyncio
import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.db import SessionLocal
from app.models import Billet, Commande

from .conftest import connexion, nouvelle_seance

INTERNE = {"X-Service-Token": settings.service_token}


async def sieges_libres(client, seance_id, n):
    plan = (await client.get(f"/api/seances/{seance_id}/plan")).json()
    return [s["id"] for s in plan["sieges"] if s["etat"] == "libre"][:n]


async def acheter(client, seance_id, sieges, categorie="plein"):
    reponse = await client.post(
        "/api/commandes",
        json={"seance_id": seance_id, "places": [{"siege_id": s, "categorie": categorie} for s in sieges]},
    )
    assert reponse.status_code == 201, reponse.text
    commande = reponse.json()
    paiement = await client.post(f"/api/paiement-simule/{commande['psp_session']}", json={"resultat": "accepte"})
    assert paiement.json()["statut"] == "payee"
    return (await client.get(f"/api/commandes/{commande['id']}")).json()


async def test_achat_complet(client, seance):
    sieges = await sieges_libres(client, seance, 2)
    commande = await acheter(client, seance, sieges)
    assert commande["statut"] == "payee"
    assert len(commande["billets"]) == 2
    assert all(b["jeton"].startswith("CIN1.") for b in commande["billets"])

    plan = (await client.get(f"/api/seances/{seance}/plan")).json()
    etats = {s["id"]: s["etat"] for s in plan["sieges"]}
    assert all(etats[s] == "vendu" for s in sieges)

    pdf = await client.get(f"/api/commandes/{commande['id']}/billets.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


async def test_un_seul_gagnant_quand_tout_le_monde_veut_le_meme_siege(client, seance):
    [siege] = await sieges_libres(client, seance, 1)
    reponses = await asyncio.gather(
        *(
            client.post("/api/commandes", json={"seance_id": seance, "places": [{"siege_id": siege, "categorie": "plein"}]})
            for _ in range(25)
        )
    )
    codes = sorted(r.status_code for r in reponses)
    assert codes.count(201) == 1
    assert codes.count(409) == 24


async def test_la_base_refuse_deux_billets_valides_sur_la_meme_place(client, seance):
    [siege] = await sieges_libres(client, seance, 1)
    commande = await acheter(client, seance, [siege])
    async with SessionLocal() as session:
        session.add(
            Billet(
                commande_id=uuid.UUID(commande["id"]),
                seance_id=seance,
                siege_id=siege,
                categorie="plein",
                libelle_tarif="doublon",
                prix_centimes=0,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_verrou_libere_si_la_commande_est_annulee(client, seance):
    sieges = await sieges_libres(client, seance, 2)
    reponse = await client.post(
        "/api/commandes", json={"seance_id": seance, "places": [{"siege_id": s, "categorie": "plein"} for s in sieges]}
    )
    commande = reponse.json()
    await client.delete(f"/api/commandes/{commande['id']}")
    etats = {s["id"]: s["etat"] for s in (await client.get(f"/api/seances/{seance}/plan")).json()["sieges"]}
    assert all(etats[s] == "libre" for s in sieges)


async def test_paiement_refuse_apres_expiration(client, seance):
    [siege] = await sieges_libres(client, seance, 1)
    commande = (
        await client.post("/api/commandes", json={"seance_id": seance, "places": [{"siege_id": siege, "categorie": "plein"}]})
    ).json()
    async with SessionLocal() as session:
        c = await session.get(Commande, uuid.UUID(commande["id"]))
        c.expire_le = c.cree_le
        await session.commit()
    reponse = await client.post(f"/api/paiement-simule/{commande['psp_session']}", json={"resultat": "accepte"})
    assert reponse.status_code == 409


async def test_nombre_de_places_limite(client, seance):
    sieges = await sieges_libres(client, seance, 11)
    reponse = await client.post(
        "/api/commandes", json={"seance_id": seance, "places": [{"siege_id": s, "categorie": "plein"} for s in sieges]}
    )
    assert reponse.status_code == 422


async def test_controle_une_seule_entree_puis_remboursement_impossible(client, seance):
    sieges = await sieges_libres(client, seance, 2)
    commande = await acheter(client, seance, sieges)
    scanne, autre = commande["billets"]

    premier = await client.post(f"/internal/billets/{scanne['id']}/utiliser", json={"poste": "test"}, headers=INTERNE)
    second = await client.post(f"/internal/billets/{scanne['id']}/utiliser", json={"poste": "test"}, headers=INTERNE)
    assert premier.json()["resultat"] == "accepte"
    assert second.json()["resultat"] == "deja_utilise"

    refus = await client.post(f"/api/billets/{scanne['id']}/remboursement", json={"commande_id": commande["id"]})
    assert refus.status_code == 409

    ok = await client.post(f"/api/billets/{autre['id']}/remboursement", json={"commande_id": commande["id"]})
    assert ok.status_code == 200
    rembourse = await client.post(f"/internal/billets/{autre['id']}/utiliser", json={"poste": "test"}, headers=INTERNE)
    assert rembourse.json()["resultat"] == "rembourse"


async def test_routes_internes_fermees_sans_jeton_de_service(client, seance):
    reponse = await client.post(f"/internal/billets/{uuid.uuid4()}/utiliser", json={})
    assert reponse.status_code == 403


async def test_evenement_au_tarif_unique(client):
    seance = await nouvelle_seance(jours=3, evenement_id=1)
    tarifs = (await client.get(f"/api/seances/{seance}")).json()["tarifs"]
    assert {t["prix_centimes"] for t in tarifs} == {2500}


async def test_remplissage_suit_les_ventes(client, seance):
    gerant = await connexion(client, "gerant")
    avant = {l["seance_id"]: l["vendus"] for l in (await client.get("/api/admin/remplissage?jours=7", headers=gerant)).json()}
    await acheter(client, seance, await sieges_libres(client, seance, 3))
    apres = {l["seance_id"]: l["vendus"] for l in (await client.get("/api/admin/remplissage?jours=7", headers=gerant)).json()}
    assert apres[seance] == avant.get(seance, 0) + 3


async def test_back_office_reserve_au_gerant(client):
    controleur = await connexion(client, "controleur")
    assert (await client.get("/api/admin/resume", headers=controleur)).status_code == 403
    assert (await client.get("/api/admin/resume")).status_code == 401
