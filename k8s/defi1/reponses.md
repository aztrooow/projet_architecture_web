# Défi 1 : premiers pas sur Kubernetes

Fichiers : `commandes.txt` (les commandes exécutées, ligne par ligne), `schema.svg` (schéma d'infrastructure).
Questions du sujet : aucune, le schéma suffit. Ce document sert d'aide pour l'expliquer.

## Ce que fait chaque commande

| Commande | Ce qui se passe dans le cluster |
|---|---|
| `kubectl create deployment csc8567 --image=xhelozs/csc8567:v1` | kubectl envoie un objet Deployment à l'**API server** (Node 1). Il est stocké dans **etcd**. Le contrôleur de Deployments crée un **ReplicaSet**, qui crée un **Pod**. Le **scheduler** choisit un nœud worker, le **kubelet** de ce nœud demande à containerd de télécharger l'image sur Docker Hub puis de démarrer le conteneur. |
| `kubectl get pods -o wide` | Montre le nom du Pod (`csc8567-<hash du ReplicaSet>-<suffixe>`), son IP dans le réseau des pods (10.42.x.y) et le nœud qui l'héberge. |
| `kubectl port-forward pods/<pod> 8080:5000` | kubectl ouvre le port 8080 de la machine locale. Chaque connexion est tunnelée par l'API server jusqu'au kubelet du nœud, puis jusqu'au port 5000 du Pod. Aucun Service n'est utilisé : on parle directement à un Pod précis. |
| `kubectl logs <pod>` | Lit la sortie standard du conteneur (les requêtes reçues par Flask). |

Un Pod est la plus petite unité déployable : un ou plusieurs conteneurs qui partagent la même IP et le même `localhost`
(slide 7 du cours). Ici il n'en contient qu'un, l'image `xhelozs/csc8567:v1` (Flask, port 5000).

## Fiche oral (schéma)

1. Mon poste exécute `kubectl`, qui parle à l'API server (port 6443, Node 1 master) avec le kubeconfig du cours.
2. L'API server enregistre le Deployment dans etcd ; le contrôleur crée le ReplicaSet puis le Pod.
3. Le scheduler place le Pod sur un worker, le kubelet démarre le conteneur Flask (port 5000), le Pod reçoit une IP du réseau des pods (10.42.x.y).
4. `port-forward` n'utilise aucun Service : le tunnel passe par l'API server et le kubelet, jusqu'au Pod, puis ressort sur `localhost:8080`.
5. Limite : un seul Pod. S'il disparaît le Deployment en recrée un, mais l'adresse change, d'où l'intérêt des Services au défi 2.

## Vérifié sur cluster local (kind, 1 control-plane + 2 workers, namespace de test)

```text
$ kubectl create deployment csc8567 --image=xhelozs/csc8567:v1
$ kubectl rollout status deployment/csc8567
deployment "csc8567" successfully rolled out
$ kubectl get pods -o wide
NAME                       READY   STATUS    IP              NODE
csc8567-55bc9cc7bb-8864w   1/1     Running   10.42.128.106   cinetint-worker2
$ kubectl port-forward pods/csc8567-55bc9cc7bb-8864w 18080:5000 &
$ curl -s localhost:18080/
<h1>CSC 8567</h1>
<p>Site assez simpliste !</p>
<p>v1</p>
<p>L'URL utilisé pour accéder au site : http://localhost:18080/</p><p>L'heure : 14/10/2026 11:33:37</p>
```

(Sur le cluster du cours, le namespace est `u-XXX` : ajouter `-n u-XXX` à chaque commande.)
