#!/usr/bin/env bash
# =============================================================================
# Trippo - DuckDNS Dynamic DNS Updater
# =============================================================================
# Usage:
#   export DUCKDNS_DOMAIN="yoursubdomain"   # without .duckdns.org
#   export DUCKDNS_TOKEN="your-token-uuid"
#   ./duckdns_update.sh
#
# Crontab entry (run every 10 minutes):
#   */10 * * * * /opt/trippo/duckdns_update.sh >/dev/null 2>&1
# =============================================================================

set -euo pipefail

DOMAIN="${DUCKDNS_DOMAIN:-}"
TOKEN="${DUCKDNS_TOKEN:-}"

if [[ -z "$DOMAIN" || -z "$TOKEN" ]]; then
    echo "Error: DUCKDNS_DOMAIN and DUCKDNS_TOKEN must be set." >&2
    echo "Usage: DUCKDNS_DOMAIN=mysubdomain DUCKDNS_TOKEN=mytoken $0" >&2
    exit 1
fi

RESPONSE=$(curl -s "https://www.duckdns.org/update?domains=${DOMAIN}&token=${TOKEN}&ip=")

if [[ "$RESPONSE" == "OK" ]]; then
    echo "$(date -u +'%Y-%m-%dT%H:%M:%SZ') - DuckDNS update successful for ${DOMAIN}.duckdns.org"
else
    echo "$(date -u +'%Y-%m-%dT%H:%M:%SZ') - DuckDNS update FAILED: ${RESPONSE}" >&2
    exit 1
fi
