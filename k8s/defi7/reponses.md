# Défi 7 : StatefulSet, volume persistant, service headless

Fichiers : `values-defi7.yaml`, `commandes.txt`, `schema.svg`. Modèle concerné dans la charte : `templates/postgres.yaml` (mode `statefulset`).

## Contenu réalisé (mise à jour de la charte Helm)

- **StatefulSet `postgres`**, une seule réplique (`replicas: 1`), image `postgres:17-alpine`, ressources 100m / 100Mi et 200m / 200Mi.
- **Volume persistant** : `volumeClaimTemplates` crée un PVC `data-postgres-0` de **100Mi** (0.1 Go), monté sur `/var/lib/postgresql/data`. Les données sont dans le sous-dossier `pgdata`
  (la racine d'un volume formaté contient `lost+found`, `initdb` refuse un dossier non vide). Le PVC est lié à un PV par le provisionneur de la StorageClass par défaut du cluster.
- **Service headless** `postgres` (`clusterIP: None`) : le DNS renvoie directement l'IP du Pod.
- **Réglages de PostgreSQL adaptés au petit volume et à 200Mi** : `shared_buffers=32MB`, `max_wal_size=48MB`, `min_wal_size=32MB` (sinon le journal d'écriture peut grossir jusqu'à 1 Go et remplir les 100Mi).
  Taille mesurée de la base avec ses données de démonstration : 11 Mo de données, 65 Mo en tout avec le journal.
- La charte reste utilisable en mode `deployment` (défi 6) : l'option `postgres.mode` choisit.
- Passage du défi 6 au défi 7 : le Service `postgres` change de ClusterIP à headless, ce qu'un `helm upgrade` refuse (champ `clusterIP` immuable). Procédure : `helm uninstall` puis réinstallation.

## Questions

### 1. Quel est l'avantage d'un StatefulSet par rapport à un Deployment ? Dans quel cas l'utilise-t-on ?

Un Deployment gère des Pods **interchangeables et jetables** (sans état) : noms aléatoires (`postgres-579b88-8kkzg`), tout nouveau Pod repart de zéro, mise à jour et arrêt dans le désordre.
Un **StatefulSet** apporte ce qu'une application **avec état** exige :

- **identité stable** : les Pods s'appellent `postgres-0`, `postgres-1`... et gardent leur nom après recréation ;
- **stockage stable** : chaque Pod a SON volume (`volumeClaimTemplates`), qui est **reconnecté au même Pod** après un redémarrage ou un déplacement et qui n'est pas supprimé avec lui ;
- **nom DNS stable** par Pod grâce au Service headless (`postgres-0.postgres.u-XXX.svc.cluster.local`) ;
- **ordre** : création, mise à jour et suppression dans l'ordre (0, 1, 2... ; en sens inverse à l'arrêt), ce qui permet qu'un primaire démarre avant ses répliques.

On l'utilise pour les bases de données (PostgreSQL, MySQL), les files de messages (Kafka, RabbitMQ), les systèmes de coordination (etcd, ZooKeeper) : tout ce qui doit retrouver ses données et son identité.
Preuve (cluster local) : une ligne écrite dans la base, `kubectl delete pod postgres-0`, le Pod est recréé avec le même nom, la même identité et le même volume : la ligne est toujours là.

### 2. Expliquez ce qu'est un service Headless

C'est un Service avec `clusterIP: None` : **il n'a pas d'IP virtuelle**. Il n'y a donc pas de règle kube-proxy ni d'équilibrage fait par Kubernetes. À la place, le DNS du cluster renvoie
**directement les IP des Pods** qu'il sélectionne : une requête DNS sur `postgres` donne l'IP du Pod (`10.42.128.71` dans notre test), et s'il y avait plusieurs Pods, plusieurs enregistrements A.
Pour un StatefulSet, il crée en plus un enregistrement par Pod (`postgres-0.postgres...`). On s'en sert quand le client doit choisir lui-même son interlocuteur (primaire ou réplique d'une base,
membres d'un cluster) ou quand on veut éviter un intermédiaire inutile : ici la base n'a qu'un Pod, le headless est un choix de cohérence avec le StatefulSet (c'est aussi ce que la documentation de Kubernetes
prescrit pour `serviceName`).

### 3. Mise à jour de la charte Helm

Voir `templates/postgres.yaml` (StatefulSet, volumeClaimTemplates, Service headless) et `values-defi7.yaml` (`postgres.mode: statefulset`, `postgres.persistance.enabled: true`, taille `100Mi`).

### 4. Le schéma

Voir `schema.svg` et la fiche oral.

## Fiche oral (schéma)

1. Le StatefulSet `postgres` crée un seul Pod `postgres-0`, à l'identité stable, sur un worker (IP 10.42.x.y).
2. Son volumeClaimTemplate crée le PVC `data-postgres-0` (100Mi), lié à un PV par la StorageClass par défaut ; le volume est monté dans le conteneur sur `/var/lib/postgresql/data`.
3. Si le Pod est supprimé, le StatefulSet recrée `postgres-0` et reconnecte le MÊME PVC : les données survivent (contrairement à un Deployment, défi 3).
4. Le Service `postgres` est headless : pas d'IP virtuelle, pas de kube-proxy sur ce chemin. CoreDNS répond directement avec l'IP du Pod ; le back se connecte donc au Pod sans intermédiaire.
5. Le reste de l'infrastructure est inchangé (Ingress, 3 front, 3 back, qr-generator, qr-verifier, Redis).

## Vérifié sur cluster local

```text
$ helm upgrade --install cinetint ../helm/cinetint -f values-kind.yaml -f values-defi7.yaml
$ kubectl get pvc,pv
persistentvolumeclaim/data-postgres-0   Bound   pvc-38331260-8bd4-4a30-b0af-bab72cdf1091   100Mi   RWO   standard
$ kubectl exec postgres-0 -- psql -U cinetint -d cinetint -c "CREATE TABLE marqueur(...); INSERT INTO marqueur VALUES (1, 'ecrit avant la suppression du pod')" -c 'SELECT count(*) FROM films'
 films: 8
$ kubectl delete pod postgres-0 ; kubectl wait --for=condition=Ready pod/postgres-0
$ kubectl exec postgres-0 -- psql ... -c 'SELECT * FROM marqueur' -c 'SELECT count(*) FROM films'
 1 | ecrit avant la suppression du pod        films: 8
$ kubectl run dns --rm -i --image=busybox:1.37 -- nslookup postgres.u-test.svc.cluster.local
Name: postgres.u-test.svc.cluster.local   Address: 10.42.128.71      (IP du Pod, pas d'IP virtuelle)
```

Limite du cluster local : le provisionneur `local-path` de kind ne fait pas respecter la taille demandée (100Mi) ; sur le cluster du cours, la StorageClass appliquera sans doute la limite, d'où
les réglages du journal ci-dessus (65 Mo utilisés sur 100).
