import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Salle(Base):
    __tablename__ = "salles"

    id: Mapped[int] = mapped_column(primary_key=True)
    nom: Mapped[str] = mapped_column(String(40))
    capacite: Mapped[int]


class Siege(Base):
    __tablename__ = "sieges"
    __table_args__ = (UniqueConstraint("salle_id", "rang", "numero"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    salle_id: Mapped[int] = mapped_column(ForeignKey("salles.id", ondelete="CASCADE"), index=True)
    rang: Mapped[str] = mapped_column(String(2))
    numero: Mapped[int]
    # position sur le plan (colonnes vides = allées)
    x: Mapped[int]
    y: Mapped[int]
    pmr: Mapped[bool] = mapped_column(default=False)


class Film(Base):
    __tablename__ = "films"

    id: Mapped[int] = mapped_column(primary_key=True)
    titre: Mapped[str] = mapped_column(String(120))
    realisation: Mapped[str] = mapped_column(String(120), default="")
    annee: Mapped[int | None]
    duree_min: Mapped[int]
    genre: Mapped[str] = mapped_column(String(40), default="")
    synopsis: Mapped[str] = mapped_column(Text, default="")
    # standard, 3d, art_essai : sert au moteur de tarification
    type_production: Mapped[str] = mapped_column(String(20), default="standard")
    # teinte dominante de l'affiche, reprise en fond de la fiche du film
    couleur: Mapped[str] = mapped_column(String(7), default="#8f1d21")
    affiche_url: Mapped[str | None] = mapped_column(String(300))
    image_url: Mapped[str | None] = mapped_column(String(300))
    # identifiant chez la source de la programmation (films importés)
    source_id: Mapped[str | None] = mapped_column(String(40), unique=True)
    actif: Mapped[bool] = mapped_column(default=True)


class Evenement(Base):
    __tablename__ = "evenements"

    id: Mapped[int] = mapped_column(primary_key=True)
    nom: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")


class Seance(Base):
    __tablename__ = "seances"

    id: Mapped[int] = mapped_column(primary_key=True)
    film_id: Mapped[int] = mapped_column(ForeignKey("films.id", ondelete="CASCADE"), index=True)
    salle_id: Mapped[int] = mapped_column(ForeignKey("salles.id", ondelete="CASCADE"))
    debut: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    version: Mapped[str] = mapped_column(String(8), default="VF")
    evenement_id: Mapped[int | None] = mapped_column(ForeignKey("evenements.id", ondelete="SET NULL"))
    source_id: Mapped[str | None] = mapped_column(String(40), unique=True)


class Categorie(Base):
    __tablename__ = "categories"

    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    libelle: Mapped[str] = mapped_column(String(60))
    ordre: Mapped[int] = mapped_column(default=0)
    actif: Mapped[bool] = mapped_column(default=True)


class RegleTarifaire(Base):
    __tablename__ = "regles_tarifaires"

    id: Mapped[int] = mapped_column(primary_key=True)
    libelle: Mapped[str] = mapped_column(String(80))
    prix_centimes: Mapped[int]
    priorite: Mapped[int] = mapped_column(default=0)
    # critères, None = s'applique à tout. jours : 0 = lundi ... 6 = dimanche
    jours: Mapped[list[int] | None] = mapped_column(ARRAY(SmallInteger))
    type_production: Mapped[str | None] = mapped_column(String(20))
    categorie: Mapped[str | None] = mapped_column(ForeignKey("categories.code", ondelete="CASCADE"))
    evenement_id: Mapped[int | None] = mapped_column(ForeignKey("evenements.id", ondelete="CASCADE"))
    actif: Mapped[bool] = mapped_column(default=True)


class Commande(Base):
    __tablename__ = "commandes"
    __table_args__ = (
        CheckConstraint("statut IN ('en_attente', 'payee', 'expiree', 'annulee')", name="commandes_statut"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reference: Mapped[str] = mapped_column(String(16), unique=True)
    seance_id: Mapped[int] = mapped_column(ForeignKey("seances.id", ondelete="CASCADE"), index=True)
    statut: Mapped[str] = mapped_column(String(12), default="en_attente")
    canal: Mapped[str] = mapped_column(String(8), default="web")
    # places choisies avant paiement : [{siege_id, rang, numero, categorie, libelle, prix_centimes}]
    lignes: Mapped[list] = mapped_column(JSONB)
    montant_centimes: Mapped[int]
    psp_session: Mapped[str | None] = mapped_column(String(64), unique=True)
    cree_le: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expire_le: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payee_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Billet(Base):
    __tablename__ = "billets"
    __table_args__ = (
        # la base arbitre : jamais deux billets valides sur la même place d'une séance
        Index(
            "billets_place_unique",
            "seance_id",
            "siege_id",
            unique=True,
            postgresql_where=text("statut IN ('valide', 'utilise')"),
        ),
        CheckConstraint("statut IN ('valide', 'utilise', 'rembourse')", name="billets_statut"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    commande_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("commandes.id", ondelete="CASCADE"), index=True)
    seance_id: Mapped[int] = mapped_column(ForeignKey("seances.id", ondelete="CASCADE"))
    siege_id: Mapped[int] = mapped_column(ForeignKey("sieges.id", ondelete="CASCADE"))
    categorie: Mapped[str] = mapped_column(String(20))
    libelle_tarif: Mapped[str] = mapped_column(String(80))
    prix_centimes: Mapped[int]
    statut: Mapped[str] = mapped_column(String(12), default="valide")
    jeton: Mapped[str | None] = mapped_column(Text)
    emis_le: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    utilise_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rembourse_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    remboursement_ref: Mapped[str | None] = mapped_column(String(64))


class Controle(Base):
    """Journal des passages au contrôle d'entrée."""

    __tablename__ = "controles"

    id: Mapped[int] = mapped_column(primary_key=True)
    billet_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("billets.id", ondelete="SET NULL"))
    resultat: Mapped[str] = mapped_column(String(24))
    poste: Mapped[str] = mapped_column(String(40), default="")
    cree_le: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class Parametre(Base):
    __tablename__ = "parametres"

    cle: Mapped[str] = mapped_column(String(40), primary_key=True)
    valeur: Mapped[int]
    libelle: Mapped[str] = mapped_column(String(120))


class Compte(Base):
    __tablename__ = "comptes"

    id: Mapped[int] = mapped_column(primary_key=True)
    identifiant: Mapped[str] = mapped_column(String(40), unique=True)
    mot_de_passe: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(12))
