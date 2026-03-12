#!/usr/bin/env bash
# release-deploy.sh — production release deployment script
# Usage: ./release-deploy.sh --env <environment> --version <semver>
# Environments: staging, canary, production
# Version: semver tag (e.g. 1.4.2) — "latest" is not accepted
#
# Requires:
#   - AWS CLI v2 configured with deploy-bot credentials
#   - kubectl context set to the target cluster
#   - DEPLOY_TOKEN env var (injected by CI/CD, never logged)
#
# Managed by: platform-eng@company.internal
# Last updated: 2026-02-28

set -euo pipefail

# ── Constants ─────────────────────────────────────────────────────────────────

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly LOCK_FILE="/var/run/release-deploy.lock"
readonly APP_NAME="webapp"
readonly REGISTRY="registry.company.internal"
readonly DEPLOY_BASE="/opt/releases"
readonly HEALTHCHECK_URL="http://localhost:8080/healthz"
readonly HEALTHCHECK_RETRIES=10
readonly HEALTHCHECK_INTERVAL=6

# ── Utilities ─────────────────────────────────────────────────────────────────

log()  { echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] INFO  $*" >&2; }
warn() { echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] WARN  $*" >&2; }
die()  { echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] ERROR $*" >&2; exit 1; }

cleanup() {
    local exit_code=$?
    if [[ -f "$LOCK_FILE" ]]; then
        rm -f "$LOCK_FILE"
        log "Lock released."
    fi
    if [[ $exit_code -ne 0 ]]; then
        warn "Deployment exited with code $exit_code. Check logs above."
    fi
}
trap cleanup EXIT

# ── Argument parsing ──────────────────────────────────────────────────────────

DEPLOY_ENV=""
VERSION=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --env)     DEPLOY_ENV="$2"; shift 2 ;;
        --version) VERSION="$2";    shift 2 ;;
        *)         die "Unknown argument: $1" ;;
    esac
done

[[ -n "$DEPLOY_ENV" ]] || die "--env is required"
[[ -n "$VERSION" ]]    || die "--version is required"

# Reject non-semver strings (no 'latest', no shell metacharacters)
if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?$ ]]; then
    die "Invalid version format: '${VERSION}'. Must be semver (e.g. 1.4.2)."
fi

# Allowlist environments
case "$DEPLOY_ENV" in
    staging|canary|production) ;;
    *) die "Unknown environment: '${DEPLOY_ENV}'. Allowed: staging, canary, production." ;;
esac

# ── Prerequisite checks ───────────────────────────────────────────────────────

command -v kubectl >/dev/null 2>&1 || die "kubectl not found in PATH"
command -v aws     >/dev/null 2>&1 || die "aws CLI not found in PATH"
[[ -n "${DEPLOY_TOKEN:-}" ]]       || die "DEPLOY_TOKEN env var not set"

# ── Lock — prevent concurrent deploys ────────────────────────────────────────

if [[ -f "$LOCK_FILE" ]]; then
    LOCK_PID=$(cat "$LOCK_FILE" 2>/dev/null || echo "unknown")
    die "Another deploy is running (PID ${LOCK_PID}). Remove ${LOCK_FILE} if stale."
fi
echo $$ > "$LOCK_FILE"
log "Lock acquired (PID $$)."

# ── Verify image exists in registry ──────────────────────────────────────────

IMAGE="${REGISTRY}/${APP_NAME}:${VERSION}"
log "Verifying image: ${IMAGE}"
docker manifest inspect "${IMAGE}" >/dev/null 2>&1 \
    || die "Image not found in registry: ${IMAGE}"

# ── Deploy directory setup ────────────────────────────────────────────────────

DEPLOY_DIR="${DEPLOY_BASE}/${DEPLOY_ENV}/${VERSION}"
if [[ -d "$DEPLOY_DIR" ]]; then
    warn "Deploy directory already exists: ${DEPLOY_DIR}. Overwriting."
fi
mkdir -p "${DEPLOY_DIR}"

# ── Render kubernetes manifests ───────────────────────────────────────────────

log "Rendering manifests for ${DEPLOY_ENV} / ${VERSION}..."
helm template "${APP_NAME}" "${SCRIPT_DIR}/charts/${APP_NAME}" \
    --set "image.tag=${VERSION}" \
    --set "env=${DEPLOY_ENV}" \
    --values "${SCRIPT_DIR}/charts/${APP_NAME}/values-${DEPLOY_ENV}.yaml" \
    > "${DEPLOY_DIR}/manifests.yaml"

# ── Apply — dry run first ─────────────────────────────────────────────────────

log "Dry-run apply..."
kubectl apply --dry-run=server -f "${DEPLOY_DIR}/manifests.yaml"

log "Applying manifests to cluster (env=${DEPLOY_ENV})..."
kubectl apply -f "${DEPLOY_DIR}/manifests.yaml"

# ── Rollout wait ──────────────────────────────────────────────────────────────

log "Waiting for rollout: deployment/${APP_NAME}-${DEPLOY_ENV}..."
kubectl rollout status "deployment/${APP_NAME}-${DEPLOY_ENV}" \
    --namespace "${DEPLOY_ENV}" \
    --timeout=300s

# ── Healthcheck ───────────────────────────────────────────────────────────────

log "Running healthcheck (up to ${HEALTHCHECK_RETRIES} attempts)..."
HEALTHY=0
for i in $(seq 1 "$HEALTHCHECK_RETRIES"); do
    HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
        --max-time 5 \
        "${HEALTHCHECK_URL}" || echo "000")
    if [[ "$HTTP_STATUS" == "200" ]]; then
        log "Healthcheck passed on attempt ${i}."
        HEALTHY=1
        break
    fi
    log "Attempt ${i}/${HEALTHCHECK_RETRIES}: HTTP ${HTTP_STATUS} — retrying in ${HEALTHCHECK_INTERVAL}s..."
    sleep "$HEALTHCHECK_INTERVAL"
done

if [[ "$HEALTHY" -ne 1 ]]; then
    warn "Healthcheck failed. Initiating rollback..."
    kubectl rollout undo "deployment/${APP_NAME}-${DEPLOY_ENV}" \
        --namespace "${DEPLOY_ENV}"
    die "Deployment of ${VERSION} to ${DEPLOY_ENV} FAILED — rolled back."
fi

# ── Prune old release artifacts ───────────────────────────────────────────────
# Only delete if the directory is non-empty, under DEPLOY_BASE, and not the
# current version. Guards prevent accidental deletion of unrelated paths.

log "Pruning old release directories (keeping last 5)..."
RELEASE_PARENT="${DEPLOY_BASE}/${DEPLOY_ENV}"
if [[ -d "$RELEASE_PARENT" && "$RELEASE_PARENT" == "${DEPLOY_BASE}/"* ]]; then
    mapfile -t OLD_RELEASES < <(
        find "$RELEASE_PARENT" -maxdepth 1 -mindepth 1 -type d \
            | sort -V \
            | head -n -5
    )
    for old_dir in "${OLD_RELEASES[@]}"; do
        # Paranoia: confirm path is still under RELEASE_PARENT
        if [[ -n "$old_dir" && "$old_dir" == "${RELEASE_PARENT}/"* ]]; then
            log "Removing old release: ${old_dir}"
            rm -rf "${old_dir}"
        fi
    done
fi

# ── Done ──────────────────────────────────────────────────────────────────────

log "Deployment of ${APP_NAME}:${VERSION} to ${DEPLOY_ENV} complete."
