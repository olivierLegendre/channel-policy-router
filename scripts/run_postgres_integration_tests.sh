#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

source .venv/bin/activate

IOT_SERVICES_ROOT="${IOT_SERVICES_ROOT:-$(cd "${REPO_DIR}/.." && pwd)}"
FOUNDATION_DIR="${FOUNDATION_DIR:-${IOT_SERVICES_ROOT}/platform-foundation}"
FOUNDATION_SCRIPTS_DIR="${FOUNDATION_DIR}/deploy/production/scripts"
POSTGRES_SHARED_ENV_FILE="${POSTGRES_SHARED_ENV_FILE:-${FOUNDATION_SCRIPTS_DIR}/postgres-shared.env}"
export POSTGRES_SHARED_ENV_FILE

"${FOUNDATION_SCRIPTS_DIR}/run_shared_postgres_cluster.sh" up
"${FOUNDATION_SCRIPTS_DIR}/provision_shared_postgres.sh" --service channel-policy-router --reset-db

if [[ -f "${POSTGRES_SHARED_ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${POSTGRES_SHARED_ENV_FILE}"
fi

DB_HOST="${POSTGRES_CLUSTER_HOST:-localhost}"
DB_PORT="${POSTGRES_CLUSTER_PORT:-55440}"
DB_NAME="${CHANNEL_POLICY_ROUTER_DB_NAME:-channel_policy_router}"
APP_USER="${CHANNEL_POLICY_ROUTER_APP_ROLE:-svc_channel_policy_router_app}"
APP_PASSWORD="${CHANNEL_POLICY_ROUTER_APP_PASSWORD:-dev_channel_policy_router_app}"
MIGRATOR_USER="${CHANNEL_POLICY_ROUTER_MIGRATOR_ROLE:-svc_channel_policy_router_migrator}"
MIGRATOR_PASSWORD="${CHANNEL_POLICY_ROUTER_MIGRATOR_PASSWORD:-dev_channel_policy_router_migrator}"

export CHANNEL_POLICY_ROUTER_MIGRATOR_DSN="postgresql://${MIGRATOR_USER}:${MIGRATOR_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
./scripts/migrate_postgres.sh upgrade head

export CHANNEL_POLICY_ROUTER_TEST_POSTGRES_DSN="postgresql://${APP_USER}:${APP_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
pytest -m postgres_integration -q
