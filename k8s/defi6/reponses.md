# Défi 6 : la charte Helm

Fichiers : `values-defi6.yaml` (les valeurs de ce défi), `commandes.txt`, `schema.svg`. La charte elle-même est dans `../helm/cinetint/` (dans l'archive de rendu elle est à
la racine, à côté des dossiers `defiN`). Questions du sujet : aucune, « une belle charte Helm fera amplement l'affaire ».

## Ce qu'est la charte

Helm est le « docker compose » de Kubernetes : une **charte** (chart) est un dossier de **modèles** (templates YAML avec des variables) plus un fichier de **valeurs**
(`values.yaml`). `helm install` fusionne les deux, envoie les manifests obtenus à l'API server et enregistre le résultat dans un Secret `sh.helm.release.v1.cinetint.vN`
(historique des révisions : `helm history`, `helm rollback`). `helm upgrade` calcule la différence avec la révision précédente.

```text
helm/cinetint/
  Chart.yaml                  nom, version, dépendance (sous-charte de réplication du défi 13)
  values.yaml                 TOUTES les options, commentées en français
  values-cours.yaml           registre d'images, domaine, namespace du Ingress du cluster du cours
  values-kind.yaml            idem pour le cluster de test local
  templates/
    _helpers.tpl, _sauvegarde.tpl   noms, étiquettes, ressources, sondes, durcissement (fonctions communes)
    configmap.yaml            connexion à la base + adresses internes (ce défi)
    secrets.yaml              mots de passe, jetons, clé Ed25519 (générés une seule fois)
    front.yaml back.yaml qr-generator.yaml qr-verifier.yaml redis.yaml postgres.yaml   un Deployment (ou StatefulSet) + un Service chacun
    ingress.yaml              les routes /api, /qr, /verification, /
    hpa.yaml networkpolicies.yaml hooks.yaml sauvegardes.yaml   défis 9, 11, 15, 16 (désactivés dans values-defi6.yaml)
    tests/test-connexion.yaml "helm test" : sondes de santé des quatre services
  charts/postgres-replication/   sous-charte PostgreSQL maître/réplique (défi 13)
```

`values-defi6.yaml` désactive tout ce qui appartient aux défis suivants : la base est dans un **Deployment sans volume**, comme au défi 5. La charte reproduit donc exactement
l'infrastructure du défi 5, mais en une commande : `helm upgrade --install`.

## Les ConfigMaps du défi

La ConfigMap `cinetint-config` contient **les informations de connexion entre le site et la base** et les adresses internes :

| Clé | Valeur | Utilisée par |
|---|---|---|
| `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER` | `postgres`, `5432`, `cinetint`, `cinetint` | back, initContainer d'attente de la base, Jobs de sauvegarde |
| `REDIS_URL`, `REDIS_HOST` | `redis://redis:6379/0`, `redis` | back |
| `QR_GENERATOR_URL`, `BACK_URL`, `API_INTERNE` | `http://qr-generator:8001`, `http://back:8000` | back, qr-verifier, front |
| `CORS_ORIGINS`, `URL_API`, `URL_QR`, `URL_VERIFICATION` | domaine du site, valeurs vides (même origine) | tous |

Le **mot de passe** de la base n'est pas dans la ConfigMap (elle n'est pas chiffrée, tout lecteur du namespace la voit) mais dans un **Secret**, `cinetint-secrets`. Dans le Deployment du
back, Kubernetes assemble l'URL de connexion avec la syntaxe `$(VARIABLE)` à partir des variables déclarées juste au-dessus (ConfigMap pour l'hôte, le port, la base et l'utilisateur ;
Secret pour le mot de passe) :

```yaml
- name: DATABASE_URL
  value: "postgresql+asyncpg://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@$(POSTGRES_HOST):$(POSTGRES_PORT)/$(POSTGRES_DB)"
```

Avantage : pour changer de base ou de port, on modifie une valeur dans `values.yaml` ; l'image Docker ne change pas (les variables sont découplées du conteneur, slide 17 du cours).
Une annotation `checksum/config` sur les Pods relance les Deployments quand la ConfigMap change (sinon ils garderaient l'ancienne valeur).

## Points de conception

- **Secrets générés, jamais dans le dépôt** : mots de passe aléatoires créés au premier `helm install` (`randAlphaNum`), puis relus dans le cluster (`lookup`) à chaque `helm upgrade` pour ne pas
  les changer. La clé Ed25519 des billets est générée de la même façon (`genPrivateKey "ed25519"`). Mot de passe du back-office : voir `commandes.txt`.
- **Un seul fichier de valeurs par défi** : `values-defiN.yaml` décrit l'état complet voulu à la fin du défi N. Passer d'un défi au suivant, c'est `helm upgrade -f values-defi(N+1).yaml`.
- **Sans `--wait`** : la charte contient un PVC de sauvegarde que le fournisseur de stockage ne lie qu'au premier Pod qui s'en sert, donc `--wait` attendrait indéfiniment. Les sondes et le hook de
  test de fumée (défi 15) jouent le rôle de barrière.
- **Aucune ressource hors du namespace** : pas de namespace, ClusterRole, CRD ni StorageClass, conformément aux droits du compte `u-XXX`.

## Fiche oral (schéma)

1. Le poste exécute `helm upgrade --install` : Helm fusionne `templates/` et `values-defi6.yaml`, appelle l'API server et stocke la révision dans un Secret du namespace.
2. Les ressources créées sont celles du défi 5 : 4 Deployments applicatifs, Redis, PostgreSQL, 6 Services ClusterIP, 2 Ingress.
3. Nouveautés : la ConfigMap `cinetint-config` (hôte, port, base, utilisateur) et le Secret `cinetint-secrets` (mot de passe), injectés dans les Pods du back par `configMapKeyRef` / `secretKeyRef`.
4. L'URL `DATABASE_URL` est assemblée par Kubernetes dans le conteneur du back ; l'image Docker ne contient aucune configuration.
5. Le reste du chemin réseau est celui du défi 5 (Ingress, Services, kube-proxy, CoreDNS).

## Vérifié sur cluster local

```text
$ helm upgrade --install cinetint ../helm/cinetint -n u-test -f ../helm/cinetint/values-kind.yaml -f values-defi6.yaml
STATUS: deployed   REVISION: 1
deployment "front", "back", "qr-generator", "qr-verifier", "redis" successfully rolled out
$ python3 k8s/outils/parcours.py http://localhost:8080 --hote cinetint.test --controleur ...
OK  (17 contrôles : sondes, programme, réservation, paiement, billets, PDF, QR, contrôle d'entrée, /internal fermé)  ->  Résultat : tout passe
```
