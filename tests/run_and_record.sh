#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# run_and_record.sh — Run pytest and save results for traceability
#
# Usage:
#   ./tests/run_and_record.sh DEF-011
#   ./tests/run_and_record.sh DEF-009 DEF-010
#   ./tests/run_and_record.sh baseline
#   ./tests/run_and_record.sh docs
#
# Output: tests/results/YYYY-MM-DD_<ID>_<result>.txt
#
# Cross-platform: macOS (zsh/bash) + Linux (bash)
# Adapted from franklinwh-energy-manager (AP-11)
# ═══════════════════════════════════════════════════════════════════
set -euo pipefail

# ── Resolve project root (script lives in tests/) ────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RESULTS_DIR="$PROJECT_ROOT/tests/results"

# ── Validate arguments ───────────────────────────────────────────
if [ $# -eq 0 ]; then
    echo "Usage: $0 <ID> [<ID2> ...]"
    echo "  ID = DEF-xxx, FEAT-xxx, CR-xxx, baseline, or docs"
    echo ""
    echo "Examples:"
    echo "  $0 FEAT-testing"
    echo "  $0 DEF-001 DEF-002"
    echo "  $0 baseline"
    exit 1
fi

# ── Build filename from IDs ──────────────────────────────────────
DATE_STR=$(date +%Y-%m-%d)
TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S %Z")
ID_PART=$(echo "$@" | tr ' ' '_')
BRANCH=$(git -C "$PROJECT_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
COMMIT=$(git -C "$PROJECT_ROOT" rev-parse --short HEAD 2>/dev/null || echo "unknown")

# ── Ensure results directory exists ──────────────────────────────
mkdir -p "$RESULTS_DIR"

# ── Run pytest ───────────────────────────────────────────────────
echo "🧪 Running test suite for: $@"
echo "   Branch: $BRANCH  Commit: $COMMIT"
echo ""

PYTEST_OUTPUT=""
EXIT_CODE=0

cd "$PROJECT_ROOT"

# Detect Python — prefer venv if available
if [ -x "$PROJECT_ROOT/venv/bin/python3" ]; then
    PYTHON="$PROJECT_ROOT/venv/bin/python3"
else
    PYTHON=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || echo "python3")
fi

# Capture output and exit code (skip live tests)
PYTEST_OUTPUT=$($PYTHON -m pytest tests/ -m "not live" -q --tb=short 2>&1) || EXIT_CODE=$?

# ── Determine result ─────────────────────────────────────────────
if [ $EXIT_CODE -eq 0 ]; then
    RESULT="pass"
    RESULT_LABEL="PASS ✅"
elif echo "$PYTEST_OUTPUT" | grep -q "passed"; then
    RESULT="partial"
    RESULT_LABEL="PARTIAL ⚠️"
else
    RESULT="fail"
    RESULT_LABEL="FAIL ❌"
fi

# ── Extract summary line ─────────────────────────────────────────
SUMMARY_LINE=$(echo "$PYTEST_OUTPUT" | tail -1)

# ── Write results file ───────────────────────────────────────────
RESULTS_FILE="$RESULTS_DIR/${DATE_STR}_${ID_PART}_${RESULT}.txt"

# Handle duplicate filenames (multiple runs same day/same ID)
if [ -f "$RESULTS_FILE" ]; then
    COUNTER=2
    while [ -f "${RESULTS_DIR}/${DATE_STR}_${ID_PART}_${RESULT}_${COUNTER}.txt" ]; do
        COUNTER=$((COUNTER + 1))
    done
    RESULTS_FILE="${RESULTS_DIR}/${DATE_STR}_${ID_PART}_${RESULT}_${COUNTER}.txt"
fi

cat > "$RESULTS_FILE" << EOF
═══════════════════════════════════════════════════════════
 TEST RESULTS — ${ID_PART}
 Date:    ${TIMESTAMP}
 Branch:  ${BRANCH}
 Commit:  ${COMMIT} (pre-commit)
 Result:  ${RESULT_LABEL}
═══════════════════════════════════════════════════════════

${PYTEST_OUTPUT}

═══════════════════════════════════════════════════════════
 Summary: ${SUMMARY_LINE}
═══════════════════════════════════════════════════════════
EOF

# ── Append to master test history log ────────────────────────────
HISTORY_LOG="$RESULTS_DIR/test_history.log"
RESULT_UPPER=$(echo "$RESULT" | tr '[:lower:]' '[:upper:]')
echo "${TIMESTAMP} | ${ID_PART} | ${BRANCH}@${COMMIT} | ${RESULT_UPPER} | ${SUMMARY_LINE}" >> "$HISTORY_LOG"

echo ""
echo "═══════════════════════════════════════════════════════"
echo " Result: ${RESULT_LABEL}"
echo " ${SUMMARY_LINE}"
echo " Saved:  ${RESULTS_FILE##*/}"
echo "═══════════════════════════════════════════════════════"

exit $EXIT_CODE
