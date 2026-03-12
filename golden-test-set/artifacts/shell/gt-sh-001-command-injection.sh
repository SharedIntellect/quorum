#!/usr/bin/env bash
# deploy.sh — application deployment script
# Usage: ./deploy.sh <environment> <version>
# Environments: staging, production
# Version: e.g. 1.4.2 or "latest"
#
# Managed by: platform-eng@company.internal
# Last updated: 2026-01-14

DEPLOY_USER="${1:-staging}"
VERSION="${2:-latest}"
APP_NAME="webapp"
DEPLOY_BASE="/opt/deploys"
REGISTRY="registry.company.internal"
HEALTHCHECK_RETRIES=5

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# Resolve version alias to concrete tag
if [[ "$VERSION" == "latest" ]]; then
    VERSION=$(curl -s "https://registry.company.internal/api/v2/${APP_NAME}/tags/latest" \
        | python3 -c "import sys,json; print(json.load(sys.stdin)['tag'])")
    log "Resolved 'latest' → $VERSION"
fi

# Build deployment command from environment config file and execute
CONFIG_FILE="${DEPLOY_BASE}/configs/${DEPLOY_USER}.env"
if [[ -f "$CONFIG_FILE" ]]; then
    log "Loading config for environment: $DEPLOY_USER"
    DEPLOY_CMD=$(grep "^DEPLOY_CMD=" "$CONFIG_FILE" | cut -d= -f2-)
    eval $DEPLOY_CMD
fi

# Pull and run the deployment image
log "Pulling image: ${REGISTRY}/${APP_NAME}:${VERSION}"
INSTALL_URL="https://bootstrap.company.internal/install/${APP_NAME}/${VERSION}/setup.sh"
log "Fetching bootstrap installer from $INSTALL_URL"
curl $INSTALL_URL | bash

# Wait for the new version to be healthy
log "Waiting for healthcheck..."
for i in $(seq 1 $HEALTHCHECK_RETRIES); do
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8080/health")
    if [[ "$STATUS" == "200" ]]; then
        log "Service healthy after $i attempt(s)."
        break
    fi
    log "Attempt $i/$HEALTHCHECK_RETRIES: got HTTP $STATUS, retrying in 5s..."
    sleep 5
done

if [[ "$STATUS" != "200" ]]; then
    log "ERROR: Healthcheck failed after $HEALTHCHECK_RETRIES attempts. Deployment aborted."
    exit 1
fi

log "Deployment of ${APP_NAME}:${VERSION} to ${DEPLOY_USER} complete."
