#!/usr/bin/env python3
"""Charge d'écriture continue pour éprouver une migration : crée puis annule une commande, en boucle.

Chaque tour écrit en base (INSERT puis UPDATE de la commande) et dans Redis (verrous de sièges posés puis libérés),
donc exerce exactement le code touché par la migration. Aucune place n'est consommée.

  python3 k8s/defi20/ecritures.py http://localhost:8080 --hote cinetint.test --duree 120
Sortie : nombre de tours réussis et d'erreurs, avec la date de la première erreur éventuelle.
"""

import argparse
import json
import random
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone


def appel(base, hote, methode, chemin, corps=None):
    entetes = {"Host": hote} if hote else {}
    donnees = None
    if corps is not None:
        donnees = json.dumps(corps).encode()
        entetes["Content-Type"] = "application/json"
    requete = urllib.request.Request(base + chemin, data=donnees, method=methode, headers=entetes)
    try:
        with urllib.request.urlopen(requete, timeout=10) as reponse:
            brut = reponse.read()
            return reponse.status, (json.loads(brut) if brut else None)
    except urllib.error.HTTPError as erreur:
        return erreur.code, None
    except OSError:
        return 0, None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base")
    parser.add_argument("--hote")
    parser.add_argument("--duree", type=int, default=60)
    parser.add_argument("--journal", help="fichier où écrire une ligne par tour (heure, code)")
    args = parser.parse_args()
    base = args.base.rstrip("/")

    _, programme = appel(base, args.hote, "GET", "/api/programme")
    maintenant = datetime.now(timezone.utc)
    seances = [
        s for f in programme["films"] for s in f["seances"]
        if (datetime.fromisoformat(s["debut"]) - maintenant).total_seconds() > 1800
    ]
    seance = seances[-1]["id"]
    _, plan = appel(base, args.hote, "GET", f"/api/seances/{seance}/plan")
    libres = [s["id"] for s in plan["sieges"] if s["etat"] == "libre"]

    ok = erreurs = 0
    premiere = None
    journal = open(args.journal, "w") if args.journal else None
    fin = time.time() + args.duree
    while time.time() < fin:
        siege = random.choice(libres)
        c1, commande = appel(base, args.hote, "POST", "/api/commandes",
                             {"seance_id": seance, "places": [{"siege_id": siege, "categorie": "plein"}]})
        c2 = 0
        if c1 == 201:
            c2, _ = appel(base, args.hote, "DELETE", f"/api/commandes/{commande['id']}")
        bon = c1 == 201 and c2 in (200, 204)
        if bon:
            ok += 1
        else:
            erreurs += 1
            premiere = premiere or datetime.now().strftime("%H:%M:%S")
        if journal:
            journal.write(f"{datetime.now():%H:%M:%S} {c1} {c2}\n")
        time.sleep(0.15)
    print(f"tours réussis : {ok}, erreurs : {erreurs}" + (f", première erreur à {premiere}" if premiere else ""))
    return 1 if erreurs else 0


if __name__ == "__main__":
    sys.exit(main())
