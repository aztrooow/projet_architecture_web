#!/usr/bin/env bash
# Construction (et publication) des quatre images de CinetINT.
#
# Les images s'appellent  <REGISTRE>/cinetint-front, cinetint-back,
# cinetint-qr-generator et cinetint-qr-verifier, avec le tag voulu (v1, v2...).
#
# Exemples
#   REGISTRE=ghcr.io/eldertek ./k8s/images.sh construire          # build v1
#   REGISTRE=ghcr.io/eldertek ./k8s/images.sh pousser             # docker push v1
#   REGISTRE=ghcr.io/eldertek TAG=v2 ./k8s/images.sh tout front   # build + push du seul front en v2
#   ./k8s/images.sh kind                                             # charge les images dans le cluster kind local
#
# Variables
#   REGISTRE  préfixe des images (défaut : cinetint-local, pour un usage 100 % local avec kind)
#   TAG       version de l'image (défaut : v1). On change de tag à chaque nouvelle image :
#             le cluster ne retélécharge pas un tag qu'il a déjà en cache (Défi 3 et Défi 8).
#   DOCKER    commande docker à utiliser (défaut : docker)
#   CLUSTER   nom du cluster kind pour la commande « kind » (défaut : cinetint)
#   SOURCE    dossier contenant front/, back/, qr-generator/, qr-verifier/ (défaut : racine du dépôt)
#
# Ce script ne pousse jamais de lui-même : « pousser » et « tout » sont des demandes explicites,
# et il refuse de pousser vers le registre local factice.
set -euo pipefail

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REGISTRE="${REGISTRE:-cinetint-local}"
TAG="${TAG:-v1}"
DOCKER="${DOCKER:-docker}"
CLUSTER="${CLUSTER:-cinetint}"
SOURCE="${SOURCE:-$RACINE}"
TOUS=(front back qr-generator qr-verifier)

usage() {
    sed -n '2,23p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

action="${1:-}"
[ -n "$action" ] || usage 1
shift || true
services=("$@")
[ "${#services[@]}" -gt 0 ] || services=("${TOUS[@]}")

for s in "${services[@]}"; do
    case " ${TOUS[*]} " in
        *" $s "*) ;;
        *) echo "Service inconnu : $s (attendu : ${TOUS[*]})" >&2; exit 1 ;;
    esac
done

construire() {
    for s in "${services[@]}"; do
        echo "==> build $REGISTRE/cinetint-$s:$TAG"
        # la dernière étape de chaque Dockerfile est l'image de production (les étapes « tests » sont à part)
        "$DOCKER" build -t "$REGISTRE/cinetint-$s:$TAG" "$SOURCE/$s"
    done
}

pousser() {
    if [ "$REGISTRE" = "cinetint-local" ]; then
        echo "REGISTRE n'est pas défini : rien à pousser (exemple : REGISTRE=ghcr.io/eldertek)." >&2
        exit 1
    fi
    for s in "${services[@]}"; do
        echo "==> push $REGISTRE/cinetint-$s:$TAG"
        "$DOCKER" push "$REGISTRE/cinetint-$s:$TAG"
    done
}

charger_kind() {
    for s in "${services[@]}"; do
        echo "==> kind load $REGISTRE/cinetint-$s:$TAG"
        kind load docker-image "$REGISTRE/cinetint-$s:$TAG" --name "$CLUSTER"
    done
}

case "$action" in
    construire) construire ;;
    pousser) pousser ;;
    tout) construire; pousser ;;
    kind) charger_kind ;;
    -h|--help|aide) usage 0 ;;
    *) usage 1 ;;
esac
