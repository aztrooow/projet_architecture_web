#!/usr/bin/env bash
# Défi 20 : migration de base de données sans interruption, sous charge d'écriture et de lecture continues.
# Trois phases : A (back v1 -> v2, Alembic reconnaît le schéma existant), B (back v2 -> v3, migration expand 0002),
# C (tentative de retour arrière du code vers v2 : voir la limite décrite dans k8s/defi20/reponses.md).
#
#   N=u-XXX BASE=https://django.MONGROUPE.csc8567.luxbulb.org VALEURS_COURS=k8s/helm/cinetint/values-cours.yaml \
#     HELM_SUP="--set images.registre=ghcr.io/eldertek --set ingress.host=django.MONGROUPE.csc8567.luxbulb.org" \
#     ./k8s/outils/demo-migration.sh
#   N=u-test ./k8s/outils/demo-migration.sh                      (cluster kind local, images cinetint-local/...:v1, v2, v3)
# Prérequis : image back v3 construite (k8s/defi20/construire-v3.sh) et disponible pour le cluster.
set -uo pipefail
N=${N:?Renseigner N (namespace)}
BASE=${BASE:-http://localhost:8080}
HOTE=${HOTE:-cinetint.test}
DEPOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CHARTE="$DEPOT/k8s/helm/cinetint"
VALEURS_COURS=${VALEURS_COURS:-$CHARTE/values-kind.yaml}
HELM_SUP=${HELM_SUP:-}
POD_BASE=${POD_BASE:-postgres-primaire-0}

Q() { kubectl exec "$POD_BASE" -n "$N" -c postgres -- psql -U cinetint -d cinetint -Atc "$1"; }

lecture() { # durée fichier : une requête GET toutes les 0,2 s sur trois routes, un code HTTP par ligne
    local fin=$(( $(date +%s) + $1 ))
    : > "$2"
    while [ "$(date +%s)" -lt "$fin" ]; do
        for p in / /api/sante /api/programme; do
            echo "$(date +%T) $p $(curl -sk -o /dev/null -m 5 -w '%{http_code}' -H "Host: $HOTE" "$BASE$p")" >> "$2"
        done
        sleep 0.2
    done
}

phase() { # titre, puis la commande helm
    echo "=== $1"; shift
    python3 "$DEPOT/k8s/defi20/ecritures.py" "$BASE" --hote "$HOTE" --duree 100 > /tmp/ecritures.txt &
    local ecr=$!
    lecture 100 /tmp/lecture.log &
    local lec=$!
    sleep 8
    "$@" 2>&1 | grep -E 'STATUS|REVISION|Error|Rollback'
    kubectl rollout status deployment/back -n "$N" --timeout=300s | tail -1
    wait "$ecr"; wait "$lec"
    cat /tmp/ecritures.txt
    printf 'lectures (codes HTTP) : '; awk '{print $3}' /tmp/lecture.log | sort | uniq -c | tr '\n' ' '; echo
}

upgrade() { helm upgrade cinetint "$CHARTE" -n "$N" -f "$VALEURS_COURS" -f "$DEPOT/k8s/defi20/values-defi20.yaml" $HELM_SUP --timeout 10m "$@"; }

echo "version alembic avant : $(Q 'select version_num from alembic_version' 2>&1 | head -1)"
echo "billets avant : $(Q 'select count(*) from billets')"

phase "A. back v1 (create_all) vers v2 (Alembic)" upgrade
echo "version alembic : $(Q 'select version_num from alembic_version')"

phase "B. back v2 vers v3 (migration expand 0002)" upgrade --set images.tags.back=v3
echo "version alembic : $(Q 'select version_num from alembic_version')"
Q "select column_name, data_type, column_default, is_nullable from information_schema.columns where table_name='commandes' and column_name='canal_detail'"
Q "select canal_detail, count(*) from commandes group by 1"
echo "billets après : $(Q 'select count(*) from billets')"

phase "C. retour arrière du code (helm rollback) sans toucher au schéma" helm rollback cinetint -n "$N" --timeout 10m
echo "version alembic (inchangée) : $(Q 'select version_num from alembic_version')"
echo "Pour revenir à un état sain après C : helm upgrade ... --set images.tags.back=v3"
