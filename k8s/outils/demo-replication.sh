#!/usr/bin/env bash
# Démonstration de la réplication PostgreSQL (Défis 12 et 13) : écriture sur le primaire, lecture sur la réplique,
# écriture refusée sur la réplique, pg_stat_replication, pg_stat_wal_receiver, accès par les deux Services.
#   N=u-XXX ./k8s/outils/demo-replication.sh                         (Défi 12 : Secret postgres-secrets)
#   N=u-XXX SECRET=cinetint-secrets ./k8s/outils/demo-replication.sh   (Défi 13 : Secret de la charte)
# Variables : N (namespace), PRIM et REPL (noms des Pods), SECRET.
N=${N:-u-test}; P=${PRIM:-postgres-primaire-0}; R=${REPL:-postgres-replique-0}
q() { kubectl exec "$1" -n $N -c postgres -- psql -U cinetint -d cinetint -P pager=off "${@:2}"; }
echo "## 1. la réplique est bien une réplique"; q $R -c "SELECT pg_is_in_recovery() AS en_replication"; q $P -c "SELECT pg_is_in_recovery() AS en_replication"
echo "## 2. écriture sur le primaire (service postgres)"; q $P -c "CREATE TABLE IF NOT EXISTS essai_replication(id serial PRIMARY KEY, texte text, ecrit_le timestamptz DEFAULT now())" -c "INSERT INTO essai_replication(texte) VALUES ('ecrit sur le primaire'), ('deuxieme ligne')" -c "SELECT * FROM essai_replication"
sleep 2
echo "## 3. lecture sur la réplique (service postgres-lecture)"; q $R -c "SELECT * FROM essai_replication"
echo "## 4. écriture refusée sur la réplique"; q $R -c "INSERT INTO essai_replication(texte) VALUES ('tentative sur la replique')" 2>&1 | tail -2
echo "## 5. état de la réplication vu du primaire (pg_stat_replication)"; q $P -x -c "SELECT application_name, client_addr, state, sync_state, sent_lsn, replay_lsn, pg_wal_lsn_diff(sent_lsn, replay_lsn) AS retard_octets FROM pg_stat_replication"
q $P -c "SELECT slot_name, slot_type, active, restart_lsn FROM pg_replication_slots"
echo "## 6. vu de la réplique (pg_stat_wal_receiver)"; q $R -x -c "SELECT status, sender_host, slot_name, written_lsn, flushed_lsn, latest_end_time FROM pg_stat_wal_receiver"
echo "## 7. via les Services"; kubectl run psql-$RANDOM -n $N --rm -i --restart=Never --image=postgres:17-alpine --env=PGPASSWORD="$(kubectl get secret ${SECRET:-postgres-secrets} -n $N -o jsonpath='{.data.POSTGRES_PASSWORD}' | base64 -d)" --command -- sh -c 'echo "postgres (ecriture) : $(psql -h postgres -U cinetint -d cinetint -Atc "select pg_is_in_recovery()")  / postgres-lecture : $(psql -h postgres-lecture -U cinetint -d cinetint -Atc "select pg_is_in_recovery()")"; echo "lignes lues sur postgres-lecture : $(psql -h postgres-lecture -U cinetint -d cinetint -Atc "select count(*) from essai_replication")"' 2>&1 | grep -v "^If you\|^All commands\|pod .* deleted"
