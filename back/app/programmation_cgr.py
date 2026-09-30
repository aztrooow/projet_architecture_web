"""Programmation réelle, importée du CGR Évry 2.

Le site du CGR s'appuie sur une API publique (sans compte) qui donne les films
à l'affiche, leurs affiches et les séances de la semaine. On la relit toutes
les heures : les nouvelles séances sont ajoutées, celles déjà importées ne
bougent plus (des billets ont pu être vendus). Le CGR a dix salles et nous six :
chaque séance va dans la première de nos salles libre à cet horaire, sinon elle
est laissée de côté.
"""

import colorsys
import hashlib
import io
import json
import logging
import math
import re
from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .models import Film, Salle, Seance

log = logging.getLogger(__name__)
PARIS = ZoneInfo(settings.fuseau)
MENAGE = timedelta(minutes=20)
ENTETES = {"User-Agent": "CinetINT/1.0 (projet etudiant, Telecom SudParis)"}


def version(tags: list[str]) -> str:
    return "VOST" if "Localization.Version.Original" in tags else "VF"


def empreinte(identifiant: str) -> str:
    """Les identifiants de séance du CGR sont très longs : on en garde l'empreinte."""
    return hashlib.sha1(identifiant.encode()).hexdigest()


def variante(url: str, taille: str) -> str:
    """Le CDN des affiches redimensionne à la volée : .../c_215_290/img/..."""
    return re.sub(r"(acsta\.net/)", rf"\g<1>{taille}/", url, count=1)


def teinte(image: bytes) -> str | None:
    """Couleur dominante et saturée de l'affiche, assombrie pour rester lisible sous du texte clair."""
    im = Image.open(io.BytesIO(image)).convert("RGB")
    im.thumbnail((80, 80))
    reduite = im.quantize(colors=6)
    palette = reduite.getpalette()
    choix, meilleur = None, -1.0
    for nombre, index in reduite.getcolors():
        r, g, b = palette[index * 3 : index * 3 + 3]
        h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        if l < 0.1 or l > 0.9:
            continue
        score = s * nombre**0.5
        if score > meilleur:
            choix, meilleur = (h, l, s), score
    if not choix:
        return None
    h, l, s = choix
    r, g, b = colorsys.hls_to_rgb(h, min(l, 0.36), min(s, 0.7))
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


def infos_film(donnees: dict, seances: dict) -> dict:
    local = donnees.get("locale") or {}
    realisateurs = [
        f"{(p['person'].get('firstName') or '').strip()} {(p['person'].get('lastName') or '').strip()}".strip()
        for p in (donnees.get("directors") or {}).get("nodes", [])
    ]
    sortie = donnees.get("release")
    if isinstance(sortie, dict):
        sortie = sortie.get("releaseDate")
    genres = [g.strip() for g in (donnees.get("genres") or "").split(",") if g.strip()]
    toutes = [s for jour in seances.values() for s in jour]
    en_3d = sum(1 for s in toutes if "Format.Projection.3d" in s["tags"])
    images = [i["url"] for i in donnees.get("images") or [] if i.get("url")]
    return {
        "titre": donnees["title"],
        "realisation": ", ".join(r for r in realisateurs if r),
        "annee": int(sortie[:4]) if isinstance(sortie, str) and sortie[:4].isdigit() else None,
        "duree_min": max(1, (donnees.get("runtime") or 0) // 60) if donnees.get("runtime") else 100,
        "genre": ", ".join(genres[:2]),
        "synopsis": local.get("synopsis") or donnees.get("synopsis") or "",
        # un film surtout projeté en 3D suit la grille 3D
        "type_production": "3d" if toutes and en_3d * 2 > len(toutes) else "standard",
        "affiche_url": donnees.get("poster") or (local.get("poster") or {}).get("url"),
        "image_url": images[0] if images else None,
    }


def salle_preferee(ecran: str, nb_salles: int) -> int:
    """Même écran chez le CGR, même salle chez nous, d'une semaine à l'autre."""
    if "ICE" in ecran.upper():
        return 0
    chiffres = "".join(c for c in ecran if c.isdigit())
    return (int(chiffres) - 1) % nb_salles if chiffres else 0


def salle_libre(salles, occupation, debut, fin, preferee: int):
    ordre = salles[preferee:] + salles[:preferee]
    for salle in ordre:
        if all(fin <= a or debut >= b for a, b in occupation.get(salle.id, [])):
            return salle
    return None


async def occupation_actuelle(session: AsyncSession, debut: datetime, fin: datetime) -> dict[int, list]:
    occupation: dict[int, list] = {}
    lignes = await session.execute(
        select(Seance.salle_id, Seance.debut, Film.duree_min)
        .join(Film, Film.id == Seance.film_id)
        .where(Seance.debut >= debut - timedelta(hours=4), Seance.debut < fin)
    )
    for salle_id, d, duree in lignes:
        occupation.setdefault(salle_id, []).append((d, d + timedelta(minutes=duree) + MENAGE))
    return occupation


async def importer(session: AsyncSession, jours: int = 8) -> dict[Seance, float]:
    """Ajoute films et séances ; renvoie les nouvelles séances avec leur taux de remplissage chez le CGR."""
    maintenant = datetime.now(PARIS)
    debut = maintenant.replace(hour=3, minute=0, second=0, microsecond=0)
    fin = debut + timedelta(days=jours)
    cinema = settings.programme_cinema
    async with httpx.AsyncClient(base_url=settings.programme_api, timeout=20, headers=ENTETES) as client:
        reponse = await client.get(
            "/schedule",
            params={
                "from": debut.strftime("%Y-%m-%dT%H:%M:%S"),
                "to": fin.strftime("%Y-%m-%dT%H:%M:%S"),
                # l'API refuse un JSON avec espaces
                "theaters": json.dumps({"id": cinema, "timeZone": settings.fuseau}, separators=(",", ":")),
            },
        )
        reponse.raise_for_status()
        planning = reponse.json()[cinema]["schedule"]
        ids = list(planning)
        details = []
        for i in range(0, len(ids), 20):
            parametres = [("basic", "false"), ("castingLimit", "3")] + [("ids", x) for x in ids[i : i + 20]]
            reponse = await client.get("/movies", params=parametres)
            reponse.raise_for_status()
            details += reponse.json()

        existants = {f.source_id: f for f in await session.scalars(select(Film).where(Film.source_id.is_not(None)))}
        films: dict[str, Film] = {}
        for donnees in details:
            infos = infos_film(donnees, planning.get(donnees["id"], {}))
            film = existants.get(donnees["id"])
            if film is None:
                film = Film(source_id=donnees["id"], **infos)
                if film.affiche_url:
                    try:
                        affiche = await client.get(variante(film.affiche_url, "c_215_290"))
                        film.couleur = teinte(affiche.content) or film.couleur
                    except Exception:
                        log.warning("teinte non calculée pour %s", film.titre)
                session.add(film)
            else:
                # les champs éditoriaux suivent la source, la teinte et le type restent ceux du gérant
                for champ in ("titre", "synopsis", "affiche_url", "image_url", "duree_min", "realisation", "genre"):
                    setattr(film, champ, infos[champ])
                film.actif = True
            films[donnees["id"]] = film
        await session.flush()

    salles = list(await session.scalars(select(Salle).order_by(Salle.capacite.desc(), Salle.id)))
    occupation = await occupation_actuelle(session, debut, fin)
    deja = set(await session.scalars(select(Seance.source_id).where(Seance.source_id.is_not(None))))
    candidates = []
    for film_id, parjour in planning.items():
        film = films.get(film_id)
        if not film:
            continue
        for liste in parjour.values():
            for s in liste:
                moment = datetime.fromisoformat(s["startsAt"]).replace(tzinfo=PARIS)
                if empreinte(s["id"]) in deja or s.get("isExpired") or moment <= maintenant:
                    continue
                candidates.append((moment, film, s))

    # quota par film et par jour, au prorata de nos salles : sinon les premiers
    # horaires de la journée prennent toute la place et un film ne passe qu'une fois
    ecrans = {(s.get("screen") or {}).get("name") for _, _, s in candidates} or {None}
    part = len(salles) / max(len(ecrans), len(salles))
    demandes = Counter((film.id, moment.date()) for moment, film, _ in candidates)
    quotas = {cle: math.ceil(n * part) for cle, n in demandes.items()}
    places = Counter()

    nouvelles: dict[Seance, float] = {}
    for avec_quota in (True, False):
        for moment, film, s in sorted(candidates, key=lambda c: c[0]):
            if empreinte(s["id"]) in deja:
                continue
            cle = (film.id, moment.date())
            if avec_quota and places[cle] >= quotas[cle]:
                continue
            fin_seance = moment + timedelta(minutes=film.duree_min) + MENAGE
            preferee = salle_preferee((s.get("screen") or {}).get("name", ""), len(salles))
            salle = salle_libre(salles, occupation, moment, fin_seance, preferee)
            if not salle:
                continue
            occupation.setdefault(salle.id, []).append((moment, fin_seance))
            places[cle] += 1
            deja.add(empreinte(s["id"]))
            seance = Seance(
                film_id=film.id, salle_id=salle.id, debut=moment, version=version(s["tags"]), source_id=empreinte(s["id"])
            )
            nouvelles[seance] = ((s.get("occupancy") or {}).get("rate") or 0) / 100
    session.add_all(nouvelles)
    await session.flush()
    log.info("programme CGR : %d films, %d séances ajoutées", len(films), len(nouvelles))
    return nouvelles
