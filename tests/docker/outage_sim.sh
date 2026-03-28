#!/usr/bin/env bash
# outage_sim.sh — Simulate total API blackouts inside the Chaos Harness
#
# Usage:
#   ./tests/docker/outage_sim.sh block     # Block Cloud API
#   ./tests/docker/outage_sim.sh unblock   # Restore Cloud API
#   ./tests/docker/outage_sim.sh status    # Show actual iptables config
#

set -euo pipefail

# Cloud API Hostnames
CLOUD_HOSTS=(
    "fhp-api.franklinwh.com"
    "fhp-api-ah.franklinwh.com"
)

_block_cloud() {
    for host in "${CLOUD_HOSTS[@]}"; do
        # We must resolve because iptables inside containers may complain about DNS names
        local ips
        ips=$(getent ahosts "$host" 2>/dev/null | awk '{print $1}' | sort -u) || true
        if [ -z "$ips" ]; then
            echo "⚠️  Could not resolve $host — skipping IP block."
            continue
        fi
        for ip in $ips; do
            iptables -C OUTPUT -d "$ip" -j DROP 2>/dev/null || \
                iptables -A OUTPUT -d "$ip" -j DROP
        done
        echo "🔴 Cloud BLOCKED → $host"
    done
}

_unblock_cloud() {
    for host in "${CLOUD_HOSTS[@]}"; do
        local ips
        ips=$(getent ahosts "$host" 2>/dev/null | awk '{print $1}' | sort -u) || true
        for ip in $ips; do
            iptables -D OUTPUT -d "$ip" -j DROP 2>/dev/null || true
        done
        echo "🟢 Cloud UNBLOCKED → $host"
    done
}

_status() {
    echo "═══ iptables OUTPUT block rules ═══"
    iptables -L OUTPUT -n --line-numbers 2>/dev/null || echo "(no rules)"
}

target="${1:-status}"

case "$target" in
    block)   _block_cloud ;;
    unblock) _unblock_cloud ;;
    status)  _status ;;
    *)
        echo "Usage: $0 [block|unblock|status]"
        exit 1
        ;;
esac
