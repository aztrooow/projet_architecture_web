import secrets
import uuid
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .. import formats, parametres, qr_client, remplissage, tarifs, verrous
from ..models import Billet, Commande, Evenement, Film, Salle, Seance, Siege
from ..paiement import prestataire
from ..temps_reel import canal_seance, publier
from .commun import Session, categories_actives, maintenant, regles_actives, seance_json

router = APIRouter(prefix="/api", tags=["commandes"])

ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def nouvelle_reference() -> str:
    return "CIN-" + "".join(secrets.choice(ALPHABET) for _ in range(6))


class PlaceDemandee(BaseModel):
    siege_id: int
    categorie: str


class NouvelleCommande(BaseModel):
    seance_id: int
    places: list[PlaceDemandee] = Field(min_length=1)
    canal: Literal["web", "borne"] = "web"


class ResultatPaiement(BaseModel):
    resultat: Literal["accepte", "refuse"]


class DemandeRemboursement(BaseModel):
    commande_id: uuid.UUID


async def publier_sieges(seance_id: int, siege_ids: list[int], etat: str) -> None:
    await publier(canal_seance(seance_id), {"sieges": [{"id": i, "etat": etat} for i in siege_ids]})


async def expirer_si_besoin(session: AsyncSession, commande: Commande) -> None:
    if commande.statut == "en_attente" and commande.expire_le <= maintenant():
        commande.statut = "expiree"
        await session.commit()
        ids = [ligne["siege_id"] for ligne in commande.lignes]
        await verrous.liberer(commande.seance_id, ids, str(commande.id))
        await publier_sieges(commande.seance_id, ids, "libre")


async def detail_commande(session: AsyncSession, commande_id: uuid.UUID) -> dict:
    commande = await session.get(Commande, commande_id)
    if not commande:
        raise HTTPException(404, "Commande introuvable")
    await expirer_si_besoin(session, commande)
    seance, film, salle, evenement = (
        await session.execute(
            select(Seance, Film, Salle, Evenement)
            .join(Film, Film.id == Seance.film_id)
            .join(Salle, Salle.id == Seance.salle_id)
            .outerjoin(Evenement, Evenement.id == Seance.evenement_id)
            .where(Seance.id == commande.seance_id)
        )
    ).one()
    billets = (
        await session.execute(
            select(Billet, Siege)
            .join(Siege, Siege.id == Billet.siege_id)
            .where(Billet.commande_id == commande.id)
            .order_by(Siege.y, Siege.x)
        )
    ).all()
    limite = (await parametres.lire(session))["remboursement_limite_min"]
    return {
        "id": str(commande.id),
        "reference": commande.reference,
        "statut": commande.statut,
        "canal": commande.canal,
        "montant_centimes": commande.montant_centimes,
        "expire_le": commande.expire_le.isoformat(),
        "psp_session": commande.psp_session if commande.statut == "en_attente" else None,
        "seance": seance_json(seance, film, salle, evenement),
        "lignes": commande.lignes,
        "remboursable_jusqua": (seance.debut - timedelta(minutes=limite)).isoformat(),
        "billets": [
            {
                "id": str(b.id),
                "rang": s.rang,
                "numero": s.numero,
                "categorie": b.categorie,
                "libelle_tarif": b.libelle_tarif,
                "prix_centimes": b.prix_centimes,
                "statut": b.statut,
                "jeton": b.jeton,
                "utilise_le": b.utilise_le.isoformat() if b.utilise_le else None,
                "rembourse_le": b.rembourse_le.isoformat() if b.rembourse_le else None,
            }
            for b, s in billets
        ],
    }


@router.post("/commandes", status_code=201)
async def creer_commande(data: NouvelleCommande, session: Session):
    params = await parametres.lire(session)
    if len(data.places) > params["places_max"]:
        raise HTTPException(422, f"{params['places_max']} places au maximum par commande")
    ids = [p.siege_id for p in data.places]
    if len(set(ids)) != len(ids):
        raise HTTPException(422, "Le même siège est demandé deux fois")

    ligne = (await session.execute(select(Seance, Film).join(Film).where(Seance.id == data.seance_id))).first()
    if not ligne:
        raise HTTPException(404, "Séance introuvable")
    seance, film = ligne
    if seance.debut <= maintenant():
        raise HTTPException(409, "La séance a déjà commencé")

    sieges = {
        s.id: s
        for s in await session.scalars(select(Siege).where(Siege.id.in_(ids), Siege.salle_id == seance.salle_id))
    }
    if len(sieges) != len(ids):
        raise HTTPException(422, "Siège inconnu dans cette salle")
    categories = {c.code for c in await categories_actives(session)}
    if any(p.categorie not in categories for p in data.places):
        raise HTTPException(422, "Catégorie de tarif inconnue")

    deja_vendus = set(
        await session.scalars(
            select(Billet.siege_id).where(
                Billet.seance_id == seance.id,
                Billet.siege_id.in_(ids),
                Billet.statut.in_(remplissage.BILLETS_OCCUPANT),
            )
        )
    )
    if deja_vendus:
        raise HTTPException(409, {"message": "Ces places viennent d'être vendues", "sieges": sorted(deja_vendus)})

    regles = await regles_actives(session)
    lignes = []
    for p in data.places:
        regle = tarifs.choisir(
            regles, tarifs.contexte_seance(seance.debut, film.type_production, seance.evenement_id, p.categorie)
        )
        if not regle:
            raise HTTPException(422, "Aucun tarif ne s'applique à cette place")
        siege = sieges[p.siege_id]
        lignes.append(
            {
                "siege_id": siege.id,
                "rang": siege.rang,
                "numero": siege.numero,
                "categorie": p.categorie,
                "libelle": regle.libelle,
                "prix_centimes": regle.prix_centimes,
            }
        )

    commande_id = uuid.uuid4()
    duree = params["duree_verrou_min"] * 60
    conflits = await verrous.poser(seance.id, ids, str(commande_id), duree)
    if conflits:
        raise HTTPException(
            409, {"message": "Ces places sont en cours de réservation par quelqu'un d'autre", "sieges": conflits}
        )
    try:
        montant = sum(ligne["prix_centimes"] for ligne in lignes)
        reference = nouvelle_reference()
        session.add(
            Commande(
                id=commande_id,
                reference=reference,
                seance_id=seance.id,
                canal=data.canal,
                lignes=lignes,
                montant_centimes=montant,
                expire_le=maintenant() + timedelta(seconds=duree),
                psp_session=await prestataire.creer_session(reference, montant),
            )
        )
        await session.commit()
    except Exception:
        await verrous.liberer(seance.id, ids, str(commande_id))
        raise
    await publier_sieges(seance.id, ids, "verrouille")
    return await detail_commande(session, commande_id)


@router.get("/commandes/{commande_id}")
async def lire_commande(commande_id: uuid.UUID, session: Session):
    return await detail_commande(session, commande_id)


@router.delete("/commandes/{commande_id}")
async def annuler_commande(commande_id: uuid.UUID, session: Session):
    commande = await session.get(Commande, commande_id, with_for_update=True)
    if not commande:
        raise HTTPException(404, "Commande introuvable")
    if commande.statut == "en_attente":
        commande.statut = "annulee"
        await session.commit()
        ids = [ligne["siege_id"] for ligne in commande.lignes]
        await verrous.liberer(commande.seance_id, ids, str(commande.id))
        await publier_sieges(commande.seance_id, ids, "libre")
    return await detail_commande(session, commande_id)


async def confirmer(session: AsyncSession, commande: Commande) -> None:
    """Paiement accepté : émission des billets signés."""
    ids = [ligne["siege_id"] for ligne in commande.lignes]
    # si le verrou a expiré mais que personne n'a repris les places, on peut encore conclure
    if await verrous.poser(commande.seance_id, ids, str(commande.id), 120):
        commande.statut = "expiree"
        await session.commit()
        raise HTTPException(409, "Délai dépassé : ces places ont été reprises par un autre spectateur")

    billets = [
        Billet(
            id=uuid.uuid4(),
            commande_id=commande.id,
            seance_id=commande.seance_id,
            siege_id=ligne["siege_id"],
            categorie=ligne["categorie"],
            libelle_tarif=ligne["libelle"],
            prix_centimes=ligne["prix_centimes"],
        )
        for ligne in commande.lignes
    ]
    jetons = await qr_client.signer(
        [
            {"id": str(b.id), "seance_id": b.seance_id, "place": f"{ligne['rang']}{ligne['numero']}"}
            for b, ligne in zip(billets, commande.lignes)
        ]
    )
    for billet, jeton in zip(billets, jetons):
        billet.jeton = jeton
    session.add_all(billets)
    commande.statut = "payee"
    commande.payee_le = maintenant()
    try:
        await session.commit()
    except IntegrityError:
        # la contrainte d'unicité a tranché : une place était déjà vendue
        await session.rollback()
        commande = await session.get(Commande, commande.id)
        commande.statut = "annulee"
        await session.commit()
        await verrous.liberer(commande.seance_id, ids, str(commande.id))
        raise HTTPException(409, "Une des places a déjà été vendue, le paiement n'a pas été encaissé")

    await verrous.liberer(commande.seance_id, ids, str(commande.id))
    await remplissage.ajuster(session, commande.seance_id, len(billets))
    await publier_sieges(commande.seance_id, ids, "vendu")


@router.post("/paiement-simule/{psp_session}")
async def paiement_simule(psp_session: str, data: ResultatPaiement, session: Session):
    """Retour du prestataire simulé. Avec le vrai prestataire, ce serait sa notification."""
    commande = await session.scalar(
        select(Commande).where(Commande.psp_session == psp_session).with_for_update()
    )
    if not commande:
        raise HTTPException(404, "Session de paiement inconnue")
    if commande.statut == "payee":
        return {"statut": "payee", "commande_id": str(commande.id)}
    if commande.statut == "en_attente" and commande.expire_le <= maintenant():
        await expirer_si_besoin(session, commande)
    if commande.statut != "en_attente":
        raise HTTPException(409, "Le délai de paiement est dépassé, vos places ont été remises en vente")
    if data.resultat == "refuse":
        await session.commit()
        return {"statut": "refuse", "commande_id": str(commande.id)}
    await confirmer(session, commande)
    return {"statut": "payee", "commande_id": str(commande.id)}


@router.get("/commandes/{commande_id}/billets.pdf")
async def billets_pdf(commande_id: uuid.UUID, session: Session):
    detail = await detail_commande(session, commande_id)
    if detail["statut"] != "payee":
        raise HTTPException(409, "Commande non payée")
    seance = detail["seance"]
    contenu = await qr_client.pdf(
        {
            "reference": detail["reference"],
            "film": seance["film"]["titre"],
            "date": formats.date_longue(
                (await session.get(Seance, seance["id"])).debut
            ),
            "salle": seance["salle"]["nom"],
            "version": seance["version"],
            "evenement": seance["evenement"]["nom"] if seance["evenement"] else None,
            "billets": [
                {
                    "jeton": b["jeton"],
                    "place": f"{b['rang']}{b['numero']}",
                    "tarif": b["libelle_tarif"],
                    "prix": formats.euros(b["prix_centimes"]),
                }
                for b in detail["billets"]
                if b["statut"] == "valide" and b["jeton"]
            ],
        }
    )
    return Response(
        contenu,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="billets-{detail["reference"]}.pdf"'},
    )


async def rembourser(session: AsyncSession, billet: Billet, controler_delai: bool = True) -> None:
    if billet.statut == "utilise":
        raise HTTPException(409, "Ce billet a déjà été scanné à l'entrée, il ne peut plus être remboursé")
    if billet.statut == "rembourse":
        raise HTTPException(409, "Ce billet est déjà remboursé")
    seance = await session.get(Seance, billet.seance_id)
    limite = (await parametres.lire(session))["remboursement_limite_min"]
    if controler_delai and maintenant() > seance.debut - timedelta(minutes=limite):
        raise HTTPException(409, f"Le remboursement n'est possible que jusqu'à {limite} minutes avant la séance")
    commande = await session.get(Commande, billet.commande_id)
    billet.remboursement_ref = await prestataire.rembourser(commande.psp_session or "", billet.prix_centimes)
    billet.statut = "rembourse"
    billet.rembourse_le = maintenant()
    await session.commit()
    await remplissage.ajuster(session, billet.seance_id, -1)
    await publier_sieges(billet.seance_id, [billet.siege_id], "libre")


@router.post("/billets/{billet_id}/remboursement")
async def demande_remboursement(billet_id: uuid.UUID, data: DemandeRemboursement, session: Session):
    # verrou de ligne : un scan et un remboursement simultanés ne peuvent pas se croiser
    billet = await session.scalar(
        select(Billet).where(Billet.id == billet_id, Billet.commande_id == data.commande_id).with_for_update()
    )
    if not billet:
        raise HTTPException(404, "Billet introuvable")
    await rembourser(session, billet)
    return await detail_commande(session, data.commande_id)
