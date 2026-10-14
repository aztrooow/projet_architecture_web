#!/usr/bin/env bash
# Tests des NetworkPolicy (Défis 11 et 18) avec de petits Pods d'essai étiquetés comme les composants.
#   N=u-XXX ./k8s/outils/test-networkpolicy.sh                       (un Pod d'essai par cas)
#   N=u-XXX AUTRE_NS=un-autre-namespace ./k8s/outils/test-networkpolicy.sh   (ajoute le cas « autre namespace » : le namespace doit exister)
# Première partie : qui joint PostgreSQL ? Seconde partie : matrice d'accès entre tous les composants (Défi 18).
N=${N:?Renseigner N (namespace)}
AUTRE_NS=${AUTRE_NS:-}
t() { # nom namespace labels
  kubectl run "$1" -n "$2" --image=postgres:17-alpine --restart=Never ${3:+--labels=$3} --command -- sh -c 'nc -zv -w 4 postgres.'"$N"'.svc.cluster.local 5432 && echo CONNEXION_AUTORISEE || echo CONNEXION_BLOQUEE' >/dev/null
  for i in $(seq 1 30); do s=$(kubectl get pod "$1" -n "$2" -o jsonpath='{.status.phase}'); [ "$s" = Succeeded ] || [ "$s" = Failed ] && break; sleep 1; done
  printf '%-52s' "$4"; kubectl logs "$1" -n "$2" | grep -E 'CONNEXION' ; kubectl delete pod "$1" -n "$2" --now >/dev/null
}
t t-back $N app.kubernetes.io/instance=cinetint,app.kubernetes.io/component=back "pod du back (autorisé)"
t t-front $N app.kubernetes.io/instance=cinetint,app.kubernetes.io/component=front "pod du front"
t t-anonyme $N "" "pod quelconque du même namespace"
AUTRE=${AUTRE_NS:-}
[ -n "$AUTRE" ] && t t-autre "$AUTRE" "" "pod d'un autre namespace ($AUTRE)"

echo
echo "## matrice d'accès entre composants (Défi 18)"

L() { echo "app.kubernetes.io/instance=cinetint,app.kubernetes.io/component=$1"; }
run() { # nom namespace labels cible port
  kubectl run "$1" -n "$2" --image=postgres:17-alpine --restart=Never ${3:+--labels=$3} --command -- sh -c "nc -z -w 3 $4.$N.svc.cluster.local $5 && echo AUTORISE || echo BLOQUE" >/dev/null
  for i in $(seq 1 40); do s=$(kubectl get pod "$1" -n "$2" -o jsonpath='{.status.phase}'); [ "$s" = Succeeded ] && break; sleep 1; done
  kubectl logs "$1" -n "$2" | grep -E 'AUTORISE|BLOQUE'; kubectl delete pod "$1" -n "$2" --now >/dev/null
}
printf '%-14s -> %-13s : ' "front" back; run m1 $N "$(L front)" back 8000
printf '%-14s -> %-13s : ' "front" qr-generator; run m2 $N "$(L front)" qr-generator 8001
printf '%-14s -> %-13s : ' "front" redis; run m3 $N "$(L front)" redis 6379
printf '%-14s -> %-13s : ' "front" postgres; run m4 $N "$(L front)" postgres 5432
printf '%-14s -> %-13s : ' "back" postgres; run m5 $N "$(L back)" postgres 5432
printf '%-14s -> %-13s : ' "back" redis; run m6 $N "$(L back)" redis 6379
printf '%-14s -> %-13s : ' "back" qr-generator; run m7 $N "$(L back)" qr-generator 8001
printf '%-14s -> %-13s : ' "qr-verifier" back; run m8 $N "$(L qr-verifier)" back 8000
printf '%-14s -> %-13s : ' "qr-verifier" postgres; run m9 $N "$(L qr-verifier)" postgres 5432
printf '%-14s -> %-13s : ' "inconnu" back; run m10 $N "" back 8000
[ -n "${AUTRE_NS:-}" ] && { printf "%-14s -> %-13s : " "autre namespace" front; run m11 "$AUTRE_NS" "" front 8080; }
