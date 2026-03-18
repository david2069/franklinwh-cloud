---
description: End-of-session push — commit any uncommitted changes and push to GitHub
---

## End-of-Session Push

Run this at the end of every working session to ensure all changes are backed up to GitHub.

// turbo-all

1. Check for uncommitted changes:
```bash
git -C /Users/davidhona/dev/franklinwh-cloud status --short
```

2. If there are changes, stage and commit them:
```bash
git -C /Users/davidhona/dev/franklinwh-cloud add -A && git -C /Users/davidhona/dev/franklinwh-cloud commit -m "Session checkpoint: $(date +%Y-%m-%d)"
```

3. Push to GitHub:
```bash
git -C /Users/davidhona/dev/franklinwh-cloud push
```

4. Confirm the push succeeded:
```bash
git -C /Users/davidhona/dev/franklinwh-cloud log --oneline -3
```
