---
description: sync library and test changes from dev workspace to live-test workspace
---

# Sync Dev → Test Workspace

Run this after committing changes in `franklinwh-cloud` to keep `franklinwh-cloud-test` current before running live tests.

## Why this exists

- `franklinwh-cloud` — development workspace (`feat/*` branches)
- `franklinwh-cloud-test` — live-gateway test workspace (tracks `main`)
- Both contain their own copies of the library and tests
- Without syncing, `franklinwh-cloud-test` will run against stale code

## Steps

// turbo
1. Run the sync script:
```bash
/Users/davidhona/dev/franklinwh-cloud-test/sync-from-dev.sh
```

// turbo
2. Verify the test suite still passes in the test workspace:
```bash
cd /Users/davidhona/dev/franklinwh-cloud-test && venv/bin/pytest --ignore=tests/test_live.py -q
```

3. If any tests fail, investigate before running live tests.

## Tests-only mode

To sync only test files (skip library code):
```bash
/Users/davidhona/dev/franklinwh-cloud-test/sync-from-dev.sh --tests-only
```
