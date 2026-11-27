{{- define "cg.name" -}}{{ .Release.Name }}-careergraph{{- end -}}
{{- define "cg.labels" -}}
app.kubernetes.io/name: careergraph
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end -}}
{{- define "cg.selector" -}}
app.kubernetes.io/name: careergraph
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
{{- define "cg.secretName" -}}
{{- if .Values.secret.create }}{{ include "cg.name" . }}{{ else }}{{ .Values.secret.existingSecret }}{{ end -}}
{{- end -}}
{{- define "cg.env" -}}
{{- range $k, $v := .Values.env }}
- name: {{ $k }}
  value: {{ $v | quote }}
{{- end }}
- name: DATA_DIR
  value: /data
- name: CACHE_DIR
  value: /data/cache
- name: OUTPUT_DIR
  value: /data/outputs
{{- if .Values.postgres.enabled }}
- name: PGPASSWORD_
  valueFrom:
    secretKeyRef: {name: {{ include "cg.secretName" . }}, key: {{ .Values.postgres.passwordKey }}}
- name: DATABASE_URL
  value: "postgresql://{{ .Values.postgres.database }}:$(PGPASSWORD_)@{{ include "cg.name" . }}-postgres:5432/{{ .Values.postgres.database }}"
{{- end }}
{{- end -}}
{{- define "cg.envFrom" -}}
{{- if or .Values.secret.create .Values.secret.existingSecret }}
- secretRef:
    name: {{ include "cg.secretName" . }}
    optional: true
{{- end }}
{{- end -}}
{{- define "cg.mounts" -}}
- name: data
  mountPath: /data
{{- if .Values.config }}
- name: config
  mountPath: /app/config
  readOnly: true
{{- end }}
{{- if .Values.profile.existingSecret }}
- name: profile
  mountPath: /app/profiles/me
  readOnly: true
{{- end }}
{{- end -}}
{{- define "cg.volumes" -}}
- name: data
  {{- if .Values.persistence.enabled }}
  persistentVolumeClaim:
    claimName: {{ include "cg.name" . }}-data
  {{- else }}
  emptyDir: {}
  {{- end }}
{{- if .Values.config }}
- name: config
  configMap:
    name: {{ include "cg.name" . }}-config
{{- end }}
{{- if .Values.profile.existingSecret }}
- name: profile
  secret:
    secretName: {{ .Values.profile.existingSecret }}
{{- end }}
{{- end -}}
{{- define "cg.containerSecurity" -}}
allowPrivilegeEscalation: false
capabilities:
  drop: ["ALL"]
{{- end -}}
