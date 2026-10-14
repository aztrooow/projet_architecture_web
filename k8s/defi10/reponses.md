# Défi 10 : les sondes (liveness, readiness, startup)

Fichiers : `values-defi10.yaml`, `exemple-liveness-en-echec.yaml`, `commandes.txt`, `schema.svg`. Modèles : `templates/_helpers.tpl` (`cinetint.sondesHttp`), `front.yaml`, `back.yaml`, `qr-generator.yaml`,
`qr-verifier.yaml`, `redis.yaml`, `postgres.yaml`.

## Les trois sondes

- **liveness** : « le conteneur est-il en vie ? » Si elle échoue (`failureThreshold` fois de suite), le **kubelet tue et redémarre le conteneur**. Elle répare un processus bloqué.
- **readiness** : « le Pod peut-il recevoir du trafic ? » Si elle échoue, le Pod est **retiré des endpoints du Service** (mais pas redémarré) jusqu'à ce qu'elle réussisse. Elle protège les utilisateurs.
- **startup** : « le démarrage est-il fini ? » Tant qu'elle n'a pas réussi, les deux autres sont suspendues : un démarrage lent (migrations, import du programme) n'est pas pris pour une panne et ne déclenche pas de redémarrage.

Les routes existent dans le code des services (vérifié) : `front/server/main.py` (`/sante`), `back/app/main.py` (`/api/sante`), `qr-generator/app/main.py` (`/qr/sante`), `qr-verifier/app/main.py` (`/verification/sante`).

## Question : pour chaque probe, pourquoi ce type de sonde ?

| Conteneur | Type | Cible | Pourquoi ce type |
|---|---|---|---|
| **front** | `httpGet` | `GET /sante` port 8080 (liveness, readiness, startup) | Service HTTP : la route teste que l'application répond vraiment (pas seulement que le port est ouvert). `/sante` est indépendante du back : si l'API tombe, le front n'est pas redémarré pour rien. |
| **back** (readiness et startup) | `httpGet` | `GET /api/sante` port 8000 | Cette route **vérifie PostgreSQL et Redis** (`SELECT 1`, `PING`) : c'est exactement ce qu'on veut pour savoir si le Pod peut servir. Si la base est absente, le Pod sort du Service. La startup (48 essais x 5 s) laisse le temps aux migrations. |
| **back** (liveness) | `httpGet` | `GET /api/docs` port 8000 | Volontairement PAS `/api/sante` : mesuré sur le cluster local, avec `/api/sante` en liveness et la base arrêtée 2 minutes, **les trois Pods du back sont passés en CrashLoopBackOff** (5 redémarrages chacun) alors que redémarrer le back ne répare pas la base. `/api/docs` ne touche aucune dépendance : elle prouve seulement que le processus répond. Résultat avec ce réglage : Pods non Ready (donc sortis du Service) mais 0 redémarrage, et retour à la normale tout seul au retour de la base. |
| **qr-generator** | `httpGet` | `GET /qr/sante` port 8001 | Service HTTP sans dépendance : la route répond tant que le processus est sain. |
| **qr-verifier** | `httpGet` | `GET /verification/sante` port 8002 | Service HTTP ; la route indique aussi si la clé publique est chargée et combien de passages sont à rejouer. Elle ne dépend pas du back (le mode dégradé existe pour ça). |
| **PostgreSQL** | `exec` | `pg_isready -U $POSTGRES_USER -d $POSTGRES_DB` | Pas de HTTP : le protocole est celui de PostgreSQL. `pg_isready` (fourni avec l'image) interroge le serveur et répond « accepting connections » ; plus fiable qu'un `tcpSocket` qui réussirait dès que le port est ouvert, même pendant la récupération après un arrêt brutal. |
| **Redis** | `exec` | `redis-cli ping \| grep -q PONG` | Pas de HTTP non plus. `PING` prouve que Redis exécute des commandes ; un simple test de port ne détecterait pas un Redis bloqué ou en chargement. |

Un `tcpSocket` serait le bon choix pour un service sans protocole testable (démon TCP opaque) ; il n'y en a pas ici. Réglages : liveness toutes les 15 s (10 s pour les bases), 4 échecs consécutifs (6 pour PostgreSQL) avant le redémarrage, `timeoutSeconds` 3 à 5.

## Fiche oral (schéma)

1. Chaque nœud a un kubelet qui exécute les sondes de ses conteneurs : requêtes HTTP vers le port du Pod, ou commande exécutée dans le conteneur (`pg_isready`, `redis-cli ping`).
2. Startup réussie, puis readiness : le Pod entre dans les endpoints du Service ; si la readiness échoue il en sort, sans redémarrage.
3. Liveness en échec : le kubelet redémarre le conteneur (le compteur RESTARTS augmente). Le back a une liveness différente de sa readiness pour ne pas être redémarré quand c'est la base qui est en panne.
4. Cas montré sur le schéma : base arrêtée, les 3 Pods du back passent à 0/1 Ready (retirés du Service) mais RESTARTS reste à 0 ; au retour de la base ils redeviennent Ready seuls.
5. PostgreSQL et Redis : sondes de type exec, adaptées à leur protocole.

## Vérifié sur cluster local

```text
$ kubectl get deploy -o custom-columns=...      (sondes déclarées)
front         liveness=/sante                readiness=/sante                startup=/sante
back          liveness=/api/docs             readiness=/api/sante            startup=/api/sante
qr-generator  liveness=/qr/sante             readiness=/qr/sante             startup=/qr/sante
qr-verifier   liveness=/verification/sante   readiness=/verification/sante   startup=/verification/sante
postgres liveness exec : ["sh","-c","pg_isready -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\""]
redis    liveness exec : ["sh","-c","redis-cli ping | grep -q PONG"]

Essai 1 : base arrêtée (kubectl scale statefulset postgres --replicas=0), liveness du back sur /api/sante
t+30s 0/1   t+60s 0/1 RESTARTS 1   t+75s CrashLoopBackOff 2   t+120s Error 4 ...  (events : Unhealthy, Readiness/Startup probe failed)
Essai 2 : même scénario, liveness du back sur /api/docs
t+40s 0/1 Running RESTARTS 0  ...  t+120s 0/1 RESTARTS 0 ;  base relancée : 1/1 Running RESTARTS 0 en 45 s, HTTP 200 sur /api/sante
```

Pod d'essai `exemple-liveness-en-echec.yaml` : sa sonde vise `/inexistante` ; événements `Liveness probe failed: HTTP probe failed with statuscode: 404` puis `Container demo failed liveness probe, will be restarted`.
