{{- define "sanvi.labels" -}}
app.kubernetes.io/part-of: sanvi
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}
{{- define "sanvi.dbSecret" -}}
{{- if eq .Values.database.mode "cloudnativepg" -}}{{ .Release.Name }}-pg-app{{- else -}}{{ .Values.database.external.secretName }}{{- end -}}
{{- end -}}
{{- define "sanvi.dbKey" -}}
{{- if eq .Values.database.mode "cloudnativepg" -}}uri{{- else -}}{{ .Values.database.external.secretKey }}{{- end -}}
{{- end -}}
