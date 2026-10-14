#!/bin/sh
# Démarrage du conteneur back : migrations, fixtures, puis le serveur.
# Plusieurs répliques peuvent passer ici en même temps : les migrations et le
# chargement des fixtures sont protégés par un verrou consultatif PostgreSQL.
set -e

echo "[back] migrations Alembic"
essais=0
until alembic upgrade head; do
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
