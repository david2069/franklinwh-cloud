import os
import re
import sys
import argparse
import subprocess


def main():
    parser = argparse.ArgumentParser(description="PII Redaction Checker")
    parser.add_argument("--scan", action="store_true", help="Scan for PII and exit with error if found")
    args = parser.parse_args()

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    # Core identifying PII strings (non-standard formats)
    bad_strings = [
        "hona", "david.hona", "roseville", "79a boundary", "2069"
    ]

    # Regular expressions for structured PII types
    email_regex = re.compile(r'[\w.-]+@[\w.-]+\.\w+')
    geo_lat = re.compile(r'-33\.\d{5,}')
    geo_lon = re.compile(r'151\.\d{5,}')
    serial_regex = re.compile(r'100[56][A-Z0-9]{16}')

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
            if p.strip() and p.strip().endswith(('.py', '.md', '.json', '.yml', '.txt', '.sh', '.ini'))
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
                if file.endswith(('.py', '.md', '.json', '.yml', '.txt', '.sh', '.ini')):
                    tracked_files.append(os.path.join(root, file))

    found = 0
    count = 0

    for filepath in tracked_files:
        if not os.path.isfile(filepath):
            continue
        # Skip the scanner itself and brain/agent artefacts
        if "/.gemini/" in filepath or "brain" in filepath or "check_pii.py" in os.path.basename(filepath):
            continue

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            count += 1

            for i, line in enumerate(lines):
                # Skip lines that are local filesystem paths embedded in test output
                stripped = line.strip()
                if stripped.startswith(('/Users/', '/home/', '/runner/work/')):
                    continue

                line_lower = line.lower()

                # ── Generic bad-string check ──────────────────────────────
                for bs in bad_strings:
                    if bs not in line_lower:
                        continue

                    if bs == "2069":
                        if "david2069" in line_lower or "2069-" in line_lower or "-2069" in line_lower:
                            continue

                    if bs == "hona":
                        # Only flag 'hona' when it appears standalone, not embedded in
                        # 'davidhona' filesystem path tokens or the noreply GitHub handle.
                        scrubbed = line_lower.replace("davidhona", "").replace("david2069", "")
                        if "hona" not in scrubbed:
                            continue

                    print(f"PII Leak [{bs}]: {os.path.relpath(filepath, repo_root)}:{i+1}")
                    found += 1

                # ── Email check ───────────────────────────────────────────
                for match in email_regex.finditer(line):
                    email = match.group(0).lower()
                    if email in ignore_emails or "example.com" in email:
                        continue
                    if version_string_regex.match(email):
                        continue
                    print(f"PII Leak [Email {email}]: {os.path.relpath(filepath, repo_root)}:{i+1}")
                    found += 1

                # ── GPS coordinates ───────────────────────────────────────
                if geo_lat.search(line):
                    print(f"PII Leak [Latitude]: {os.path.relpath(filepath, repo_root)}:{i+1}")
                    found += 1
                if geo_lon.search(line):
                    print(f"PII Leak [Longitude]: {os.path.relpath(filepath, repo_root)}:{i+1}")
                    found += 1

                # ── Serial numbers ────────────────────────────────────────
                for match in serial_regex.finditer(line):
                    serial = match.group(0)
                    if "X" not in serial.upper() and serial != "10060006A00000000000":
                        print(f"PII Leak [Raw Serial {serial}]: {os.path.relpath(filepath, repo_root)}:{i+1}")
                        found += 1

        except UnicodeDecodeError:
            pass

    if args.scan:
        print(f"\nScanned {count} files.")
        if found > 0:
            print(f"❌ FAILED: Found {found} PII leaks.")
            sys.exit(1)
        else:
            print("✅ SUCCESS: No PII leaks found!")
            sys.exit(0)


if __name__ == "__main__":
    main()
