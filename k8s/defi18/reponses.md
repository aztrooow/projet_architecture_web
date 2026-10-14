# Défi 18 (bonus) : durcissement du site

Fichiers : `values-defi18.yaml`, `commandes.txt`, `schema.svg`. Les protections sont dans la charte : `_helpers.tpl` (`cinetint.secPod`, `cinetint.secConteneur`), `ingress.yaml`, `networkpolicies.yaml`, `secrets.yaml`.

## Contre quoi se protège-t-on ?

Le sujet demande de rendre le site « non vulnérable à l'attaque précédente » (le défi 17, faire planter le site d'un autre groupe, n'est pas réalisé : voir `../README.md`). L'attaque n'est pas décrite ; le titre du défi (« connexions moins dangereuses »)
et la configuration par défaut de Kubernetes désignent les scénarios réalistes, que cette charte ferme un par un. **C'est une hypothèse, pas un contenu imposé** :

| Attaque possible sur le site d'un autre groupe | Pourquoi elle marche par défaut | Protection ici |
|---|---|---|
| Se connecter directement à la base (mot de passe par défaut, requêtes destructrices, saturation des connexions) depuis un autre namespace | Le réseau des pods est plat : tout Pod joint tout Pod | **NetworkPolicy** sur la base (défi 11) et sur tous les composants ; **mots de passe aléatoires** en Secrets (jamais de `postgres/postgres`) |
| Appeler les routes `/internal` du back (marquer des billets comme utilisés) | Le Service du back est joignable de partout | NetworkPolicy (le back n'accepte que front, qr-verifier, Ingress) + jeton `X-Service-Token` aléatoire + `/internal` jamais routé par l'Ingress |
| Inonder le site de requêtes (déni de service) | Rien ne limite le débit à l'entrée | **limites de débit de l'Ingress** : `limit-rps: 20`, `limit-connections: 30` par adresse IP, corps de requête limité à 1 Mo |
| Saturer la mémoire ou le CPU d'un Pod pour faire tomber le nœud | Un conteneur sans limite consomme tout | limites de ressources (200m / 200Mi), HPA (3 à 10 Pods) |
| Exécuter du code dans un conteneur compromis pour s'installer, élever ses droits, atteindre l'API Kubernetes | Les conteneurs tournent souvent en root avec un jeton d'accès à l'API | **contexte de sécurité** ci-dessous, `automountServiceAccountToken: false` |

Limite à connaître : `limit-rps` compte par adresse source telle que la voit nginx. Si le LoadBalancer MetalLB réécrit l'adresse source (SNAT, `externalTrafficPolicy: Cluster`), tous les visiteurs partagent
le même compteur : le seuil (20 requêtes/s, avec une rafale tolérée de 5 fois) devient global. Il se règle dans `ingress.limites` de `values.yaml` (ou se coupe avec `enabled: false`).

## Durcissement des Pods (`global.securite: true`)

Pour chaque Pod et conteneur : `runAsNonRoot: true` avec un UID explicite (1000 pour les services applicatifs, 70 pour PostgreSQL, 999 pour Redis : Kubernetes ne peut pas vérifier un `USER cinetint` non numérique),
`allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`, `readOnlyRootFilesystem: true` (seuls `/tmp`, `/var/run/postgresql`, `/data` et les volumes de données sont inscriptibles, par `emptyDir` ou PVC),
`seccompProfile: RuntimeDefault` (filtre des appels système), `automountServiceAccountToken: false` (aucun jeton d'API monté dans les Pods applicatifs). Les valeurs sensibles sont dans des **Secrets** générés par la charte,
pas dans les manifests ni dans le dépôt.

Le profil est compatible avec les images : tous les services démarrent et le parcours complet passe, y compris PostgreSQL en réplication (initContainer `pg_basebackup` inclus) avec un système de fichiers en lecture seule.

## NetworkPolicy complètes (`networkPolicies.applicatives.enabled`)

| Destination | Source autorisée |
|---|---|
| front | contrôleur Ingress (namespace `kube-system` sur RKE2, `ingress-nginx` sur kind) |
| back | front, qr-verifier, contrôleur Ingress |
| qr-generator | back, qr-verifier, contrôleur Ingress |
| qr-verifier | contrôleur Ingress |
| redis | back |
| postgres | back, tâches de sauvegarde, Pods PostgreSQL entre eux (réplication) |

Tout le reste est refusé, y compris tout trafic venant d'un autre namespace. (Les sorties ne sont pas filtrées : DNS et appels HTTP sortants restent libres.)

## Fiche oral (schéma)

1. Quatre couches empilées entre Internet et les données. Couche 1, l'Ingress : débit limité à 20 requêtes/s et 30 connexions par IP, corps limité à 1 Mo ; les excès reçoivent HTTP 503 ou 413 sans atteindre les Pods.
2. Couche 2, le réseau : une NetworkPolicy par composant, seules les flèches de la matrice existent ; un Pod inconnu ou d'un autre namespace est bloqué.
3. Couche 3, le Pod : utilisateur non root, aucune capability, système de fichiers en lecture seule, seccomp, pas de jeton d'API, limites CPU et mémoire.
4. Couche 4, les secrets : mots de passe, jeton de service, clé de signature des billets générés aléatoirement par la charte, injectés par des Secrets.
5. Résultat mesuré : le site reste disponible pendant une attaque par inondation, et l'attaque contre la base depuis un Pod quelconque échoue.

## Vérifié sur cluster local (`../outils/demo-securite.sh`, `../outils/test-networkpolicy.sh`)

```text
front         1000 nonRoot=true seccomp=RuntimeDefault privEsc=false readOnlyFS=true drop=["ALL"] token=false
back / qr-generator / qr-verifier  idem (1000)         redis 999 (idem)        postgres-primaire-0 et postgres-replique-0 : 70, nonRoot, readOnlyFS, drop ALL
$ kubectl exec back -- sh -c 'id; touch /app/essai; touch /tmp/essai; grep Cap /proc/1/status; grep NoNewPrivs /proc/1/status'
uid=1000(cinetint) gid=1000(cinetint)   touch: cannot touch '/app/essai': Read-only file system   écriture /tmp : ok
CapEff: 0000000000000000   CapBnd: 0000000000000000   NoNewPrivs: 1
$ 400 requêtes en 40 connexions simultanées sur /api/sante :    69 x HTTP 200, 331 x HTTP 503      puis HTTP 200 (le site reste debout)
$ corps de 2 Mo vers /api/commandes : HTTP 413
Matrice réseau (Pods d'essai étiquetés) :
front -> back AUTORISE        front -> qr-generator BLOQUE     front -> redis BLOQUE         front -> postgres BLOQUE
back -> postgres AUTORISE     back -> redis AUTORISE           back -> qr-generator AUTORISE
qr-verifier -> back AUTORISE  qr-verifier -> postgres BLOQUE   Pod inconnu -> back BLOQUE   Pod d'un autre namespace -> front BLOQUE
Parcours complet (achat, QR, contrôle, /internal) : tout passe avec tout le durcissement actif
```
