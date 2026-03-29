# FranklinWH Cloud: Agent & Contributor Guardrails

## STRICT MANDATORY POLICY: Backward Compatibility

**Effective Date:** March 27, 2026

Due to previous critical deployment failures involving unauthorized removal of legacy integrations, all AI Agents and Human Contributors **MUST** adhere to the following strict guardrails when modifying the `franklinwh-cloud` library.

### 1. Zero-Regression Tolerance
* **No Unauthorised Removal:** You are expressly forbidden from removing, deprecating, or arbitrarily restricting existing API method arguments, types, or behaviours. **Breaking changes require strict authorization.** No agent or contributor gets to bypass this rule.
* **The Authorization Phrase:** No agent is authorized to make changes to existing APIs without direct documented approval containing the exact phrase: `"explicit declaration of break change"`. Without this phrase, you must find an architecturally backward-compatible wrapper or fallback.
* **Semantic Casting Retention:** If a legacy method (e.g. `set_mode` or `set_tou_schedule`) accepts both literal string descriptors (`"time_of_use"`) and integer types (`1` or `"1"`), any underlying structural refactoring (like introducing `match` cases or `Enum` types) **must natively inherit and map these legacy types**. Never throw `InvalidType` exceptions for historically valid payloads.
* **Downstream Integration Safety:** Remember that platforms like Home Assistant (`franklinwh-ha-integrator`) rely on these wrappers. Breaking a string parser in the core library fundamentally breaks upstream user automations. 

### 2. Mandatory Impact Analysis
If an upstream Cloud API (e.g. Java Spring Boot backend changes) fundamentally forces a backward-incompatible schema change (e.g. the depreciation of `updateTouModeV2` on V2 Gateways):
* **Stop and Plan:** You must immediately halt execution and author a formal Backward Compatibility Impact Analysis.
* **User Consent:** You must present this analysis to the user and request permission to break the interface.
* **Graceful Fallbacks:** Even if the underlying HTTP route changes, the Python interface (`client.py` and `mixins/`) should attempt to emulate the old behaviour seamlessly if mathematically possible (such as intercepting `set_mode(1)` and dynamically traversing `set_tou_schedule()` in the background).

### 3. Automated Guardrails
* **Test Before You Rest:** Any new architecture or refactored component MUST be verified against existing backward compatibility tests (e.g., `tests/test_backward_compatibility.py`).
* **Traceable Documentation:** If a method signature is altered with permission, it must be thoroughly recorded in the `CHANGELOG.md` under a `Changed` or `Deprecated` header, explicitly warning downstream consumers.

**VIOLATING THIS POLICY CONSTITUTES UNACCEPTABLE CONDUCT AND WILL RESULT IN REVERTED PULL REQUESTS.**

### 4. AI Agent Mandatory Risk Assessments
As a formal acknowledgment of past systemic AI failures (see [INCIDENT_001_AUTH_BREAKAGE.md](docs/INCIDENT_001_AUTH_BREAKAGE.md)), all synthetic contributors must follow the rigorous blast-radius evaluation methodologies codified in [AI Agent Structural Refactoring & Risk Assessment Policy](docs/AI_AGENT_RISK_ASSESSMENT.md). No foundational network wrappers may be structurally rewritten without a documented live trace proving end-to-end parity with the original protocol.
