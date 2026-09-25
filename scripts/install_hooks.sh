#!/bin/sh
# Enable the repository's optional commit hooks for this clone and all its worktrees.
# The hooks do nothing unless a scanner is configured: git config whshr.labelScan /path/to/label_scan.py
set -e
cd "$(git rev-parse --show-toplevel)"
chmod +x scripts/hooks/pre-commit scripts/hooks/commit-msg
git config core.hooksPath scripts/hooks
echo "Hooks enabled (core.hooksPath = scripts/hooks)."
