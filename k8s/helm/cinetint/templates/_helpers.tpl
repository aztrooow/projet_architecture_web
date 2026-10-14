{{/*
Fonctions communes à tous les modèles de la charte.
*/}}

{{/* Nom d'un composant : préfixe global + nom court (front, back, redis...). Usage : include "cinetint.nom" (dict "ctx" . "n" "back") */}}
{{- define "cinetint.nom" -}}
{{- printf "%s%s" (.ctx.Values.global.prefixe | default "") .n -}}
{{- end -}}

{{/* Nom d'une ressource transversale : cinetint-config, cinetint-secrets... */}}
{{- define "cinetint.nomApp" -}}
{{- printf "%scinetint-%s" (.ctx.Values.global.prefixe | default "") .n -}}
{{- end -}}

{{/* Étiquettes communes. Usage : include "cinetint.labels" (dict "ctx" . "c" "back") */}}
{{- define "cinetint.labels" -}}
app.kubernetes.io/name: cinetint
app.kubernetes.io/instance: {{ .ctx.Release.Name }}
app.kubernetes.io/component: {{ .c }}
app.kubernetes.io/part-of: cinetint
app.kubernetes.io/managed-by: {{ .ctx.Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .ctx.Chart.Name .ctx.Chart.Version | replace "+" "_" }}
{{- end -}}

{{/* Étiquettes de sélection : ne doivent JAMAIS changer pour un Deployment ou un StatefulSet existant */}}
{{- define "cinetint.selecteur" -}}
app.kubernetes.io/name: cinetint
app.kubernetes.io/instance: {{ .ctx.Release.Name }}
app.kubernetes.io/component: {{ .c }}
{{- end -}}

{{/* Référence d'une image applicative. Usage : include "cinetint.image" (dict "ctx" . "nom" "cinetint-front" "tag" .Values.images.tags.front) */}}
{{- define "cinetint.image" -}}
{{- if .ctx.Values.images.registre -}}
{{- printf "%s/%s:%s" .ctx.Values.images.registre .nom .tag -}}
{{- else -}}
{{- printf "%s:%s" .nom .tag -}}
{{- end -}}
{{- end -}}

{{/* Ressources d'un composant : les siennes si elles sont renseignées, sinon ressources.defaut */}}
{{- define "cinetint.ressources" -}}
{{- toYaml (.comp.ressources | default .ctx.Values.ressources.defaut) -}}
{{- end -}}

{{/* Secrets de registre privé */}}
{{- define "cinetint.pullSecrets" -}}
{{- with .Values.images.pullSecrets }}
imagePullSecrets:
  {{- range . }}
  - name: {{ . }}
  {{- end }}
{{- end }}
{{- end -}}

{{/* Durcissement au niveau du pod. Usage : include "cinetint.secPod" (dict "ctx" . "uid" 1000) */}}
{{- define "cinetint.secPod" -}}
{{- if .ctx.Values.global.securite }}
securityContext:
  runAsNonRoot: true
  runAsUser: {{ .uid }}
  runAsGroup: {{ .uid }}
  fsGroup: {{ .uid }}
  seccompProfile:
    type: RuntimeDefault
{{- end }}
{{- end -}}

{{/* Durcissement au niveau du conteneur */}}
{{- define "cinetint.secConteneur" -}}
{{- if .Values.global.securite }}
securityContext:
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop: ["ALL"]
{{- end }}
{{- end -}}

{{/* Hôte de PostgreSQL vu par le back : le service en lecture/écriture */}}
{{- define "cinetint.hotePostgres" -}}
{{- if eq .Values.postgres.mode "externe" -}}
{{- .Values.postgres.externe.hote -}}
{{- else -}}
{{- include "cinetint.nom" (dict "ctx" . "n" "postgres") -}}
{{- end -}}
{{- end -}}

{{/* Vrai si la sous-charte de réplication est activée */}}
{{- define "cinetint.replication" -}}
{{- if (index .Values "postgres-replication").enabled -}}true{{- end -}}
{{- end -}}

{{/* Vrai si la charte déploie elle-même PostgreSQL (donc la base existe dans le release) */}}
{{- define "cinetint.baseInterne" -}}
{{- if or (include "cinetint.replication" .) (ne .Values.postgres.mode "externe") -}}true{{- end -}}
{{- end -}}

{{/* Topologie : répartit les répliques d'un composant sur les nœuds */}}
{{- define "cinetint.repartition" -}}
{{- if .ctx.Values.repartition.enabled }}
topologySpreadConstraints:
  - maxSkew: 1
    topologyKey: kubernetes.io/hostname
    whenUnsatisfiable: ScheduleAnyway
    labelSelector:
      matchLabels:
        {{- include "cinetint.selecteur" (dict "ctx" .ctx "c" .c) | nindent 8 }}
{{- end }}
{{- end -}}

{{/*
Valeur d'un secret : celle de values si elle est renseignée, sinon celle déjà présente dans le cluster
(pour ne pas changer un mot de passe à chaque "helm upgrade"), sinon une valeur aléatoire.
Usage : include "cinetint.valeurSecret" (dict "existant" $existant "cle" "JWT_SECRET" "valeur" .Values.secrets.jwtSecret "longueur" 32)
Le résultat est déjà encodé en base64 (champ data).
*/}}
{{- define "cinetint.valeurSecret" -}}
{{- if .valeur -}}
{{- .valeur | b64enc -}}
{{- else if and .existant (hasKey (.existant.data | default dict) .cle) -}}
{{- index .existant.data .cle -}}
{{- else -}}
{{- randAlphaNum (.longueur | default 24 | int) | b64enc -}}
{{- end -}}
{{- end -}}

{{/* Probes HTTP. Usage : include "cinetint.sondesHttp" (dict "ctx" . "chemin" "/sante" "port" "http" "livenessChemin" "/sante") */}}
{{- define "cinetint.sondesHttp" -}}
{{- if .ctx.Values.sondes.startup.enabled }}
startupProbe:
  httpGet: {path: {{ .chemin }}, port: {{ .port }}}
  periodSeconds: {{ .demarrage | default 5 }}
  timeoutSeconds: 3
  failureThreshold: {{ .essaisDemarrage | default 24 }}
{{- end }}
{{- if .ctx.Values.sondes.readiness.enabled }}
readinessProbe:
  httpGet: {path: {{ .chemin }}, port: {{ .port }}}
  periodSeconds: 10
  timeoutSeconds: 3
  failureThreshold: 3
{{- end }}
{{- if .ctx.Values.sondes.liveness.enabled }}
livenessProbe:
  httpGet: {path: {{ .livenessChemin | default .chemin }}, port: {{ .port }}}
  periodSeconds: 15
  timeoutSeconds: 5
  failureThreshold: 4
{{- end }}
{{- end -}}

{{/* Variables d'environnement lues dans la ConfigMap. Usage : include "cinetint.envConfig" (dict "ctx" . "cles" (list "REDIS_URL")) */}}
{{- define "cinetint.envConfig" -}}
{{- $ctx := .ctx -}}
{{- range .cles }}
- name: {{ . }}
  valueFrom:
    configMapKeyRef:
      name: {{ include "cinetint.nomApp" (dict "ctx" $ctx "n" "config") }}
      key: {{ . }}
{{- end }}
{{- end -}}

{{/* Variables d'environnement lues dans le Secret */}}
{{- define "cinetint.envSecret" -}}
{{- $ctx := .ctx -}}
{{- range .cles }}
- name: {{ . }}
  valueFrom:
    secretKeyRef:
      name: {{ include "cinetint.nomApp" (dict "ctx" $ctx "n" "secrets") }}
      key: {{ . }}
{{- end }}
{{- end -}}

{{/* Nombre de répliques : omis quand un HPA pilote le Deployment (sinon chaque upgrade remettrait la valeur de départ) */}}
{{- define "cinetint.repliques" -}}
{{- if not (and .ctx.Values.hpa.enabled (has .c .ctx.Values.hpa.composants)) }}
replicas: {{ .n }}
{{- end }}
{{- end -}}

{{/* Stratégie de mise à jour et paramètres communs des Deployments */}}
{{- define "cinetint.miseAJour" -}}
revisionHistoryLimit: {{ .Values.miseAJour.revisionHistoryLimit }}
minReadySeconds: {{ .Values.miseAJour.minReadySeconds }}
progressDeadlineSeconds: {{ .Values.miseAJour.progressDeadlineSeconds }}
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxSurge: {{ .Values.miseAJour.maxSurge }}
    maxUnavailable: {{ .Values.miseAJour.maxUnavailable }}
{{- end -}}
