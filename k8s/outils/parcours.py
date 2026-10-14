#!/usr/bin/env python3
"""Test de fumée de CinetINT sur un déploiement Kubernetes (ou Docker), bibliothèque standard seulement.

Rejoue le parcours complet d'un spectateur puis d'un contrôleur :
  sondes de santé des quatre services, programme, plan de salle, réservation de deux places,
  paiement simulé, billets, image du QR code (qr-generator), contrôle d'entrée (qr-verifier),
  seconde présentation refusée, et route /internal jamais exposée.

Usage
  python3 k8s/outils/parcours.py http://localhost:8080 --hote cinetint.test --controleur MOT_DE_PASSE
  python3 k8s/outils/parcours.py http://localhost:8080 --hote cinetint.test --controleur "$(kubectl get secret cinetint-secrets -o jsonpath='{.data.CONTROLEUR_MOT_DE_PASSE}' | base64 -d)"

Code de sortie : 0 si tout passe, 1 sinon.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone


class Client:
    def __init__(self, base: str, hote: str | None, verifier_tls: bool):
        self.base = base.rstrip("/")
        self.hote = hote
        self.contexte = None
        if base.startswith("https") and not verifier_tls:
            import ssl

            self.contexte = ssl._create_unverified_context()

    def appel(self, methode: str, chemin: str, corps=None, jeton: str | None = None):
        entetes = {"Accept": "application/json"}
        if self.hote:
            entetes["Host"] = self.hote
        if jeton:
            entetes["Authorization"] = f"Bearer {jeton}"
        donnees = None
        if corps is not None:
            donnees = json.dumps(corps).encode()
            entetes["Content-Type"] = "application/json"
        requete = urllib.request.Request(self.base + chemin, data=donnees, method=methode, headers=entetes)
        try:
            with urllib.request.urlopen(requete, timeout=20, context=self.contexte) as reponse:
                brut = reponse.read()
                return reponse.status, brut
        except urllib.error.HTTPError as erreur:
            return erreur.code, erreur.read()

    def json(self, *args, **kwargs):
        statut, brut = self.appel(*args, **kwargs)
        try:
            return statut, json.loads(brut)
        except ValueError:
            return statut, None


echecs = 0


def verifier(libelle: str, condition: bool, detail: str = "") -> None:
    global echecs
    print(f"{'OK  ' if condition else 'ECHEC'} {libelle}" + (f" ({detail})" if detail else ""))
    if not condition:
        echecs += 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("base", help="adresse de l'Ingress, ex. http://localhost:8080")
    parser.add_argument("--hote", help="en-tête Host à envoyer (Ingress sans DNS)")
    parser.add_argument("--controleur", default="controleur", help="mot de passe du compte « controleur »")
    parser.add_argument("--tls-verifier", action="store_true", help="vérifier le certificat HTTPS")
    parser.add_argument("--repetitions-qr", type=int, default=12, help="nombre de lectures de l'image du QR code")
    parser.add_argument("--attente", type=int, default=0, help="secondes d'attente maximale que le site réponde")
    args = parser.parse_args()
    c = Client(args.base, args.hote, args.tls_verifier)

    # 0. attente éventuelle (démarrage du cluster, mise à jour en cours)
    limite = time.time() + args.attente
    while True:
        try:
            if c.appel("GET", "/api/sante")[0] == 200:
                break
        except OSError:
            pass
        if time.time() >= limite:
            break
        time.sleep(3)

    # 1. sondes de santé, par l'Ingress
    for chemin in ("/sante", "/api/sante", "/qr/sante", "/verification/sante"):
        statut, _ = c.appel("GET", chemin)
        verifier(f"sonde {chemin}", statut == 200, f"HTTP {statut}")

    # 2. programme et plan de salle
    statut, programme = c.json("GET", "/api/programme")
    verifier("programme", statut == 200 and bool(programme and programme["films"]), f"HTTP {statut}")
    maintenant = datetime.now(timezone.utc)
    seances = [
        s
        for f in programme["films"]
        for s in f["seances"]
        if (datetime.fromisoformat(s["debut"]) - maintenant).total_seconds() > 1800
    ]
    verifier("une séance à venir existe", bool(seances))
    if not seances:
        return 1
    seance = seances[-1]
    statut, plan = c.json("GET", f"/api/seances/{seance['id']}/plan")
    libres = [s["id"] for s in plan["sieges"] if s["etat"] == "libre"]
    verifier("plan de salle avec des places libres", statut == 200 and len(libres) >= 2, f"{len(libres)} libres")

    # 3. réservation, paiement simulé, billets
    places = [{"siege_id": libres[-1], "categorie": "plein"}, {"siege_id": libres[-2], "categorie": "etudiant"}]
    statut, commande = c.json("POST", "/api/commandes", {"seance_id": seance["id"], "places": places})
    verifier("réservation de deux places (verrous Redis)", statut == 201, f"HTTP {statut}")
    if statut != 201:
        print(commande)
        return 1
    statut, paiement = c.json("POST", f"/api/paiement-simule/{commande['psp_session']}", {"resultat": "accepte"})
    verifier("paiement accepté (signature des billets par le qr-generator)", statut == 200 and paiement["statut"] == "payee", f"HTTP {statut}")
    statut, detail = c.json("GET", f"/api/commandes/{commande['id']}")
    billets = detail["billets"] if detail else []
    verifier("deux billets émis", statut == 200 and len(billets) == 2)
    jeton = billets[0]["jeton"]
    # plusieurs essais : le Service répartit les requêtes entre les répliques du qr-generator,
    # qui doivent toutes reconnaître le billet (clé de signature commune)
    codes = [c.appel("GET", f"/qr/{jeton}.svg")[0] for _ in range(args.repetitions_qr)]
    verifier(f"image du QR code, {args.repetitions_qr} essais", set(codes) == {200}, "codes " + ",".join(map(str, codes)))
    statut, pdf = c.appel("GET", f"/api/commandes/{commande['id']}/billets.pdf")
    verifier("PDF des billets", statut == 200 and pdf[:4] == b"%PDF", f"HTTP {statut}")

    # 4. contrôle d'entrée : accepté une fois, refusé la seconde
    statut, connexion = c.json("POST", "/api/auth/connexion", {"identifiant": "controleur", "mot_de_passe": args.controleur})
    verifier("connexion du contrôleur", statut == 200, f"HTTP {statut}")
    if statut == 200:
        statut, verdict = c.json("POST", "/verification", {"jeton": jeton, "poste": "test"}, jeton=connexion["jeton"])
        verifier("premier passage accepté", statut == 200 and verdict["verdict"] == "accepte", str(verdict and verdict.get("code")))
        statut, verdict = c.json("POST", "/verification", {"jeton": jeton, "poste": "test"}, jeton=connexion["jeton"])
        verifier("second passage refusé", statut == 200 and verdict["verdict"] == "refuse", str(verdict and verdict.get("code")))
        statut, verdict = c.json("POST", "/verification", {"jeton": jeton[:-4] + "AAAA", "poste": "test"}, jeton=connexion["jeton"])
        verifier("faux billet refusé", statut == 200 and verdict["verdict"] == "refuse")

    # 5. routes entre services : jamais exposées
    statut, _ = c.appel("POST", f"/internal/billets/{billets[1]['id']}/utiliser", {})
    verifier("/internal inaccessible depuis l'extérieur", statut in (403, 404), f"HTTP {statut}")

    print("\nRésultat :", "tout passe" if not echecs else f"{echecs} échec(s)")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
