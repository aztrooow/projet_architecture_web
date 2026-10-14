# Défi 8 : mise à jour progressive (Rolling Update)

Fichiers : `values-defi8.yaml`, `commandes.txt`, `schema.svg`. Modèles concernés : `templates/front.yaml` (stratégie, sondes) et `templates/_helpers.tpl` (`cinetint.miseAJour`).

## Contenu réalisé

- **Nouvelle fonctionnalité du front** : la page `/infos` (accès, horaires, grille tarifaire), présente dans l'image `cinetint-front:v2` ; la v1 n'a pas cette page (`/infos` répond 404).
- **Image v2** construite et envoyée avec un tag supérieur : `TAG=v2 REGISTRE=ghcr.io/eldertek k8s/images.sh tout front`. Le tag change à chaque version : le cluster ne retélécharge pas un tag déjà en cache.
- **Stratégie explicite** dans le Deployment : `type: RollingUpdate`, `maxSurge: 1`, `maxUnavailable: 0`, `minReadySeconds: 5`, `revisionHistoryLimit: 10`, `progressDeadlineSeconds: 300`.
- **readinessProbe** (`/sante`) : sans elle Kubernetes envoie du trafic à un Pod dès que son conteneur a démarré, avant que l'application ne soit prête.
- **preStop** (`sleep 5`) : le Pod retiré reste actif 5 secondes pour finir ses requêtes et laisser le temps au Service et à l'Ingress de le sortir de leurs listes.
- Mise à jour : `helm upgrade ... --set images.tags.front=v2` (ou `kubectl set image deployment/front front=<registre>/cinetint-front:v2`).

## Question : la suite d'exécutions d'une Rolling Update

État de départ : Deployment `front` à 3 répliques, ReplicaSet A (v1) avec 3 Pods Ready, le Service `front` envoie les requêtes à ces 3 Pods. Avec `maxSurge: 1` et `maxUnavailable: 0`,
il y a toujours au plus 4 Pods et au moins 3 Pods Ready.

1. **Déclenchement** : `helm upgrade` (ou `kubectl set image`) modifie le modèle de Pod du Deployment (nouvelle image). L'API server enregistre la nouvelle révision dans etcd.
2. **Nouveau ReplicaSet** : le contrôleur de Deployment crée le ReplicaSet B (v2) à 0 réplique puis le monte à **1** (surge : 3 + 1 = 4 Pods).
3. **Démarrage du Pod v2** : planifié, image téléchargée, conteneur lancé. Tant que la **readinessProbe** (`GET /sante`) n'a pas réussi, le Pod n'est **pas Ready** : il n'est pas dans les endpoints du
   Service, il ne reçoit aucune requête. Après réussite, il doit rester Ready 5 s (`minReadySeconds`).
4. **Bascule** : le Pod v2 est Ready, il entre dans les endpoints du Service. Le contrôleur réduit alors le ReplicaSet A à **2** : un Pod v1 reçoit SIGTERM. Il sort des endpoints, attend 5 s (`preStop`) pour
   finir ses requêtes, puis s'arrête. Pendant tout ce temps, 3 Pods au moins sont Ready.
5. **On recommence** : B monte à 2 (4 Pods), attend qu'il soit Ready, A descend à 1 ; B monte à 3, A descend à 0.
6. **Fin** : ReplicaSet B (v2) à 3 Pods, ReplicaSet A (v1) conservé à **0 Pod** (`revisionHistoryLimit`) : c'est ce qui permet le **retour arrière** (`kubectl rollout undo deployment/front`
   ou `helm rollback`) sans reconstruire quoi que ce soit : le ReplicaSet A est simplement remonté à 3 pendant que B descend, avec la même procédure.
7. Si le Pod v2 ne devient jamais Ready (bug, image introuvable), le déploiement **s'arrête** : les 3 Pods v1 continuent de servir (aucun impact utilisateur) et après `progressDeadlineSeconds`
   le Deployment est déclaré en échec.

Le Service et l'Ingress ne changent pas : seule la liste des endpoints évolue. C'est ce qui rend la mise à jour invisible pour le client.

## Fiche oral (schéma)

1. Cinq instantanés T0 à T4 du Deployment `front`. En haut, rien ne bouge : navigateur, Ingress, Service `front` (même IP virtuelle).
2. T0 : 3 Pods v1 dans le ReplicaSet A. T1 : un Pod v2 est créé (ReplicaSet B, surge de 1), pas encore Ready : le Service ne lui envoie rien (readinessProbe).
3. T2 : le Pod v2 est Ready et ajouté aux endpoints ; un Pod v1 est retiré (preStop de 5 s). T3 : même cycle, 2 Pods v2 pour 1 Pod v1.
4. T4 : 3 Pods v2 ; ReplicaSet A reste à 0 pour le retour arrière.
5. Courbe du bas : jamais moins de 3 Pods Ready, 4 Pods au plus, zéro requête en erreur. Commandes : `helm upgrade --set images.tags.front=v2`, `kubectl rollout status/history/undo`.

## Vérifié sur cluster local (boucle de 10 requêtes/s sur 3 routes pendant la mise à jour)

```text
$ kubectl get deploy front -o wide          IMAGES : cinetint-local/cinetint-front:v1        GET /infos (v1) -> 404
$ helm upgrade cinetint ... --set images.tags.front=v2        STATUS: deployed   REVISION: 3
Waiting for deployment "front" rollout to finish: 1 out of 3 new replicas have been updated...   (puis 2 out of 3, puis 1 old replicas are pending termination)
deployment "front" successfully rolled out
$ kubectl get deploy front -o wide          IMAGES : cinetint-local/cinetint-front:v2        GET /infos (v2) -> 200
$ kubectl get rs -l app.kubernetes.io/component=front
front-6b57585fff   0   0   0     (anciens ReplicaSets conservés à 0)
front-7c79bd8664   0   0   0
front-86466db4b    3   3   3     (v2)
$ kubectl rollout history deployment/front
REVISION  CHANGE-CAUSE
1  <none>      2  <none>      3  front v2 : page /infos
codes HTTP pendant la mise à jour : 861 x 200     (aucune erreur, aucun timeout)
$ kubectl rollout undo deployment/front   ->  image v1, GET /infos -> 404     (retour arrière OK, puis kubectl set image ... :v2 pour revenir en v2)
```

Limite à connaître : les connexions SSE (plan de salle en direct) ouvertes sur un Pod arrêté sont coupées ; le navigateur se reconnecte tout seul à un Pod encore actif.
