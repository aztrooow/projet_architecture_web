# Défi 20 (bonus) : migrations de base de données sans interruption

Fichiers : `values-defi20.yaml`, `exemple-migration/0002_expand_canal_detail.py` (migration Alembic d'exemple), `construire-v3.sh` (image back v3 contenant cette migration), `ecritures.py` (charge d'écriture continue),
`commandes.txt`, `schema.svg`.

## Contenu réalisé

Le back lance Alembic à chaque démarrage (`back/entrypoint.sh` : `alembic upgrade head` sous un **verrou consultatif PostgreSQL** `pg_advisory_lock`, puis les fixtures idempotentes, puis `uvicorn`).
Plusieurs Pods qui démarrent ensemble ne se gênent donc pas : le premier migre, les autres attendent le verrou, constatent que la base est à jour et continuent. Cette mécanique existe déjà dans le dépôt ; ce défi
l'exploite avec la stratégie **expand / contract** et le prouve par un rolling update sous charge.

### La règle : chaque migration doit être compatible avec la version PRÉCÉDENTE du code

Pendant un rolling update, l'ancien et le nouveau code coexistent plusieurs dizaines de secondes sur la **même** base. On ne peut donc jamais renommer ou supprimer en une seule étape : on procède en deux versions.

| Étape | Ce qu'on fait | Compatibilité |
|---|---|---|
| **Expand** (version N+1) | on **ajoute** ce qui est nouveau (colonne avec valeur par défaut, table, index créé `CONCURRENTLY`), sans rien retirer. Le nouveau code lit/écrit le nouveau schéma. | l'ancien code ignore la nouveauté et continue de marcher |
| Migration des données | si besoin : remplissage de la nouvelle colonne par lots (hors du verrou), double écriture dans les deux colonnes pendant la transition | les deux codes voient des données cohérentes |
| **Contract** (version N+2) | une fois qu'aucun Pod n'utilise l'ancienne forme : on **retire** l'ancienne colonne / on ajoute la contrainte `NOT NULL` (`NOT VALID` puis `VALIDATE`) | plus aucun code ne dépend de l'ancien schéma |

Exemples : *renommer* une colonne = ajouter la nouvelle (N+1, double écriture), copier, retirer l'ancienne (N+2). *Ajouter un `NOT NULL`* = ajouter la colonne avec un défaut constant, ou nullable puis remplie, puis contrainte validée.
*Supprimer une colonne* = d'abord arrêter de l'utiliser dans le code (N+1), la supprimer ensuite (N+2).

### Migration d'exemple (expand) : `0002_expand_canal_detail.py`

```sql
SET LOCAL lock_timeout = '5s';
ALTER TABLE commandes ADD COLUMN canal_detail varchar(24) NOT NULL DEFAULT 'standard';
```

- Valeur par défaut **constante** : depuis PostgreSQL 11 la colonne est ajoutée **sans réécrire la table** (simple métadonnée) ; verrou exclusif de quelques millisecondes.
- `lock_timeout` : un `ALTER TABLE` doit attendre les transactions en cours ; pendant son attente, toutes les requêtes suivantes sur la table font la queue derrière lui. Avec un délai de 5 s, l'`ALTER` échoue plutôt que de bloquer le site,
  et `entrypoint.sh` relance la migration (jusqu'à 15 essais).
- L'ancien code n'est pas touché : ses `INSERT` omettent la colonne (la base met `standard`), ses `SELECT` ne la demandent pas.
- Cette migration est dans `exemple-migration/` et appliquée à une copie des sources par `construire-v3.sh` (on ne modifie pas l'application ici) ; dans un vrai projet on ajouterait simplement le fichier dans `back/migrations/versions/`
  et le champ dans `models.py`.

## Procédure et preuve (`commandes.txt`, `../outils/demo-migration.sh`)

1. `construire-v3.sh` fabrique l'image `cinetint-back:v3` (migration 0002 + champ du modèle).
2. `ecritures.py` crée puis annule des commandes en boucle (6 par seconde) : chaque tour exerce l'INSERT, l'UPDATE, les verrous Redis et la base pendant les mises à jour ; une boucle de `curl` lit le site en parallèle.
3. `helm upgrade --set images.tags.back=v3` : rolling update du back (`maxSurge 1`, `maxUnavailable 0`, readinessProbe `/api/sante`). Le premier Pod v3 exécute la migration sous verrou pendant que les Pods v2 servent.
4. Contrôle : `alembic_version` = `0002`, la colonne existe, les commandes déjà présentes valent `standard`, **aucun billet perdu**, aucune erreur dans la boucle.

### Mesures (cluster local, base répliquée, durcissement actif, 3 Pods back)

```text
A. back v1 (ancien create_all) -> v2 (Alembic : schéma existant reconnu et marqué à la révision 0001)
   écritures : 539 tours réussis, 0 erreur       lectures : 1170 x HTTP 200
B. back v2 -> v3 (migration expand 0002 appliquée pendant la mise à jour)
   écritures : 560 tours réussis, 0 erreur       lectures : 1182 x HTTP 200
   alembic_version : 0002 ; canal_detail | character varying | DEFAULT 'standard' | NOT NULL
   commandes : standard = 1325 (toutes les lignes existantes) ; billets : 11759 avant, 11759 après
```

## Limite constatée : le retour arrière du code

Après la v3, `helm rollback` vers une image qui **ne contient pas** la migration 0002 échoue : l'entrypoint de l'ancienne image exécute `alembic upgrade head` et Alembic répond
`Can't locate revision identified by '0002'` ; le nouveau ReplicaSet reste bloqué (`exceeded its progress deadline`). Les Pods v3 existants continuent de servir : **aucune requête n'a échoué** (0 erreur pendant l'essai), mais le rollback n'aboutit pas.
Règles qui en découlent : on ne revient **jamais en arrière sur le schéma**, seulement sur le code ; une image doit contenir **toutes les migrations déjà appliquées** (ne pas rétrograder sous la dernière image qui contient 0002) ; pour se prémunir, l'entrypoint
pourrait ignorer une révision inconnue plus récente que son code (amélioration à proposer à l'équipe de l'application). La sauvegarde pg_dump automatique avant chaque mise à jour (défi 15) couvre le cas d'une migration défectueuse.

## Fiche oral (schéma)

1. P0 : trois Pods back v2, base à la révision 0001. Service et Ingress inchangés.
2. P1 : `helm upgrade --set images.tags.back=v3`. Le premier Pod v3 démarre (surge) : son `entrypoint.sh` prend le verrou `pg_advisory_lock` et applique 0002 (colonne ajoutée avec un défaut constant, sans réécriture de table). Pendant ce temps les Pods v2 servent toujours.
3. Les autres Pods v3 prennent le même verrou, voient que la base est à jour et démarrent ; les v2 sortent un par un, comme au défi 8.
4. P2 : trois Pods v3, révision 0002, zéro erreur, zéro donnée perdue. P3 (version suivante) : la phase contract retirerait ce qui est devenu inutile.
5. Règle d'or : ajouter avant de retirer ; chaque migration reste compatible avec la version précédente du code. Limite : on ne rétrograde pas le code sous une image qui ne connaît pas la dernière migration.
