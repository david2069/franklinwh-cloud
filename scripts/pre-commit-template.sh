#!/bin/sh

# Pre-commit hook to scan for PII leaks
echo "Running PII Scanner..."

python3 scripts/check_pii.py --scan

if [ $? -ne 0 ]; then
    echo "❌ PII Leak Detected! Commit rejected."
    echo "Please redact the sensitive information and try again."
    exit 1
fi

echo "✅ PII Check Passed."
exit 0
