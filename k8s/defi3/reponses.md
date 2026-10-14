# Défi 3 : le site et sa base de données

Fichiers : `site-deployment.yaml`, `site-service.yaml` (le site), `postgres-deployment.yaml`, `postgres-service.yaml` (la base, dans des
fichiers séparés comme demandé), `redis.yaml` (voir ci-dessous), `commandes.txt`, `schema.svg`.

## Contenu réalisé

- **Le site** : un Deployment `site` de 3 répliques. CinetINT n'est pas un projet Django à deux applications dans une seule image : ce sont deux
  processus distincts (`front` = équivalent de « public », `back` = équivalent de « api »). L'équivalent fidèle de « une image avec les deux apps »
  est un **Pod à deux conteneurs** (slide 7 du cours : « un Pod contient un ou plusieurs conteneurs »). Les deux conteneurs partagent l'IP et le
  `localhost` du Pod : le front appelle l'API sur `http://localhost:8000`. Chaque conteneur a ses ressources (100m / 100Mi demandés, 200m / 200Mi en limite).
- **Le Service `site`** (ClusterIP) expose les deux ports : 8080 (front) et 8000 (back).
- **La base** : un Deployment `postgres` d'un seul Pod (`postgres:17-alpine`), un Service ClusterIP `postgres` sur 5432. Les mots de passe
  viennent d'un Secret créé par commande (`appliquer.sh secrets`), jamais écrits dans le dépôt.
- **Redis** : le back en a besoin dès le démarrage (verrous de sièges, compteurs, temps réel ; sa sonde `/api/sante` le teste). Il n'est pas demandé
  par le sujet mais le back ne répond pas sans lui : un Deployment et un Service ClusterIP `redis`.
- Les images `cinetint-front:v1` et `cinetint-back:v1` sont construites par `k8s/images.sh` (registre paramétrable) et publiées sur le registre public ghcr.io/eldertek. On change de tag
  à chaque nouvelle image : le cluster ne retélécharge pas un tag déjà présent dans son cache.
- Le qr-generator et le qr-verifier n'arrivent qu'au défi 5 (« infrastructure complète ») : jusqu'au défi 4 on peut parcourir le programme, mais pas acheter.

## Questions

### 1. Différence entre un Service ClusterIP et NodePort ?

Voir le défi 2 : ClusterIP = IP virtuelle interne au cluster ; NodePort = ClusterIP + un port (30000-32767) ouvert sur **chaque nœud** pour joindre le Service
de l'extérieur. Ici tous les Services (`site`, `postgres`, `redis`) sont des ClusterIP : seul le site sera exposé, par l'Ingress (défi 4), et la base ne doit
jamais l'être.

### 2. Critique de l'utilisation d'un Pod (Deployment) pour la base de données

- **Pas de persistance** : les données sont dans le système de fichiers du conteneur. Si le Pod est supprimé, déplacé ou redémarré, la base repart vide
  (dans notre cas : le back recrée le schéma et les données de démonstration, mais les commandes et billets sont perdus). C'est ce que corrige le défi 7 (volume persistant).
- **Pas d'identité stable** : le nom du Pod change à chaque recréation (`postgres-579b8878f9-xxxxx`). Un Deployment est conçu pour des applications **sans état**, interchangeables.
- **Pas de haute disponibilité** : un seul Pod, donc une seule base ; pendant sa recréation, le site est en panne. Plus d'une réplique d'un Deployment donnerait deux bases vides
  indépendantes, pas une base répliquée (c'est le défi 12).
- **Mises à jour risquées** : la stratégie par défaut (RollingUpdate) démarrerait un second Pod PostgreSQL avant d'arrêter le premier ; d'où `strategy: Recreate` dans `postgres-deployment.yaml`.
- **Sauvegarde et sécurité** : rien ne sauvegarde ces données, et sans NetworkPolicy tout Pod du cluster peut s'y connecter (défis 11, 16, 18).

### 3. Sur quel type de ressource KubeDNS crée-t-il des entrées ? Quelle information propre à la ressource est utilisée ?

Le DNS du cluster (KubeDNS, aujourd'hui **CoreDNS**, Service `kube-dns` 10.43.0.10 dans `kube-system`) crée des entrées pour les **Services** (et, pour les Services *headless*,
pour les Pods qui les composent). Les informations de la ressource utilisées sont :

- son **nom** et son **espace de noms**, qui forment le nom DNS `<service>.<namespace>.svc.cluster.local` (depuis le même namespace, le nom court `postgres` suffit grâce au
  domaine de recherche du Pod) ;
- son **ClusterIP** (`spec.clusterIP`) : l'enregistrement A renvoie cette IP virtuelle ;
- pour un Service *headless* (`clusterIP: None`), les **IP des Pods prêts** (EndpointSlices) : un enregistrement A par Pod ;
- pour un port nommé, un enregistrement SRV `_port._protocole.service.namespace.svc.cluster.local`.

Le DNS ne fait pas d'entrées pour les Deployments ni pour les ReplicaSets : un Deployment n'a pas d'adresse, seul le Service qui sélectionne ses Pods en a une.

### 4. Le schéma

Voir `schema.svg` et la fiche oral.

## Fiche oral (schéma)

1. Trois Pods `site` identiques, chacun avec deux conteneurs : front (8080) et back (8000) qui se parlent par `localhost`, sur la même IP de Pod (10.42.x.y).
2. Le Service `site` (ClusterIP) a une IP virtuelle 10.43.x.y avec deux ports ; kube-proxy répartit les connexions entre les trois Pods par des règles iptables.
3. Le back joint la base par le **nom DNS `postgres`** : CoreDNS répond avec la ClusterIP du Service `postgres`, kube-proxy redirige vers l'unique Pod PostgreSQL. Idem pour `redis`.
4. Le mot de passe de la base est dans un Secret injecté en variable d'environnement ; l'URL de connexion est assemblée par Kubernetes avec `$(POSTGRES_PASSWORD)`.
5. Accès par `kubectl proxy`, qui joint les Services via l'API server. La base est dans un Deployment : si son Pod meurt, les données sont perdues (limite corrigée au défi 7).

## Vérifié sur cluster local

```text
$ ./k8s/appliquer.sh secrets && ./k8s/appliquer.sh defi3
$ kubectl get pods -o wide
site-b77bc7b5b-2fmmp   2/2   Running   10.42.128.112   cinetint-worker2
site-b77bc7b5b-m2jvt   2/2   Running   10.42.251.214   cinetint-worker
site-b77bc7b5b-mld8p   2/2   Running   10.42.128.111   cinetint-worker2
postgres-579b8878f9-8kkzg   1/1   Running   10.42.128.109   cinetint-worker2
redis-6c857db5cb-qzfcp      1/1   Running   10.42.128.110   cinetint-worker2
$ kubectl top pods --containers      (après 1 minute)
site-b77bc7b5b-2fmmp   back    126m   82Mi      # pic de démarrage, 76 à 82 Mi ensuite
site-b77bc7b5b-2fmmp   front     2m   42Mi
postgres-579b8878f9-8kkzg  postgres  40m  54Mi
$ curl http://127.0.0.1:8001/api/v1/namespaces/u-defis/services/site:front/proxy/        -> 200
$ curl http://127.0.0.1:8001/api/v1/namespaces/u-defis/services/site:api/proxy/api/sante  -> {"statut":"ok"}
```

Remarque : au premier démarrage, chaque conteneur `back` redémarre une fois (`RESTARTS 1`) parce que PostgreSQL n'est pas encore prêt quand il se lance et que l'API s'arrête si
la base est injoignable. Le défi 5 ajoute un initContainer qui attend la base, la charte Helm aussi. Mémoire mesurée : toutes les tailles tiennent largement dans la limite de 200Mi.
