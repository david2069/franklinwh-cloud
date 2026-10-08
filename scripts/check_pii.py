import os
import re
import sys
import argparse
import subprocess


def load_personal_terms(repo_root):
    """Return ([(label, compiled_regex)], allow_set) from env PII_TERMS, .pii_terms or ~/.config/pii_terms.

    "allow:<value>" lines are exact values (e.g. MAC addresses) that are already
    published and should not fail the scan. They live outside git like the terms.
    """
    text = os.environ.get("PII_TERMS")
    if not text:
        for path in (os.path.join(repo_root, ".pii_terms"),
                     os.path.expanduser("~/.config/pii_terms")):
            if os.path.isfile(path):
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
                break
    terms, allow = [], set()
    for n, raw in enumerate((text or "").splitlines(), 1):
        t = raw.strip()
        if not t or t.startswith("#"):
            continue
        if t.startswith("allow:"):
            allow.add(t[6:].strip().upper())
            continue
        if t.startswith("re:"):
            rx = re.compile(t[3:], re.IGNORECASE)
        else:
            rx = re.compile(r"(?<![A-Za-z0-9])" + re.escape(t) + r"(?![A-Za-z0-9])", re.IGNORECASE)
        terms.append((f"personal term #{n}", rx))  # label never echoes the term
    return terms, allow


def main():
    parser = argparse.ArgumentParser(description="PII Redaction Checker")
    parser.add_argument("--scan", action="store_true", help="Scan for PII and exit with error if found")
    args = parser.parse_args()

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    # ── Personal terms: loaded from OUTSIDE git, never written in this file ──
    # Kept outside git so this file never contains them. Sources, first found wins:
    #   1. env PII_TERMS        (CI: a repository secret)
    #   2. <repo>/.pii_terms    (gitignored)
    #   3. ~/.config/pii_terms
    # One term per line. Plain lines match case-insensitively on word boundaries;
    # lines starting "re:" are regular expressions. "#" starts a comment.
    personal_terms, allowed_values = load_personal_terms(repo_root)
    if not personal_terms:
        msg = ("No personal PII terms configured (PII_TERMS / .pii_terms / "
               "~/.config/pii_terms): names, addresses and handles are NOT being checked.")
        if os.environ.get("CI"):
            print(f"ERROR: {msg} Set the PII_TERMS repository secret.")
            sys.exit(2)
        print(f"WARNING: {msg}")

    # Regular expressions for structured PII types
    email_regex = re.compile(r'[\w.-]+@[\w.-]+\.\w+')
    # Home directories name the user. Placeholders and CI runners are fine.
    home_path_regex = re.compile(r'(?:/Users|/home)/(?!<|runner/|user/|you/|username/|\$)[A-Za-z0-9._-]+')
    serial_regex = re.compile(r'100[56][A-Z0-9]{16}')
    mac_regex = re.compile(r'\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b')
    # Placeholder MACs are fine; real ones that are already published are listed
    # as "allow:" lines in the terms source, never here.
    mac_placeholder_prefixes = ("AA:BB:CC:", "DE:AD:BE:", "00:00:00:", "11:22:33:")

    # Allowed emails / version-string false positives
    ignore_emails = [
        "david2069@users.noreply.github.com", "user@example.com", "user@email.com",
        "nobody@example.invalid", "cli@test.com", "ini@test.com", "env@test.com",
        "your@email.com", "john.doe@anymail.com", "installer@company.com",
        "[REDACTED]", "david[redacted]", "franklinwh-cloud.git@v0.3.0",
        "a@b.com", "nobody@doesnotexist.invalid",
    ]
    # Skip software-version strings that look like emails: python@3.14, setuptools@68.0
    version_string_regex = re.compile(r'^[a-z][a-z0-9_-]+@\d+\.\d+', re.IGNORECASE)
    # Skip pip/git URL refs that look like emails: franklinwh-cloud.git@v0.4.10, repo.git@vX.Y.Z
    git_ref_regex = re.compile(r'\.git@v(\d+|x)\.', re.IGNORECASE)

    # ── File list: only scan git-tracked files ─────────────────────────────────
    # This exactly mirrors what GitHub Actions sees after actions/checkout@v4.
    # Gitignored local files (franklinwh.ini, scratch_*.json, etc.) are never
    # committed, so they must never trigger CI failures.
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            capture_output=True, text=True, cwd=repo_root, check=True,
        )
        tracked_files = [
            os.path.join(repo_root, p.strip())
            for p in result.stdout.splitlines()
            if p.strip()
        ]
    except Exception:
        # Fallback if git is unavailable (e.g. Docker without git)
        ignore_dirs = [
            ".git", "node_modules", "venv", ".pytest_cache", ".cursor",
            "__pycache__", "site", ".gemini", "hars", "dist", ".github",
            "franklinwh_cloud.egg-info", "franklinwh_cloud_client.egg-info",
        ]
        tracked_files = []
        for root, dirs, files in os.walk(repo_root):
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            for file in files:
                tracked_files.append(os.path.join(root, file))

    found = 0
    count = 0

    for filepath in tracked_files:
        if not os.path.isfile(filepath):
            continue
        rel = os.path.relpath(filepath, repo_root)
        # Generated files carry absolute paths and machine state; never commit them.
        if re.search(r'(^|/)(\.coverage|\.DS_Store)$|\.pyc$', rel):
            print(f"PII Risk [generated file committed]: {rel}")
            found += 1
            continue
        # Agent scratch artefacts are not shipped
        if "/.gemini/" in filepath or "brain" in filepath:
            continue

        try:
            with open(filepath, 'rb') as fb:
                raw = fb.read()
            if b"\x00" in raw[:8192]:
                continue  # binary
            lines = raw.decode('utf-8').splitlines()
            count += 1

            for i, line in enumerate(lines):
                line_lower = line.lower()

                # ── Personal terms (from outside git) ──────────────────
                for label, rx in personal_terms:
                    if rx.search(line):
                        print(f"PII Leak [{label}]: {rel}:{i+1}")
                        found += 1

                # ── Home directory paths ──────────────────────────────────
                for m in home_path_regex.finditer(line):
                    print(f"PII Leak [Home path {m.group(0)}]: {rel}:{i+1}")
                    found += 1

                # ── Email check ───────────────────────────────────────────
                for match in email_regex.finditer(line):
                    email = match.group(0).lower()
                    domain = email.rpartition("@")[2]
                    if email in ignore_emails or domain == "example.com" or domain.endswith(".example.com"):
                        continue
                    if version_string_regex.match(email) or git_ref_regex.search(email):
                        continue
                    print(f"PII Leak [Email {email}]: {rel}:{i+1}")
                    found += 1

                # ── MAC addresses ─────────────────────────────────────────
                for match in mac_regex.finditer(line):
                    mac = match.group(0).upper()
                    if mac.startswith(mac_placeholder_prefixes) or mac in allowed_values:
                        continue
                    print(f"PII Leak [MAC {mac}]: {rel}:{i+1}")
                    found += 1

                # ── Serial numbers ────────────────────────────────────────
                for match in serial_regex.finditer(line):
                    serial = match.group(0)
                    if "X" not in serial.upper() and serial != "10060006A00000000000":
                        print(f"PII Leak [Raw Serial {serial}]: {rel}:{i+1}")
                        found += 1

        except UnicodeDecodeError:
            pass

    # ── Commit metadata: authors of commits not yet pushed ────────────────────
    author_found = 0
    try:
        # Commits not yet on any remote — the ones still cheap to amend.
        rev = subprocess.run(
            # HEAD must be named explicitly: "--not --remotes" alone has no
            # positive ref to walk from and returns nothing.
            ["git", "log", "HEAD", "--format=%H%x1f%an%x1f%ae", "--not", "--remotes"],
            cwd=repo_root, capture_output=True, text=True, timeout=30,
        )
        for line in rev.stdout.splitlines():
            parts = line.split("\x1f")
            if len(parts) != 3:
                continue
            sha, name, email = parts
            ident = f"{name} <{email}>"
            low = ident.lower()
            if any(rx.search(ident) for _, rx in personal_terms):
                print(f"PII Leak [Commit author {ident}]: {sha[:12]} (unpushed)")
                author_found += 1
            elif email_regex.search(email) and email.rpartition("@")[2].lower() != "users.noreply.github.com":
                print(f"PII Leak [Commit email {email}]: {sha[:12]} (unpushed)")
                author_found += 1
        if author_found:
            print("  Fix before pushing:  git commit --amend --reset-author")
            print("  Prevent:  git config --local user.email "
                  "<id>+<user>@users.noreply.github.com")
    except Exception as e:
        print(f"⚠ Could not check commit metadata: {e}")
    found += author_found

    if args.scan:
        print(f"\nScanned {count} files and the unpushed commit authors.")
        if found > 0:
            print(f"❌ FAILED: Found {found} PII leaks.")
            sys.exit(1)
        else:
            print("✅ SUCCESS: No PII leaks found!")
            sys.exit(0)


if __name__ == "__main__":
    main()
