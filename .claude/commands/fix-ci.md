---
description: Debug and fix failing GitHub Actions CI checks on the current PR
---

Read and follow the instructions in `agents/gh-fix-ci/SKILL.md`.

When running scripts, use paths relative to the project root:
- `python agents/gh-fix-ci/scripts/inspect_pr_checks.py --repo "." --pr "<number>"`
- Add `--json` for machine-friendly output.
