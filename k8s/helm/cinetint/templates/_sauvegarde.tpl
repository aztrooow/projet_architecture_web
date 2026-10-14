{{/*
Sauvegarde logique de la base avec pg_dump (format custom, compressé), écrite sur le volume
dédié /sauvegardes. Utilisée par le CronJob (Défi 16) et par les hooks avant/après mise à jour (Défi 15).
Le script attend d'abord que la base réponde, vérifie le fichier avec pg_restore --list, puis ne garde
que les N dernières sauvegardes.
*/}}
{{- define "cinetint.scriptSauvegarde" -}}
set -eu
etiquette="$1"
echo "[sauvegarde] attente de ${POSTGRES_HOST}:${POSTGRES_PORT}"
n=0
until pg_isready -q -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB"; do
  n=$((n + 1))
  if [ "$n" -ge 60 ]; then echo "[sauvegarde] base injoignable" >&2; exit 1; fi
  sleep 5
done
fichier="/sauvegardes/cinetint-${etiquette}-$(date -u +%Y%m%d-%H%M%S).dump"
pg_dump -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f "${fichier}.partiel"
mv "${fichier}.partiel" "$fichier"
pg_restore --list "$fichier" > /dev/null
echo "[sauvegarde] écrit et vérifié :"
ls -l "$fichier"
ls -1t /sauvegardes/cinetint-*.dump | tail -n +$((CONSERVER + 1)) | xargs -r rm -v
echo "[sauvegarde] sauvegardes présentes :"
ls -l /sauvegardes
{{- end -}}

{{/*
Spécification de pod d'une sauvegarde. Usage : include "cinetint.podSauvegarde" (dict "ctx" . "etiquette" "planifiee")
Le pod porte l'étiquette component=sauvegarde, que la NetworkPolicy de PostgreSQL autorise.
*/}}
{{- define "cinetint.podSauvegarde" -}}
{{- $ctx := .ctx }}
restartPolicy: OnFailure
automountServiceAccountToken: false
{{- include "cinetint.secPod" (dict "ctx" $ctx "uid" 70) }}
containers:
  - name: sauvegarde
    image: {{ $ctx.Values.images.outils }}
    imagePullPolicy: {{ $ctx.Values.images.pullPolicy }}
    command: ["sh", "-c", {{ include "cinetint.scriptSauvegarde" $ctx | quote }}, "sauvegarde", {{ .etiquette | quote }}]
    env:
      {{- include "cinetint.envConfig" (dict "ctx" $ctx "cles" (list "POSTGRES_HOST" "POSTGRES_PORT" "POSTGRES_DB" "POSTGRES_USER")) | nindent 6 }}
      {{- include "cinetint.envSecret" (dict "ctx" $ctx "cles" (list "POSTGRES_PASSWORD")) | nindent 6 }}
      - name: PGPASSWORD
        valueFrom:
          secretKeyRef:
            name: {{ include "cinetint.nomApp" (dict "ctx" $ctx "n" "secrets") }}
            key: POSTGRES_PASSWORD
      - name: CONSERVER
        value: {{ $ctx.Values.sauvegardes.conserver | quote }}
    resources:
      requests: {cpu: 50m, memory: 64Mi}
      limits: {cpu: 200m, memory: 200Mi}
    {{- include "cinetint.secConteneur" $ctx | nindent 4 }}
    volumeMounts:
      - {name: sauvegardes, mountPath: /sauvegardes}
      - {name: tmp, mountPath: /tmp}
volumes:
  - name: sauvegardes
    persistentVolumeClaim:
      claimName: {{ include "cinetint.nomApp" (dict "ctx" $ctx "n" "sauvegardes") }}
  - name: tmp
    emptyDir: {}
{{- end -}}

{{/* Test de fumée : les quatre services répondent sur leur route de santé. Utilisé par le hook post-déploiement et par "helm test". Positionne la variable sante (ok ou echec). */}}
{{- define "cinetint.scriptFumee" -}}
attendre() {
  n=0
  until wget -q -T 5 -O /dev/null "$1"; do
    n=$((n + 1))
    if [ "$n" -ge 60 ]; then echo "ECHEC $1"; return 1; fi
    sleep 5
  done
  echo "OK $1"
}
sante=ok
attendre {{ printf "http://%s:%d/sante" (include "cinetint.nom" (dict "ctx" . "n" "front")) (.Values.front.port | int) }} || sante=echec
attendre {{ printf "http://%s:%d/api/sante" (include "cinetint.nom" (dict "ctx" . "n" "back")) (.Values.back.port | int) }} || sante=echec
attendre {{ printf "http://%s:%d/qr/sante" (include "cinetint.nom" (dict "ctx" . "n" "qr-generator")) (.Values.qrGenerator.port | int) }} || sante=echec
attendre {{ printf "http://%s:%d/verification/sante" (include "cinetint.nom" (dict "ctx" . "n" "qr-verifier")) (.Values.qrVerifier.port | int) }} || sante=echec
{{- end -}}
