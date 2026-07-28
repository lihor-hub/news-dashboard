{{- define "news-dashboard.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "news-dashboard.fullname" -}}
{{- printf "%s-%s" .Release.Name (include "news-dashboard.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "news-dashboard.neo4jSecretName" -}}
{{- default (printf "%s-neo4j" (include "news-dashboard.fullname" .)) .Values.neo4j.auth.existingSecret -}}
{{- end -}}

{{- define "news-dashboard.neo4jPasswordKey" -}}
{{- default "NEO4J_PASSWORD" .Values.neo4j.auth.passwordKey -}}
{{- end -}}

{{- define "news-dashboard.neo4jEnv" -}}
{{- if .Values.neo4j.enabled }}
- name: NEO4J_URI
  value: {{ printf "bolt://%s-neo4j:%v" (include "news-dashboard.fullname" .) .Values.neo4j.service.port | quote }}
- name: NEO4J_USER
  value: {{ .Values.neo4j.auth.user | quote }}
- name: NEO4J_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ include "news-dashboard.neo4jSecretName" . | quote }}
      key: {{ include "news-dashboard.neo4jPasswordKey" . | quote }}
- name: NEO4J_DATABASE
  value: {{ .Values.neo4j.database | quote }}
{{- end }}
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

{{- define "news-dashboard.difyEnv" -}}
{{- if .Values.app.dify.enabled }}
{{- if not .Values.app.dify.baseUrl }}
{{- fail "app.dify.baseUrl is required when app.dify.enabled=true" }}
{{- end }}
{{- if not .Values.app.dify.existingSecret }}
{{- fail "app.dify.existingSecret is required when app.dify.enabled=true" }}
{{- end }}
- name: DIFY_CHAT_ENABLED
  value: "true"
- name: DIFY_CHAT_BASE_URL
  value: {{ .Values.app.dify.baseUrl | quote }}
- name: DIFY_CHAT_APP_TOKEN
  valueFrom:
    secretKeyRef:
      name: {{ .Values.app.dify.existingSecret | quote }}
      key: {{ .Values.app.dify.appTokenKey | quote }}
- name: DIFY_CHAT_TITLE
  value: {{ .Values.app.dify.title | quote }}
{{- end }}
{{- end -}}

{{- define "news-dashboard.sentryEnv" -}}
{{- if .Values.app.sentry.existingSecret }}
- name: SENTRY_DSN
  valueFrom:
    secretKeyRef:
      name: {{ .Values.app.sentry.existingSecret | quote }}
      key: {{ .Values.app.sentry.dsnKey | default "SENTRY_DSN" | quote }}
      optional: true
- name: SENTRY_DSN_FRONTEND
  valueFrom:
    secretKeyRef:
      name: {{ .Values.app.sentry.existingSecret | quote }}
      key: {{ .Values.app.sentry.frontendDsnKey | default "SENTRY_DSN_FRONTEND" | quote }}
      optional: true
{{- end }}
{{- if .Values.app.sentry.environment }}
- name: SENTRY_ENVIRONMENT
  value: {{ .Values.app.sentry.environment | quote }}
{{- end }}
{{- if .Values.app.sentry.release }}
- name: SENTRY_RELEASE
  value: {{ .Values.app.sentry.release | quote }}
{{- end }}
{{- end -}}

{{- define "news-dashboard.newsletterEnv" -}}
{{- if .Values.app.newsletter.imapHost }}
- name: NEWSLETTER_IMAP_HOST
  value: {{ .Values.app.newsletter.imapHost | quote }}
- name: NEWSLETTER_IMAP_PORT
  value: {{ .Values.app.newsletter.imapPort | default 993 | quote }}
- name: NEWSLETTER_IMAP_FOLDER
  value: {{ .Values.app.newsletter.imapFolder | default "INBOX" | quote }}
- name: NEWSLETTER_POLL_MINUTES
  value: {{ .Values.app.newsletter.pollMinutes | default 15 | quote }}
{{- if .Values.app.newsletter.maxMessageBytes }}
- name: NEWSLETTER_MAX_MESSAGE_BYTES
  value: {{ .Values.app.newsletter.maxMessageBytes | quote }}
{{- end }}
{{- if .Values.app.newsletter.existingSecret }}
- name: NEWSLETTER_IMAP_USERNAME
  valueFrom:
    secretKeyRef:
      name: {{ .Values.app.newsletter.existingSecret | quote }}
      key: {{ .Values.app.newsletter.usernameKey | default "NEWSLETTER_IMAP_USERNAME" | quote }}
      optional: true
- name: NEWSLETTER_IMAP_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ .Values.app.newsletter.existingSecret | quote }}
      key: {{ .Values.app.newsletter.passwordKey | default "NEWSLETTER_IMAP_PASSWORD" | quote }}
      optional: true
{{- end }}
{{- end }}
{{- end -}}

{{- define "news-dashboard.configEnv" -}}
{{- if .Values.app.config.metricsEnabled }}
- name: METRICS_ENABLED
  value: "true"
{{- end }}
{{- if .Values.app.config.enableApiDocs }}
- name: ENABLE_API_DOCS
  value: "true"
{{- end }}
{{- if .Values.app.config.analyticsRetentionDays }}
- name: ANALYTICS_RETENTION_DAYS
  value: {{ .Values.app.config.analyticsRetentionDays | quote }}
{{- end }}
{{- if .Values.app.config.corsOrigins }}
- name: CORS_ORIGINS
  value: {{ .Values.app.config.corsOrigins | quote }}
{{- end }}
{{- end -}}
