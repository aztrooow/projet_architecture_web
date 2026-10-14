# Défi 15 (bonus) : hooks Helm

Fichiers : `values-defi15.yaml`, `commandes.txt`, `schema.svg`. Modèles : `../helm/cinetint/templates/hooks.yaml` (hooks de ConfigMap, RBAC, nettoyage, sauvegardes), `_sauvegarde.tpl` (script pg_dump et test de fumée),
`sauvegardes.yaml` (volume de destination), `tests/test-connexion.yaml` (`helm test`).

## Qu'est-ce qu'un hook ?

Un hook est une ressource ordinaire (ici des Jobs) portant l'annotation `helm.sh/hook`. Helm la crée à un moment précis du cycle de vie du release, **attend sa fin**, et n'avance que si elle réussit :
un hook qui échoue fait échouer le `helm install` ou `helm upgrade`. `helm.sh/hook-weight` ordonne les hooks d'un même moment ; `helm.sh/hook-delete-policy` règle leur nettoyage.

## Les hooks de la charte

| Moment | Poids | Job | Rôle |
|---|---|---|---|
| `pre-install`, `pre-upgrade` | -20 | ServiceAccount, Role, RoleBinding `cinetint-hooks` | droits limités au namespace : lire/écrire des ConfigMaps (existent avant les Jobs qui s'en servent) |
| `pre-install`, `pre-upgrade` | 0 | `cinetint-config-avant` | **configure la ConfigMap avant le déploiement** : crée/remet à zéro la ConfigMap `cinetint-deploiement` (carnet de déploiement) avec `etat=en-cours`, le numéro de révision, l'action (installation ou mise à jour), les versions d'images, le mode de base, l'heure de début |
| `pre-upgrade` | 5 | `cinetint-sauvegarde-avant` | **sauvegarde pg_dump AVANT la mise à jour** (fichier `cinetint-avant-revN-<date>.dump` sur le volume de sauvegarde) pour pouvoir revenir en arrière si une migration se passe mal |
| `post-install`, `post-upgrade` | 0 | `cinetint-config-apres` | **configure la ConfigMap après le déploiement** : attend que les quatre services répondent (test de fumée sur `/sante`, `/api/sante`, `/qr/sante`, `/verification/sante`), puis passe le carnet à `etat=termine`, `sante=ok`, heure de fin ; échoue si un service ne répond pas |
| `post-upgrade` | 5 | `cinetint-sauvegarde-apres` | **sauvegarde pg_dump APRÈS la mise à jour** (`cinetint-apres-revN-<date>.dump`) |
| `post-delete` | 0 | `cinetint-nettoyage` | à la désinstallation, supprime le carnet (créé par un Job, donc inconnu de Helm) |
| `test` | - | `cinetint-test` | `helm test cinetint` : mêmes sondes, à la demande |

Les Jobs d'écriture de ConfigMap utilisent l'image `alpine/kubectl` et un ServiceAccount dédié ; le Role ne donne **que** les ConfigMaps du namespace (compatible avec les droits limités du compte `u-XXX`, à condition que celui-ci puisse
créer des Roles dans son namespace : sinon `hooks.configMap.rbac: false` et un ServiceAccount existant, ou `hooks.configMap.enabled: false`).

Précautions :

- **Le hook de sauvegarde avant mise à jour n'est rendu que si le volume de sauvegarde existe déjà** (`lookup`) : au premier déploiement il n'y a ni base ni sauvegarde à faire, et le Job attendrait un volume pas encore créé.
- Chaque sauvegarde **attend que la base réponde** (`pg_isready`, jusqu'à 5 min), est écrite en `.partiel` puis renommée, **vérifiée par `pg_restore --list`**, et la rétention ne garde que les 7 dernières.
- Les Pods des hooks qui joignent la base portent les étiquettes autorisées par la NetworkPolicy de PostgreSQL (`component=sauvegarde`, `component=test`).
- Les ressources RBAC des hooks (ServiceAccount, Role, RoleBinding `cinetint-hooks`) sont elles-mêmes des hooks : Helm ne les suit pas, elles restent après `helm uninstall` (étiquette `cinetint.io/hook=true`,
  supprimables avec `kubectl delete sa,role,rolebinding -l cinetint.io/hook=true`). Vérifié : après `helm uninstall`, le carnet est supprimé par le hook `post-delete`, les volumes de données et de sauvegarde sont conservés.
- Les sauvegardes survivent à `helm uninstall` (`helm.sh/resource-policy: keep` sur leur volume) ; les Jobs réussis sont supprimés (`hook-succeeded`), les Jobs en échec sont conservés pour le diagnostic.

## Fiche oral (schéma)

1. Chronologie d'un `helm upgrade` en bandes : pre-upgrade, application des manifests (rolling update des Deployments), post-upgrade ; plus post-delete à la désinstallation.
2. **Avant** : Job `config-avant` écrit la ConfigMap `cinetint-deploiement` (`etat=en-cours`, révision, versions) via le ServiceAccount `cinetint-hooks` ; Job `sauvegarde-avant` fait un `pg_dump` vers le PVC `cinetint-sauvegardes`.
3. Helm applique les nouvelles ressources : les Deployments se mettent à jour progressivement.
4. **Après** : Job `config-apres` interroge les quatre Services (test de fumée) et passe la ConfigMap à `etat=termine, sante=ok` ; Job `sauvegarde-apres` refait un `pg_dump`.
5. Si un hook échoue, Helm déclare l'opération en échec : le carnet reste à `en-cours` ou `echec`, et la sauvegarde d'avant permet de revenir en arrière (défi 16 pour la restauration).

## Vérifié sur cluster local (deux `helm upgrade` successifs)

```text
$ kubectl get cm cinetint-deploiement -o jsonpath='{.data}'      (après la mise à jour n°1, révision 3)
{"action":"mise-a-jour","base":"replication","debut":"2026-10-14T12:28:19Z","etat":"termine","fin":"2026-10-14T12:28:32Z","release":"cinetint","revision":"3","sante":"ok","versions":"front=v2 back=v1 qr-generator=v1 qr-verifier=v1"}
$ idem après la mise à jour n°2 (révision 4) : debut 12:28:53Z, fin 12:29:03Z, sante ok
$ contenu du volume cinetint-sauvegardes
cinetint-apres-rev3-20261014-122841.dump   406044 octets     (n°1 : pas de sauvegarde « avant », le volume n'existait pas encore)
cinetint-avant-rev4-20261014-122859.dump   406594
cinetint-apres-rev4-20261014-122908.dump   406594
Durée de la mise à jour avec hooks : 22 à 34 s
```

Premier `helm install` : hooks `config-avant`, puis création des ressources, puis `config-apres` (carnet `action: installation`, `etat: termine`, `sante: ok`, environ une minute sur kind).
