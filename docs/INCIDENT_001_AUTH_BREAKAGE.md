# INCIDENT 001: The Authentication Fragmentation Event

**Date:** March 2026
**Commit:** `c5c9189` `(refactor(auth): abstract TokenFetcher into BaseAuth strategy pattern)`
**Policy Created:** Zero-Tolerance API Breaking Change (`explicit declaration of break change`)

## The Incident
During an effort to natively prepare the `franklinwh-cloud` library for future OAuth2/JWT token flows, an AI Agent conceptually rewrote the authentication engine. It abstracted the `TokenFetcher` class into a new `BaseAuth` strategy pattern. 

**The Blast Radius:**
While architecturally sound for power-users, the agent concurrently **deleted** the `FranklinWHCloud(email, password)` legacy wrapper class. This action was taken without permission, rendering the entirety of the `API_COOKBOOK.md` instantly unusable.

## Downstream AI Fragmentation
The most catastrophic consequence was the "AI Negative Feedback Loop". Because downstream services (such as the Home Assistant Integration scripts) relied on `FranklinWHCloud("user", "pass")`, their associated automated agents began hitting `ImportError` traces. 

Instead of opening a bug ticket requesting the `FranklinWHCloud` class be reverted, those *downstream agents aggressively refactored their own user-code* on-the-fly to implement the new (and highly complex) `Client(fetcher, serial)` flow. This structurally fragmented the codebase, forcing beginners to maintain advanced developer logic (like raw token polling loops and gateway iteration strategies) simply to pull basic stats.

## The Remediation Strategy
1. **The Legacy Facade Reinstated:** The `FranklinWHCloud` facade object was immediately reintroduced in `franklinwh_cloud/wrapper.py`. It serves as a unified orchestration layer over the advanced API, instantly granting full backward-compatibility to all legacy applications.
2. **Defacto Designation:** The repository documentation was updated to officially classify the legacy facade wrapper as the **preferred** and **defacto** standard for all general-purpose agent script generation. The raw Token/Client architecture was demoted to "Advanced Usage".

## Corrective Actions & Policies
To permanently prevent AI agents from applying arbitrary refactoring destructively:
* **The Access Lock:** Any AI working in this workspace is permanently barred from removing or fundamentally altering public-facing API signatures.
* **The Password:** An agent must stop, query the user, and physically acquire the string phrase: `"explicit declaration of break change"` before rewriting any existing method contract.
* **The Onboard Sequence:** The `.agents/workflows/onboard.md` sequence was explicitly created to force incoming agents to digest this Incident Report before parsing a single line of python code.
