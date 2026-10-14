# Défi 16 (bonus) : sauvegarde du volume de la base de données

Fichiers : `values-defi16.yaml`, `restaurer-job.yaml` (restauration, appliquée à la main), `commandes.txt`, `schema.svg`. Modèles : `../helm/cinetint/templates/sauvegardes.yaml` (PVC + CronJob), `_sauvegarde.tpl` (script).

## Contenu réalisé

- **PVC dédié** `cinetint-sauvegardes` (200Mi), **distinct** du volume de la base (`data-postgres-...`) : si le volume de la base est perdu ou corrompu, les sauvegardes sont ailleurs. Il survit à `helm uninstall`.
- **CronJob** `cinetint-sauvegarde` : tous les jours à 03:00 (`0 3 * * *`, fuseau du cluster), `concurrencyPolicy: Forbid` (jamais deux sauvegardes en même temps), 3 Jobs gardés en historique, `activeDeadlineSeconds: 900`.
  Chaque exécution lance un Pod `postgres:17-alpine` (même version majeure que le serveur) qui :
  1. attend que la base réponde ;
  2. fait un `pg_dump -Fc` (format custom, compressé, restaurable table par table) vers `cinetint-planifiee-AAAAMMJJ-HHMMSS.dump.partiel`, puis le renomme (un fichier incomplet n'est jamais pris pour une sauvegarde) ;
  3. **vérifie** le fichier avec `pg_restore --list` ;
  4. applique la **rétention** : seules les 7 dernières sauvegardes sont gardées.
- La sauvegarde est **logique** (pg_dump), cohérente (un instantané d'une transaction) et faite **sans arrêter la base**. Avec la réplication (défis 12 et 13) elle vise le service `postgres` (le primaire).
  Choix par rapport à une copie du volume : un `pg_dump` est portable (restaurable sur une autre version, dans une autre base), vérifiable, et ne dépend pas du fournisseur de stockage (pas de VolumeSnapshot, qui exige des CRD interdites sur le cluster du cours).
  Limite : la restauration porte sur l'état de la dernière sauvegarde (RPO de 24 h ; les hooks du défi 15 ajoutent une sauvegarde avant et après chaque mise à jour).
- Le Pod de sauvegarde porte l'étiquette `component=sauvegarde`, autorisée par la NetworkPolicy de la base.

## Procédure de restauration (testée)

```text
kubectl scale deployment back --replicas=0 -n u-XXX     # plus aucune connexion à la base (l'HPA ne remonte pas un Deployment à 0)
kubectl apply -f restaurer-job.yaml -n u-XXX            # FICHIER vide = la sauvegarde la plus récente ; sinon cinetint-planifiee-...dump
kubectl logs -f job/cinetint-restauration -n u-XXX
kubectl delete job cinetint-restauration -n u-XXX
kubectl scale deployment back --replicas=3 -n u-XXX
```

`pg_restore --clean --if-exists --no-owner --single-transaction` supprime puis recrée chaque objet du dump dans **une seule transaction** : en cas d'erreur, la base reste dans son état d'avant. Les compteurs Redis
(`remplissage:*`) sont un cache recalculable depuis la base.

## Fiche oral (schéma)

1. Le CronJob (`0 3 * * *`) crée un Job, qui crée un Pod `pg_dump`. Le Pod joint la base par le Service `postgres` (NetworkPolicy : l'étiquette `component=sauvegarde` est autorisée).
2. Le dump (format compressé, vérifié par `pg_restore --list`) est écrit sur le PVC `cinetint-sauvegardes`, séparé du PVC de données ; rétention des 7 dernières.
3. Les hooks du défi 15 écrivent sur le même volume avant et après chaque mise à jour.
4. Restauration : on arrête le back (0 réplique), un Job `pg_restore` lit le dernier dump sur le PVC et recrée la base dans une transaction, puis on remonte le back à 3.
5. Les volumes de sauvegarde et de données sont deux ressources indépendantes : perdre l'un ne perd pas l'autre.

## Vérifié sur cluster local (sauvegarde puis sinistre puis restauration)

```text
$ kubectl get cronjob       cinetint-sauvegarde   0 3 * * *   Suspend False
$ kubectl create job sauvegarde-manuelle --from=cronjob/cinetint-sauvegarde        -> complete
[sauvegarde] écrit et vérifié : /sauvegardes/cinetint-planifiee-20261014-123017.dump   (407145 octets)
[sauvegarde] sauvegardes présentes : 3 « apres » et 2 « avant » des hooks du défi 15 + 1 planifiée (total 6 fichiers, 2,4 Mo)
état avant sinistre : billets = 11755
sinistre : TRUNCATE billets, controles CASCADE   ->  billets = 0
kubectl scale deployment back --replicas=0 ; kubectl apply -f restaurer-job.yaml
[restauration] fichier : /sauvegardes/cinetint-planifiee-20261014-123017.dump
[restauration] terminée          billets restaurés : 11755
kubectl scale deployment back --replicas=3 ; billets = 11755 ; sur la réplique PostgreSQL aussi : 11755
```
