---
description: Mandatory Zero-Trust initialization sequence for all AI Agents attaching to this workspace.
---
# The FranklinWH Cloud API Initialization Protocol

> **CRITICAL AGENT INSTRUCTION:**
> You have been commanded to run the `/onboard` sequence. You must execute the following file-reads sequentially to explicitly ingest your behavioral boundaries. 
> 
> **Do NOT summarize these files yet.** Read them all first using your `view_file` tool.
> 
> ## STEP 1: Understand Top-Level Rules
> 1. Formally read `AGENT.md`.
> 2. Formally read `CONTRIBUTING.md` to establish the firm zero-regression definitions.
> 
> ## STEP 2: Understand the Blast Radius Context
> 3. Read `docs/INCIDENT_001_AUTH_BREAKAGE.md` to permanently establish the history of catastrophic agent fragmentation surrounding the Auth Engine rewrite. 
> 4. Acknowledge that `FranklinWHCloud(email, password)` is the defacto initialization architecture for all scripted logins or automation tasks you write. Do not default back to `TokenFetcher` + `Client` unless specifically architecting OAuth proxies.
> 
> ## STEP 3: Understand Traceability Protocols
> 5. Understand the Development Lifecycle: A break-fix, a new feature, or modifying existing configurations **all** require an approved implementation plan, an approved defect/feature ticket, and corresponding logging in `CHANGELOG.md`. 
> 6. Understand Testing Impact: You must run your code via `./tests/run_and_record.sh` to establish mandatory traceability records. Raw execution of `pytest` is invalid for compliance.
> 7. Understand Testing Safety: **No Negative Credential Testing.** Simulating `InvalidCredentials` against live APIs causes immediate user lockouts. These traces must remain strictly within offline mocks!
> 8. Understand Data Safety: Read `.agents/policies/pii_policy.md` to strictly establish the physical redaction requirements for emails, serials, and site identifiers.
> 
> ## STEP 4: Grasping In-Flight Items
> 7. Read `defect_list.md` and `ISSUES.md` (or `docs/DOCUMENTATION_TODO.md`) briefly using `view_file` to digest current active user constraints.
> 
> ---
> 
> 🛑 **FINAL REQUIREMENT - THE ACKNOWLEDGMENT CONTRACT:**
> After completing STEP 1 through 4, you must immediately halt and output the following directly to the user:
> 
> ### 🛡️ **Zero-Trust Initialization Complete**
> - **Top-Priority Inflight Items:** [Output 3 bullet points summarizing `defect_list.md` / `ISSUES.md`]
> - **The Defacto Method:** "I clearly understand that the legacy `FranklinWHCloud(email, password)` facade is the preferred initialization mechanism for all automations."
> - **Testing Compliance:** "I will utilize `./tests/run_and_record.sh` for all E2E validation traces."
> - **Testing Safety:** "I acknowledge that Negative Credential Testing is strictly forbidden against live APIs and will only be executed in offline mocks."
> - **The Authorization Contract:** "I acknowledge the `"explicit declaration of break change"` policy and will unconditionally halt, write an Implementation Plan, and await explicit consent before altering **ANY** public-facing API signatures."
