{{- define "processor-forge.name" -}}
{{- .Chart.Name | lower -}}
{{- end -}}

{{- define "processor-forge.fullname" -}}
{{- printf "%s-%s-%s" (include "processor-forge.name" .) .Values.application.environment .Values.application.name -}}
{{- end -}}

{{- define "processor-forge.labels" -}}
{{- with .Values.labels }}
{{ toYaml . | indent 2 }}
{{- end }}
{{- end -}}