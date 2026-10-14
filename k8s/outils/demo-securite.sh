#!/usr/bin/env bash
# Preuves du durcissement (Défi 18) : contexte de sécurité des Pods, système de fichiers en lecture seule,
# capabilities, limites de débit de l'Ingress (inondation), limite de taille des corps de requête.
#   N=u-XXX BASE=https://django.MONGROUPE.csc8567.luxbulb.org ./k8s/outils/demo-securite.sh
#   N=u-test BASE=http://localhost:8080 HOTE=cinetint.test ./k8s/outils/demo-securite.sh      (cluster kind local)
N=${N:?Renseigner N (namespace)}; BASE=${BASE:-http://localhost:8080}; HOTE=${HOTE:-}
H=${HOTE:+Host: $HOTE}; H=${H:-X-Sans-Hote: 1}
echo "## 1. contexte de sécurité des pods"
for d in front back qr-generator qr-verifier redis; do
  printf '%-13s ' $d; kubectl get pod -n $N -l app.kubernetes.io/component=$d -o jsonpath='{.items[0].spec.securityContext.runAsUser}{" nonRoot="}{.items[0].spec.securityContext.runAsNonRoot}{" seccomp="}{.items[0].spec.securityContext.seccompProfile.type}{" privEsc="}{.items[0].spec.containers[0].securityContext.allowPrivilegeEscalation}{" readOnlyFS="}{.items[0].spec.containers[0].securityContext.readOnlyRootFilesystem}{" drop="}{.items[0].spec.containers[0].securityContext.capabilities.drop}{" token="}{.items[0].spec.automountServiceAccountToken}{"\n"}'
done
for p in postgres-primaire-0 postgres-replique-0; do printf '%-13s ' $p; kubectl get pod $p -n $N -o jsonpath='{.spec.securityContext.runAsUser}{" nonRoot="}{.spec.securityContext.runAsNonRoot}{" readOnlyFS="}{.spec.containers[0].securityContext.readOnlyRootFilesystem}{" drop="}{.spec.containers[0].securityContext.capabilities.drop}{"\n"}'; done
echo "## 2. preuve dans le conteneur"
B=$(kubectl get pod -n $N -l app.kubernetes.io/component=back -o name | head -1)
kubectl exec -n $N $B -- sh -c 'id; touch /app/essai 2>&1 | head -1; touch /tmp/essai && echo "ecriture /tmp : ok"; grep -E "^Cap(Eff|Bnd)" /proc/1/status; grep NoNewPrivs /proc/1/status'
echo "## 3. limites de débit de l'Ingress (limit-rps 20, limit-connections 30)"
kubectl get ingress cinetint-api -n $N -o jsonpath='{.metadata.annotations}' | tr ',' '\n' | grep -E 'limit|body'; echo
seq 1 400 | xargs -P 40 -I{} curl -sk -o /dev/null -m 10 -w '%{http_code}\n' -H "$H" $BASE/api/sante | sort | uniq -c
echo "## 4. après l'attaque, le site répond toujours"; sleep 3; curl -sk -o /dev/null -w 'HTTP %{http_code}\n' -H "$H" $BASE/api/sante
echo "## 5. corps trop gros (proxy-body-size 1m)"; head -c 2000000 /dev/zero | curl -sk -o /dev/null -w 'HTTP %{http_code}\n' -m 10 -H "$H" -H 'Content-Type: application/json' --data-binary @- $BASE/api/commandes
