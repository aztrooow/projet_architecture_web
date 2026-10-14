# Défi 2 : un Deployment de 3 répliques, un Service ClusterIP, un proxy

Fichiers : `deployment.yaml`, `service.yaml`, `commandes.txt`, `schema.svg`.

## Contenu réalisé

- **Deployment `csc8567`** : 3 répliques de `xhelozs/csc8567:v1`, avec `requests` 100m CPU / 100Mi de mémoire et `limits` 200m CPU / 200Mi.
  Le Deployment pilote un ReplicaSet qui maintient 3 Pods vivants : si l'un disparaît, un autre est créé.
- **Service `csc8567`** de type ClusterIP (port 80, cible le port 5000 des pods). Le port du Service n'a volontairement pas de nom :
  l'URL de proxy `.../services/csc8567/proxy/` ne fonctionne que si le Service a un seul port sans nom (sinon il faut écrire `csc8567:http`).
- **Accès** : `kubectl proxy` ouvre `127.0.0.1:8001` ; l'API server relaie `/api/v1/namespaces/u-XXX/services/csc8567/proxy/` vers un des pods du Service.

## Questions

### 1. Quel est le but d'un Service ?

Un Pod est éphémère : son IP change à chaque recréation, et un Deployment en crée plusieurs. Le Service donne un **point d'accès stable** à
un ensemble de Pods choisis par leurs étiquettes (`selector`). Il fournit :

- une **IP virtuelle** stable (ClusterIP, réseau des services 10.43.0.0/16) et une **entrée DNS** (`csc8567.u-XXX.svc.cluster.local`) ;
- un **équilibrage de charge** entre les Pods prêts (kube-proxy écrit des règles iptables sur chaque nœud qui redirigent l'IP virtuelle vers l'un des Pods) ;
- la **découverte** : le contrôleur d'EndpointSlices tient à jour la liste des IP de Pods prêts, les Pods en panne en sortent automatiquement.

### 2. Différence entre ClusterIP et NodePort ?

- **ClusterIP** (défaut) : IP virtuelle accessible **seulement depuis l'intérieur du cluster** (autres Pods, proxy de l'API server). C'est le type de
  tous les Services internes (back, base, Redis...).
- **NodePort** : en plus de la ClusterIP, ouvre le **même port (30000 à 32767) sur chaque nœud** du cluster ; un client externe qui joint
  `IP-du-nœud:port` est redirigé vers les Pods. C'est la façon la plus simple de sortir du cluster, mais elle expose des ports élevés sur tous les
  nœuds. Sur le cluster du cours on ne l'utilise pas : l'Ingress derrière un LoadBalancer MetalLB sert d'entrée unique (défi 4).
  Un LoadBalancer est un NodePort auquel un fournisseur (ici MetalLB) ajoute une IP externe.

### 3. Le schéma

Voir `schema.svg` et la fiche ci-dessous.

## Fiche oral (schéma)

1. Le Deployment `csc8567` demande 3 Pods ; le ReplicaSet les crée, le scheduler les répartit sur les workers (IP 10.42.x.y, port 5000), chacun avec ses limites 100m/100Mi et 200m/200Mi.
2. Le Service `csc8567` (ClusterIP 10.43.x.y, port 80) reçoit une IP virtuelle qui n'existe sur aucune interface. CoreDNS (10.43.0.10) résout `csc8567.u-XXX.svc.cluster.local` vers cette IP.
3. Sur chaque nœud, **kube-proxy** a écrit des règles iptables : un paquet vers 10.43.x.y:80 est réécrit (DNAT) vers l'un des trois Pods (10.42.x.y:5000), choisi au hasard.
4. `kubectl proxy` n'utilise pas ce réseau : il relaie les requêtes vers l'API server qui, à son tour, joint le Service (`/api/v1/namespaces/u-XXX/services/csc8567/proxy/`).
5. Les trois Pods répondent à tour de rôle ; si l'un tombe, il sort des endpoints et le ReplicaSet le recrée.

## Vérifié sur cluster local

```text
$ kubectl apply -f deployment.yaml -f service.yaml
$ kubectl get deployments,pods,services,endpoints -o wide
deployment.apps/csc8567   3/3   3   3   13s   csc8567   xhelozs/csc8567:v1
pod/csc8567-7bb49889b6-8llgt   1/1 Running   10.42.251.213   cinetint-worker
pod/csc8567-7bb49889b6-c5fxc   1/1 Running   10.42.128.108   cinetint-worker2
pod/csc8567-7bb49889b6-pqjx5   1/1 Running   10.42.128.107   cinetint-worker2
service/csc8567   ClusterIP   10.43.61.135   <none>   80/TCP
endpoints/csc8567   10.42.128.107:5000,10.42.128.108:5000,10.42.251.213:5000
$ kubectl top pods
csc8567-7bb49889b6-8llgt   14m   18Mi
$ kubectl proxy --port=8001 &
$ curl -s http://127.0.0.1:8001/api/v1/namespaces/u-defis/services/csc8567/proxy/
<h1>CSC 8567</h1><p>Site assez simpliste !</p><p>v1</p>...
```

Piège rencontré : avec un port de Service nommé (`name: http`), l'URL de proxy sans nom de port renvoie « no endpoints available for service ».
