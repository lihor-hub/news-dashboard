#!/usr/bin/env bash

# Shared fail-closed controls for production Helm entry points. This file is
# sourced by CI and scripts/deploy-local-k8s.sh.

production_cutover_enabled() {
  [[ "${INGRESS_CUTOVER_ENABLED:-}" == "true" ]]
}

cleanup_production_helm_secret_files() {
  if [[ -n "${PRODUCTION_HELM_SECRET_DIR:-}" && -d "${PRODUCTION_HELM_SECRET_DIR}" ]]; then
    rm -f \
      "${PRODUCTION_SESSION_SECRET_FILE:-}" \
      "${PRODUCTION_POSTGRES_PASSWORD_FILE:-}" \
      "${PRODUCTION_ADDITIONAL_EGRESS_FILE:-}"
    rmdir "${PRODUCTION_HELM_SECRET_DIR}"
  fi
  unset PRODUCTION_HELM_SECRET_DIR
  unset PRODUCTION_SESSION_SECRET_FILE
  unset PRODUCTION_POSTGRES_PASSWORD_FILE
  unset PRODUCTION_ADDITIONAL_EGRESS_FILE
  unset PRODUCTION_HELM_SECRET_ARGS
}

prepare_production_additional_egress_file() {
  if [[ -z "${PRODUCTION_HELM_SECRET_DIR:-}" ]]; then
    echo "Prepare production Helm files before additional egress values." >&2
    return 1
  fi

  local input_file="${1:?additional egress input path is required}"
  PRODUCTION_ADDITIONAL_EGRESS_FILE="${PRODUCTION_HELM_SECRET_DIR}/additional-egress-values.json"
  python3 ./scripts/normalize_additional_egress_values.py \
    "${input_file}" "${PRODUCTION_ADDITIONAL_EGRESS_FILE}"
  chmod 600 "${PRODUCTION_ADDITIONAL_EGRESS_FILE}"
}

prepare_production_helm_secret_files() {
  cleanup_production_helm_secret_files

  if [[ -z "${SESSION_SECRET:-}" ]]; then
    echo "SESSION_SECRET is required for production auth." >&2
    return 1
  fi
  if [[ -z "${POSTGRES_PASSWORD:-}" ]]; then
    echo "POSTGRES_PASSWORD is required for production PostgreSQL." >&2
    return 1
  fi

  PRODUCTION_HELM_SECRET_DIR="$(mktemp -d "${TMPDIR:-/tmp}/news-dashboard-helm.XXXXXX")"
  trap cleanup_production_helm_secret_files EXIT
  trap 'exit 1' HUP INT TERM
  chmod 700 "${PRODUCTION_HELM_SECRET_DIR}"
  PRODUCTION_SESSION_SECRET_FILE="${PRODUCTION_HELM_SECRET_DIR}/session-secret"
  PRODUCTION_POSTGRES_PASSWORD_FILE="${PRODUCTION_HELM_SECRET_DIR}/postgres-password"

  (
    umask 077
    printf %s "${SESSION_SECRET}" >"${PRODUCTION_SESSION_SECRET_FILE}"
    printf %s "${POSTGRES_PASSWORD}" >"${PRODUCTION_POSTGRES_PASSWORD_FILE}"
  )
  chmod 600 "${PRODUCTION_SESSION_SECRET_FILE}" "${PRODUCTION_POSTGRES_PASSWORD_FILE}"

  # shellcheck disable=SC2034 # Consumed by scripts that source this library.
  PRODUCTION_HELM_SECRET_ARGS=(
    --set-file "app.auth.sessionSecret=${PRODUCTION_SESSION_SECRET_FILE}"
    --set-file "postgresql.password=${PRODUCTION_POSTGRES_PASSWORD_FILE}"
  )
}
