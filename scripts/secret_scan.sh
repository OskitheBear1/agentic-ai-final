#!/bin/sh
# Blocks commits that contain API keys or a tracked .env file.
# Installed as .git/hooks/pre-commit by scripts/install_hooks.sh.
set -e
if git diff --cached --name-only | grep -E '(^|/)\.env($|\.)' | grep -v '\.env\.example$' >/dev/null; then
  echo "BLOCKED: a .env file is staged. Run: git rm --cached <file>"; exit 1
fi
PATTERN='sk-ant-[A-Za-z0-9_-]{10,}|sk-[A-Za-z0-9]{32,}|eyJhbGciOi[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}|postgres(ql)?://[^:@/ ]+:[^@/ ]{6,}@'
if git diff --cached -U0 | grep '^+' | grep -E "$PATTERN" >/dev/null; then
  echo "BLOCKED: staged changes look like they contain a secret (API key, JWT or DB password)."; exit 1
fi
# Also block the literal value of any key in the local .env
if [ -f .env ]; then
  STAGED=$(git diff --cached -U0 | grep '^+' || true)
  for v in $(grep -E '^[A-Z_]+=.{8,}' .env | cut -d= -f2-); do
    if printf '%s' "$STAGED" | grep -F -- "$v" >/dev/null; then echo "BLOCKED: a value from .env is staged."; exit 1; fi
  done
fi
exit 0
