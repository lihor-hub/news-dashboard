{{- define "news-dashboard.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "news-dashboard.fullname" -}}
{{- printf "%s-%s" .Release.Name (include "news-dashboard.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "news-dashboard.aiEnv" -}}
{{- if .Values.app.ai.existingSecret }}
- name: OPENAI_API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.app.ai.existingSecret | quote }}
      key: {{ .Values.app.ai.openaiApiKeyKey | quote }}
      optional: true
- name: FREE_LLM_API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.app.ai.existingSecret | quote }}
      key: {{ .Values.app.ai.freeLlmApiKeyKey | quote }}
      optional: true
{{- end }}
{{- if .Values.app.ai.freeLlmBaseUrl }}
- name: FREE_LLM_BASE_URL
  value: {{ .Values.app.ai.freeLlmBaseUrl | quote }}
{{- end }}
{{- if .Values.app.ai.briefingModel }}
- name: OPENAI_BRIEFING_MODEL
  value: {{ .Values.app.ai.briefingModel | quote }}
{{- end }}
{{- if .Values.app.ai.langfuse.host }}
- name: LANGFUSE_HOST
  value: {{ .Values.app.ai.langfuse.host | quote }}
{{- if .Values.app.ai.existingSecret }}
- name: LANGFUSE_PUBLIC_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.app.ai.existingSecret | quote }}
      key: {{ .Values.app.ai.langfuse.publicKeyKey | default "LANGFUSE_PUBLIC_KEY" | quote }}
      optional: true
- name: LANGFUSE_SECRET_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.app.ai.existingSecret | quote }}
      key: {{ .Values.app.ai.langfuse.secretKeyKey | default "LANGFUSE_SECRET_KEY" | quote }}
      optional: true
{{- end }}
{{- end }}
{{- end -}}
