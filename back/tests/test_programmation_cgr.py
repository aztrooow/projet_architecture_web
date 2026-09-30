from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.programmation_cgr import empreinte, infos_film, salle_libre, salle_preferee, variante, version

PARIS = ZoneInfo("Europe/Paris")


def test_version_originale_sous_titree():
    assert version(["Localization.Language.French", "Showtime.Accessibility.Accessible"]) == "VF"
    assert version(["Localization.Version.Original", "Showtime.Accessibility.Subtitled"]) == "VOST"


def test_empreinte_stable_et_courte():
    identifiant = "55774-2026-09-30 13:30:00-Localization.Language.French,Auditorium.Experience.Ice"
    assert empreinte(identifiant) == empreinte(identifiant)
    assert len(empreinte(identifiant)) == 40


def test_variante_d_affiche():
    url = "https://all.web.img.acsta.net/img/59/da/affiche.jpg"
    assert variante(url, "c_310_420") == "https://all.web.img.acsta.net/c_310_420/img/59/da/affiche.jpg"


def test_salle_ice_dans_la_plus_grande_salle():
    assert salle_preferee("SALLE ICE", 6) == 0
    assert salle_preferee("Salle 04", 6) == 3
    assert salle_preferee("Salle 09", 6) == 2


def test_une_salle_occupee_n_est_pas_proposee():
    salles = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
    debut = datetime(2026, 10, 3, 20, 0, tzinfo=PARIS)
    occupation = {1: [(debut - timedelta(minutes=30), debut + timedelta(hours=2))]}
    assert salle_libre(salles, occupation, debut, debut + timedelta(hours=2), preferee=0).id == 2
    occupation[2] = [(debut, debut + timedelta(hours=1))]
    assert salle_libre(salles, occupation, debut, debut + timedelta(hours=2), preferee=0) is None


def test_fiche_film_depuis_la_source():
    donnees = {
        "title": "Cars",
        "runtime": 7020,
        "genres": "Animation, Comédie, Action",
        "poster": "https://all.web.img.acsta.net/img/59/da/affiche.jpg",
        "release": "2006-06-14T00:00:00.000Z",
        "directors": {"nodes": [{"person": {"firstName": "John", "lastName": "Lasseter"}}]},
        "locale": {"synopsis": "Flash McQueen découvre Radiator Springs."},
        "images": [{"url": "https://all.web.img.acsta.net/pictures/photo.jpg"}],
    }
    seances = {"2026-09-30": [{"tags": ["Format.Projection.3d"]}, {"tags": ["Format.Projection.3d"]}]}
    infos = infos_film(donnees, seances)
    assert infos["duree_min"] == 117
    assert infos["annee"] == 2006
    assert infos["genre"] == "Animation, Comédie"
    assert infos["realisation"] == "John Lasseter"
    assert infos["type_production"] == "3d"
    assert infos["image_url"].endswith("photo.jpg")
