# Défi 4 : le site accessible depuis Internet (Ingress)

Fichiers : ceux du défi 3 (`site-*.yaml`, `postgres-*.yaml`, `redis.yaml`) plus `ingress.yaml`, `commandes.txt`, `schema.svg`.
Questions du sujet : « on met à jour le schéma, ça suffira ».

## Contenu réalisé

Une ressource **Ingress** `site` dans le namespace du groupe, avec l'hôte `django.<groupe>.csc8567.luxbulb.org` (paramétrable dans `appliquer.sh` par `HOTE=...`) :

| Chemin | Service cible | Conteneur atteint |
|---|---|---|
| `/api` | `site:8000` | back (API REST, flux SSE) |
| `/` (tout le reste) | `site:8080` | front (pages Jinja et application React) |

Des annotations coupent le tampon et allongent les délais de lecture pour l'API : les flux temps réel (Server-Sent Events) ne se terminent jamais.
Le TLS (HTTPS) est géré par le contrôleur du cluster : sans certificat dédié il présente son certificat par défaut ; avec cert-manager on ajouterait
`cert-manager.io/cluster-issuer` et une section `tls`. À valider avec les enseignants (le sujet ne dit pas qui fournit le certificat).

## Comment la requête arrive

1. Le navigateur résout `django.<groupe>.csc8567.luxbulb.org` : entrée DNS créée par les enseignants vers **157.159.11.201**.
2. Cette IP est **annoncée par MetalLB**, qui l'a attribuée au Service `rke2-ingress-nginx-controller` de type **LoadBalancer** (namespace `kube-system`,
   ClusterIP 10.43.144.159, ports `80:31324/TCP,443:30747/TCP` : le LoadBalancer est un NodePort auquel MetalLB ajoute une IP externe).
3. Le trafic arrive sur un nœud, kube-proxy le redirige vers un Pod du **contrôleur Ingress** (un nginx).
4. Le contrôleur lit la ressource Ingress du namespace `u-XXX` (c'est une table de routage : `host` + `path` -> `Service:port`), choisit la règle (`/api` ou `/`) et relaie
   **directement vers l'IP d'un Pod** du Service (il utilise les endpoints, pas la ClusterIP).
5. Le Pod répond par le chemin inverse.

L'Ingress est une ressource du namespace du groupe (droits suffisants) ; le contrôleur et son LoadBalancer sont gérés par les administrateurs du cluster.

## Fiche oral (schéma)

1. Chaîne complète : navigateur -> DNS -> 157.159.11.201 (MetalLB) -> Service LoadBalancer `rke2-ingress-nginx-controller` -> Pod nginx du contrôleur (kube-system).
2. La ressource Ingress `site` est la table de routage de ce nginx : `/api` vers le Service `site` port 8000, `/` vers le port 8080.
3. Le nginx envoie ensuite vers un Pod du Service (réseau des pods 10.42.x.y), conteneur front ou back du même Pod.
4. Le back parle à `postgres` et `redis` par leur nom DNS, comme au défi 3. La base n'est pas exposée : aucun Ingress ne la vise.
5. Ce qui est nouveau par rapport au défi 3 : DNS public, MetalLB, Service LoadBalancer, contrôleur Ingress, ressource Ingress.

## Vérifié sur cluster local (kind + ingress-nginx, `Host` forcé)

```text
$ NAMESPACE=u-defis ./k8s/appliquer.sh defi4
$ kubectl get ingress
NAME   CLASS   HOSTS           ADDRESS   PORTS   AGE
site   nginx   cinetint.test             80      8s
$ for p in / /api/sante /api/programme /qr/sante /sante; do curl -s -o /dev/null -w "$p %{http_code}\n" -H 'Host: cinetint.test' http://localhost:8080$p; done
/ 200            /api/sante 200        /api/programme 200
/qr/sante 404    (le qr-generator n'existe pas encore : il arrive au défi 5)
/sante 200
```

Sur le cluster du cours, le contrôleur est dans `kube-system` et la classe d'Ingress s'appelle `nginx` (champ `ingressClassName`). L'IP 157.159.11.201 et les
numéros de NodePort sont ceux donnés dans le sujet.
