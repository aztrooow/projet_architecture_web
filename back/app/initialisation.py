"""Création du schéma et données de démonstration.

Plusieurs instances de l'API peuvent démarrer en même temps : un verrou
consultatif PostgreSQL garantit qu'une seule initialise la base.
"""

import asyncio
import logging
import random
import secrets
import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text

from . import programmation_cgr, remplissage, tarifs
from .auth import hasher
from .config import settings
from .db import SessionLocal, engine
from .models import (
    Base,
    Billet,
    Categorie,
    Commande,
    Compte,
    Evenement,
    Film,
    Parametre,
    RegleTarifaire,
    Salle,
    Seance,
    Siege,
)
from .parametres import DEFAUTS

log = logging.getLogger(__name__)
PARIS = ZoneInfo(settings.fuseau)
VERROU_INIT = 856_700

# nom, rangs, sièges par rang, allées (après ces numéros)
SALLES = [
    ("Salle Lumière", 17, 20, (4, 16)),
    ("Salle Méliès", 16, 20, (4, 16)),
    ("Salle Varda", 15, 20, (5, 15)),
    ("Salle Truffaut", 15, 19, (4, 15)),
    ("Salle Demy", 14, 20, (5, 15)),
    ("Salle Gance", 15, 18, (4, 14)),
]

FILMS = [
    dict(
        titre="Terminator 2 : Le Jugement dernier", realisation="James Cameron", annee=1991, duree_min=137,
        genre="Science-fiction", type_production="standard", couleur="#7d1a1a",
        synopsis="Un cyborg venu du futur doit protéger le jeune John Connor, traqué par un modèle "
        "bien plus avancé capable de prendre n'importe quelle apparence.",
    ),
    dict(
        titre="Interstellar", realisation="Christopher Nolan", annee=2014, duree_min=169,
        genre="Science-fiction", type_production="standard", couleur="#23405c",
        synopsis="La Terre se meurt. Un ancien pilote traverse un trou de ver à la recherche d'un monde "
        "habitable, en laissant derrière lui ses enfants.",
    ),
    dict(
        titre="Dune : Deuxième partie", realisation="Denis Villeneuve", annee=2024, duree_min=166,
        genre="Science-fiction", type_production="standard", couleur="#9a5b22",
        synopsis="Paul Atréides rejoint les Fremen du désert d'Arrakis pour venger sa famille, tout en "
        "redoutant l'avenir qu'il entrevoit.",
    ),
    dict(
        titre="Le Voyage de Chihiro", realisation="Hayao Miyazaki", annee=2001, duree_min=125,
        genre="Animation", type_production="art_essai", couleur="#2c6457",
        synopsis="Perdue dans un monde peuplé d'esprits, une fillette de dix ans travaille dans des bains "
        "magiques pour sauver ses parents changés en cochons.",
    ),
    dict(
        titre="Le Fabuleux Destin d'Amélie Poulain", realisation="Jean-Pierre Jeunet", annee=2001,
        duree_min=122, genre="Comédie", type_production="art_essai", couleur="#6b2420",
        synopsis="À Montmartre, une serveuse discrète décide de réparer en secret la vie des gens qui "
        "l'entourent.",
    ),
    dict(
        titre="Avatar : La Voie de l'eau", realisation="James Cameron", annee=2022, duree_min=192,
        genre="Aventure", type_production="3d", couleur="#1d5f78",
        synopsis="Jake Sully et sa famille quittent la forêt de Pandora et trouvent refuge auprès d'un "
        "peuple de l'océan.",
    ),
    dict(
        titre="Parasite", realisation="Bong Joon-ho", annee=2019, duree_min=132,
        genre="Thriller", type_production="art_essai", couleur="#3a3a36",
        synopsis="Une famille sans emploi s'infiltre, un membre après l'autre, au service d'une riche "
        "famille de Séoul.",
    ),
    dict(
        titre="Spider-Man : Across the Spider-Verse",
        realisation="Joaquim Dos Santos, Kemp Powers, Justin K. Thompson", annee=2023, duree_min=140,
        genre="Animation", type_production="3d", couleur="#5b2a86",
        synopsis="Miles Morales traverse le multivers et découvre une société de Spider-héros qui ne voit "
        "pas son destin du même oeil que lui.",
    ),
]

EVENEMENT = dict(
    nom="Terminator grandeur nature",
    description="Terminator 2 dans une salle transformée : décors, fumée, cascadeurs et bande-son "
    "jouée en direct. Tarif unique, tous les samedis soir.",
)

CATEGORIES = [
    ("plein", "Plein tarif", 0),
    ("etudiant", "Étudiant", 1),
    ("enfant", "Moins de 14 ans", 2),
    ("senior", "Senior (65 ans et plus)", 3),
]

SEMAINE, WEEK_END = [0, 1, 2, 3], [4, 5, 6]


def regles(evenement_id: int) -> list[dict]:
    return [
        dict(libelle="Plein tarif semaine", prix_centimes=1050, priorite=10, jours=SEMAINE),
        dict(libelle="Plein tarif week-end", prix_centimes=1250, priorite=10, jours=WEEK_END),
        dict(libelle="Film en 3D", prix_centimes=1450, priorite=20, type_production="3d"),
        dict(libelle="Art et essai", prix_centimes=850, priorite=20, type_production="art_essai"),
        dict(libelle="Tarif étudiant", prix_centimes=790, priorite=30, categorie="etudiant"),
        dict(libelle="Moins de 14 ans", prix_centimes=590, priorite=30, categorie="enfant"),
        dict(libelle="Tarif senior", prix_centimes=890, priorite=30, categorie="senior"),
        dict(libelle="Étudiant, film en 3D", prix_centimes=1090, priorite=40, categorie="etudiant",
             type_production="3d"),
        dict(libelle="Moins de 14 ans, film en 3D", prix_centimes=890, priorite=40, categorie="enfant",
             type_production="3d"),
        dict(libelle="Senior, film en 3D", prix_centimes=1190, priorite=40, categorie="senior",
             type_production="3d"),
        dict(libelle="Terminator grandeur nature, tarif unique", prix_centimes=2500, priorite=100,
             evenement_id=evenement_id),
    ]


async def creer_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("SELECT pg_advisory_xact_lock(:v)"), {"v": VERROU_INIT})
        await conn.run_sync(Base.metadata.create_all)


async def creer_comptes(session) -> None:
    """Les mots de passe du personnel suivent la configuration à chaque démarrage."""
    for identifiant, mot_de_passe in (
        ("gerant", settings.gerant_mot_de_passe),
        ("controleur", settings.controleur_mot_de_passe),
    ):
        compte = await session.scalar(select(Compte).where(Compte.identifiant == identifiant))
        if not compte:
            session.add(Compte(identifiant=identifiant, mot_de_passe=hasher.hash(mot_de_passe), role=identifiant))
        elif not hasher.verify(mot_de_passe, compte.mot_de_passe):
            compte.mot_de_passe = hasher.hash(mot_de_passe)


async def creer_donnees_demo(session) -> None:
    """Salles, grille tarifaire et évènement du samedi ; les films viennent de la programmation."""
    for nom, rangs, par_rang, allees in SALLES:
        salle = Salle(nom=nom, capacite=rangs * par_rang)
        session.add(salle)
        await session.flush()
        for r in range(rangs):
            for n in range(1, par_rang + 1):
                x = n - 1 + sum(1 for a in allees if n > a)
                pmr = r == 0 and (n <= 2 or n > par_rang - 2)
                session.add(Siege(salle_id=salle.id, rang=chr(ord("A") + r), numero=n, x=x, y=r, pmr=pmr))
    # le film de l'évènement est projeté en séance spéciale, hors programmation importée
    session.add(Film(**FILMS[0]))
    evenement = Evenement(**EVENEMENT)
    session.add(evenement)
    session.add_all(Categorie(code=c, libelle=l, ordre=o) for c, l, o in CATEGORIES)
    await session.flush()
    session.add_all(RegleTarifaire(**r) for r in regles(evenement.id))
    session.add_all(Parametre(cle=k, valeur=v, libelle=l) for k, (v, l) in DEFAUTS.items())


def arrondi(moment: datetime, minutes: int = 5) -> datetime:
    reste = moment.minute % minutes
    if reste:
        moment += timedelta(minutes=minutes - reste)
    return moment.replace(second=0, microsecond=0)


def creneaux(jour: date, films: list[Film]):
    """Séances successives d'une salle sur une journée, ménage compris entre deux films."""
    moment = datetime.combine(jour, time(10, 45), PARIS)
    i = 0
    while moment.time() <= time(22, 30) and moment.date() == jour:
        film = films[i % len(films)]
        yield moment, film
        moment = arrondi(moment + timedelta(minutes=film.duree_min + 25))
        i += 1


async def programmer_evenements(session, jours: int) -> list[Seance]:
    """Chaque samedi à 20h30, la plus grande salle accueille « Terminator grandeur nature »."""
    evenement = await session.scalar(select(Evenement).order_by(Evenement.id).limit(1))
    film = await session.scalar(select(Film).where(Film.titre == FILMS[0]["titre"]))
    salle = await session.scalar(select(Salle).order_by(Salle.capacite.desc(), Salle.id).limit(1))
    if not (evenement and film and salle):
        return []
    nouvelles = []
    aujourd_hui = datetime.now(PARIS).date()
    for d in range(jours):
        jour = aujourd_hui + timedelta(days=d)
        if jour.weekday() != 5:
            continue
        soiree = datetime.combine(jour, time(20, 30), PARIS)
        if not await session.scalar(select(Seance.id).where(Seance.evenement_id == evenement.id, Seance.debut == soiree)):
            nouvelles.append(Seance(film_id=film.id, salle_id=salle.id, debut=soiree, evenement_id=evenement.id))
    session.add_all(nouvelles)
    await session.flush()
    return nouvelles


async def programmation_fictive(session, jours: int) -> list[Seance]:
    """Semaine générée avec des classiques, quand la programmation réelle est injoignable."""
    if not await session.scalar(select(func.count()).select_from(Film).where(Film.titre == FILMS[1]["titre"])):
        session.add_all(Film(**f) for f in FILMS[1:])
        await session.flush()
    films = list(await session.scalars(select(Film).where(Film.actif, Film.source_id.is_(None)).order_by(Film.id)))
    films = [f for f in films if f.titre != FILMS[0]["titre"]]
    salles = list(await session.scalars(select(Salle).order_by(Salle.capacite.desc(), Salle.id)))
    minuit = datetime.combine(datetime.now(PARIS).date(), time(0), PARIS)
    occupation = await programmation_cgr.occupation_actuelle(session, minuit, minuit + timedelta(days=jours))
    nouvelles = []
    for d in range(jours):
        debut_jour = minuit + timedelta(days=d)
        deja = await session.scalar(
            select(func.count())
            .select_from(Seance)
            .where(Seance.debut >= debut_jour, Seance.debut < debut_jour + timedelta(days=1), Seance.evenement_id.is_(None))
        )
        if deja:
            continue
        rotation = debut_jour.toordinal()
        for k, salle in enumerate(salles):
            paire = [films[(rotation + k) % len(films)], films[(rotation + k + 3) % len(films)]]
            for moment, film in creneaux(debut_jour.date(), paire):
                fin = moment + timedelta(minutes=film.duree_min + 20)
                if any(not (fin <= a or moment >= b) for a, b in occupation.get(salle.id, [])):
                    continue
                # Parasite toujours en VO, et les soirées de la dernière salle en VOST
                vost = film.titre == "Parasite" or (k == 5 and moment.hour >= 20 and "Amélie" not in film.titre)
                nouvelles.append(Seance(film_id=film.id, salle_id=salle.id, debut=moment, version="VOST" if vost else "VF"))
    session.add_all(nouvelles)
    await session.flush()
    return nouvelles


async def simuler_ventes(session, seances: dict[Seance, float | None]) -> None:
    """Remplit les salles pour que les plans ne soient pas vides à la démo.

    Pour une séance importée, on part du taux de remplissage réel annoncé par le CGR.
    """
    regles_actives = list(await session.scalars(select(RegleTarifaire).where(RegleTarifaire.actif)))
    types = dict((await session.execute(select(Film.id, Film.type_production))).all())
    sieges_par_salle: dict[int, list[Siege]] = {}
    maintenant = datetime.now(PARIS)
    for seance, taux_source in seances.items():
        if seance.salle_id not in sieges_par_salle:
            sieges_par_salle[seance.salle_id] = list(
                await session.scalars(select(Siege).where(Siege.salle_id == seance.salle_id).order_by(Siege.y, Siege.x))
            )
        sieges = sieges_par_salle[seance.salle_id]
        hasard = random.Random(seance.id)
        local = seance.debut.astimezone(PARIS)
        # plus la séance est proche, plus elle est remplie
        proximite = max(0.25, 1 - (local.date() - maintenant.date()).days / 8)
        if seance.evenement_id:
            taux = hasard.uniform(0.55, 0.8)
        elif taux_source is not None:
            taux = min(0.95, taux_source + hasard.uniform(0.02, 0.12) * proximite)
        elif local.weekday() >= 4 or local.hour >= 19:
            taux = hasard.uniform(0.25, 0.6) * proximite
        else:
            taux = hasard.uniform(0.05, 0.3) * proximite
        objectif = int(len(sieges) * taux)
        pris: set[int] = set()
        while len(pris) < objectif:
            # des petits groupes côte à côte, comme de vrais spectateurs
            depart = hasard.randrange(len(sieges))
            for s in sieges[depart : depart + hasard.randint(1, 4)]:
                if s.y == sieges[depart].y:
                    pris.add(s.id)
        if not pris:
            continue
        vendu_le = min(maintenant, seance.debut) - timedelta(hours=hasard.uniform(1, 150))
        deja_passee = seance.debut < maintenant
        billets = []
        for siege_id in pris:
            categorie = hasard.choices(["plein", "etudiant", "enfant", "senior"], weights=[70, 15, 10, 5])[0]
            regle = tarifs.choisir(
                regles_actives,
                tarifs.contexte_seance(seance.debut, types[seance.film_id], seance.evenement_id, categorie),
            )
            if not regle:
                continue
            # pour une séance déjà commencée, la plupart des spectateurs sont passés au contrôle
            entre = deja_passee and hasard.random() < 0.92
            billets.append(
                Billet(
                    seance_id=seance.id,
                    siege_id=siege_id,
                    categorie=categorie,
                    libelle_tarif=regle.libelle,
                    prix_centimes=regle.prix_centimes,
                    emis_le=vendu_le,
                    statut="utilise" if entre else "valide",
                    utilise_le=seance.debut - timedelta(minutes=hasard.uniform(2, 25)) if entre else None,
                )
            )
        # ventes faites aux bornes avant la mise en ligne : pas de billet électronique
        commande = Commande(
            id=uuid.uuid4(),
            reference="CIN-" + secrets.token_hex(3).upper(),
            seance_id=seance.id,
            statut="payee",
            canal="borne",
            lignes=[],
            montant_centimes=sum(b.prix_centimes for b in billets),
            expire_le=vendu_le,
            payee_le=vendu_le,
        )
        session.add(commande)
        # sans relation déclarée, la commande doit exister avant ses billets
        await session.flush()
        for billet in billets:
            billet.commande_id = commande.id
        session.add_all(billets)


async def completer_programmation(jours: int = 8) -> None:
    """Évènements du samedi, puis programmation réelle (ou fictive en secours). Idempotent."""
    async with SessionLocal() as session:
        await session.execute(text("SELECT pg_advisory_xact_lock(:v)"), {"v": VERROU_INIT + 1})
        if not await session.scalar(select(func.count()).select_from(Salle)):
            return
        nouvelles: dict[Seance, float | None] = {s: None for s in await programmer_evenements(session, jours)}
        if settings.programme_source == "cgr":
            try:
                async with session.begin_nested():
                    nouvelles |= await programmation_cgr.importer(session, jours)
            except Exception:
                log.exception("programmation du CGR injoignable, on garde celle en place")
        a_venir = await session.scalar(
            select(func.count())
            .select_from(Seance)
            .where(Seance.debut > datetime.now(PARIS), Seance.evenement_id.is_(None))
        )
        if settings.programme_source == "demo" or (settings.programme_source == "cgr" and not a_venir):
            nouvelles |= {s: None for s in await programmation_fictive(session, jours)}
        await simuler_ventes(session, nouvelles)
        await session.commit()
        if nouvelles:
            await remplissage.recalculer(session, [s.id for s in nouvelles])
            log.info("%d séances programmées", len(nouvelles))


async def initialiser() -> None:
    await creer_schema()
    async with SessionLocal() as session:
        await session.execute(text("SELECT pg_advisory_xact_lock(:v)"), {"v": VERROU_INIT})
        await creer_comptes(session)
        if settings.donnees_demo and not await session.scalar(select(func.count()).select_from(Salle)):
            await creer_donnees_demo(session)
        await session.commit()
    if settings.donnees_demo:
        await completer_programmation()


async def entretien_periodique() -> None:
    """Toutes les heures : ajoute les jours de programmation qui manquent."""
    while True:
        await asyncio.sleep(3600)
        try:
            await completer_programmation()
        except Exception:
            log.exception("échec de la programmation automatique")
