"""Accès au prestataire de paiement du cinéma.

Le cinéma a déjà un prestataire : on passe par une interface pour pouvoir le
brancher sans toucher au reste. En attendant, PrestataireSimule joue son rôle
(page de paiement factice côté front). Aucune donnée de carte ne transite par
nos services, c'est le prestataire qui la reçoit.
"""

import secrets
from typing import Protocol


class Prestataire(Protocol):
    async def creer_session(self, reference: str, montant_centimes: int) -> str: ...

    async def rembourser(self, session: str, montant_centimes: int) -> str: ...


class PrestataireSimule:
    async def creer_session(self, reference: str, montant_centimes: int) -> str:
        return "ps_" + secrets.token_urlsafe(18)

    async def rembourser(self, session: str, montant_centimes: int) -> str:
        return "rb_" + secrets.token_urlsafe(12)


prestataire: Prestataire = PrestataireSimule()
