# Défi 19 (bonus) : site de production et workflows de test avant mise à jour

Fichiers : `ci.yml` (copie du workflow `.github/workflows/ci.yml` du dépôt), `schema.svg`, `reponses.md`. Le workflow lui-même vit dans `.github/workflows/ci.yml`.

## Ce que le sujet demande

« Mettez à jour votre site pour qu'il convienne à un environnement de production. Mettez en particulier en place des workflows pour tester votre site sur le cluster avant d'installer la mise à jour. »

- **Convenir à la production** : c'est l'ensemble de la charte : 3 répliques et HPA (défi 9), sondes (défi 10), NetworkPolicy (défis 11 et 18), durcissement (défi 18), volumes persistants (défi 7), réplication (défi 12 et 13),
  sauvegardes et restauration (défis 15 et 16), migrations sans interruption (défi 20), Secrets générés, ressources bornées.
- **Workflows de test sur un cluster avant la mise à jour** : le workflow GitHub Actions décrit ci-dessous. Les tests tournent sur un **cluster Kubernetes jetable** (kind) créé à chaque exécution, jamais sur le cluster du cours.

## Le workflow (`.github/workflows/ci.yml`)

Déclenché à chaque `push` sur `main` ou tag `v*`, à chaque pull request, et à la demande (`workflow_dispatch`). Les portes de qualité s'enchaînent, rien n'est publié tant que tout n'est pas vert :

| Job | Ce qu'il fait | Échec = |
|---|---|---|
| `tests` (x4 en parallèle) | `docker compose --profile tests run --rm <service>-tests` pour back (avec vraie base PostgreSQL et Redis, 25 réservations simultanées, contrainte d'unicité...), qr-generator, qr-verifier, front : les mêmes commandes que le README | une régression de code |
| `charte` | `helm lint` de la charte avec **chaque** jeu de valeurs des défis (et la réplication), puis `helm template` validé par **kubeconform** contre le schéma de l'API Kubernetes ; manifests simples des défis 2 à 5 et 12 validés de même | une charte invalide ou un manifest qui ne passerait pas à l'API |
| `cluster` | crée un cluster **kind** (1 control-plane + 2 workers, Calico, ingress-nginx, metrics-server : `k8s/outils/kind-creer.sh`), construit les 4 images de la version testée, les charge, **installe la charte** (état final du défi 18) ; exécute `helm test` (les hooks de la charte font déjà un test de fumée) ; rejoue le **parcours complet** par l'Ingress (achat, QR code, PDF, contrôle d'entrée, seconde présentation refusée, `/internal` fermé) ; fait un **redémarrage progressif du front et du back sous charge d'écriture continue** (aucune erreur tolérée) ; vérifie l'**isolation réseau** (le front ne joint pas la base) | l'application ne marche pas **sur Kubernetes**, même si les tests unitaires passent |
| `publier` | construit et envoie les 4 images sur **ghcr.io** (`ghcr.io/<propriétaire>/cinetint-<service>:<tag>`), **seulement** après un push sur `main` ou un tag `v*` ou une demande explicite, **et seulement si tous les jobs précédents sont verts** | (rien n'est publié) |
| `deploiement` | facultatif, manuel (`workflow_dispatch` avec `deployer`) : met à jour la charte sur le cluster du cours avec les images publiées, puis `helm test` ; exige le secret `KUBECONFIG_COURS`, les variables `NAMESPACE_COURS` et `HOTE_COURS`, et un environnement `cours` (approbation possible) | le déploiement échoue, les anciennes versions restent en place (rolling update) |

Points de conception : permissions minimales (`contents: read`, `packages: write` seulement pour `publier`), annulation d'une exécution quand une plus récente arrive (`concurrency`), versions d'actions et d'outils épinglées, diagnostic automatique (état des Pods, événements, journaux)
en cas d'échec du job `cluster`, suppression du cluster à la fin quoi qu'il arrive. L'accès au cluster du cours depuis GitHub n'est pas supposé possible : le déploiement automatique est donc une option, désactivée par défaut.

## Fiche oral (schéma)

1. Un `push` ou une pull request déclenche le workflow. Deux portes en parallèle : les tests unitaires des quatre services (avec PostgreSQL et Redis réels) et la validation de la charte Helm (lint avec chaque jeu de valeurs, kubeconform).
2. Troisième porte : un cluster kind éphémère, proche du cluster du cours (Calico, ingress-nginx, metrics-server). On y installe la charte avec les images de la version testée.
3. Sur ce cluster : `helm test`, parcours complet d'un spectateur et d'un contrôleur par l'Ingress, redémarrage progressif sous charge d'écriture sans erreur, vérification de l'isolation réseau.
4. Seulement si tout est vert, et seulement sur `main` ou un tag : publication des images sur ghcr.io.
5. Déploiement sur le cluster du cours : étape manuelle et facultative, approuvée dans un environnement protégé ; sinon le déploiement se fait à la main avec les mêmes commandes (`k8s/README.md`).

## Vérifié

- `actionlint` (analyseur statique de workflows) : aucune erreur.
- Les étapes des jobs `charte` et `cluster` ont été **rejouées localement** dans les mêmes conditions : `helm lint` de la charte avec les 14 jeux de valeurs (0 échec), kubeconform sur les manifests rendus (toutes les ressources valides),
  création du cluster avec `kind-creer.sh`, installation de la charte, `helm test` (Succeeded), parcours complet (tout passe), redémarrage progressif sous charge d'écriture (504 tours, 0 erreur), isolation réseau (fermée).
- Exécution réelle sur GitHub le 14/10/2026 ([exécution 38574635616](https://github.com/aztrooow/projet_architecture_web/actions/runs/38574635616), 9 min 41 s) : tests back, front, qr-generator et qr-verifier, charte Helm, cluster kind (installation, parcours, mise à jour) et publication des images sur `ghcr.io` : tous en succès. Le déploiement sur le cluster du cours (manuel) n'a pas été lancé.
- Le job `tests` repose sur le profil `tests` de `docker-compose.yml`.
