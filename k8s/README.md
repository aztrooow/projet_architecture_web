# CinetINT sur Kubernetes : défis du cours CSC 8567

Partie Kubernetes du projet (sujet : https://github.com/DF-Telecom-SudParis/CSC8567-Final). La note dépend du nombre de **défis validés** (démonstration + explication du schéma devant un enseignant) ;
réussir proprement le défi 12 (PostgreSQL maître/réplique écrit à la main) assure la note maximale, les défis suivants sont des bonus. Chaque dossier `defiN/` contient ce que le sujet exige pour le rendu :
les fichiers appliqués (ou `commandes.txt`), un `schema.svg` (infrastructure réseau complète du défi) et `reponses.md` (réponses aux questions, **fiche oral** de 5 lignes pour expliquer le schéma, preuves relevées sur un cluster de test).

```text
k8s/
  defi1 ... defi16, defi18, defi19, defi20   un dossier par défi (commandes.txt, manifests ou values-defiN.yaml, schema.svg, reponses.md)
  helm/cinetint/                            la charte Helm de tout le projet (+ sous-charte charts/postgres-replication, défi 13)
  images.sh                                 construit et pousse cinetint-front, -back, -qr-generator, -qr-verifier (registre paramétrable)
  appliquer.sh                              applique/supprime les manifests simples des défis 2 à 5 et 12 ; crée les Secrets
  rendu.sh                                  fabrique l'archive de rendu (un dossier par défi)
  outils/                                   parcours.py (test de fumée complet), démonstrations, kind-creer.sh, generer_schemas.py
```

## État des défis

| Défi | Sujet | Contenu | Vérifié sur cluster local |
|---|---|---|---|
| 1 | Premier Pod | `commandes.txt` (image `xhelozs/csc8567:v1`, port-forward) | oui |
| 2 | Deployment x3 + Service + proxy | manifests, requests 100m/100Mi, limits 200m/200Mi, `kubectl proxy` | oui |
| 3 | Site + base | Pod à deux conteneurs front+back, Deployment PostgreSQL (fichiers séparés), Redis | oui |
| 4 | Ingress | Ingress vers `django.<groupe>.csc8567.luxbulb.org` | oui (Host forcé) |
| 5 | Infrastructure complète | 4 services + Redis + PostgreSQL, 6 Services ClusterIP, Ingress | oui, parcours complet |
| 6 | Helm + ConfigMap | charte `helm/cinetint`, ConfigMap de connexion | oui |
| 7 | StatefulSet + PV + headless | PostgreSQL persistant (PVC 100Mi) | oui, données survivent à la suppression du Pod |
| 8 | Rolling Update | v1 vers v2 du front (page `/infos`) | oui, 861 requêtes, 0 erreur |
| 9 | HPA | 60 % CPU, 3 à 10 Pods (front et back) | oui, 3 à 10 puis retour à 3 |
| 10 | Liveness probes | une sonde adaptée par conteneur (+ readiness, startup) | oui, panne de base simulée |
| 11 | NetworkPolicy | seul le back (et les sauvegardes) joint la base | oui, 4 cas |
| 12 | Maître/esclave PostgreSQL | StatefulSets primaire + réplique, `pg_basebackup`, slot, Secret, 4 Services | oui, écriture/lecture/read-only/`pg_stat_replication`/reprise/promotion |
| 13 | Idem en Helm | sous-charte `postgres-replication` incluse dans la charte | oui |
| 14 | Redis | rôle réel d'après le code, charte, NetworkPolicy | oui (verrous, TTL, pub/sub) |
| 15 | Hooks Helm | carnet de déploiement (ConfigMap) avant/après, sauvegardes avant/après la mise à jour | oui |
| 16 | Sauvegarde | CronJob `pg_dump` vers un PVC dédié, restauration | oui, sinistre puis restauration |
| 18 | Durcissement | non root, capabilities, lecture seule, limites de débit, NetworkPolicy, Secrets | oui |
| 19 | CI | `.github/workflows/ci.yml` : tests, charte, cluster kind éphémère, publication | étapes rejouées en local, workflow non exécuté sur GitHub |
| 20 | Migrations sans interruption | expand/contract avec Alembic, rolling update sous charge d'écriture | oui, 0 erreur ; limite du retour arrière documentée |

### Défis non réalisés, et pourquoi

- **Défi 17 (« faire crasher le site de la correction »)** : il s'agit d'attaquer le service d'un autre groupe sur le cluster partagé. Ce n'est pas du travail sur notre infrastructure, et attaquer un système qui ne nous appartient pas est hors sujet
  pour ce projet (et contraire à l'éthique du cours). Le défi 18 (durcissement) est traité de façon générale, avec l'hypothèse sur l'attaque expliquée dans `defi18/reponses.md`.
- **Défi 21 (hébergement de machines virtuelles)** : demande un opérateur de virtualisation (par exemple KubeVirt) qui installe des **CRD, des ClusterRoles et un DaemonSet privilégié** et de la virtualisation matérielle sur les nœuds.
  Le compte du cours est limité à un namespace (pas de ressource de cluster, pas de CRD) : c'est impossible avec nos droits.
- **Défi 22 (Kubeflow, MNIST)** : Kubeflow est un ensemble d'opérateurs avec des dizaines de **CRD cluster**, un maillage de services (Istio), des ressources importantes ; impossible dans un namespace sans droits d'administration du cluster.

## Démarrage sur le cluster du cours

1. Installer `kubectl` (https://kubernetes.io/fr/docs/tasks/tools/install-kubectl/) et `helm` (https://helm.sh/docs/intro/install/). La charte est testée avec Helm 4.3.0 ; le format de charte (`apiVersion: v2`) est celui de Helm 3, mais non testé avec Helm 3.
2. Donner la composition du groupe à un enseignant : il crée le namespace `u-XXX` et le compte. Se connecter à https://csc8567.luxbulb.org, créer un mot de passe, « Cluster Management », cluster `csc8567`, « Download KubeConfig »,
   puis `mkdir -p ~/.kube && mv ~/Téléchargements/csc8567.yaml ~/.kube/config`.
3. Contrôler : `kubectl get pods -n u-XXX` doit répondre « No resources found ». Pour ne plus taper `-n` : `kubectl config set-context --current --namespace=u-XXX`.
4. Contrôler les droits utiles (le compte est limité au namespace) :

   ```text
   kubectl auth can-i create deployments -n u-XXX      kubectl auth can-i create ingresses -n u-XXX
   kubectl auth can-i create networkpolicies -n u-XXX  kubectl auth can-i create persistentvolumeclaims -n u-XXX
   kubectl auth can-i create roles -n u-XXX            # utile pour les hooks du défi 15 (sinon hooks.configMap.rbac=false)
   kubectl get resourcequota,limitrange -n u-XXX       # quotas éventuels du namespace
   kubectl top pods -n u-XXX                           # metrics-server présent (défi 9)
   kubectl get ingressclass                            # nom de la classe d'Ingress (nginx attendu)
   ```
5. Les images sont publiées en public sur le registre GitHub ghcr.io/eldertek. Pour les reconstruire et les publier (depuis la racine du dépôt) :

   ```text
   gh auth token | docker login ghcr.io -u eldertek --password-stdin   # jeton avec le droit write:packages
   REGISTRE=ghcr.io/eldertek ./k8s/images.sh tout          # v1 des quatre images (construire + pousser)
   TAG=v2 REGISTRE=ghcr.io/eldertek ./k8s/images.sh tout front   # v2 du front pour le défi 8 (page /infos)
   ```

   Le script ne pousse rien sans `REGISTRE` explicite. Il construit pour l'architecture de la machine : le cluster est en amd64, sur un Mac ARM construire à la main avec `docker buildx build --platform linux/amd64 --push`.
   Rate limit de Docker Hub (images postgres et redis) : les nœuds du cluster partagent des adresses IP ; si des `ImagePullBackOff` « toomanyrequests » apparaissent, créer un Secret `docker-registry` et le déclarer dans `images.pullSecrets`.

## Ordre d'application et commandes de démonstration

Chaque défi laisse l'état voulu pour le suivant, sauf deux transitions qui demandent de repartir d'une installation propre (indiquées dans les `commandes.txt`) : défi 6 vers 7 (le Service de la base change de nature)
et défis 12/13 (une seule base à la fois). Le détail de chaque démonstration est dans `defiN/commandes.txt` ; les explications dans `defiN/reponses.md`.

| Défi | Appliquer | Montrer à l'enseignant |
|---|---|---|
| 1 | `kubectl create deployment csc8567 --image=xhelozs/csc8567:v1` | `kubectl get pods -o wide`, `port-forward`, page dans le navigateur |
| 2 | `kubectl apply -f defi2/` | 3 Pods, `kubectl get endpoints`, `kubectl proxy` + URL du Service, supprimer un Pod |
| 3 | `NAMESPACE=u-XXX ./k8s/appliquer.sh secrets && REGISTRE=... ./k8s/appliquer.sh defi3` | Pods à 2 conteneurs, `kubectl proxy` vers `site:front` et `site:api`, `nslookup postgres` |
| 4 | `HOTE=django.<groupe>.csc8567.luxbulb.org ./k8s/appliquer.sh defi4` (puis demander l'entrée DNS) | `https://django.<groupe>.csc8567.luxbulb.org/` |
| 5 | `./k8s/appliquer.sh defi4 supprimer`, puis `./k8s/appliquer.sh defi5` | `python3 k8s/outils/parcours.py https://django.<groupe>... --controleur <mdp>` |
| 6 | `helm upgrade --install cinetint helm/cinetint -n u-XXX -f helm/cinetint/values-cours.yaml -f defi6/values-defi6.yaml --set images.registre=... --set ingress.host=...` | `helm list`, `kubectl get configmap cinetint-config -o yaml` |
| 7 | `helm uninstall` puis même commande avec `defi7/values-defi7.yaml` | PVC lié, supprimer `postgres-0`, la donnée survit |
| 8 | valeurs du défi 8 puis `--set images.tags.front=v2` | boucle de `curl` sans erreur, `kubectl rollout status/history/undo` |
| 9 | valeurs du défi 9 | `kubectl get hpa -w` pendant une charge (fortio) |
| 10 | valeurs du défi 10 | `describe pod`, base arrêtée (back non Ready mais non redémarré), `exemple-liveness-en-echec.yaml` |
| 11 | valeurs du défi 11 | `outils/test-networkpolicy.sh` |
| 12 | `./k8s/appliquer.sh secrets-postgres && ./k8s/appliquer.sh defi12` | `outils/demo-replication.sh` |
| 13 | valeurs du défi 13 (la base du défi 12 doit être supprimée) | `outils/demo-replication.sh` avec `SECRET=cinetint-secrets` |
| 14 | valeurs du défi 14 | `outils/demo-redis.sh` |
| 15 | valeurs du défi 15 | carnet `cinetint-deploiement`, sauvegardes avant/après sur le volume |
| 16 | valeurs du défi 16 | `kubectl create job --from=cronjob/cinetint-sauvegarde`, sinistre, `restaurer-job.yaml` |
| 18 | valeurs du défi 18 | `outils/demo-securite.sh`, `outils/test-networkpolicy.sh` |
| 19 | `.github/workflows/ci.yml` | onglet Actions de GitHub (voir `defi19/reponses.md`) |
| 20 | valeurs du défi 20 | `outils/demo-migration.sh` (boucles d'écriture et de lecture pendant la mise à jour) |

Les mots de passe (back-office `gerant`, contrôle `controleur`) sont générés : `kubectl get secret cinetint-secrets -n u-XXX -o jsonpath='{.data.GERANT_MOT_DE_PASSE}' | base64 -d`.
**Laisser tous les déploiements sur le cluster après le rendu** (consigne du sujet) : l'état à laisser est celui du dernier défi réalisé (valeurs du défi 18 ou 20).

## La charte Helm

`helm/cinetint/values.yaml` est entièrement commenté en français. Les `values-defiN.yaml` sont **cumulatifs** : chacun décrit l'état complet voulu à la fin du défi N. `values-cours.yaml` fixe le registre, le domaine et la classe d'Ingress du cluster du cours,
`values-kind.yaml` ceux du cluster local. Options notables : `global.securite`, `postgres.mode` (`deployment`, `statefulset`, `externe`), `postgres-replication.enabled`, `hpa.*`, `sondes.*`, `networkPolicies.*`, `hooks.*`, `sauvegardes.*`, `ingress.limites`,
`images.tags.*`, `back.programmeSource` (`cgr`, `demo`, `aucune`).

La charte ne crée **aucune ressource hors du namespace** : pas de namespace, ClusterRole, CRD, StorageClass.

## Valider en local (cluster kind)

```text
k8s/outils/kind-creer.sh cinetint                       # 1 control-plane + 2 workers, Calico, ingress-nginx, metrics-server (http://localhost:8080)
REGISTRE=cinetint-local ./k8s/images.sh construire && ./k8s/images.sh kind
kubectl create namespace u-test
helm upgrade --install cinetint k8s/helm/cinetint -n u-test -f k8s/helm/cinetint/values-kind.yaml -f k8s/defi18/values-defi18.yaml
python3 k8s/outils/parcours.py http://localhost:8080 --hote cinetint.test --controleur "$(kubectl get secret cinetint-secrets -n u-test -o jsonpath='{.data.CONTROLEUR_MOT_DE_PASSE}' | base64 -d)"
```

Sur kind, le réseau par défaut (kindnet) n'applique pas les NetworkPolicy : le script installe Calico. Sur WSL, si la création d'un second cluster échoue, augmenter `fs.inotify.max_user_instances`.

## Pièges rencontrés

- **Pas de `--wait` avec la charte** : le volume de sauvegarde n'est lié qu'au premier Pod qui s'en sert (classe de stockage en `WaitForFirstConsumer`), donc `--wait` attendrait indéfiniment. Le hook post-déploiement (défi 15) attend les quatre services et fait échouer le `helm upgrade` si l'un ne répond pas.
- **StorageClass et taille** : la charte laisse la classe par défaut du cluster (`postgres.persistance.storageClass`). Un PVC de 100Mi est très petit : réglages du journal PostgreSQL (`max_wal_size=48MB`) pour tenir (65 Mo utilisés sur kind). À vérifier sur le cluster du cours.
- **Quota du namespace** : l'infrastructure demande environ 1,3 CPU et 1,3 Gi de mémoire en `requests` (3 front, 3 back, 2 qr-generator, 2 qr-verifier, Redis, 2 PostgreSQL), davantage avec l'HPA (jusqu'à 10 front et 10 back). Demander s'il existe un `ResourceQuota` ;
  sinon baisser les répliques (`front.replicas`, `back.replicas`, `qrGenerator.replicas`...) ou `hpa.max`.
- **Classe d'Ingress et TLS** : `ingress.className: nginx` (à confirmer par `kubectl get ingressclass`). Pour HTTPS, le certificat dépend du cluster : certificat par défaut du contrôleur, ou cert-manager (`ingress.tls.clusterIssuer`).
- **NetworkPolicy et contrôleur Ingress** : sans les règles qui l'autorisent, l'Ingress ne joindrait plus les Pods ; `networkPolicies.namespaceIngress` doit être le namespace du contrôleur (`kube-system` sur RKE2, `ingress-nginx` sur kind).
- **Hooks et droits** : les hooks du défi 15 créent un ServiceAccount, un Role et un RoleBinding dans le namespace. Si `kubectl auth can-i create roles` répond non, mettre `hooks.configMap.rbac=false` (avec un ServiceAccount existant) ou `hooks.configMap.enabled=false`.
- **Images externes** : `postgres:17-alpine`, `redis:8-alpine`, `alpine/kubectl` (hooks), `fortio/fortio` (charge du défi 9) viennent de Docker Hub.
- **Back sur Alembic** : l'image `back` exécute les migrations au démarrage sous verrou. Les images v1 (construites avant Alembic) créent le schéma avec `create_all`. Une image ne doit jamais être rétrogradée sous la dernière qui contient les migrations appliquées (défi 20).
- **Limite de débit** : `limit-rps` compte par adresse source vue par nginx ; derrière un LoadBalancer qui réécrit l'adresse, le seuil devient global (défi 18).

## Documentation officielle consultée

Kubernetes : https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/ (HPA, algorithme et comportement par défaut), https://kubernetes.io/docs/concepts/services-networking/network-policies/,
https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/, https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/.
Helm : https://helm.sh/docs/topics/charts_hooks/ (hooks), https://helm.sh/docs/topics/charts/ (dépendances et `condition`).
kind : https://kind.sigs.k8s.io/docs/user/configuration/ (`disableDefaultCNI`, `extraPortMappings`), https://kind.sigs.k8s.io/docs/user/ingress/.
PostgreSQL 17 : https://www.postgresql.org/docs/17/app-pgbasebackup.html (`-R`, `-S`, `-X stream`), https://www.postgresql.org/docs/17/runtime-config-replication.html (`max_slot_wal_keep_size`, `hot_standby`),
https://www.postgresql.org/docs/17/hot-standby.html (paramètres qui ne doivent pas être plus petits sur une réplique).
Versions utilisées en local : kind v0.33.0 (Kubernetes 1.37), kubectl 1.37.1, Helm 4.3.0, Calico 3.33.0, ingress-nginx controller-v1.15.1, metrics-server 0.9.0.
