"""Signature des billets en Ed25519.

Le jeton porté par le QR code a la forme  CIN1.<contenu>.<signature>
(base64url sans remplissage). Le contenu est un petit JSON : identifiant du
billet, séance, place et date d'émission. Aucune donnée personnelle.
"""

import base64
import json
import logging
import os
import time
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

log = logging.getLogger(__name__)

PREFIXE = "CIN1"


def b64(donnees: bytes) -> str:
    return base64.urlsafe_b64encode(donnees).rstrip(b"=").decode()


def charger_cle(chemin: str) -> Ed25519PrivateKey:
    """Lit la clé privée ; la crée au premier démarrage si elle n'existe pas encore."""
    fichier = Path(chemin)
    if fichier.exists():
        return serialization.load_pem_private_key(fichier.read_bytes(), password=None)
    cle = Ed25519PrivateKey.generate()
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_bytes(
        cle.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    os.chmod(fichier, 0o600)
    log.warning("nouvelle clé de signature créée dans %s", chemin)
    return cle


def cle_publique_pem(cle: Ed25519PrivateKey) -> str:
    return cle.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()


def signer(cle: Ed25519PrivateKey, billet_id: str, seance_id: int, place: str) -> str:
    contenu = json.dumps(
        {"b": billet_id, "s": seance_id, "p": place, "e": int(time.time())},
        separators=(",", ":"),
    ).encode()
    return f"{PREFIXE}.{b64(contenu)}.{b64(cle.sign(contenu))}"


def est_authentique(cle: Ed25519PrivateKey, jeton: str) -> bool:
    try:
        prefixe, contenu, signature = jeton.split(".")
        if prefixe != PREFIXE:
            return False
        cle.public_key().verify(
            base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4)),
            base64.urlsafe_b64decode(contenu + "=" * (-len(contenu) % 4)),
        )
        return True
    except Exception:
        return False
