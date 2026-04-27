---
description: Mid-session crash-safe checkpoint — force-saves agent state and code to disk. Run automatically every ~1 hour and immediately after any implementation plan or major task is created.
---

# Checkpoint — Mid-Session State Save

> **AUTOMATIC TRIGGER POLICY (No user prompt required)**
> Agents MUST run this workflow automatically:
> - Every ~1 hour of active work (check `.agents/.last_checkpoint` to determine elapsed time)
> - Immediately after creating or updating `implementation_plan.md`
> - Immediately after creating or updating `task.md`
> - Immediately after completing any phase of a multi-phase plan
> - Any time the agent is about to start a large, long-running sub-agent task
> - On onboard, if no recent checkpoint is found (see onboard Phase 4)
>
> Do NOT wait for the user to ask. Run silently and report a single summary line.

// turbo-all

## Steps

1. Update `task.md` — mark all currently in-progress (`[/]`) items accurately. If task.md does not yet exist, create it with the current state.

2. Update `implementation_plan.md` — ensure it reflects the current plan, including any new discoveries or scope changes. If no plan exists, write a brief "current intent" section.

3. Append a checkpoint entry to `walkthrough.md`:
```
## Checkpoint — <ISO timestamp>
**Completed:** <list what is done>
**In Progress:** <what is actively being worked on>
**Next:** <what the agent was about to do>
```

4. Stage all modified source files:
```bash
git -C /Users/davidhona/dev/franklinwh-cloud add -A
```

5. Commit with a checkpoint message:
```bash
git -C /Users/davidhona/dev/franklinwh-cloud commit -m "checkpoint: mid-session state save $(date +%Y-%m-%dT%H:%M)" --allow-empty
```

6. Push to origin:
```bash
git -C /Users/davidhona/dev/franklinwh-cloud push
```

7. **Write the checkpoint ledger record** — this is how the next agent (or next onboard) knows a checkpoint was taken and when:
```bash
echo "timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ) conversation=$CONVERSATION_ID steps=estimated" > /Users/davidhona/dev/franklinwh-cloud/.agents/.last_checkpoint
```
> If `$CONVERSATION_ID` is not available as an env var, use the conversation ID from the artifact directory path or write `unknown`. The file format is a simple key=value flat file.

8. Confirm commit and report to user in a single line:
> `✅ Checkpoint saved — <N> files committed, task.md + implementation_plan.md up to date. Next: <what you are doing>.`

---

## Context Size Warning

At every checkpoint (and on onboard), the agent MUST estimate conversation size and warn if at risk:

| Step count (estimated) | Action |
|------------------------|--------|
| < 150 steps | Normal — no warning needed |
| 150–220 steps | ⚠️ Warn user: *"Conversation is getting large (~N steps). Checkpointing frequently. Consider starting a fresh session after this task to avoid context overflow."* |
| > 220 steps | 🚨 Alert user: *"Conversation is critically large (~N steps) and is at risk of context window overflow. Strongly recommend starting a new session after completing the current task. All state has been committed to disk."* |

To estimate step count: check the highest numbered directory in `.system_generated/steps/` for this conversation. Each agent turn is approximately 1–3 steps.
