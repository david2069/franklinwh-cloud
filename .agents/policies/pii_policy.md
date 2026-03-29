# AP-3: PII & Sensitive Data Policy

> Prevents personally identifiable information from being committed to public repositories.

## Absolute Rules — No Exceptions

Any content written to files in `docs/`, `src/`, `tests/`, or any other tracked directory
**must never contain**:

| Category | Examples |
|----------|---------|
| Real email addresses | `owner@example.com` → use `user@example.com` |
| Real hardware serial numbers | Use `<agate_serial>`, `XXXXXXXX`, or fictional serials |
| Real site IDs | Use `1234` or `<site_id>` — never real Cloud API site IDs |
| Real user/account IDs | Use `12345` or `<user_id>` |
| Real names | Use generic role labels: "Owner", "User", "Admin" |
| Physical addresses | Never include street addresses in docs or code |
| API tokens / passwords | Use `<api_token>` or `***` |
| Cloud account credentials | Never log, document, or hardcode |

## Redaction Standards for Documentation

When writing examples in Markdown docs, use these placeholder conventions:

```
Serial numbers:   XXXXXXXX  or  <agate_serial>  or  <apower_serial>
Email:            user@example.com
User ID:          12345
Site ID:          1234
Site Name:        My Home  (generic, not owner's real address)
Gateway Name:     My Gateway  (generic)
```

## Agent Enforcement Rules

1. **Before writing any doc or code example**: scan for real serials, emails, IDs, and addresses
   sourced from user-provided screenshots, CLI outputs, or API responses.
2. **Never copy raw CLI/API output into docs verbatim** — always redact first.
3. **Before committing**: run a PII check across all staged `docs/` files.
4. **If PII is discovered in a previously committed file**: fix immediately, commit the fix,
   and notify the user. Do NOT proceed with other work until the fix is pushed.

## Pre-Commit PII Check Command

Run before every commit touching `docs/`:

```bash
grep -rn --include="*.md" \
  -E "[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}" \
  docs/ && echo "WARNING: email found" || echo "OK: no emails"
```

## Git History

If PII is committed and pushed to a public repo, standard `git commit --amend` or a new
fix commit is acceptable for documentation-only PII (not credentials). For credential leaks,
treat as a security incident and rotate immediately.
