# Défi 9 : mise à l'échelle automatique (HPA)

Fichiers : `values-defi9.yaml`, `commandes.txt`, `schema.svg`. Modèle : `../helm/cinetint/templates/hpa.yaml`.
Question du sujet : « un schéma ! ». Ce document donne les explications utiles à l'oral.

## Contenu réalisé

Deux **HorizontalPodAutoscaler** (`autoscaling/v2`), un par Deployment :

| HPA | Cible | Mesure | Seuil | min / max |
|---|---|---|---|---|
| `front` | Deployment `front` | CPU moyen des Pods | 60 % de la demande (`requests.cpu` = 100m, donc 60m) | 3 / 10 |
| `back` | Deployment `back` | CPU moyen des Pods | 60 % | 3 / 10 |

Réglage `behavior.scaleDown.stabilizationWindowSeconds: 60` : Kubernetes attend 60 s (300 s par défaut) avant de retirer des Pods, pour que la démonstration se voie sans attendre cinq minutes.
Quand un HPA pilote un Deployment, la charte **n'écrit plus `replicas`** dans celui-ci : sinon chaque `helm upgrade` remettrait la valeur de départ et annulerait le travail de l'HPA.

## Comment ça marche

1. Le **kubelet** de chaque nœud mesure la consommation de chaque conteneur (cAdvisor). **metrics-server** (namespace kube-system) les collecte toutes les 15 s et les publie dans l'API `metrics.k8s.io`
   (`kubectl top pods` lit cette API). Sans metrics-server, un HPA reste à `<unknown>`. Le cluster du cours (RKE2) en fournit un ; sur kind il a fallu l'installer (avec `--kubelet-insecure-tls`).
2. Le **contrôleur HPA** (dans kube-controller-manager) interroge cette API toutes les 15 s et calcule :
   `replicas désirées = ceil( replicas actuelles x utilisation moyenne / cible )`. Avec 3 Pods à 200 % de leur demande (200m utilisés pour 100m demandés) et une cible de 60 % : ceil(3 x 200 / 60) = 10.
3. Il écrit le résultat dans le champ `replicas` du Deployment (sous-ressource `scale`), borné par min et max. Le Deployment ajuste son ReplicaSet qui crée ou supprime des Pods.
4. Une tolérance de 10 % évite de réagir aux petites variations. À la hausse l'HPA réagit vite (jusqu'à doubler, ou +4 Pods, par période) ; à la baisse il attend la fenêtre de stabilisation.
5. Le pourcentage est calculé par rapport à la **demande** (`requests`), pas à la limite : avec `requests.cpu: 100m` et `limits.cpu: 200m`, un Pod qui atteint sa limite est à 200 %.

## Fiche oral (schéma)

1. En bas, les workers : le kubelet de chaque nœud exporte la consommation CPU des conteneurs. metrics-server (kube-system) la collecte toutes les 15 s et la sert via l'API `metrics.k8s.io`.
2. Le contrôleur HPA (boucle de 15 s) lit la moyenne des Pods du Deployment `back` (et du `front`), la compare à 60 % de la demande de 100m et applique `ceil(actuel x usage / cible)`.
3. Il écrit le nombre de répliques dans le Deployment (entre 3 et 10) ; le ReplicaSet crée les Pods supplémentaires, que le scheduler répartit sur les workers. Les nouveaux Pods entrent dans les endpoints du Service dès qu'ils sont Ready.
4. Charge terminée : au bout de 60 s de stabilisation le HPA redescend à 3 Pods.
5. Les Services, l'Ingress et la base ne changent pas : seul le nombre de Pods des deux Deployments varie.

## Vérifié sur cluster local (charge générée dans le cluster avec fortio : 16 connexions sur le front et 16 sur le back)

```text
t+15s   back  cpu: 1%/60%    3 pods         t+45s   back  cpu: 200%/60%   7 pods     (front 194%/60%, 7 pods)
t+60s   back  cpu: 200%/60%  10 pods  (maximum)                      front 193%/60%, 10 pods
t+120s  back  cpu: 61%/60%   10 pods        t+180s  back 61%/60%
... fin de la charge ...
back  cpu: 1%/60%  10 pods  (stabilisation)  ->  3 pods au bout d'environ 3 minutes
$ kubectl top pods :  back 72 à 81Mi par pod (200m utilisés sur les Pods saturés), front 43 à 45Mi (45 à 90m), postgres-0 135Mi / 200Mi avec 10 pods back (45 connexions)
```

Aucun Pod n'a été tué pour dépassement mémoire (`OOMKilled`) pendant les 10 Pods du back : 81Mi maximum, la limite est de 200Mi.

Attention (dimensionnement) : chaque Pod du back ouvre jusqu'à 30 connexions à PostgreSQL (`pool_size=10`, `max_overflow=20`). À 10 Pods, le plafond théorique est 300 connexions, au-delà de
`max_connections=100` : en pratique 45 connexions ont été utilisées pendant le test, mais une charge très concurrente pourrait saturer la base. Remède : réduire le pool par Pod ou intercaler un
pooler (PgBouncer). La limite de mémoire de 200Mi impose de ne pas monter `max_connections` (chaque connexion active coûte quelques Mo).
