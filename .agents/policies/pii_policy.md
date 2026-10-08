# AP-3: PII & Sensitive Data Policy

> Prevents personally identifiable information from being committed to public repositories.

## Absolute Rules — No Exceptions

Nothing tracked by git — **files, commit messages, commit author fields, tag messages,
PR descriptions, release notes, issue comments** — may contain:

| Category | Use instead |
|----------|-------------|
| Real email addresses | `user@example.com` |
| Real names | Role labels: "Owner", "User", "the maintainer" |
| **Home-directory paths** (`/Users/<name>/…`, `/home/<name>/…`) | `~/…` or `/Users/<username>/…` |
| Physical addresses, suburbs, GPS coordinates | Nothing. Never include them |
| Real hardware serial numbers | `<agate_serial>`, `10060006AXXXXXXXXX` |
| Real site / user / account IDs | `1234`, `<site_id>`, `12345`, `<user_id>` |
| API tokens, passwords, credentials | `<api_token>`, `***`. Never log, document or hard-code |
| Generated files (`.coverage`, `*.pyc`, `.DS_Store`) | Never commit. They embed absolute paths |

**Never write a real personal value into the repo as an example of what to avoid.**
That includes comments, test fixtures, policy docs, and the scanner itself.

## The Scanner — `scripts/check_pii.py`

The scanner covers every tracked text file, its own source included, and the authors
of unpushed commits. Personal terms (names, handles, address fragments) are **never
in the repo**. They're loaded from, first found wins:

1. env `PII_TERMS`: in CI, the `PII_TERMS` repository secret
2. `<repo>/.pii_terms` (gitignored)
3. `~/.config/pii_terms`: one local file shared by every repo

One term per line. Plain lines match case-insensitively on word boundaries, and `re:` lines
are regular expressions. In CI the scanner **fails** if no terms are configured, so it can't
pass silently. Output labels terms by line number and never prints the term.

### Enforcement points

| When | What runs |
|---|---|
| Before every push | `scripts/hooks/pre-push`, enabled once per clone with `git config core.hooksPath scripts/hooks` |
| Every push and PR | `.github/workflows/pii-check.yml` |
| Before any commit an agent makes | `python3 scripts/check_pii.py --scan`, which must pass |

## Agent Enforcement Rules

1. **Before writing any doc, code, test fixture or commit message**, check it for real
   names, emails, paths, serials, IDs and addresses taken from screenshots, CLI output,
   API responses or tool results.
2. **Never copy raw CLI/API/test output into tracked files verbatim.** Redact first. For
   saved pytest output: `sed "s#$HOME#~#g"`.
3. **Commit identity.** Every commit must be authored as
   `david2069 <david2069@users.noreply.github.com>`. Check `git config user.email`
   before the first commit in any clone.
4. **Commit messages and PR bodies are public.** Apply rule 1 to them too, including when
   cherry-picking: a copied message carries the original's content.
5. **Don't add skips to the scanner** (files, line prefixes, extensions) without user
   approval. Each skip is a blind spot.
6. **If PII is found in a pushed commit**, stop other work, tell the user, and follow
   the procedure below. A fix commit alone leaves it in the history.

## Removing PII From Published History

A fix commit removes PII from the current files only. To remove it from the repo:

1. Work in a fresh `git clone --mirror`, never in the user's working copy.
2. `git filter-repo --replace-text <rules> --replace-message <rules> --mailmap <map>`.
   Also use `--path-glob … --invert-paths` for generated files. Keep the rules file
   **outside** the repo.
3. Scan every object (blobs, commits, tags, author fields) in the rewritten mirror. Then
   run the offline test suite on each branch tip and confirm the counts haven't changed.
4. Force-push `refs/heads/*` and `refs/tags/*`. If `main` is protected, save the protection
   settings, allow force-pushes, push, and restore them, then check they're identical.
5. Re-clone and re-scan from GitHub. Repoint local branches through
   `filter-repo/commit-map`, after checking for unpushed local commits.
6. Open replacement PRs: GitHub closes open PRs whose base history changed.
7. Ask GitHub Support to purge cached views and `refs/pull/*`, which keep the old commits
   reachable by SHA. For credentials, rotate them first.
