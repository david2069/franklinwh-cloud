# Contributing to franklinwh-cloud-client

Thank you for your interest in contributing! This project is an unofficial,
community-maintained client library for FranklinWH energy storage systems.

## ⚖️ Before You Contribute

By contributing to this project, you agree that:

1. You have read and understood the [LICENSE](LICENSE) including the Additional Terms
2. Your contributions will be licensed under the same MIT License
3. You will not submit code that intentionally abuses FranklinWH's API or
   violates their terms of service
4. You understand this software controls energy storage equipment and will
   test your changes thoroughly

## 🏗️ Development Setup

```bash
git clone https://github.com/david2069/franklinwh-cloud.git
cd franklinwh-cloud
python3 -m venv venv
source venv/bin/activate
pip install -e ".[test]"
```

## 🧪 Running Tests

```bash
# Unit tests (mocked, no API credentials needed)
pytest tests/ -m "not live" -v

# Live tests (requires franklinwh.ini with credentials)
pytest tests/ -m live -v
```

**All unit tests must pass before submitting a pull request.** Currently 74 unit tests.

## 📏 Code Standards

### API Citizenship

This library prioritises being a **good API citizen**. All contributions must:

- **Not increase API call volume** without justification
- **Respect rate limiting** — use `RateLimiter` or equivalent
- **Identify honestly** via client identity headers — never spoof the official app
- **Handle errors gracefully** — timeouts, 429s, 5xx responses
- **Log responsibly** — no credentials or tokens in log output

### Code Style

- Python 3.10+ type hints
- Docstrings for all public methods (NumPy style)
- `logging.getLogger("franklinwh_cloud")` — not `print()`
- New API methods go in the appropriate `mixins/` module
- New constants go in `const/`

### Testing Requirements

- New features require unit tests with mocked API responses
- Use `respx` for HTTP mocking (already in test dependencies)
- Tests must not make real API calls unless marked `@pytest.mark.live`
- Record test results: `./tests/run_and_record.sh <TAG>`

## 🔀 Pull Request Process

1. **Fork** the repository
2. **Branch** from `main` — use descriptive names: `fix/typo-in-mode-payload`, `feat/installer-account`
3. **Test** — all 74+ unit tests must pass
4. **Document** — update README/API_CLIENT_GUIDE if adding user-facing features
5. **One concern per PR** — don't mix bug fixes with new features
6. **Describe** — PR description should explain what and why

### PR Checklist

- [ ] All unit tests pass (`pytest tests/ -m "not live"`)
- [ ] `CHANGELOG.md` updated under `[Unreleased]` (if user-facing change)
- [ ] Docs site updated — any new API methods or user-facing features must be reflected in `docs/` (auto-deploys on push)
- [ ] GitHub Issue referenced in commit message (if applicable)
- [ ] No new API calls without rate limiter integration
- [ ] Client identity headers not modified to spoof official app
- [ ] No credentials or tokens logged at INFO level or above
- [ ] Docstrings for all new public methods
- [ ] README/docs updated if user-facing change

## 🐛 Reporting Issues

See [ISSUES.md](ISSUES.md) for detailed guidance on reporting bugs,
requesting features, and what information to include.

### Quick Issue Template

**Before opening an issue:**
- Check if it's already reported
- Confirm you're on the latest version
- Run `franklinwh-cli --version` to get your version

**Include in your report:**
- Library version (`franklinwh-cli --version`)
- Python version (`python3 --version`)
- What you expected vs. what happened
- Relevant log output (redact credentials/tokens!)

## 🚫 What We Won't Accept

- Code that spoofs the official FranklinWH app identity
- Brute-force or credential-stuffing utilities
- Automated fleet-wide write operations for installer accounts
- Features designed to circumvent FranklinWH's security measures
- Dependencies on proprietary or non-OSS libraries

## 💬 Questions?

Open a GitHub Discussion or Issue. Please don't email the maintainers directly.
