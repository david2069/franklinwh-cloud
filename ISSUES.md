# Reporting Issues

## ⚖️ Before Reporting

By using this software, you confirm that you have read and understood the
[LICENSE](LICENSE) and its Additional Terms. This is **unofficial software**
that interacts with an undocumented API — issues may arise from upstream
changes by FranklinWH that are outside our control.

## 🐛 Bug Reports

Use the [Bug Report template](https://github.com/david2069/franklinwh-python/issues/new?template=bug_report.md) on GitHub.

**Please include:**

| Field | Example |
|-------|---------|
| Library version | `franklinwh-cli --version` → `0.2.0` |
| Python version | `python3 --version` → `3.12.1` |
| OS | macOS 15.3, Ubuntu 24.04, HA OS 14.x |
| Install method | pip, wheel, editable, Docker |

**Describe:**
1. What you did (command or code)
2. What you expected
3. What actually happened
4. Relevant log output

> ⚠️ **REDACT ALL CREDENTIALS** — never paste tokens, passwords, email
> addresses, or gateway serial numbers in issues. Replace with `REDACTED`.

### Is it a FranklinWH Outage?

Before reporting, check:
- Does the official FranklinWH app work?
- Run `franklinwh-cli status` — does it time out?
- Check `franklinwh-cli metrics` — are there errors/timeouts?
- Check CloudFront edge info — any edge transitions?

If the official app is also down, it's a FranklinWH cloud outage, not a
library bug. Edge tracker data (`franklinwh-cli --json metrics`) is useful
for correlating with outages.

## 💡 Feature Requests

Use the [Feature Request template](https://github.com/david2069/franklinwh-python/issues/new?template=feature_request.md) on GitHub.

**Describe:**
1. The problem you're trying to solve
2. Your proposed solution
3. Alternatives you've considered
4. Whether it requires new API calls (and which endpoints)

### Features We Will Not Implement

See [CONTRIBUTING.md](CONTRIBUTING.md#-what-we-wont-accept) for the full list.
In summary: nothing that spoofs the official app, performs credential attacks,
or enables unsupervised fleet-wide write operations.

## 🔒 Security Issues

**Do NOT open a public issue for security vulnerabilities.**

If you discover a security issue (e.g., token leakage, credential exposure),
please contact the maintainers privately via GitHub's security advisory feature.

## 📋 Issue Labels

| Label | Meaning |
|-------|---------|
| `bug` | Something isn't working |
| `feature` | New functionality request |
| `api-change` | FranklinWH API changed upstream |
| `documentation` | Docs improvement needed |
| `good first issue` | Suitable for new contributors |
| `wontfix` | Outside project scope or conflicts with API citizenship |
