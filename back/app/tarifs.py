"""Moteur de tarification.

Aucun prix n'est écrit dans le code : on garde toutes les règles qui
s'appliquent à la place demandée et on retient la plus prioritaire.
Un évènement (ex. « Terminator grandeur nature ») porte une règle de priorité
maximale qui court-circuite la grille habituelle.
"""

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from .config import settings

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


@dataclass
class Contexte:
    jour: int  # 0 = lundi
    type_production: str
    categorie: str
    evenement_id: int | None


def contexte_seance(debut: datetime, type_production: str, evenement_id: int | None, categorie: str) -> Contexte:
    # le jour s'apprécie à l'heure de Paris, pas en UTC
    jour = debut.astimezone(ZoneInfo(settings.fuseau)).weekday()
    return Contexte(jour, type_production, categorie, evenement_id)


def s_applique(regle, ctx: Contexte) -> bool:
    if not regle.actif:
        return False
    if regle.jours and ctx.jour not in regle.jours:
        return False
    if regle.type_production and regle.type_production != ctx.type_production:
        return False
    if regle.categorie and regle.categorie != ctx.categorie:
        return False
    if regle.evenement_id is not None and regle.evenement_id != ctx.evenement_id:
        return False
    return True


def precision(regle) -> int:
    """Nombre de critères renseignés : à priorité égale, la règle la plus précise gagne."""
    return sum(
        1
        for critere in (regle.jours, regle.type_production, regle.categorie, regle.evenement_id)
        if critere not in (None, [])
    )


def choisir(regles, ctx: Contexte):
    candidates = [r for r in regles if s_applique(r, ctx)]
    if not candidates:
        return None
    return max(candidates, key=lambda r: (r.priorite, precision(r), -r.prix_centimes))
