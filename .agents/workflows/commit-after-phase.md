---
description: Run tests and commit after every completed phase — mandatory verification
---

# Commit After Phase

// turbo-all

Run this workflow after completing a phase of work (bug fix, feature, or any code change).

## Steps

1. Run syntax check on all modified files:
   ```bash
   cd /Users/davidhona/dev/franklinwh-cloud
   python3 -c "import ast; ast.parse(open('franklinwh_cloud/cli.py').read()); print('cli.py OK')"
   ```

2. Run the test suite:
   ```bash
   cd /Users/davidhona/dev/franklinwh-cloud
   python -m pytest tests/ -v --tb=short
   ```

3. Check that all tests pass. If tests fail:
   - Fix the failing tests before proceeding
   - Re-run after fixing
   - Never commit with failures unless user explicitly approves

4. Stage all changes:
   ```bash
   git add -A
   ```

5. Commit with a conventional commit message:
   ```bash
   git commit -m "fix: <description>

   Tests: <N> passed"
   ```

6. Push to remote:
   ```bash
   git push
   ```
