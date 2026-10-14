"""Expand : ajoute commandes.canal_detail (étape 1 d'une migration sans interruption).

Exemple du Défi 20. Cette migration est COMPATIBLE avec l'ancienne version du code :
  * la colonne est ajoutée avec une valeur par défaut CONSTANTE : PostgreSQL (11 et plus) ne réécrit pas
    la table, la colonne est ajoutée en quelques millisecondes ;
  * l'ancien code ne connaît pas la colonne : ses INSERT l'omettent et la base met la valeur par défaut,
    ses SELECT ne la demandent pas. Il continue donc de fonctionner pendant et après la migration ;
  * lock_timeout : ALTER TABLE prend un verrou exclusif bref. S'il doit attendre plus de 5 s derrière une
    transaction longue, la migration échoue (et l'entrypoint la relance) plutôt que de bloquer toutes les
    requêtes qui font la queue derrière lui.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.add_column(
        "commandes",
        sa.Column("canal_detail", sa.String(length=24), nullable=False, server_default="standard"),
    )


def downgrade() -> None:
    # à n'utiliser qu'une fois l'ancien code retiré (étape « contract » à l'envers)
    op.drop_column("commandes", "canal_detail")
