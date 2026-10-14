#!/usr/bin/env bash
# Applique (ou supprime) les manifests d'un défi fait de fichiers YAML simples (Défis 2 à 5 et 12).
# Les défis 6 et suivants passent par la charte Helm : voir leur commandes.txt.
#
# Usage
#   NAMESPACE=u-XXX REGISTRE=ghcr.io/eldertek ./k8s/appliquer.sh defi5            applique tous les .yaml du dossier
#   NAMESPACE=u-XXX ./k8s/appliquer.sh defi5 supprimer                              supprime ce que le défi a créé
#   NAMESPACE=u-XXX ./k8s/appliquer.sh secrets                                      crée les Secrets des Défis 3 à 5 (une seule fois)
#   NAMESPACE=u-XXX ./k8s/appliquer.sh secrets-postgres                             crée le Secret du Défi 12
#
# Le texte REGISTRE_IMAGES des manifests est remplacé par $REGISTRE (défaut : cinetint-local, pour kind)
# et HOTE_SITE par $HOTE (ex. django.monGroupe.csc8567.luxbulb.org ; défaut : cinetint.test).
# Pourquoi un script : le registre d images change d'un groupe à l'autre. Dans l'archive de
# rendu (rendu.sh), le texte est déjà remplacé par le registre réellement utilisé.
set -euo pipefail

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE="${NAMESPACE:?Renseigner NAMESPACE (ex. NAMESPACE=u-XXX)}"
REGISTRE="${REGISTRE:-cinetint-local}"
HOTE="${HOTE:-cinetint.test}"
cible="${1:?Usage : appliquer.sh defiN [supprimer] | appliquer.sh secrets}"
action="${2:-appliquer}"

if [ "$cible" = "secrets" ]; then
    # Secrets générés à la volée : rien n'est écrit dans le dépôt.
    aleatoire() { head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c "${1:-24}"; }
    if ! kubectl get secret cinetint-secrets -n "$NAMESPACE" >/dev/null 2>&1; then
        kubectl create secret generic cinetint-secrets -n "$NAMESPACE" \
            --from-literal=POSTGRES_PASSWORD="$(aleatoire 24)" \
            --from-literal=REPLICATION_PASSWORD="$(aleatoire 24)" \
            --from-literal=SERVICE_TOKEN="$(aleatoire 32)" \
            --from-literal=JWT_SECRET="$(aleatoire 48)" \
            --from-literal=GERANT_MOT_DE_PASSE="$(aleatoire 16)" \
            --from-literal=CONTROLEUR_MOT_DE_PASSE="$(aleatoire 16)"
    else
        echo "Secret cinetint-secrets déjà présent"
    fi
    if ! kubectl get secret cinetint-cle -n "$NAMESPACE" >/dev/null 2>&1; then
        # clé privée Ed25519 de signature des billets, commune à toutes les répliques du qr-generator
        tmp="$(mktemp)"; trap 'rm -f "$tmp"' EXIT
        openssl genpkey -algorithm ed25519 -out "$tmp"
        kubectl create secret generic cinetint-cle -n "$NAMESPACE" --from-file=cle-ed25519.pem="$tmp"
    else
        echo "Secret cinetint-cle déjà présent"
    fi
    exit 0
fi

if [ "$cible" = "secrets-postgres" ]; then
    # Défi 12 : mots de passe du primaire et du compte de réplication
    if ! kubectl get secret postgres-secrets -n "$NAMESPACE" >/dev/null 2>&1; then
        aleatoire() { head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c "${1:-24}"; }
        kubectl create secret generic postgres-secrets -n "$NAMESPACE"             --from-literal=POSTGRES_PASSWORD="$(aleatoire 24)"             --from-literal=REPLICATION_PASSWORD="$(aleatoire 24)"
    else
        echo "Secret postgres-secrets déjà présent"
    fi
    exit 0
fi

dossier="$RACINE/$cible"
[ -d "$dossier" ] || { echo "Dossier introuvable : $dossier" >&2; exit 1; }

fichiers=()
while IFS= read -r f; do fichiers+=("$f"); done < <(find "$dossier" -maxdepth 1 -name '*.yaml' ! -name 'values*.yaml' ! -name 'restaurer*.yaml' | sort)
[ "${#fichiers[@]}" -gt 0 ] || { echo "Aucun manifest dans $dossier" >&2; exit 1; }

for f in "${fichiers[@]}"; do
    case "$action" in
        appliquer) sed -e "s#REGISTRE_IMAGES#${REGISTRE}#g" -e "s#HOTE_SITE#${HOTE}#g" "$f" | kubectl apply -n "$NAMESPACE" -f - ;;
        supprimer) sed -e "s#REGISTRE_IMAGES#${REGISTRE}#g" -e "s#HOTE_SITE#${HOTE}#g" "$f" | kubectl delete -n "$NAMESPACE" --ignore-not-found -f - ;;
        *) echo "Action inconnue : $action" >&2; exit 1 ;;
    esac
done
