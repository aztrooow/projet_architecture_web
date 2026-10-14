"""Lecture JSON de chaque table de la base : toutes les lignes, toutes les colonnes.

  GET /api/donnees                  les tables disponibles et leur nombre de lignes
  GET /api/donnees/{table}          toutes les lignes (pagination facultative : limite, decalage)
  GET /api/donnees/{table}/{cle}    une ligne, désignée par sa clé primaire

Les tables qui contiennent des données sensibles (commandes, billets, journal
du contrôle, comptes) exigent le jeton du gérant. Un secret n'est jamais
renvoyé en clair : le mot de passe haché est masqué et le jeton signé d'un
billet est abrégé.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, inspect, select
from sqlalchemy.dialects import postgresql

from ..auth import gerant
from ..models import (
    Billet,
    Categorie,
    Commande,
    Compte,
    Controle,
    Evenement,
    Film,
    Parametre,
    RegleTarifaire,
    Salle,
    Seance,
    Siege,
)
from .commun import Session

router = APIRouter(prefix="/api/donnees", tags=["données"])


@dataclass(frozen=True)
class Source:
    nom: str
    titre: str
    modele: type
    protegee: bool
    ordre: tuple


# ordre d'affichage : les journaux et les ventes les plus récents d'abord
SOURCES = [
    Source("salles", "Salles", Salle, False, (Salle.id,)),
    Source("sieges", "Sièges", Siege, False, (Siege.salle_id, Siege.y, Siege.x)),
    Source("films", "Films", Film, False, (Film.id,)),
    Source("evenements", "Évènements", Evenement, False, (Evenement.id,)),
    Source("seances", "Séances", Seance, False, (Seance.debut, Seance.id)),
    Source("categories", "Catégories de spectateurs", Categorie, False, (Categorie.ordre, Categorie.code)),
    Source("regles-tarifaires", "Règles tarifaires", RegleTarifaire, False, (RegleTarifaire.id,)),
    Source("parametres", "Réglages de la vente", Parametre, False, (Parametre.cle,)),
    Source("commandes", "Commandes", Commande, True, (Commande.cree_le.desc(), Commande.id)),
    Source("billets", "Billets", Billet, True, (Billet.emis_le.desc(), Billet.id)),
    Source("controles", "Journal du contrôle", Controle, True, (Controle.id.desc(),)),
    Source("comptes", "Comptes du personnel", Compte, True, (Compte.id,)),
]


def masque_jeton(jeton: str | None) -> str | None:
    return None if jeton is None else f"{jeton[:8]}…{jeton[-6:]}"


# colonnes dont la valeur ne sort jamais telle quelle
MASQUES = {
    "mot_de_passe": lambda valeur: "(masqué)",
    "jeton": masque_jeton,
}


def valeur_json(valeur):
    if isinstance(valeur, (datetime, date)):
        return valeur.isoformat()
    if isinstance(valeur, uuid.UUID):
        return str(valeur)
    return valeur


def ligne_json(objet) -> dict:
    sortie = {}
    for attribut in inspect(type(objet)).column_attrs:
        valeur = getattr(objet, attribut.key)
        sortie[attribut.key] = MASQUES[attribut.key](valeur) if attribut.key in MASQUES else valeur_json(valeur)
    return sortie


def colonnes_json(modele: type) -> list[dict]:
    colonnes = []
    for colonne in inspect(modele).columns:
        cles = list(colonne.foreign_keys)
        colonnes.append(
            {
                "nom": colonne.key,
                "type": colonne.type.compile(dialect=postgresql.dialect()),
                "cle_primaire": colonne.primary_key,
                "obligatoire": not colonne.nullable,
                "reference": f"{cles[0].column.table.name}.{cles[0].column.name}" if cles else None,
            }
        )
    return colonnes


def type_cle(modele: type):
    return inspect(modele).primary_key[0].type.python_type


def route_liste(source: Source):
    async def liste(
        session: Session,
        limite: Annotated[int | None, Query(ge=1, le=100_000, description="Nombre de lignes (toutes par défaut)")] = None,
        decalage: Annotated[int, Query(ge=0)] = 0,
    ):
        total = await session.scalar(select(func.count()).select_from(source.modele))
        requete = select(source.modele).order_by(*source.ordre).offset(decalage)
        if limite:
            requete = requete.limit(limite)
        lignes = await session.scalars(requete)
        return {
            "table": source.nom,
            "titre": source.titre,
            "protegee": source.protegee,
            "total": total,
            "limite": limite,
            "decalage": decalage,
            "colonnes": colonnes_json(source.modele),
            "lignes": [ligne_json(ligne) for ligne in lignes],
        }

    return liste


def route_detail(source: Source):
    async def detail(cle: str, session: Session):
        try:
            valeur = type_cle(source.modele)(cle)
        except ValueError:
            raise HTTPException(404, "Aucune ligne avec cette clé")
        objet = await session.get(source.modele, valeur)
        if not objet:
            raise HTTPException(404, "Aucune ligne avec cette clé")
        return ligne_json(objet)

    return detail


for _source in SOURCES:
    protection = [Depends(gerant)] if _source.protegee else []
    acces = "réservé au gérant" if _source.protegee else "public"
    router.add_api_route(
        f"/{_source.nom}",
        route_liste(_source),
        methods=["GET"],
        dependencies=protection,
        name=f"donnees_{_source.nom}",
        summary=f"{_source.titre} : toutes les lignes ({acces})",
    )
    router.add_api_route(
        f"/{_source.nom}/{{cle}}",
        route_detail(_source),
        methods=["GET"],
        dependencies=protection,
        name=f"donnees_{_source.nom}_detail",
        summary=f"{_source.titre} : une ligne ({acces})",
    )


@router.get("", summary="Tables disponibles et nombre de lignes")
async def tables(session: Session):
    return [
        {
            "nom": source.nom,
            "titre": source.titre,
            "protegee": source.protegee,
            "total": await session.scalar(select(func.count()).select_from(source.modele)),
            "url": f"/api/donnees/{source.nom}",
        }
        for source in SOURCES
    ]
