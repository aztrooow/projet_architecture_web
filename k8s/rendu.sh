#!/usr/bin/env bash
# Fabrique l'archive de rendu du projet Kubernetes : un dossier par défi (defi1, defi2, ...), chacun avec ses
# fichiers de configuration ou ses commandes, son schéma (schema.svg) et ses réponses (reponses.md), plus les fichiers
# communs que les commandes appellent (charte Helm, outils, scripts).
#
#   REGISTRE=ghcr.io/eldertek ./k8s/rendu.sh              crée rendu-kubernetes.tar.gz et rendu-kubernetes.zip dans le dossier courant
#   REGISTRE=ghcr.io/eldertek ./k8s/rendu.sh /chemin/rendu   (sans extension : crée /chemin/rendu.tar.gz et /chemin/rendu.zip)
#
# REGISTRE : le registre d'images réellement utilisé. Le texte REGISTRE_IMAGES des manifests y est remplacé, pour que
# les fichiers de l'archive soient ceux qui ont été appliqués. Sans REGISTRE, les manifests gardent REGISTRE_IMAGES.
set -euo pipefail

ICI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPOT="$(cd "$ICI/.." && pwd)"
SORTIE="${1:-rendu-kubernetes}"
case "$SORTIE" in /*) ;; *) SORTIE="$PWD/$SORTIE" ;; esac
NOM="$(basename "$SORTIE")"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
RACINE="$TMP/$NOM"
mkdir -p "$RACINE"

DEFIS=(1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 18 19 20)

for n in "${DEFIS[@]}"; do
    [ -d "$ICI/defi$n" ] || { echo "dossier defi$n manquant" >&2; exit 1; }
    cp -r "$ICI/defi$n" "$RACINE/defi$n"
done

# le workflow du défi 19 vit dans .github/workflows : on en joint une copie au dossier du défi
cp "$DEPOT/.github/workflows/ci.yml" "$RACINE/defi19/ci.yml"

# fichiers communs : charte Helm, outils de démonstration, scripts d'application
cp -r "$ICI/helm" "$RACINE/helm"
mkdir -p "$RACINE/outils"
for f in parcours.py demo-replication.sh demo-redis.sh demo-securite.sh demo-migration.sh test-networkpolicy.sh kind-creer.sh generer_schemas.py; do
    cp "$ICI/outils/$f" "$RACINE/outils/$f"
done
cp "$ICI/appliquer.sh" "$ICI/images.sh" "$RACINE/"
cp "$ICI/README.md" "$RACINE/LISEZMOI.md"

# nettoyage et remplacement du registre
find "$RACINE" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "$RACINE" -name '*.tgz' -delete
if [ -n "${REGISTRE:-}" ]; then
    while IFS= read -r f; do sed -i "s#REGISTRE_IMAGES#${REGISTRE}#g" "$f"; done \
        < <(grep -rl 'REGISTRE_IMAGES' "$RACINE" --include='*.yaml' --include='*.txt' --include='*.md' || true)
fi

# les commandes écrites pour k8s/defiN restent valides : ../helm, ../outils et ../appliquer.sh existent à la racine de l'archive
( cd "$TMP" && tar -czf "$SORTIE.tar.gz" "$NOM" )
( cd "$TMP" && python3 - "$NOM" "$SORTIE.zip" <<'PY'
import os, sys, zipfile
dossier, cible = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(cible, "w", zipfile.ZIP_DEFLATED) as z:
    for racine, _, fichiers in os.walk(dossier):
        for f in sorted(fichiers):
            chemin = os.path.join(racine, f)
            z.write(chemin, chemin)
PY
)
echo "archives créées : $SORTIE.tar.gz et $SORTIE.zip"
tar -tzf "$SORTIE.tar.gz" | grep -E '^[^/]+/defi[0-9]+/$' | sort -V | tr '\n' ' '; echo
