#!/bin/sh
# Démarrage du conteneur back : migrations, fixtures, puis le serveur.
# Plusieurs répliques peuvent passer ici en même temps : les migrations et le
# chargement des fixtures sont protégés par un verrou consultatif PostgreSQL.
set -e

echo "[back] migrations Alembic"
essais=0
until alembic upgrade head 2>/tmp/alembic.err; do
    cat /tmp/alembic.err >&2
    # Retour arrière (rollback) vers une image plus ancienne : la base porte déjà une
    # révision que ce code ne connaît pas. Les migrations restent compatibles avec la
    # version précédente (ajouts seulement), on démarre donc sans migrer.
    if grep -q "Can't locate revision" /tmp/alembic.err; then
        echo "[back] base en avance sur ce code (révision plus récente), démarrage sans migration" >&2
        break
    fi
    essais=$((essais + 1))
    if [ "$essais" -ge 15 ]; then
        echo "[back] migrations impossibles après $essais essais" >&2
        exit 1
    fi
    echo "[back] base indisponible ou migration en échec, nouvel essai dans 2 s ($essais/15)" >&2
    sleep 2
done

echo "[back] chargement des fixtures"
python -m app.fixtures

echo "[back] démarrage de l'API"
exec "$@"
