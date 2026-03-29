# Live Test Protocol — FranklinWH Cloud API (AP-13)

**Status**: Active  
**Scope**: All agents and contributors executing live tests against the FranklinWH Cloud API  
**References**: `pii_policy.md`, `change_management.md`, `franklinwh-cloud/docs/QA_TEST_PLAN.md`

---

## Mandatory Credential Rules

### Rule 1 — Positive-Path Tests: Real Credentials Permitted

Real account credentials (loaded from `franklinwh.ini` or environment variables) **may only be used** for tests that expect a **successful outcome**:

- Successful authentication (`login()`, `FranklinWHCloud.login()`)
- Successful device discovery (`discover()`, `get_site_and_device_info()`)
- Successful onboard (`POST /api/system/onboard`)
- Successful gateway data poll

> **The real account email address must never appear in test output, logs, or committed fixtures.** Use `email[:3]***` style masking in any logged output.

---

### Rule 2 — Negative-Path Tests: Dummy Credentials ONLY

Any test that exercises a **failure path** against the live FranklinWH Cloud API **must use a fake/dummy account** that does not correspond to a real registered user.

| Scenario | Requirement |
|----------|------------|
| Wrong password | Use dummy email e.g. `test-invalid@example.com` |
| Non-existent account | Use dummy email e.g. `nobody@doesnotexist.invalid` |
| Locked account simulation | Use dummy email only |
| 401 / `InvalidCredentialsException` testing | Use dummy email only |
| Rate-limit / account lockout testing | Use dummy email only |

**Rationale**: Repeated authentication failures against a real account can trigger account lockout, rate-limiting, or security alerts on the FranklinWH Cloud platform, potentially disrupting production access to the live gateway hardware.

---

### Rule 3 — Dummy Credentials Must Be Clearly Declared

Any test file using dummy credentials for negative-path live testing **must** declare this explicitly at the top of the test function or fixture:

```python
# NEGATIVE-PATH TEST — uses dummy credentials only, never real account
DUMMY_EMAIL = "test-negative@example.com"
DUMMY_PASSWORD = "invalid-password-for-testing"
```

---

### Rule 4 — Skip, Never Fail, When Real Credentials Are Absent

Any test requiring real credentials that cannot source them from `franklinwh.ini` or environment variables **must `pytest.skip()`** — not fail:

```python
# Correct pattern (matches franklinwh-cloud conftest.py convention)
if not email or not password:
    pytest.skip("Live credentials not available — skipping positive-path live test")
```

---

## Test Classification Matrix

| Test Type | Cloud API Call | Credentials Required | Gate |
|-----------|---------------|---------------------|------|
| Unit test | No (mocked) | None | Gate 1 |
| Integration — positive path | Yes (live) | Real (`franklinwh.ini`) | Gate 3 |
| Integration — negative path | Yes (live) | Dummy only | Gate 3 |
| Chaos/resilience (timeout) | Yes (live, network throttled) | Real | QA_TEST_PLAN.md |

---

## Scope of Enforcement

This policy applies to:

- `tests/` in this repository (`franklinwh-cloud`)
- All agent-authored test scripts (inline or file-based) that make live Cloud API calls
- Manual `curl` or Python inline test snippets proposed in agent responses

**Non-compliant tests will be rejected during peer review and must be corrected before merge.**

---

## Rationale Summary

> Real credentials represent live production access to a physical home energy system.  
> Account lockout or cloud API rate-limiting caused by negative testing with real credentials  
> could interrupt power management automation on live hardware.  
> Dummy credentials eliminate this risk at zero cost.
