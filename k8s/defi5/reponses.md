# Défi 5 : l'infrastructure complète

Fichiers : `front.yaml`, `back.yaml`, `qr-generator.yaml`, `qr-verifier.yaml`, `redis.yaml`, `postgres.yaml`, `ingress.yaml` (chaque Deployment avec son Service),
`commandes.txt`, `schema.svg`. Questions du sujet : « un beau schéma ! ».

## Correspondance avec la consigne

| Consigne | Réalisation |
|---|---|
| Deux images séparées pour API et Public | `cinetint-back` (équivalent « api ») et `cinetint-front` (équivalent « public »), plus `cinetint-qr-generator` et `cinetint-qr-verifier` : l'infrastructure équivalente au docker-compose complet |
| Deployments de 3 pods, mêmes ressources qu'au défi 2 | `front` x3, `back` x3 : 100m CPU / 100Mi demandés, 200m / 200Mi en limite. `qr-generator` x2 et `qr-verifier` x2 (mêmes ressources) |
| Base dans un Deployment d'un pod, mêmes allocations | `postgres` x1, 100m / 100Mi et 200m / 200Mi (réglages `shared_buffers=32MB` et journal limité pour tenir dans 200Mi) |
| Services « bien choisis » | six Services **ClusterIP** : aucun n'a besoin d'être joint depuis l'extérieur, l'Ingress sert d'unique entrée |
| L'Ingress remplace le nginx de Docker | deux ressources Ingress, mêmes règles que `nginx/nginx.conf` du dépôt (voir ci-dessous) |

Routage de l'Ingress (le même que le proxy nginx du docker-compose) :

| Préfixe | Service | Remarque |
|---|---|---|
| `/api` | back:8000 | tampon coupé, délai de lecture 1 h pour les flux SSE (Ingress séparé : l'annotation ne doit pas s'appliquer aux autres routes) |
| `/qr` | qr-generator:8001 | images des QR codes, clé publique |
| `/verification` | qr-verifier:8002 | contrôle d'entrée |
| `/` | front:8080 | pages rendues côté serveur et application React |
| `/internal/...` | (aucun) | jamais routé vers le back : tombe sur le front, qui répond 404. Les routes internes exigent de plus l'en-tête `X-Service-Token` |

## Points d'attention

- **Clé de signature des billets** : le qr-generator crée sa clé Ed25519 au premier démarrage s'il n'en trouve pas. Avec plusieurs répliques, chaque pod aurait SA clé :
  un billet signé par l'un serait refusé par les autres. La clé est donc générée une fois (`openssl genpkey -algorithm ed25519`) et montée depuis le Secret `cinetint-cle`
  dans tous les pods. Vérifié : 12 lectures successives du même QR code sur les 2 répliques -> 12 x HTTP 200.
- **Le qr-verifier** garde en mémoire la liste des passages à rejouer pendant une panne du back (mode dégradé) : deux répliques ont chacune leur liste. Acceptable (le mode dégradé
  est un cas rare), mais à connaître.
- **Attente de la base** : le back s'arrête s'il ne joint pas PostgreSQL au démarrage. Un `initContainer` (`pg_isready`) l'attend, ce qui évite les redémarrages au premier lancement.
- **Mémoire mesurée** (`kubectl top`, cluster local, au repos) : back 76 à 82Mi, front 42Mi, qr-generator 61 à 63Mi, qr-verifier 45Mi, postgres 57Mi, redis 5Mi, toutes très en dessous de 200Mi.

## Fiche oral (schéma)

1. Entrée unique : Internet -> 157.159.11.201 (MetalLB) -> contrôleur Ingress -> règles par préfixe -> les Services.
2. Six Services ClusterIP (IP virtuelles 10.43.x.y, noms DNS `front`, `back`, `qr-generator`, `qr-verifier`, `redis`, `postgres`), chacun devant ses Pods (réseau 10.42.x.y).
3. Les appels internes passent par les noms DNS : front -> back (rendu serveur), back -> postgres, redis, qr-generator, qr-verifier -> back et qr-generator. kube-proxy fait l'équilibrage sur chaque nœud.
4. Répartition : 3 front, 3 back, 2 qr-generator, 2 qr-verifier répartis sur les deux workers ; une seule base et un seul Redis (état partagé).
5. Le Secret `cinetint-cle` monte la même clé privée dans tous les qr-generator ; `cinetint-secrets` fournit mots de passe et jetons en variables d'environnement.

## Vérifié sur cluster local

```text
$ NAMESPACE=u-defis ./k8s/appliquer.sh secrets && ./k8s/appliquer.sh defi5
deployment.apps/back 3/3   front 3/3   postgres 1/1   qr-generator 2/2   qr-verifier 2/2   redis 1/1
service/back 10.43.17.214:8000   front 10.43.238.25:8080   postgres 10.43.88.252:5432   qr-generator 10.43.67.144:8001   qr-verifier 10.43.183.160:8002   redis 10.43.247.64:6379
ingress api, site : cinetint.test
$ python3 k8s/outils/parcours.py http://localhost:8080 --hote cinetint.test --controleur ...
OK   sonde /sante, /api/sante, /qr/sante, /verification/sante        (HTTP 200)
OK   réservation de deux places (verrous Redis)                       (HTTP 201)
OK   paiement accepté (signature des billets par le qr-generator)     (HTTP 200)
OK   image du QR code, 12 essais                                       (codes 200 x 12)
OK   premier passage accepté / second passage refusé (deja_utilise) / faux billet refusé
OK   /internal inaccessible depuis l'extérieur                         (HTTP 404)
Résultat : tout passe
```
