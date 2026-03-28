# Upstream Strategy: The Divergence Reality

**Updated**: 2026-03-28 — *Strategy revised following massive architectural divergence.*

**Goal**: Establish a respectful, realistic relationship with the upstream `richo/franklinwh-python` repository now that `franklinwh-cloud` has fundamentally evolved into a V2 architecture.

---

## 1. The Reality of the Divergence

The original strategy proposed a "Trust Ladder" of piecemeal Pull Requests (tests, timeouts, endpoints). This is **no longer viable**. 

`franklinwh-cloud` is now lightyears ahead of the original wrapper. We have:
- Fragmented the codebase into 8 domain-specific mixins (TOU, Devices, Power, Storm, Stats, Account, etc.).
- Abstracted the authentication loop into polymorphic Auth Strategies.
- Rewritten the error handling (intercepting `400`, `401`, catching Timeouts, masking PII).
- Built an extensive CLI suite.
- Re-engineered responses into Type-Hinted DataClasses.

Attempting to port these changes back to upstream piece-by-piece would require richo to accept a total rewrite of their repository. This is an unfair and unrealistic expectation for a solo maintainer.

---

## 2. The Revised Strategy: Soft Succession & Symbiosis

We must pivot from "Upstreaming Features" to **"Providing an Alternative."** We play nice by being transparent, helpful, and respectful of the foundation they built.

### Phase 1: The "State of the Fork" Discussion 💬
Instead of flooding their repository with 20 massive Pull Requests, we open a single, highly respectful **GitHub Discussion** or **Issue** on the upstream repository.

**The Message:**
1. **Gratitude**: Thank richo for providing the foundational reverse-engineering that made our project possible.
2. **The Fork**: Explain that we needed advanced functionality (TOU scheduling, Smart Circuits, CLI, telemetry) which required a fundamental architectural rewrite, leading to the creation of `franklinwh-cloud`.
3. **The Offer**: Provide links to our documentation and offer `franklinwh-cloud` as a stable alternative for power-users or Home Assistant integrators who need write-access to their gateways. 

### Phase 2: Critical Backports Only 🩹
We abandon the goal of upstreaming new features (like TOU multi-season or Smart Circuits). Instead, we exclusively offer PRs that fix **critical crashes** in their existing codebase.

**What we will PR:**
- **The `timeout` intercept**: Fixing their `TODO(richo)` where requests hang indefinitely.
- **The `assert code == 200` fix**: Replacing the silent assert drop with a proper raised Exception.

**What we will NOT PR:**
- The CLI framework.
- The Mixin architecture.
- Any new endpoints.

### Phase 3: The Migration Path 🌉
If Home Assistant ecosystem developers (like the ones working on the HA Custom Integration) hit the limits of `richo/franklinwh-python`, we provide a velvet-rope migration to our library. 

See `docs/MIGRATION.md` for exact mapping (e.g., `set_mode` integer mapping, exception handling) to prove that swapping the `franklinwh` dependency for `franklinwh-cloud` takes less than 10 minutes of refactoring.

---

## 3. Library Citizenship Rules

To ensure we remain respectful citizens and avoid fragmenting the community negatively:

1. **Namespace Isolation**: We publish strictly as `franklinwh-cloud` to avoid naming collisions with their `franklinwh` PyPI package.
2. **Honest Attribution**: Our `README.md` permanently acknowledges `richo/franklinwh-python` as the genesis of this project.
3. **No Badmouthing**: We never position our fork as "better" or frame the upstream repo as "abandoned." We position it simply as "an advanced, feature-heavy alternative."
4. **Issue Triage Assistance**: If we see users struggling in the upstream issues with problems we have already solved (e.g., the Null TOU ID deployment crash), we politely offer the solution/code-snippet there, rather than just telling them to switch libraries.
