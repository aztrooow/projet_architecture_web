"""Schéma initial : les douze tables de la billetterie.

Produite par « alembic revision --autogenerate » puis relue : elle reproduit
exactement app/models.py (colonnes, clés étrangères, contraintes d'unicité et de
statut, index unique partiel contre la double réservation).

Revision ID: 0001
Revises:
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('categories',
    sa.Column('code', sa.String(length=20), nullable=False),
    sa.Column('libelle', sa.String(length=60), nullable=False),
    sa.Column('ordre', sa.Integer(), nullable=False),
    sa.Column('actif', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('code')
    )
    op.create_table('comptes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('identifiant', sa.String(length=40), nullable=False),
    sa.Column('mot_de_passe', sa.String(length=255), nullable=False),
    sa.Column('role', sa.String(length=12), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('identifiant')
    )
    op.create_table('evenements',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nom', sa.String(length=120), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('films',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('titre', sa.String(length=120), nullable=False),
    sa.Column('realisation', sa.String(length=120), nullable=False),
    sa.Column('annee', sa.Integer(), nullable=True),
    sa.Column('duree_min', sa.Integer(), nullable=False),
    sa.Column('genre', sa.String(length=40), nullable=False),
    sa.Column('synopsis', sa.Text(), nullable=False),
    sa.Column('type_production', sa.String(length=20), nullable=False),
    sa.Column('couleur', sa.String(length=7), nullable=False),
    sa.Column('affiche_url', sa.String(length=300), nullable=True),
    sa.Column('image_url', sa.String(length=300), nullable=True),
    sa.Column('source_id', sa.String(length=40), nullable=True),
    sa.Column('actif', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source_id')
    )
    op.create_table('parametres',
    sa.Column('cle', sa.String(length=40), nullable=False),
    sa.Column('valeur', sa.Integer(), nullable=False),
    sa.Column('libelle', sa.String(length=120), nullable=False),
    sa.PrimaryKeyConstraint('cle')
    )
    op.create_table('salles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nom', sa.String(length=40), nullable=False),
    sa.Column('capacite', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('regles_tarifaires',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('libelle', sa.String(length=80), nullable=False),
    sa.Column('prix_centimes', sa.Integer(), nullable=False),
    sa.Column('priorite', sa.Integer(), nullable=False),
    sa.Column('jours', postgresql.ARRAY(sa.SmallInteger()), nullable=True),
    sa.Column('type_production', sa.String(length=20), nullable=True),
    sa.Column('categorie', sa.String(length=20), nullable=True),
    sa.Column('evenement_id', sa.Integer(), nullable=True),
    sa.Column('actif', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['categorie'], ['categories.code'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['evenement_id'], ['evenements.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('seances',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('film_id', sa.Integer(), nullable=False),
    sa.Column('salle_id', sa.Integer(), nullable=False),
    sa.Column('debut', sa.DateTime(timezone=True), nullable=False),
    sa.Column('version', sa.String(length=8), nullable=False),
    sa.Column('evenement_id', sa.Integer(), nullable=True),
    sa.Column('source_id', sa.String(length=40), nullable=True),
    sa.ForeignKeyConstraint(['evenement_id'], ['evenements.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['film_id'], ['films.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['salle_id'], ['salles.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source_id')
    )
    op.create_index(op.f('ix_seances_debut'), 'seances', ['debut'], unique=False)
    op.create_index(op.f('ix_seances_film_id'), 'seances', ['film_id'], unique=False)
    op.create_table('sieges',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('salle_id', sa.Integer(), nullable=False),
    sa.Column('rang', sa.String(length=2), nullable=False),
    sa.Column('numero', sa.Integer(), nullable=False),
    sa.Column('x', sa.Integer(), nullable=False),
    sa.Column('y', sa.Integer(), nullable=False),
    sa.Column('pmr', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['salle_id'], ['salles.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('salle_id', 'rang', 'numero')
    )
    op.create_index(op.f('ix_sieges_salle_id'), 'sieges', ['salle_id'], unique=False)
    op.create_table('commandes',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('reference', sa.String(length=16), nullable=False),
    sa.Column('seance_id', sa.Integer(), nullable=False),
    sa.Column('statut', sa.String(length=12), nullable=False),
    sa.Column('canal', sa.String(length=8), nullable=False),
    sa.Column('lignes', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('montant_centimes', sa.Integer(), nullable=False),
    sa.Column('psp_session', sa.String(length=64), nullable=True),
    sa.Column('cree_le', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expire_le', sa.DateTime(timezone=True), nullable=False),
    sa.Column('payee_le', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("statut IN ('en_attente', 'payee', 'expiree', 'annulee')", name='commandes_statut'),
    sa.ForeignKeyConstraint(['seance_id'], ['seances.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('psp_session'),
    sa.UniqueConstraint('reference')
    )
    op.create_index(op.f('ix_commandes_seance_id'), 'commandes', ['seance_id'], unique=False)
    op.create_table('billets',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('commande_id', sa.UUID(), nullable=False),
    sa.Column('seance_id', sa.Integer(), nullable=False),
    sa.Column('siege_id', sa.Integer(), nullable=False),
    sa.Column('categorie', sa.String(length=20), nullable=False),
    sa.Column('libelle_tarif', sa.String(length=80), nullable=False),
    sa.Column('prix_centimes', sa.Integer(), nullable=False),
    sa.Column('statut', sa.String(length=12), nullable=False),
    sa.Column('jeton', sa.Text(), nullable=True),
    sa.Column('emis_le', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('utilise_le', sa.DateTime(timezone=True), nullable=True),
    sa.Column('rembourse_le', sa.DateTime(timezone=True), nullable=True),
    sa.Column('remboursement_ref', sa.String(length=64), nullable=True),
    sa.CheckConstraint("statut IN ('valide', 'utilise', 'rembourse')", name='billets_statut'),
    sa.ForeignKeyConstraint(['commande_id'], ['commandes.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['seance_id'], ['seances.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['siege_id'], ['sieges.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('billets_place_unique', 'billets', ['seance_id', 'siege_id'], unique=True, postgresql_where=sa.text("statut IN ('valide', 'utilise')"))
    op.create_index(op.f('ix_billets_commande_id'), 'billets', ['commande_id'], unique=False)
    op.create_table('controles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('billet_id', sa.UUID(), nullable=True),
    sa.Column('resultat', sa.String(length=24), nullable=False),
    sa.Column('poste', sa.String(length=40), nullable=False),
    sa.Column('cree_le', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['billet_id'], ['billets.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_controles_cree_le'), 'controles', ['cree_le'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_controles_cree_le'), table_name='controles')
    op.drop_table('controles')
    op.drop_index(op.f('ix_billets_commande_id'), table_name='billets')
    op.drop_index('billets_place_unique', table_name='billets', postgresql_where=sa.text("statut IN ('valide', 'utilise')"))
    op.drop_table('billets')
    op.drop_index(op.f('ix_commandes_seance_id'), table_name='commandes')
    op.drop_table('commandes')
    op.drop_index(op.f('ix_sieges_salle_id'), table_name='sieges')
    op.drop_table('sieges')
    op.drop_index(op.f('ix_seances_film_id'), table_name='seances')
    op.drop_index(op.f('ix_seances_debut'), table_name='seances')
    op.drop_table('seances')
    op.drop_table('regles_tarifaires')
    op.drop_table('salles')
    op.drop_table('parametres')
    op.drop_table('films')
    op.drop_table('evenements')
    op.drop_table('comptes')
    op.drop_table('categories')
