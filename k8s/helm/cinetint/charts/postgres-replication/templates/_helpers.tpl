{{/* Nom préfixé par global.prefixe. Usage : include "pgr.nom" (dict "ctx" . "n" "postgres") */}}
{{- define "pgr.nom" -}}
{{- printf "%s%s" (.ctx.Values.global.prefixe | default "") .n -}}
{{- end -}}

{{/* Nom du Secret qui porte les mots de passe */}}
{{- define "pgr.secret" -}}
{{- default (printf "%spostgres-secrets" (.Values.global.prefixe | default "")) .Values.existingSecret -}}
{{- end -}}

{{/* Étiquettes. component=postgres est commun au primaire et aux répliques (NetworkPolicy), role les distingue */}}
{{- define "pgr.labels" -}}
app.kubernetes.io/name: cinetint
app.kubernetes.io/instance: {{ .ctx.Release.Name }}
app.kubernetes.io/component: postgres
app.kubernetes.io/part-of: cinetint
app.kubernetes.io/managed-by: {{ .ctx.Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .ctx.Chart.Name .ctx.Chart.Version | replace "+" "_" }}
cinetint.io/role: {{ .role }}
{{- end -}}

{{- define "pgr.selecteur" -}}
app.kubernetes.io/name: cinetint
app.kubernetes.io/instance: {{ .ctx.Release.Name }}
app.kubernetes.io/component: postgres
cinetint.io/role: {{ .role }}
{{- end -}}

{{/* Réglages du serveur sous forme d'arguments -c clé=valeur */}}
{{- define "pgr.args" -}}
{{- range $cle, $valeur := .Values.reglages }}
- -c
- {{ printf "%s=%s" $cle ($valeur | toString) | quote }}
{{- end }}
- -c
- listen_addresses=*
{{- if .Values.synchrone }}
- -c
- synchronous_standby_names=ANY 1 (*)
{{- end }}
{{- end -}}

{{- define "pgr.secPod" -}}
{{- if .Values.global.securite }}
securityContext:
  runAsNonRoot: true
  runAsUser: 70
  runAsGroup: 70
  fsGroup: 70
  seccompProfile:
    type: RuntimeDefault
{{- end }}
{{- end -}}

{{- define "pgr.secConteneur" -}}
{{- if .Values.global.securite }}
securityContext:
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop: ["ALL"]
{{- end }}
{{- end -}}

{{/* Variables d'environnement communes aux conteneurs PostgreSQL */}}
{{- define "pgr.env" -}}
- name: POSTGRES_DB
  value: {{ .Values.base | quote }}
- name: POSTGRES_USER
  value: {{ .Values.utilisateur | quote }}
- name: POSTGRES_PASSWORD
  valueFrom:
    secretKeyRef: {name: {{ include "pgr.secret" . }}, key: POSTGRES_PASSWORD}
- name: REPLICATION_USER
  value: {{ .Values.utilisateurReplication | quote }}
- name: REPLICATION_PASSWORD
  valueFrom:
    secretKeyRef: {name: {{ include "pgr.secret" . }}, key: REPLICATION_PASSWORD}
- name: PGDATA
  value: /var/lib/postgresql/data/pgdata
{{- end -}}

{{- define "pgr.sondes" -}}
startupProbe:
  exec:
    command: ["sh", "-c", "pg_isready -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\""]
  periodSeconds: 3
  timeoutSeconds: 3
  failureThreshold: 60
readinessProbe:
  exec:
    command: ["sh", "-c", "pg_isready -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\""]
  periodSeconds: 5
  timeoutSeconds: 3
livenessProbe:
  exec:
    command: ["sh", "-c", "pg_isready -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\""]
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 6
{{- end -}}
