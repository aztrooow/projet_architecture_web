# Défi 11 : NetworkPolicy sur la base de données

Fichiers : `values-defi11.yaml`, `commandes.txt`, `schema.svg`. Modèle : `../helm/cinetint/templates/networkpolicies.yaml`. Questions du sujet : « rien ! » (mais la démonstration est demandée).

## La règle

Par défaut, dans Kubernetes, tout Pod peut joindre tout Pod, y compris dans un autre namespace : n'importe quel groupe du cours pourrait ouvrir une connexion vers `postgres.u-XXX.svc`.
Une **NetworkPolicy** de type Ingress, dès qu'elle sélectionne un Pod, ferme tout sauf ce qu'elle autorise. La politique `cinetint-postgres-acces` :

```yaml
podSelector:   {component: postgres}                       # s'applique aux Pods de la base
policyTypes:   [Ingress]
ingress:
  - from:
      - podSelector:                                       # même namespace uniquement (pas de namespaceSelector)
          matchExpressions: [{component In (back, sauvegarde, postgres)}]
    ports: [{protocol: TCP, port: 5432}]
```

Elle est appliquée par le plugin réseau (CNI : Canal/Calico sur RKE2) sur l'interface du Pod de la base. Seules les connexions entrantes sont limitées ; DNS et sorties restent libres.

## Qui parle vraiment à PostgreSQL ? (vérifié dans le code)

Le sujet demande « n'autoriser que les Pods Front et API ». Dans CinetINT :

- **back** : seul service qui ouvre des connexions SQL (`back/app/db.py`, SQLAlchemy + asyncpg, `DATABASE_URL`). **Autorisé.**
- **front** : pas de pilote de base de données dans ses dépendances (`front/requirements.txt` : fastapi, uvicorn, jinja2, httpx...) ; il lit le catalogue **par l'API du back** (`API_INTERNE=http://back:8000`).
  Dans le sujet, l'application « public » (Django) lisait directement la base ; ici le rôle équivalent passe par l'API. **Non autorisé** par défaut : le moindre privilège est de refuser ce qu'aucun code n'utilise.
  Pour reproduire la lettre du sujet, il suffit d'ajouter `front` dans `networkPolicies.postgres.composantsAutorises` de `values.yaml`.
- **qr-generator, qr-verifier** : aucun pilote SQL ; le qr-verifier passe par l'API interne du back.
- **Tâches de sauvegarde** (défi 16, étiquette `sauvegarde`) et **Pods PostgreSQL entre eux** (réplication, défi 13) : autorisés.

## Fiche oral (schéma)

1. Le Pod `postgres-0` est sélectionné par la NetworkPolicy : seul le port 5432 reste ouvert, et seulement pour les Pods du même namespace portant `component=back` (ou `sauvegarde`, `postgres`).
2. Chemin autorisé (vert) : back -> Service postgres -> Pod postgres-0.
3. Chemins bloqués (rouge) : front, un Pod quelconque du namespace, et un Pod d'un autre namespace (`u-autre`) : la connexion expire (timeout), car le paquet est jeté à l'entrée du Pod.
4. Le contrôle se fait par **étiquettes** (podSelector) : on autorise un rôle, pas une adresse IP, donc les Pods peuvent être recréés ou multipliés sans changer la règle.
5. Le reste du trafic (Ingress vers front/back, etc.) n'est pas concerné par cette règle : elle ne protège que la base.

## Vérifié sur cluster local (Calico applique les règles)

```text
Avant (défi 10)                                        Après (défi 11)
pod du back (autorisé)           CONNEXION_AUTORISEE   CONNEXION_AUTORISEE
pod du front                     CONNEXION_AUTORISEE   CONNEXION_BLOQUEE
pod quelconque du même namespace CONNEXION_AUTORISEE   CONNEXION_BLOQUEE
pod d'un autre namespace         CONNEXION_AUTORISEE   CONNEXION_BLOQUEE
$ python3 k8s/outils/parcours.py ...    ->  tout passe (le site fonctionne)
```

(`nc -zv -w 4 postgres.<ns>.svc.cluster.local 5432` lancé depuis un Pod d'essai avec l'étiquette indiquée.) Sur kind, le réseau par défaut (kindnet) n'applique pas les NetworkPolicy : le cluster d'essai utilise Calico.
