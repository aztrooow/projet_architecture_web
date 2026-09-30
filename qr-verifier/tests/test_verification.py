from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .conftest import billet, entete


def scanner(client, jeton, role="controleur"):
    return client.post("/verification", json={"jeton": jeton, "poste": "Salle Varda"}, headers=entete(role))


def test_billet_valide_accepte_une_seule_fois(client, back):
    back.statuts["b1"] = "valide"
    premier = scanner(client, billet("b1")).json()
    second = scanner(client, billet("b1")).json()
    assert premier["verdict"] == "accepte"
    assert second["verdict"] == "refuse" and second["code"] == "deja_utilise"


def test_billet_rembourse_refuse(client, back):
    back.statuts["b2"] = "rembourse"
    assert scanner(client, billet("b2")).json()["code"] == "rembourse"


def test_faux_billet_signe_avec_une_autre_cle(client, back):
    back.statuts["b3"] = "valide"
    faux = billet("b3", cle=Ed25519PrivateKey.generate())
    reponse = scanner(client, faux).json()
    assert reponse["verdict"] == "refuse" and reponse["code"] == "signature_invalide"
    # le back n'a même pas été sollicité pour changer le statut
    assert back.statuts["b3"] == "valide"


def test_code_illisible(client):
    assert scanner(client, "n'importe quoi").json()["code"] == "signature_invalide"


def test_reserve_au_personnel(client):
    assert client.post("/verification", json={"jeton": billet("x")}).status_code == 401
    assert scanner(client, billet("x"), role="spectateur").status_code == 403
    assert scanner(client, billet("x"), role="gerant").status_code == 200


def test_mode_degrade_quand_la_billetterie_ne_repond_plus(client, back):
    back.en_panne = True
    premier = scanner(client, billet("b4")).json()
    second = scanner(client, billet("b4")).json()
    assert premier["verdict"] == "accepte" and premier["code"] == "hors_ligne"
    assert second["verdict"] == "refuse"
    assert client.get("/verification/sante").json()["passages_a_rejouer"] == 1
