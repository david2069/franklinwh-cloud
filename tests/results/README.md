# Test Results Archive

This directory stores test execution results for **every commit**, providing historical traceability and instant rollback context.

## Naming Convention

```
YYYY-MM-DD_<ID>_<result>.txt
```

| Component | Values | Example |
|-----------|--------|---------|
| **Date** | `YYYY-MM-DD` | `2026-03-16` |
| **ID** | `DEF-xxx`, `FEAT-xxx`, `CR-xxx`, `baseline`, `docs` | `FEAT-testing` |
| **Result** | `pass`, `partial`, `fail` | `pass` |

### Examples

```
2026-03-16_FEAT-testing_pass.txt       # Feature work
2026-03-16_DEF-001_pass.txt            # Defect fix
2026-03-16_baseline_pass.txt           # Periodic baseline
```

## File Format

Each results file contains:

```
═══════════════════════════════════════════════════════════
 TEST RESULTS — <ID>
 Date:    YYYY-MM-DD HH:MM:SS TZ
 Branch:  main
 Commit:  <short-hash> (pre-commit)
 Result:  PASS | PARTIAL | FAIL
═══════════════════════════════════════════════════════════

<full pytest output>

═══════════════════════════════════════════════════════════
 Summary: X passed, Y failed, Z skipped in N.NNs
═══════════════════════════════════════════════════════════
```

## Policy

See [CONTRIBUTING.md](../../CONTRIBUTING.md) — test results are **mandatory before every code commit**.
