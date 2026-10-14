# Défi 12 : PostgreSQL en réplication (maître / réplique), écrit à la main

Fichiers : `init-configmap.yaml`, `primaire.yaml`, `replique.yaml`, `services.yaml`, `values-app-defi12.yaml` (facultatif : brancher l'application), `commandes.txt`, `schema.svg`.
Aucune charte pré-faite : les quatre manifests sont écrits à la main à partir de la documentation de PostgreSQL et de Kubernetes. Le défi ne demande pas de mise à jour de la charte (elle est faite au défi 13).
Question du sujet : le schéma.

## Principe : la réplication en flux (streaming replication) de PostgreSQL

Toute écriture dans PostgreSQL est d'abord inscrite dans un journal, le **WAL** (write-ahead log). La réplication physique consiste à envoyer ce journal, au fil de l'eau, à une autre instance qui le **rejoue** :

1. À sa création, la réplique fait une **copie complète** du primaire (`pg_basebackup`).
2. Puis elle ouvre une connexion de réplication permanente : un processus **walsender** du primaire envoie les nouvelles entrées du WAL à un **walreceiver** de la réplique, qui les rejoue.
3. La réplique démarre en mode **hot standby** (`standby.signal`) : elle accepte les **lectures** mais refuse toute écriture. Elle est en retard de quelques millisecondes au plus (réplication **asynchrone** : le primaire
   valide une écriture sans attendre la réplique ; l'option `synchronous_standby_names` la rendrait synchrone au prix de la disponibilité des écritures).

## Ce qui est déployé

| Ressource | Rôle |
|---|---|
| Secret `postgres-secrets` (créé par commande) | `POSTGRES_PASSWORD` (compte principal) et `REPLICATION_PASSWORD` (compte de réplication) : jamais dans le dépôt |
| ConfigMap `postgres-init` | script lancé **une fois** à la création du primaire : `CREATE ROLE replicateur WITH REPLICATION LOGIN` et ligne `host replication replicateur all scram-sha-256` dans `pg_hba.conf` (le mot-clé `replication` n'est pas couvert par `all`) |
| StatefulSet `postgres-primaire` (1 pod) | le maître : `wal_level=replica`, `max_wal_senders=5`, `max_replication_slots=5`, PVC `data-postgres-primaire-0` de 100Mi |
| StatefulSet `postgres-replique` (1 pod, extensible) | l'esclave : un **initContainer** `copie-du-primaire` (`pg_basebackup -X stream -R -S <slot>`) copie le primaire dans le volume si celui-ci est vide ; le conteneur PostgreSQL démarre ensuite en réplique. PVC `data-postgres-replique-0` |
| Service `postgres` (ClusterIP) | **lecture et écriture**, désigne toujours le primaire : c'est le nom que l'application utilise |
| Service `postgres-lecture` (ClusterIP) | **lecture seule**, répartie entre les répliques |
| Services headless `postgres-primaire`, `postgres-replique` | noms DNS stables par Pod (`postgres-primaire-0.postgres-primaire`) : les répliques joignent le primaire par ce nom |

Détails qui comptent :

- **Slot de réplication** (`postgres_replique_0`, créé de façon idempotente par l'initContainer) : le primaire garde le WAL tant que la réplique ne l'a pas lu, même si elle est arrêtée. Comme le volume ne fait que 100Mi,
  `max_slot_wal_keep_size=32MB` abandonne un slot trop en retard plutôt que de remplir le disque du primaire (la réplique doit alors être recréée).
- **Compte dédié** : `replicateur` n'a que le droit `REPLICATION` ; il ne peut lire aucune table. Le mot de passe est en Secret.
- **Mêmes réglages sur le primaire et la réplique** : `max_connections`, `max_wal_senders`, `max_locks_per_transaction`... ne doivent pas être plus petits sur une réplique que sur le primaire (la mémoire partagée qui suit les transactions et les verrous
  doit être au moins aussi grande), sinon elle refuse de démarrer (documentation PostgreSQL 17, « Hot Standby »).
- **Reprise** : si le primaire est supprimé, le StatefulSet le recrée avec le même volume ; la réplique se reconnecte seule (`pg_stat_replication` revient à `streaming`).
- **Basculement** : il est **manuel** (`SELECT pg_promote()`). Sans outil de supervision (Patroni, opérateurs CloudNativePG/Zalando, qui demandent des CRD interdites sur le cluster du cours) deux « primaires » peuvent
  coexister (split-brain) : l'ancien primaire ne voit pas ce qui s'écrit sur le promu (vérifié, voir ci-dessous).
- Les ressources de chaque conteneur restent 100m / 100Mi et 200m / 200Mi.

## Fiche oral (schéma)

1. Deux StatefulSets : `postgres-primaire-0` (lecture/écriture) et `postgres-replique-0` (lecture seule), chacun avec son volume de 100Mi, sur des nœuds quelconques du cluster.
2. À la création de la réplique, l'initContainer exécute `pg_basebackup` vers le primaire (TCP 5432, compte `replicateur`, slot dédié) et copie toute la base dans son volume (`-R` écrit `standby.signal`).
3. Ensuite, flux continu : le walsender du primaire envoie le WAL, le walreceiver de la réplique le rejoue. Le slot garantit que rien n'est perdu si la réplique est en retard.
4. Côté clients : le Service `postgres` mène au primaire (le back écrit), `postgres-lecture` mène aux répliques (lectures). Les Services headless donnent les noms DNS par Pod, utilisés par la réplique pour trouver le primaire.
5. Démonstration : écriture sur le primaire, lecture identique sur la réplique, `INSERT` refusé sur la réplique (`read-only transaction`), `pg_stat_replication` à `streaming`.

## Vérifié sur cluster local

```text
$ NAMESPACE=u-test ../appliquer.sh secrets-postgres && ../appliquer.sh defi12
pod/postgres-primaire-0   1/1 Running   10.42.128.127      pod/postgres-replique-0   1/1 Running   10.42.128.65
pvc data-postgres-primaire-0 / data-postgres-replique-0   Bound   100Mi
service/postgres 10.43.78.68   postgres-lecture 10.43.73.27   postgres-primaire None   postgres-replique None

## réplique : pg_is_in_recovery = t       primaire : pg_is_in_recovery = f
## écriture sur le primaire          INSERT 0 2         (2 lignes)
## lecture sur la réplique           les 2 lignes, mêmes horodatages
## écriture sur la réplique          ERROR:  cannot execute INSERT in a read-only transaction
## pg_stat_replication (primaire)
application_name | postgres-replique-0     client_addr | 10.42.128.65     state | streaming     sync_state | async
sent_lsn | 0/3034AF0   replay_lsn | 0/3034AF0   retard_octets | 0
slot_name | postgres_replique_0   slot_type | physical   active | t
## pg_stat_wal_receiver (réplique)   status | streaming   sender_host | postgres-primaire-0.postgres-primaire   slot_name | postgres_replique_0
## via les Services : postgres (écriture) -> pg_is_in_recovery = f ; postgres-lecture -> t
## application branchée sur le primaire (values-app-defi12.yaml) : parcours complet OK ; sur la réplique : 8 films, 218 séances, 11745 billets
## primaire supprimé : recréé avec son volume, pg_stat_replication -> postgres-replique-0 | streaming, 4 lignes conservées
## pg_promote() sur la réplique : pg_is_in_recovery = f, INSERT accepté ; l'ancien primaire reste à 4 lignes, la réplique promue en a 5 (split-brain)
```

Mesures : la base de démonstration fait 11 Mo ; le dossier de données du primaire 65 Mo sur les 100Mi du volume (journal limité par `max_wal_size=48MB`). Mémoire des Pods PostgreSQL : sous 200Mi.
