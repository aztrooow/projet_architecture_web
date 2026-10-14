# Défi 13 (bonus) : la réplication PostgreSQL dans une charte Helm, incluse dans la charte globale

Fichiers : `values-defi13.yaml`, `commandes.txt`, `schema.svg`. Charte : `../helm/cinetint/charts/postgres-replication/` (sous-charte) et `../helm/cinetint/Chart.yaml` (dépendance).

## Contenu réalisé

- **Une charte à part entière** `postgres-replication` (`Chart.yaml`, `values.yaml`, `templates/`) qui automatise le défi 12 : ConfigMap d'initialisation, StatefulSet primaire, StatefulSet des répliques avec son initContainer
  `pg_basebackup`, quatre Services (`postgres`, `postgres-lecture`, deux headless), Secret facultatif. Elle est écrite à la main, sans charte tierce. Elle s'installe aussi seule :
  `helm install pg ../helm/cinetint/charts/postgres-replication --set enabled=true --set creerSecret=true`.
- **Incluse dans la charte globale** : `Chart.yaml` de `cinetint` la déclare comme dépendance (`dependencies: - name: postgres-replication, condition: postgres-replication.enabled`) et son dossier est rangé dans `charts/`.
  Une option de `values.yaml` l'active : `postgres-replication.enabled: true`. Quand elle est activée, elle **remplace** le StatefulSet unique du défi 7 (`templates/postgres.yaml` ne rend plus rien) ;
  le service `postgres` désigne alors le primaire, donc la ConfigMap de connexion du back n'a pas à changer.
- **Options** (`charts/postgres-replication/values.yaml`) : nombre de répliques (`repliques`), taille du volume, réglages du serveur (`reglages`), réplication synchrone (`synchrone`), ressources, Secret existant (`existingSecret`).
  Les valeurs globales `global.prefixe` et `global.securite` sont relayées à la sous-charte (durcissement du défi 18 inclus : utilisateur 70, système de fichiers en lecture seule).
- Les Secrets (`cinetint-secrets`) contiennent `POSTGRES_PASSWORD` et `REPLICATION_PASSWORD`, générés par la charte globale et partagés avec la sous-charte.
- Les sauvegardes (défi 16), les NetworkPolicy (défi 11) et les hooks (défi 15) fonctionnent avec la réplication : les Pods PostgreSQL portent l'étiquette `component=postgres`, et les Jobs de sauvegarde visent le Service `postgres` (le primaire).

## Fiche oral (schéma)

1. La charte globale `cinetint` contient une sous-charte `postgres-replication` (répertoire `charts/`, dépendance conditionnée par `postgres-replication.enabled`).
2. `helm install` fusionne les valeurs des deux chartes, rend tous les modèles et crée les mêmes ressources que celles écrites à la main au défi 12 : 2 StatefulSets, 4 Services, ConfigMap d'initialisation.
3. Le back (chart parente) se connecte au Service `postgres` : il écrit sur le primaire sans savoir qu'il existe une réplique ; `postgres-lecture` reste disponible pour des lectures.
4. Activer ou désactiver la réplication est une seule ligne de valeurs : `postgres-replication.enabled`.
5. Même flux réseau qu'au défi 12 : walsender -> walreceiver sur le port 5432, slot de réplication, initContainer `pg_basebackup`.

## Vérifié sur cluster local

```text
$ helm upgrade --install cinetint ../helm/cinetint -f values-kind.yaml -f values-defi13.yaml        (STATUS: deployed)
pod/postgres-primaire-0   1/1 Running      pod/postgres-replique-0   1/1 Running
service/postgres 10.43.16.142   postgres-lecture 10.43.200.169   postgres-primaire None   postgres-replique None
configmap/postgres-replication-init
$ demonstration (écriture sur le primaire, lecture sur la réplique, INSERT refusé sur la réplique, pg_stat_replication = streaming, pg_stat_wal_receiver = streaming)  ->  identique au défi 12
$ python3 k8s/outils/parcours.py ... -> tout passe (application sur la base répliquée)
```

Les tests de connexion par les Services depuis un Pod d'essai non étiqueté sont bloqués par la NetworkPolicy du défi 11, toujours active : c'est le comportement voulu.
