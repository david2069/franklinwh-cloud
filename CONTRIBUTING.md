# Contributing to franklinwh-python

## Commit Policy

### Conventional Commits

All commits must use [Conventional Commits](https://www.conventionalcommits.org/) format:

| Prefix | Use |
|--------|-----|
| `fix:` | Bug fix |
| `feat:` | New feature or endpoint |
| `refactor:` | Code restructure (no behaviour change) |
| `docs:` | Documentation only |
| `test:` | Test additions or fixes |
| `chore:` | Build, deps, config changes |

### Branching

- Use **feature branches** for multi-commit work
- Self-merge PRs are acceptable for solo development
- Direct pushes to `main` are OK for single-commit fixes

### Secrets

- **Never commit credentials** — use `.env` for local credentials
- See `.env.example` for the required format
- For CI, use GitHub repository secrets

## Test Policy

### Running Tests

```bash
# Install test dependencies
venv/bin/pip install -e ".[test]"

# Run all tests (excluding live)
venv/bin/pytest -m "not live" -v

# Run with coverage
venv/bin/pytest -m "not live" -v --cov=franklinwh --cov-report=term-missing

# Run live smoke tests (requires .env)
venv/bin/pytest -m live -v
```

### Test Requirements

| Rule | Detail |
|------|--------|
| New code requires tests | Any new method or bug fix needs a test |
| All tests must pass before merge | `pytest -m "not live"` exit code 0 |
| Coverage ratchet | Coverage percentage can only go up |
| Live tests are opt-in | Marked with `@pytest.mark.live`, skipped by default |

### Test Traceability (AP-11)

Every commit with code changes must have a corresponding test result:

```bash
# Run tests and save results
./tests/run_and_record.sh FEAT-my-feature

# Output: tests/results/YYYY-MM-DD_FEAT-my-feature_pass.txt
```

Commit the result file together with your code changes.

See `tests/results/README.md` for naming conventions.

### Test Types

| Type | Location | Runs By Default |
|------|----------|:---:|
| Unit tests | `tests/test_*.py` | ✅ |
| Mock integration | `tests/test_get_stats.py`, `test_retry.py` | ✅ |
| Live smoke tests | `tests/test_live.py` | ❌ (opt-in) |

## Re-syncing Downstream

The `franklinwh-energy-manager` project depends on this library. After changes here, update FEM's dependency reference.
