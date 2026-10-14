#!/usr/bin/env bash
# Démonstration des trois rôles de Redis (Défi 14) : verrous de sièges à expiration, compteur de remplissage,
# pub/sub vers le flux SSE ; puis test de la NetworkPolicy de Redis.
#   N=u-XXX BASE=https://django.MONGROUPE.csc8567.luxbulb.org ./k8s/outils/demo-redis.sh
#   N=u-test BASE=http://localhost:8080 HOTE=cinetint.test ./k8s/outils/demo-redis.sh      (cluster kind local)
N=${N:?Renseigner N (namespace)}; B=${BASE:-http://localhost:8080}; HOTE=${HOTE:-}
H=${HOTE:+Host: $HOTE}; H=${H:-X-Sans-Hote: 1}
R="kubectl exec -n $N deploy/redis -- redis-cli"
SEANCE=$(curl -sk -H "$H" $B/api/programme | python3 -c "
import sys,json
from datetime import datetime,timezone
d=json.load(sys.stdin); now=datetime.now(timezone.utc)
s=[s for f in d['films'] for s in f['seances'] if (datetime.fromisoformat(s['debut'])-now).total_seconds()>1800]
print(s[-1]['id'])")
SIEGES=$(curl -sk -H "$H" $B/api/seances/$SEANCE/plan | python3 -c "
import sys,json
d=json.load(sys.stdin); l=[x['id'] for x in d['sieges'] if x['etat']=='libre']; print(l[-1],l[-2])")
set -- $SIEGES
echo "## séance $SEANCE, sièges $1 et $2"
echo "## 1. abonnements pub/sub (un par instance du back : 3 pods)"; printf 'motifs abonnés (PSUBSCRIBE) : '; $R PUBSUB NUMPAT; printf 'connexions en abonnement : '; $R CLIENT LIST | grep -c 'psub=2' 
echo "## 2. un navigateur écoute le flux SSE de la séance (en arrière-plan 6 s)"
curl -sk -N -m 6 -H "$H" $B/api/seances/$SEANCE/flux > /tmp/flux.txt &
sleep 1
echo "## 3. réservation de 2 places : le back pose 2 verrous Redis (script Lua, SET ... EX 600)"
CMD=$(curl -sk -H "$H" -H 'Content-Type: application/json' -d "{\"seance_id\":$SEANCE,\"places\":[{\"siege_id\":$1,\"categorie\":\"plein\"},{\"siege_id\":$2,\"categorie\":\"plein\"}]}" $B/api/commandes)
echo "$CMD" | python3 -c "import sys,json; d=json.load(sys.stdin); print('commande', d['id'], 'expire le', d.get('expire_le'))"
$R --scan --pattern "verrou:*"
for s in $1 $2; do printf 'TTL verrou:{%s}:%s = ' $SEANCE $s; $R TTL "verrou:{$SEANCE}:$s"; printf 'proprietaire : '; $R GET "verrou:{$SEANCE}:$s"; done
wait
echo "## 4. événement reçu par le navigateur (pub/sub -> SSE)"; grep -m3 data /tmp/flux.txt
echo "## 5. même siège redemandé par un autre acheteur : refus (409)"
curl -sk -o /dev/null -w 'HTTP %{http_code}\n' -H "$H" -H 'Content-Type: application/json' -d "{\"seance_id\":$SEANCE,\"places\":[{\"siege_id\":$1,\"categorie\":\"plein\"}]}" $B/api/commandes
echo "## 6. paiement : verrous libérés, compteur de remplissage mis à jour"
PSP=$(echo "$CMD" | python3 -c "import sys,json; print(json.load(sys.stdin)['psp_session'])")
printf 'remplissage avant : '; $R GET "remplissage:$SEANCE"
curl -sk -o /dev/null -w 'paiement HTTP %{http_code}\n' -H "$H" -H 'Content-Type: application/json' -d '{"resultat":"accepte"}' $B/api/paiement-simule/$PSP
printf 'remplissage après : '; $R GET "remplissage:$SEANCE"; echo "verrous restants : $($R --scan --pattern 'verrou:*' | wc -l)"
echo "## 7. configuration"; $R CONFIG GET maxmemory; $R CONFIG GET maxmemory-policy; $R CONFIG GET save; $R INFO memory | grep -E 'used_memory_human'
echo "## 8. NetworkPolicy : qui joint Redis ?"
for who in "back:app.kubernetes.io/instance=cinetint,app.kubernetes.io/component=back" "front:app.kubernetes.io/instance=cinetint,app.kubernetes.io/component=front" "anonyme:"; do
  n=${who%%:*}; l=${who#*:}
  kubectl run tr-$n -n $N --image=postgres:17-alpine --restart=Never ${l:+--labels=$l} --command -- sh -c 'nc -zv -w 4 redis 6379 && echo AUTORISE || echo BLOQUE' >/dev/null
  sleep 12; printf '%-10s ' $n; kubectl logs tr-$n -n $N | grep -E 'AUTORISE|BLOQUE'; kubectl delete pod tr-$n -n $N --now >/dev/null
done
