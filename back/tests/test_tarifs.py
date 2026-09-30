from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.tarifs import choisir, contexte_seance

PARIS = ZoneInfo("Europe/Paris")
MARDI = datetime(2026, 10, 6, 20, 0, tzinfo=PARIS)
SAMEDI = datetime(2026, 10, 10, 20, 0, tzinfo=PARIS)


def regle(libelle, prix, priorite, jours=None, type_production=None, categorie=None, evenement_id=None):
    return SimpleNamespace(
        libelle=libelle,
        prix_centimes=prix,
        priorite=priorite,
        jours=jours,
        type_production=type_production,
        categorie=categorie,
        evenement_id=evenement_id,
        actif=True,
    )


GRILLE = [
    regle("Plein tarif semaine", 1050, 10, jours=[0, 1, 2, 3]),
    regle("Plein tarif week-end", 1250, 10, jours=[4, 5, 6]),
    regle("Film en 3D", 1450, 20, type_production="3d"),
    regle("Tarif étudiant", 790, 30, categorie="etudiant"),
    regle("Étudiant, film en 3D", 1090, 40, categorie="etudiant", type_production="3d"),
    regle("Terminator grandeur nature", 2500, 100, evenement_id=1),
]


def prix(debut, type_production="standard", categorie="plein", evenement_id=None):
    return choisir(GRILLE, contexte_seance(debut, type_production, evenement_id, categorie)).prix_centimes


def test_prix_selon_le_jour():
    assert prix(MARDI) == 1050
    assert prix(SAMEDI) == 1250


def test_jour_calcule_a_l_heure_de_paris():
    # samedi 00h30 à Paris = vendredi 22h30 en UTC : c'est bien le tarif du samedi
    debut = datetime(2026, 10, 10, 0, 30, tzinfo=PARIS)
    assert choisir(GRILLE, contexte_seance(debut, "standard", None, "plein")).libelle == "Plein tarif week-end"


def test_type_de_production_et_categorie():
    assert prix(MARDI, type_production="3d") == 1450
    assert prix(SAMEDI, categorie="etudiant") == 790
    assert prix(SAMEDI, type_production="3d", categorie="etudiant") == 1090


def test_evenement_court_circuite_la_grille():
    for categorie in ("plein", "etudiant"):
        assert prix(SAMEDI, categorie=categorie, evenement_id=1) == 2500
    # la règle de l'évènement ne s'applique pas aux autres séances
    assert prix(SAMEDI, evenement_id=None) == 1250


def test_a_priorite_egale_la_regle_la_plus_precise_gagne():
    grille = [regle("Générale", 900, 10), regle("Mardi", 800, 10, jours=[1])]
    assert choisir(grille, contexte_seance(MARDI, "standard", None, "plein")).libelle == "Mardi"


def test_regle_inactive_ignoree_et_absence_de_tarif():
    inactive = regle("Inactive", 100, 999)
    inactive.actif = False
    assert choisir([inactive], contexte_seance(MARDI, "standard", None, "plein")) is None
