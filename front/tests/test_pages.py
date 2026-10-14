"""Pages rendues par le front : infos pratiques, application React, sonde."""

from .conftest import GRILLE


async def test_infos_pratiques(navigateur, back_disponible):
    reponse = await navigateur.get("/infos")
    assert reponse.status_code == 200
    page = reponse.text
    assert "Infos pratiques" in page
    # accès et horaires
    assert "Place de l'Agora" in page
    assert "RER D" in page
    assert "première séance à 10h45" in page
    assert "22h30" in page


async def test_infos_affiche_la_grille_lue_dans_l_api(navigateur, back_disponible):
    page = (await navigateur.get("/infos")).text
    for regle in GRILLE:
        assert regle["libelle"] in page
    assert "10,50 €" in page
    assert "7,90 €" in page
    assert "25,00 €" in page
    # critères traduits en français
    assert "du lundi au jeudi" in page
    assert "tarif--evenement" in page


async def test_infos_reste_lisible_quand_le_back_est_arrete(navigateur, back_arrete):
    reponse = await navigateur.get("/infos")
    assert reponse.status_code == 200
    assert "momentanément indisponible" in reponse.text
    assert "Place de l'Agora" in reponse.text


async def test_infos_liee_depuis_le_menu(navigateur, back_disponible):
    page = (await navigateur.get("/infos")).text
    assert page.count('href="/infos"') >= 2  # menu et pied de page


async def test_application_react_servie_sous_admin(navigateur):
    for chemin in ("/admin", "/admin/donnees", "/admin/donnees/salles", "/admin/donnees/billets/1"):
        reponse = await navigateur.get(chemin)
        assert reponse.status_code == 200, chemin
        assert 'id="app"' in reponse.text
        assert "Espace gérant" in reponse.text


async def test_sonde(navigateur):
    reponse = await navigateur.get("/sante")
    assert reponse.status_code == 200
    assert reponse.json()["statut"] == "ok"


async def test_page_inconnue(navigateur):
    reponse = await navigateur.get("/cette-page-n-existe-pas")
    assert reponse.status_code == 404
