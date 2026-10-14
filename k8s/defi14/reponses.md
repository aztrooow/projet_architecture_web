# Défi 14 (bonus) : Redis, son avantage et la nouvelle infrastructure

Fichiers : `values-defi14.yaml`, `commandes.txt`, `schema.svg`. Modèles : `../helm/cinetint/templates/redis.yaml`, `networkpolicies.yaml`.
Le sujet demande d'expliquer l'avantage d'un cache Redis et de définir la nouvelle infrastructure.

## À quoi sert Redis dans CinetINT (d'après le code)

Redis n'est pas, ici, un cache de pages devant la base. Le back l'utilise pour trois rôles que PostgreSQL ferait mal ou lentement (`back/app/verrous.py`, `remplissage.py`, `temps_reel.py`) :

| Rôle | Clés / canaux | Pourquoi Redis |
|---|---|---|
| **Verrous de sièges à expiration** | `verrou:{<séance>}:<siège>` = identifiant de la commande, posé par un **script Lua atomique** (`SET ... EX 600` pour tous les sièges ou aucun) | Pendant que le spectateur paie, ses places sont réservées 10 minutes puis **libérées automatiquement** par l'expiration de la clé, sans tâche de nettoyage. Une opération atomique en mémoire, partagée par toutes les répliques du back : c'est ce qui rend l'achat sûr à plusieurs Pods. |
| **Compteurs de remplissage** (le vrai « cache ») | `remplissage:<séance>` = places vendues | Évite un `COUNT(*)` sur la table des billets à chaque affichage du programme et du tableau du gérant. Incrémenté/décrémenté atomiquement à chaque vente ou remboursement ; **recalculable depuis la base** s'il manque. |
| **Publication/abonnement (pub/sub)** | canaux `seance:<id>` et `remplissage` | Un siège réservé via un Pod du back apparaît en direct chez un navigateur connecté à un **autre** Pod. Chaque Pod garde UNE connexion d'abonnement (`PSUBSCRIBE seance:* remplissage`) et redistribue aux navigateurs en SSE (plan de salle, tableau du gérant). |

**Avantage dans l'infrastructure Kubernetes** : le back est **sans état** (JWT, rien en mémoire) donc on peut le multiplier à 3, puis jusqu'à 10 Pods avec l'HPA (défi 9). Redis est le point de coordination qui rend cette multiplication
possible : verrous, compteurs et événements sont communs à tous les Pods. Les temps d'accès sont de l'ordre de la microseconde à la milliseconde, bien en dessous d'une requête SQL.
**La base reste l'arbitre** : un index unique partiel sur `(séance, siège)` interdit deux billets actifs sur la même place même si Redis perdait un verrou. Perdre Redis ne perd donc aucune donnée : au pire, les verrous en cours disparaissent
(les acheteurs en train de payer doivent recommencer), les compteurs se recalculent, les navigateurs se reconnectent.
(Le front a de plus un petit cache de 20 s en mémoire du processus pour les appels au catalogue : `front/server/main.py`, `lire_api`.)

## Nouvelle infrastructure

- Redis est déployé par la charte (`templates/redis.yaml`) : Deployment d'**une seule instance** (les verrous doivent être vus de tous les Pods), Service ClusterIP `redis:6379`, ressources 100m / 100Mi et 200m / 200Mi,
  sonde exec `redis-cli ping`, `strategy: Recreate`.
- Configuration : `--save "" --appendonly no` (aucune persistance : les données sont éphémères par nature), `--maxmemory 100mb --maxmemory-policy noeviction` : si la mémoire était pleine, Redis refuserait les écritures
  (erreur franche) plutôt que d'**évincer en silence un verrou de siège**. La persistance est activable (`redis.persistance.enabled`, PVC + `appendonly`) mais inutile ici.
- **NetworkPolicy `cinetint-redis-acces`** (activée par `values-defi14.yaml`) : seul le back joint Redis. Le front, un Pod quelconque ou un autre namespace sont bloqués ; Redis n'a pas de mot de passe, la politique réseau est donc sa protection.
- Remarque : `values-defi14.yaml` active l'ensemble des NetworkPolicy applicatives (le défi 18 les détaille), pas seulement celle de Redis.
- Redis est déployé dès le défi 3 (le back ne démarre pas sans lui : `/api/sante` le teste) ; le défi 14 en fait un composant à part entière de la charte, documenté et isolé.

## Fiche oral (schéma)

1. Trois Pods du back (ou plus avec l'HPA) parlent tous au même Service `redis` (10.43.x.y:6379), qui mène à l'unique Pod Redis.
2. Rôle 1 : les verrous de sièges `verrou:{séance}:siège`, posés par un script Lua atomique avec expiration de 10 minutes : un siège réservé par un Pod est vu comme pris par tous les autres.
3. Rôle 2 : les compteurs `remplissage:<séance>`, un cache du nombre de places vendues, évite des `COUNT(*)` sur PostgreSQL.
4. Rôle 3 : pub/sub. Chaque back garde une connexion d'abonnement et relaie en SSE : un achat via le Pod 1 met à jour le plan de salle d'un navigateur connecté au Pod 3.
5. Sécurité et résilience : NetworkPolicy (seul le back joint Redis), mémoire plafonnée sans éviction, pas de persistance ; la base PostgreSQL reste l'arbitre de la cohérence.

## Vérifié sur cluster local (`demo-replication.sh` et `demo-redis.sh` dans `../outils/`)

```text
connexions en abonnement (psub=2) : 3            (un abonnement par Pod du back)
réservation de 2 places -> verrou:{1}:327 et verrou:{1}:322    TTL 599 s, propriétaire = identifiant de la commande
événement reçu par un navigateur sur /api/seances/1/flux : data: {"sieges":[{"id":327,"etat":"verrouille"},{"id":322,"etat":"verrouille"}]}
même siège demandé par un autre acheteur : HTTP 409
paiement : verrous restants 0 ; remplissage:1 passe de 202 à 204
maxmemory 104857600 / maxmemory-policy noeviction / save "" ; used_memory 1.82M
NetworkPolicy redis : back AUTORISE, front BLOQUE, pod quelconque BLOQUE
```
