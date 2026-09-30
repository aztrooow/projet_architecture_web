"""Service front.

Les pages du catalogue (accueil, fiche film, borne) sont rendues ici côté
serveur à partir de l'API : elles s'affichent vite et sont lisibles par les
moteurs de recherche. Le reste (plan de salle, paiement, billets, contrôle,
back-office) est l'application React, servie par la même page d'accueil HTML.
"""

import json
import re
import time
from collections import OrderedDict
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic_settings import BaseSettings
from starlette.exceptions import HTTPException as StarletteHTTPException


class Settings(BaseSettings):
    api_interne: str = "http://back:8000"
    # adresses vues par le navigateur ; vides = même origine
    url_api: str = ""
    url_qr: str = ""
    url_verification: str = ""
    dossier_web: str = str(Path(__file__).parent.parent / "web" / "dist")


settings = Settings()
ICI = Path(__file__).parent
DIST = Path(settings.dossier_web)
PARIS = ZoneInfo("Europe/Paris")

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]
TYPES = {"3d": "3D", "art_essai": "Art et essai"}

app = FastAPI(title="CinetINT, front", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=ICI / "static"), name="static")
if (DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

templates = Jinja2Templates(directory=ICI / "templates")
client = httpx.AsyncClient(base_url=settings.api_interne, timeout=5)


# ---------- données

_cache: dict[str, tuple[float, dict]] = {}


async def lire_api(chemin: str, duree: int = 20) -> dict:
    """GET sur l'API avec un petit cache : le catalogue change peu d'une seconde à l'autre."""
    trouve = _cache.get(chemin)
    if trouve and time.monotonic() - trouve[0] < duree:
        return trouve[1]
    try:
        reponse = await client.get(chemin)
    except httpx.HTTPError:
        if trouve:
            return trouve[1]
        raise HTTPException(503, "La billetterie est momentanément indisponible")
    if reponse.status_code == 404:
        raise HTTPException(404)
    reponse.raise_for_status()
    donnees = reponse.json()
    _cache[chemin] = (time.monotonic(), donnees)
    return donnees


def moment(iso: str) -> datetime:
    return datetime.fromisoformat(iso).astimezone(PARIS)


def jour_relatif(d: datetime) -> str:
    ecart = (d.date() - datetime.now(PARIS).date()).days
    if ecart == 0:
        return "Aujourd'hui"
    if ecart == 1:
        return "Demain"
    return f"{JOURS[d.weekday()].capitalize()} {d.day} {MOIS[d.month - 1]}"


def par_jour(seances: list[dict]) -> "OrderedDict[str, list[dict]]":
    groupes: OrderedDict[str, list[dict]] = OrderedDict()
    for s in seances:
        groupes.setdefault(moment(s["debut"]).date().isoformat(), []).append(s)
    return groupes


# ---------- filtres Jinja


def f_heure(iso: str) -> str:
    d = moment(iso)
    return f"{d.hour}h{d.minute:02d}"


def f_jour(iso: str) -> str:
    return jour_relatif(moment(iso))


def f_date_longue(iso: str) -> str:
    d = moment(iso)
    return f"{JOURS[d.weekday()]} {d.day} {MOIS[d.month - 1]}"


def f_duree(minutes: int) -> str:
    return f"{minutes // 60} h {minutes % 60:02d}"


def f_euros(centimes: int | None) -> str:
    if centimes is None:
        return ""
    euros, cents = divmod(centimes, 100)
    return f"{euros},{cents:02d} €"


MOIS_COURTS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def f_jour_court(cle: str) -> dict:
    """Onglet de jour : « Mer. / 30 / sept. »"""
    d = datetime.fromisoformat(cle)
    return {"nom": JOURS[d.weekday()][:3].capitalize() + ".", "numero": d.day, "mois": MOIS_COURTS[d.month - 1]}


def f_criteres(regle: dict) -> str:
    """Traduit les critères d'une règle en français : « du vendredi au dimanche, films en 3D »."""
    morceaux = []
    jours = regle.get("jours") or []
    if jours:
        if jours == list(range(jours[0], jours[-1] + 1)) and len(jours) > 2:
            morceaux.append(f"du {JOURS[jours[0]]} au {JOURS[jours[-1]]}")
        else:
            morceaux.append(", ".join(JOURS[j] for j in jours))
    if regle.get("type_production"):
        morceaux.append("films en 3D" if regle["type_production"] == "3d" else "films art et essai")
    if regle.get("evenement"):
        morceaux.append("séances évènement")
    return ", ".join(morceaux) or "toutes les séances"


def f_variante(url: str | None, taille: str) -> str:
    """Le CDN des affiches redimensionne à la volée : .../c_310_420/img/..."""
    if not url:
        return ""
    return re.sub(r"(acsta\.net/)", rf"\g<1>{taille}/", url, count=1)


def f_remplissage(seance: dict) -> str:
    """Niveau affiché sur les horaires : les spectateurs voient ce qui part vite."""
    restant = seance["salle"]["capacite"] - seance["vendus"]
    if restant <= 0:
        return "complet"
    if restant <= 25:
        return "dernieres"
    if seance["vendus"] / seance["salle"]["capacite"] >= 0.6:
        return "rempli"
    return ""


templates.env.filters.update(
    heure=f_heure,
    jour=f_jour,
    date_longue=f_date_longue,
    duree=f_duree,
    euros=f_euros,
    remplissage=f_remplissage,
    jour_court=f_jour_court,
    criteres=f_criteres,
    variante=f_variante,
    type_production=lambda code: TYPES.get(code, ""),
)


@lru_cache(maxsize=4)
def _lire_manifest(date_modif: float) -> dict:
    return json.loads((DIST / ".vite" / "manifest.json").read_text())


def manifest() -> dict:
    # relu seulement quand un nouveau build de l'application le remplace
    chemin = DIST / ".vite" / "manifest.json"
    return _lire_manifest(chemin.stat().st_mtime) if chemin.exists() else {}


def fichiers(entree: str) -> dict:
    """JS et CSS produits par Vite pour une entrée (voir web/vite.config.ts)."""
    m = manifest()
    bloc = m.get(entree)
    if not bloc:
        return {"js": None, "css": []}
    css = list(bloc.get("css", []))
    for importe in bloc.get("imports", []):
        css += m.get(importe, {}).get("css", [])
    return {"js": "/" + bloc["file"], "css": ["/" + c for c in dict.fromkeys(css)]}


def rendre(request: Request, gabarit: str, entree: str = "src/site.ts", statut: int = 200, **contexte):
    configuration = {
        "api": settings.url_api,
        "qr": settings.url_qr,
        "verification": settings.url_verification,
    }
    return templates.TemplateResponse(
        request,
        gabarit,
        {
            "assets": fichiers(entree),
            # inséré dans une balise <script> : on neutralise « </ »
            "configuration": json.dumps(configuration).replace("<", "\\u003c"),
            "chemin": request.url.path,
            **contexte,
        },
        status_code=statut,
    )


# ---------- pages rendues côté serveur


@app.get("/", response_class=HTMLResponse)
async def accueil(request: Request):
    programme = await lire_api("/api/programme")
    maintenant = datetime.now(PARIS)
    aujourd_hui = maintenant.date().isoformat()
    films = programme["films"]
    for film in films:
        film["prochaines"] = [s for s in film["seances"] if moment(s["debut"]).date().isoformat() == aujourd_hui]
        film["jours"] = par_jour(film["seances"])
    # à l'affiche aujourd'hui en premier
    films.sort(key=lambda f: (not f["prochaines"], f["seances"][0]["debut"] if f["seances"] else ""))
    try:
        grille = await lire_api("/api/tarifs", duree=60)
    except HTTPException:
        grille = []
    return rendre(
        request,
        "accueil.html",
        films=films,
        evenement=programme["evenements"][0] if programme["evenements"] else None,
        nb_seances=sum(len(f["prochaines"]) for f in films),
        fauteuils=programme.get("fauteuils"),
        salles=programme.get("salles"),
        grille=grille,
    )


@app.get("/films/{film_id}", response_class=HTMLResponse)
async def fiche_film(request: Request, film_id: int):
    film = await lire_api(f"/api/films/{film_id}")
    return rendre(request, "film.html", film=film, jours=par_jour(film["seances"]))


@app.get("/borne", response_class=HTMLResponse)
async def borne(request: Request):
    programme = await lire_api("/api/programme", duree=10)
    aujourd_hui = datetime.now(PARIS).date().isoformat()
    films = []
    for film in programme["films"]:
        film["prochaines"] = [s for s in film["seances"] if moment(s["debut"]).date().isoformat() == aujourd_hui]
        if film["prochaines"]:
            films.append(film)
    return rendre(request, "borne.html", films=films)


# ---------- application React (réservation, contrôle, back-office)

APPLICATION = ["/seances/{x}", "/paiement/{x}", "/commande/{x}", "/controle", "/admin", "/admin/{x:path}"]


async def application(request: Request):
    return rendre(request, "application.html", entree="src/main.tsx")


for chemin in APPLICATION:
    app.add_api_route(chemin, application, response_class=HTMLResponse, include_in_schema=False)


@app.get("/sante")
async def sante():
    return {"statut": "ok", "application": bool(manifest())}


@app.exception_handler(StarletteHTTPException)
async def page_erreur(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return rendre(request, "erreur.html", statut=404, titre="Cette page n'existe pas",
                      message="La séance a peut-être été retirée de la programmation.")
    return rendre(request, "erreur.html", statut=exc.status_code, titre="Oups", message=str(exc.detail))
