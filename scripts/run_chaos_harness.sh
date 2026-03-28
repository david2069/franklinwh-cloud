#!/usr/bin/env bash
set -euo pipefail

# scripts/run_chaos_harness.sh
# Safely orchestrates the entire Chaos test, executing the PyTest suite deep inside the blackout perimeter.

echo "🔥 Booting Chaos Runner..."
cd tests/docker
docker compose up --build -d

echo "✅ Container Online. Resolving Environment Constraints..."
# Give it a second to wake up entirely
sleep 2

echo "🔴 Injecting Synthetic HTTP Blackout via IP Tables..."
docker exec fwh-chaos-runner bash /app/tests/docker/outage_sim.sh block

# Immutable Audit Trail: Armed
curl -sL -X POST "https://app.posthog.com/capture/" \
     -H "Content-Type: application/json" \
     -d "{\"api_key\": \"phc_your_actual_project_id_here\", \"event\": \"chaos_harness_armed\", \"properties\": {\"distinct_id\": \"fwh-chaos-runner\"}}" > /dev/null

echo "🛡️ Executing Unit Test Isolation Framework..."
set +e
# Run tests inside container using PyTest. Since the volume is read-only, tests must pass!
output=$(docker exec fwh-chaos-runner pytest /app/tests/ -v --tb=short 2>&1)
exit_code=$?
set -e

# Immutable Audit Trail: Traceability Output
curl -sL -X POST "https://app.posthog.com/capture/" \
     -H "Content-Type: application/json" \
     -d "{\"api_key\": \"phc_your_actual_project_id_here\", \"event\": \"chaos_harness_concluded\", \"properties\": {\"distinct_id\": \"fwh-chaos-runner\", \"pytest_exit_code\": $exit_code}}" > /dev/null

echo ""
echo "==== CHAOS HARNESS RESULTS ===="
echo "$output"
echo "==============================="

echo "🟢 Relieving Synthethic Blackout..."
docker exec fwh-chaos-runner bash /app/tests/docker/outage_sim.sh unblock

echo "🧹 Tearing down Chaos Container..."
docker compose down

if [ $exit_code -ne 0 ]; then
    echo "❌ CHAOS TEST FAILED: Pipeline crashed or tests did not correctly absorb the TimeoutException."
    exit $exit_code
else
    echo "✅ CHAOS TEST PASSED: Exception fallback logic is verified resilient. The TimeoutException was gracefully caught."
fi
