#!/usr/bin/env bash
# Défi 20 : construit une image back « v3 » qui contient la migration d'exemple (expand) et le champ
# correspondant du modèle, SANS toucher au dépôt : on part d'une copie propre d'un commit (git archive).
#
#   REGISTRE=ghcr.io/eldertek ./k8s/defi20/construire-v3.sh            construit <registre>/cinetint-back:v3
#   REF=40bad0b ./k8s/defi20/construire-v3.sh                              commit de départ (défaut : HEAD)
# Dans un vrai projet, on ajouterait simplement la migration et le champ dans le dépôt.
set -euo pipefail
ICI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPOT="$(cd "$ICI/../.." && pwd)"
REGISTRE="${REGISTRE:-cinetint-local}"
REF="${REF:-HEAD}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
git -C "$DEPOT" archive "$REF" | tar -x -C "$TMP"
cp "$ICI/exemple-migration/0002_expand_canal_detail.py" "$TMP/back/migrations/versions/"
python3 - "$TMP/back/app/models.py" <<'PY'
import re, sys
chemin = sys.argv[1]
source = open(chemin, encoding="utf8").read()
ligne = "    payee_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))\n"
assert source.count(ligne) == 1, "ligne payee_le introuvable ou ambiguë"
ajout = '    canal_detail: Mapped[str] = mapped_column(String(24), server_default="standard")\n'
open(chemin, "w", encoding="utf8").write(source.replace(ligne, ligne + ajout))
PY
"${DOCKER:-docker}" build -t "$REGISTRE/cinetint-back:v3" "$TMP/back"
echo "image construite : $REGISTRE/cinetint-back:v3"
