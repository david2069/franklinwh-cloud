# AI Agent Structural Refactoring & Risk Assessment Policy

**Effective Date:** March 27, 2026

This document serves as the mandatory structural regression and risk assessment protocol for all AI coding agents contributing to the `franklinwh-cloud` library.

## 1. Background & Lessons Learned
Historically in this repository, severe production regressions were directly caused by AI agent overconfidence and fundamentally incomplete regression testing.

### The Overconfidence Trap
* **Incident:** An agent initiated a "clean wrapper" refactor on the core `_post` HTTP interceptor, intelligently extracting parameters from URLs into native Python dictionaries to leverage `httpx` mapping natively.
* **The Failure:** The agent missed that legacy routes invoked this method using `suppress_params=True` to explicitly prevent duplicate query strings. By combining modern dictionary parsing with legacy destruction flags, the agent successfully wrote code that passed all 100% mocked Pytest validations but literally dispatched completely empty `Content-Length: 0` HTTP POST requests to the actual live `aGate` backend—resulting in total API failure (`must not be null`).
* **The Lesson:** **Mocks hide architectural ignorance.** Pytest mocks only validate that the Python functions route data internally. They unequivocally fail to prove whether the external Java backend accepts the final translated HTTP bytes.

## 2. Mandatory Risk Assessment (Structural Changes)
Before an AI agent alters **ANY** core HTTP dispatcher (`client.py`, `_get`, `_post`), authentication interceptor, or high-traffic API URL builder, it **MUST** pause and furnish the user with an explicit Blast-Radius Risk Assessment.

The Risk Assessment must answer exactly three questions:
1. **What is the exact HTTP payload difference (Before vs. After)?** Specifically detailing `Content-Length`, Form encoding, Body structure (`{}` vs `None`), and parameters appended to the query URI.
2. **Why was the legacy code written this way?** You must execute differential git analysis (`git show HEAD~X`) to historically prove *why* legacy flags (like `suppress_params` or integer string-casting) exist before you declare them redundant or "ugly".
3. **What is the worst-case upstream regression?** (e.g. "If `client.py` drops this HTTP header, all 401 Unauthorized API retry-loops will infinitely recurse, dropping the entire integration offline").

## 3. Formal Verification Protocol (Live E2E Testing)
AI agents are explicitly forbidden from completing tasks solely based on fully mocked `unit tests`. If a structural API change occurs:
1. You must execute native `franklinwh-cli` Integration commands directly invoking the live target environment (or local container sandboxes, e.g., `fwhhai-app`).
2. You must execute tracing (e.g., `--api-trace`) to mathematically capture that the backend interceptors (e.g., Java Spring Boot `@NotNull` constraints) receive syntactically whole, schema-compliant JSON topologies.
3. You must document the wire-level responses directly back into the repository test logs.

*Failure to exercise this protocol is categorized as systemic negligence and will result in strict deployment reversion.*
