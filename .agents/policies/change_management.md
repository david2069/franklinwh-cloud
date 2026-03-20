# Change Management Policy — AP-12

*Effective: 2026-03-20*

> **Purpose:** Prevent cascading defects from reactive break-fix cycles. All changes follow a queue → group → plan → execute model. The agent MUST enforce this policy and flag violations — including by the user.

---

## 1. The Rules

### 1.1 No Reactive Fixes
- **NEVER** fix a defect the moment it's reported unless it is a **Severity 1 blocker**
- All defects and feature requests are **queued first**, never acted on immediately
- If the user says "fix this now!" the agent MUST respond:
  > *"Queued as [ID]. Per AP-12, I'll group this with related items for the next planned batch. Is this a Severity 1 blocker that prevents all work?"*

### 1.2 Severity Classification

| Severity | Definition | Response |
|----------|-----------|----------|
| **S1 — Blocker** | System down, data loss, security vulnerability, cannot proceed | Fix immediately (with test plan) |
| **S2 — High** | Feature broken but workaround exists, or non-critical path | Queue → next planned batch |
| **S3 — Medium** | Cosmetic, UX improvement, non-functional | Queue → group by area |
| **S4 — Low** | Nice-to-have, future feature, cleanup | Queue → backlog review |

### 1.3 Queue → Group → Plan → Execute

```
Report → Queue (defect_list.md) → Periodic Triage → Group by Area → Plan → Execute → Verify
         ↑                                                                              |
         └──── New defects found during Verify ────────────────────────────────────────┘
```

**Grouping areas** for this repository:

| Area | Scope |
|------|-------|
| CLI Commands | `cli.py`, `cli_commands/*.py`, `cli_output.py` |
| Client / API Core | `client.py`, `api.py`, `endpoints.py` |
| Mixins | `mixins/*.py` (modes, stats, tou, power, devices, account, storm) |
| Constants | `const/*.py` (modes, tou, devices, test_fixtures) |
| Models / Exceptions | `models.py`, `exceptions.py` |
| Tests | `tests/*.py`, `tests/fixtures/*` |
| Docs / Agent Config | `docs/`, `.agents/`, `CHANGELOG.md`, `API_CLIENT_GUIDE.md` |

### 1.4 Batch Execution Rules
- Each batch has a **written plan** before any code changes
- Each batch gets **one test run** at the end (not per-fix)
- If a fix in the batch causes a test failure, the **entire batch** is reviewed
- Version bump happens **once per batch**, not per-fix

### 1.5 No Untested Fixes
- Every fix must have a verification step *before* commit
- "It compiles" is not verification
- Regression risk must be stated: *"This change touches X, which could affect Y"*

---

## 2. Agent Enforcement

The agent MUST:

1. **Queue all requests** — add to `defect_list.md` before acting
2. **Flag violations** — if user or agent attempts a reactive fix:
   > ⚠️ **AP-12 Reminder:** This looks like a reactive fix. Should I queue it for the next planned batch instead? If this is a Severity 1 blocker, please confirm.
3. **Propose batches** — periodically suggest: *"We have N queued items in [area]. Ready to plan a batch?"*
4. **Refuse cascading fixes** — if a fix causes a new defect, STOP. Queue the new defect. Do not chain fixes.
5. **State regression risk** — before every change: *"Regression risk: [low/medium/high] — touches [components]"*

### 2.1 User Violation Response

If the user requests an immediate fix for a non-S1 issue, the agent responds:

> *"I've queued this as [DEF-XXX]. Per AP-12, I recommend grouping it with [N] other [area] items for a planned batch. Want me to plan that batch now, or is this a Severity 1 blocker?"*

---

## 3. Triage Cadence

- **Start of session:** Review queue, propose batch if ≥3 items in one area
- **End of session:** Update `defect_list.md` with any new items discovered
- **Before any commit:** Verify no open S1 blockers
- **After cascade detection:** Full queue review

---

## 4. Exceptions

The only exception to queue-first is **Severity 1**:
- CLI tool is completely non-functional
- API client crashes on all calls
- Security vulnerability actively exploited
- Cannot proceed with ANY development work

Even S1 fixes get a brief plan statement before execution.
