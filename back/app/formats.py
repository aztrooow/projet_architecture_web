from datetime import datetime
from zoneinfo import ZoneInfo

from .config import settings

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


def heure_locale(moment: datetime) -> datetime:
    return moment.astimezone(ZoneInfo(settings.fuseau))


def date_longue(moment: datetime) -> str:
    """samedi 3 octobre 2026 à 20h30"""
    m = heure_locale(moment)
    return f"{JOURS[m.weekday()]} {m.day} {MOIS[m.month - 1]} {m.year} à {m.hour}h{m.minute:02d}"


def euros(centimes: int) -> str:
    return f"{centimes // 100},{centimes % 100:02d} €"
