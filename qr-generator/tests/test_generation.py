import base64
import json

from cryptography.hazmat.primitives import serialization

from app import signature

from .conftest import SERVICE


def b64d(texte):
    return base64.urlsafe_b64decode(texte + "=" * (-len(texte) % 4))


def signer(client, place="F12"):
    reponse = client.post(
        "/internal/signer",
        json={"billets": [{"id": "5f2c6d1e-0000-4000-8000-000000000001", "seance_id": 42, "place": place}]},
        headers=SERVICE,
    )
    assert reponse.status_code == 200
    return reponse.json()["jetons"][0]


def test_le_jeton_se_verifie_avec_la_seule_cle_publique(client):
    jeton = signer(client)
    prefixe, contenu, sig = jeton.split(".")
    assert prefixe == "CIN1"
    cle = serialization.load_pem_public_key(client.get("/qr/cle-publique").text.encode())
    cle.verify(b64d(sig), b64d(contenu))
    assert json.loads(b64d(contenu)) | {"e": 0} == {"b": "5f2c6d1e-0000-4000-8000-000000000001", "s": 42, "p": "F12", "e": 0}


def test_un_jeton_modifie_n_est_plus_authentique(client):
    prefixe, contenu, sig = signer(client).split(".")
    donnees = json.loads(b64d(contenu))
    donnees["p"] = "A1"
    falsifie = f"{prefixe}.{signature.b64(json.dumps(donnees, separators=(',', ':')).encode())}.{sig}"
    assert client.get(f"/qr/{falsifie}.svg").status_code == 404


def test_image_du_qr(client):
    reponse = client.get(f"/qr/{signer(client)}.svg")
    assert reponse.status_code == 200
    assert reponse.headers["content-type"].startswith("image/svg+xml")
    assert b"<svg" in reponse.content


def test_pdf_des_billets(client):
    reponse = client.post(
        "/internal/pdf",
        json={
            "reference": "CIN-TEST42",
            "film": "Le Fabuleux Destin d'Amélie Poulain",
            "date": "samedi 10 octobre 2026 à 20h30",
            "salle": "Salle Varda",
            "version": "VF",
            "evenement": None,
            "billets": [
                {"jeton": signer(client, "F12"), "place": "F12", "tarif": "Plein tarif week-end", "prix": "12,50 €"},
                {"jeton": signer(client, "F13"), "place": "F13", "tarif": "Tarif étudiant", "prix": "7,90 €"},
            ],
        },
        headers=SERVICE,
    )
    assert reponse.status_code == 200
    assert reponse.content.startswith(b"%PDF")


def test_routes_internes_reservees_aux_services(client):
    assert client.post("/internal/signer", json={"billets": []}).status_code == 403
    assert client.post("/internal/pdf", json={}).status_code == 403


def test_la_cle_est_conservee_entre_deux_demarrages(tmp_path):
    chemin = str(tmp_path / "cle.pem")
    premiere = signature.cle_publique_pem(signature.charger_cle(chemin))
    seconde = signature.cle_publique_pem(signature.charger_cle(chemin))
    assert premiere == seconde
