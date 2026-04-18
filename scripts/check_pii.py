import os
import re
import sys
import argparse

def main():
    parser = argparse.ArgumentParser(description="PII Redaction Checker")
    parser.add_argument("--scan", action="store_true", help="Scan for PII and exit with error if found")
    args = parser.parse_args()

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    
    # Core identifying PII strings to catch that are not standard formats
    bad_strings = [
        "hona", "david.hona", "roseville", "79a boundary", "2069"
    ]
    
    # Regular expressions for data types
    email_regex = re.compile(r'[\w.-]+@[\w.-]+\.\w+')
    geo_lat = re.compile(r'-33\.\d{5,}')
    geo_lon = re.compile(r'151\.\d{5,}')
    serial_regex = re.compile(r'100[56][A-Z0-9]{16}')
    
    # Safe lists
    ignore_emails = ["david2069@users.noreply.github.com", "user@example.com", "user@email.com", "nobody@example.invalid", "cli@test.com", "ini@test.com", "env@test.com", "your@email.com", "john.doe@anymail.com", "installer@company.com", "[REDACTED]", "david[redacted]", "franklinwh-cloud.git@v0.3.0", "a@b.com", "nobody@doesnotexist.invalid"]
    # Pattern: skip false-positive version strings like python@3.14, setuptools@68.0
    version_string_regex = re.compile(r'^[a-z][a-z0-9_-]+@\d+\.\d+', re.IGNORECASE)
    ignore_dirs = [".git", "node_modules", "venv", ".pytest_cache", ".cursor", "__pycache__", "site", ".gemini", "hars", "dist", ".github", "franklinwh_cloud.egg-info", "franklinwh_cloud_client.egg-info"]
    
    found = 0
    count = 0
    
    for root, dirs, files in os.walk(repo_root):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        for file in files:
            filepath = os.path.join(root, file)
            if file.endswith(('.py', '.md', '.json', '.yml', '.txt', '.sh', '.ini')):
                # skip external brain/agent files
                if "/.gemini/" in filepath or "brain" in filepath or "check_pii.py" in file:
                    continue
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        for i, line in enumerate(lines):
                            line_lower = line.lower()
                            
                            # Check generic bad strings
                            for bs in bad_strings:
                                if bs in line_lower:
                                    if bs == "2069" and ("david2069" in line_lower or "2069-" in line_lower or "-2069" in line_lower):
                                        continue
                                    if bs == "hona" and ("davidhona" in line_lower or "david2069" in line_lower):
                                        if not ("hona" in line_lower.replace("davidhona", "")):
                                            continue
                                            
                                    print(f"PII Leak [{bs}]: {os.path.relpath(filepath, repo_root)}:{i+1}")
                                    found += 1
                                    
                            # Check emails
                            for match in email_regex.finditer(line):
                                email = match.group(0).lower()
                                if email in ignore_emails or "example.com" in email:
                                    continue
                                # Skip software version strings: python@3.14, setuptools@68.0 etc.
                                if version_string_regex.match(email):
                                    continue
                                print(f"PII Leak [Email {email}]: {os.path.relpath(filepath, repo_root)}:{i+1}")
                                found += 1
                                    
                            # Check coordinates
                            if geo_lat.search(line):
                                print(f"PII Leak [Latitude]: {os.path.relpath(filepath, repo_root)}:{i+1}")
                                found += 1
                            if geo_lon.search(line):
                                print(f"PII Leak [Longitude]: {os.path.relpath(filepath, repo_root)}:{i+1}")
                                found += 1
                            
                            # Check serial numbers
                            for match in serial_regex.finditer(line):
                                serial = match.group(0)
                                if "X" not in serial.upper() and serial != "10060006A00000000000":
                                    print(f"PII Leak [Raw Serial {serial}]: {os.path.relpath(filepath, repo_root)}:{i+1}")
                                    found += 1
                                                
                except UnicodeDecodeError:
                    pass
                count += 1
                    
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
