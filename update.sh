#!/bin/bash
# update.sh — Refresh the franklinwh-cloud-test environment
#
# Usage:
#   ./update.sh          # pull + install + test
#   ./update.sh --quick  # pull + install only (skip tests)
#   ./update.sh --test   # test only (no pull/install)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Colours
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}✓${NC} $1"; }
warn()  { echo -e "${YELLOW}⚠${NC} $1"; }
fail()  { echo -e "${RED}✗${NC} $1"; exit 1; }

# ── Check venv ───────────────────────────────────────────────────────
if [ -z "$VIRTUAL_ENV" ]; then
    if [ -f "venv/bin/activate" ]; then
        warn "venv not active — activating..."
        source venv/bin/activate
    else
        fail "No venv found. Run: python3 -m venv venv && source venv/bin/activate"
    fi
fi

MODE="${1:-full}"

# ── Pull ─────────────────────────────────────────────────────────────
if [ "$MODE" != "--test" ]; then
    echo ""
    echo "═══ Step 1: Pull latest from GitHub ═══"
    git pull || fail "git pull failed"
    info "Repository updated"
fi

# ── Install ──────────────────────────────────────────────────────────
if [ "$MODE" != "--test" ]; then
    echo ""
    echo "═══ Step 2: Install package (editable + test deps) ═══"
    # Prefer local dev directory (unpushed changes), fall back to this clone
    if [ -d "../franklinwh-cloud/franklinwh_cloud" ]; then
        pip install -e "../franklinwh-cloud[test]" --quiet || fail "pip install failed"
        info "Package installed (from ../franklinwh-cloud — local dev)"
    else
        pip install -e ".[test]" --quiet || fail "pip install failed"
        info "Package installed (from local clone)"
    fi
fi

# ── Test ─────────────────────────────────────────────────────────────
if [ "$MODE" != "--quick" ]; then
    echo ""
    echo "═══ Step 3: Run test suite ═══"
    python -m pytest tests/ -v --tb=short --ignore=tests/test_live.py
    RESULT=$?

    # Save results
    TIMESTAMP=$(date +%Y-%m-%d_%H%M)
    RESULTS_FILE="tests/results/test_run_${TIMESTAMP}.txt"
    mkdir -p tests/results
    python -m pytest tests/ -v --tb=short --ignore=tests/test_live.py > "$RESULTS_FILE" 2>&1 || true
    info "Results saved to $RESULTS_FILE"

    if [ $RESULT -ne 0 ]; then
        fail "Tests failed — check output above"
    fi
    info "All tests passed"
fi

# ── Summary ──────────────────────────────────────────────────────────
echo ""
echo "═══ Environment ═══"
echo "  Python:  $(python --version)"
echo "  Package: $(pip show franklinwh-cloud-client 2>/dev/null | grep Version || echo 'not found')"
echo "  Branch:  $(git branch --show-current)"
echo "  Commit:  $(git log --oneline -1)"
echo ""
info "Ready! Run CLI with: franklinwh-cli status"
