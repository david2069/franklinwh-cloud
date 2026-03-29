# AP-1: Change Management Policy

> Modelled on FEM's AP-12. Prevents cascading defects from reactive break-fix cycles.

## Core Rule: Queue → Plan → Execute

**Never react to a new issue by immediately writing code.**

```
1. QUEUE  — log the issue/request
2. PLAN   — describe what will change and why
3. EXECUTE — make the change, verify, commit
```

## Agent Enforcement

| Situation | Required Action |
|-----------|-----------------|
| User reports issue during active fix | "Noted — queuing for after current fix." Do NOT switch context. |
| Multiple issues reported at once | Triage and sequence. Fix one completely before the next. |
| Fix introduces a new error | Stop — this is now the current task. Fix before continuing. |
| User proposes immediate ad-hoc fix | *"AP-1 reminder — should I queue this for the next planned batch?"* |

## Verification Cycle (Non-Negotiable)

Every backend change must complete this cycle before the next change starts:

```
1. Make change
2. Restart app / run affected service
3. Check logs (zero new errors)
4. Run tests: python -m pytest tests/ -v --tb=short
5. Verify affected endpoint/entity
6. Commit
```

## Commit Discipline

- Commit after every phase or meaningful sub-step
- Commit message format: `feat(phase-N): description` or `fix: description` or `chore: description`
- Never leave a phase uncommitted
- Include test results file reference in commit when tests run
