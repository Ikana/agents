#!/usr/bin/env bash
set -euo pipefail

# agents setup — install PR automation agents into your project
#
# Usage:
#   /path/to/agents/setup.sh          # run from your project root
#   /path/to/agents/setup.sh --dry-run # preview what would be done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRY_RUN=false

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    *) echo "Unknown argument: $arg"; exit 1 ;;
  esac
done

info()  { echo "  ✓ $*"; }
skip()  { echo "  · $* (already exists, skipping)"; }
run()   { if $DRY_RUN; then echo "  → would: $*"; else "$@"; fi; }

echo "🤖 agents setup"
echo "━━━━━━━━━━━━━━━"
echo ""

# ── Step 1: Check prerequisites ─────────────────────────────────
echo "Checking prerequisites..."

if ! command -v gh &>/dev/null; then
  echo "  ✗ gh (GitHub CLI) not found. Install: https://cli.github.com/"
  exit 1
fi
info "gh found"

if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
  echo "  ✗ Python not found. Install Python 3.10+"
  exit 1
fi
PYTHON=$(command -v python3 || command -v python)
info "python found ($PYTHON)"

echo ""

# ── Step 2: Download upstream skills ─────────────────────────────
echo "Downloading upstream skills..."

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

# gh-address-comments (ComposioHQ/awesome-codex-skills)
if [ ! -d "agents/gh-address-comments" ]; then
  run mkdir -p agents/gh-address-comments/scripts
  if ! $DRY_RUN; then
    curl -sL "https://raw.githubusercontent.com/ComposioHQ/awesome-codex-skills/master/gh-address-comments/SKILL.md" \
      -o "$TMPDIR/gh-address-comments-SKILL.md"
    curl -sL "https://raw.githubusercontent.com/ComposioHQ/awesome-codex-skills/master/gh-address-comments/scripts/fetch_comments.py" \
      -o agents/gh-address-comments/scripts/fetch_comments.py
  fi
  info "gh-address-comments downloaded"
else
  skip "agents/gh-address-comments"
fi

# gh-fix-ci (ComposioHQ/awesome-codex-skills)
if [ ! -d "agents/gh-fix-ci" ]; then
  run mkdir -p agents/gh-fix-ci/scripts
  if ! $DRY_RUN; then
    curl -sL "https://raw.githubusercontent.com/ComposioHQ/awesome-codex-skills/master/gh-fix-ci/SKILL.md" \
      -o "$TMPDIR/gh-fix-ci-SKILL.md"
    curl -sL "https://raw.githubusercontent.com/ComposioHQ/awesome-codex-skills/master/gh-fix-ci/scripts/inspect_pr_checks.py" \
      -o "$TMPDIR/gh-fix-ci-inspect_pr_checks.py"
  fi
  info "gh-fix-ci downloaded"
else
  skip "agents/gh-fix-ci"
fi

# iterate-pr (getsentry/skills)
if [ ! -d "agents/iterate-pr" ]; then
  run mkdir -p agents/iterate-pr/scripts
  if ! $DRY_RUN; then
    curl -sL "https://raw.githubusercontent.com/getsentry/skills/main/plugins/sentry-skills/skills/iterate-pr/SKILL.md" \
      -o "$TMPDIR/iterate-pr-SKILL.md"
    curl -sL "https://raw.githubusercontent.com/getsentry/skills/main/plugins/sentry-skills/skills/iterate-pr/scripts/fetch_pr_checks.py" \
      -o agents/iterate-pr/scripts/fetch_pr_checks.py
    curl -sL "https://raw.githubusercontent.com/getsentry/skills/main/plugins/sentry-skills/skills/iterate-pr/scripts/fetch_pr_feedback.py" \
      -o agents/iterate-pr/scripts/fetch_pr_feedback.py
  fi
  info "iterate-pr downloaded"
else
  skip "agents/iterate-pr"
fi

echo ""

# ── Step 3: Apply modifications ─────────────────────────────────
echo "Applying modifications to make skills portable..."

if ! $DRY_RUN; then

  # ── gh-address-comments: fix script path ──
  if [ -f "$TMPDIR/gh-address-comments-SKILL.md" ]; then
    sed 's|Run scripts/fetch_comments.py|Run `python agents/gh-address-comments/scripts/fetch_comments.py`|' \
      "$TMPDIR/gh-address-comments-SKILL.md" > agents/gh-address-comments/SKILL.md
    info "gh-address-comments SKILL.md patched"
  fi

  # ── gh-fix-ci: remove sandbox escalation, fix paths, soften plan dependency ──
  if [ -f "$TMPDIR/gh-fix-ci-SKILL.md" ]; then
    sed \
      -e 's|name: gh-fix-ci|name: "gh-fix-ci"|' \
      -e 's|description: Inspect GitHub PR checks.*|description: "Use when a user asks to debug or fix failing GitHub PR checks that run in GitHub Actions; use `gh` to inspect checks and logs, summarize failure context, draft a fix plan, and implement only after explicit approval. Treat external providers (for example Buildkite) as out of scope and report only the details URL."|' \
      -e '/^metadata:/d' \
      -e '/^  short-description:/d' \
      -e 's|^- Depends on the `plan` skill.*|- If a plan-oriented skill (for example `create-plan`) is available, use it; otherwise draft a concise plan inline and request approval before implementing.|' \
      -e 's|Prereq: ensure `gh` is authenticated.*|Prereq: authenticate with the standard GitHub CLI once (for example, run `gh auth login`), then confirm with `gh auth status` (repo + workflow scopes are typically required).|' \
      -e 's|   - Run `gh auth status` in the repo with escalated.*|   - Run `gh auth status` in the repo.|' \
      -e 's|   - If sandboxed auth status fails.*|   - If unauthenticated, ask the user to run `gh auth login` (ensuring repo + workflow scopes) before proceeding.|' \
      -e '/   - If unauthenticated, ask the user to log in/d' \
      -e "s|python \"<path-to-skill>/scripts/inspect_pr_checks.py\"|python agents/gh-fix-ci/scripts/inspect_pr_checks.py|g" \
      -e 's|Use the `plan` skill to draft|Use the `create-plan` skill to draft|' \
      "$TMPDIR/gh-fix-ci-SKILL.md" > agents/gh-fix-ci/SKILL.md
    info "gh-fix-ci SKILL.md patched"
  fi

  # gh-fix-ci: add shutil.which guard to inspect_pr_checks.py
  if [ -f "$TMPDIR/gh-fix-ci-inspect_pr_checks.py" ]; then
    # Add 'from shutil import which' import and gh check
    sed '/^import sys/a\
from shutil import which' "$TMPDIR/gh-fix-ci-inspect_pr_checks.py" > "$TMPDIR/gh-fix-ci-patched.py"

    # Add the which("gh") guard inside the main auth check function
    python3 -c "
import re
with open('$TMPDIR/gh-fix-ci-patched.py', 'r') as f:
    content = f.read()
# Find the verify_gh_auth or equivalent function and add which check
# The guard goes right after the function def that checks gh auth
content = content.replace(
    '    if which(\"gh\") is None:',
    '    if which(\"gh\") is None:',
)
# If the guard doesn't exist yet, we need to add it
if 'which(\"gh\")' not in content:
    # Find the function that runs gh auth status and add guard before it
    content = content.replace(
        '    result = subprocess.run(',
        '    if which(\"gh\") is None:\n        print(\"Error: gh is not installed or not on PATH.\", file=sys.stderr)\n        return False\n    result = subprocess.run(',
        1  # only first occurrence
    )
with open('agents/gh-fix-ci/scripts/inspect_pr_checks.py', 'w') as f:
    f.write(content)
" 2>/dev/null || cp "$TMPDIR/gh-fix-ci-patched.py" agents/gh-fix-ci/scripts/inspect_pr_checks.py
    info "gh-fix-ci inspect_pr_checks.py patched"
  fi

  # ── iterate-pr: full rewrite from template ──
  # The iterate-pr SKILL.md has extensive modifications (Copilot review, thread resolution,
  # removed uv/reply_to_thread.py deps). We generate it from the known-good modified version.
  if [ -f "$TMPDIR/iterate-pr-SKILL.md" ]; then
    cp "$SCRIPT_DIR/patches/iterate-pr-SKILL.md" agents/iterate-pr/SKILL.md
    info "iterate-pr SKILL.md replaced with modified version"
  fi

fi

echo ""

# ── Step 4: Copy Claude commands ─────────────────────────────────
echo "Installing Claude commands..."

run mkdir -p .claude/commands

for cmd in address-comments fix-ci iterate-pr; do
  if [ ! -f ".claude/commands/${cmd}.md" ]; then
    run cp "$SCRIPT_DIR/.claude/commands/${cmd}.md" ".claude/commands/${cmd}.md"
    info "/$(echo $cmd) command installed"
  else
    skip ".claude/commands/${cmd}.md"
  fi
done

echo ""

# ── Step 5: Copy Copilot review config ───────────────────────────
echo "Installing Copilot review configuration..."

run mkdir -p .github

if [ ! -f ".github/copilot-reviews.yml" ]; then
  run cp "$SCRIPT_DIR/.github/copilot-reviews.yml" ".github/copilot-reviews.yml"
  info "copilot-reviews.yml installed (auto-review after CI passes)"
else
  skip ".github/copilot-reviews.yml"
fi

if [ ! -f ".github/copilot-instructions.md" ]; then
  run cp "$SCRIPT_DIR/.github/copilot-instructions.md" ".github/copilot-instructions.md"
  info "copilot-instructions.md installed (LOGAF priority tagging)"
else
  skip ".github/copilot-instructions.md"
fi

echo ""

# ── Done ─────────────────────────────────────────────────────────
echo "━━━━━━━━━━━━━━━"
echo "✅ Done!"
echo ""
echo "Next steps:"
echo "  1. If you haven't already: specify init --here --ai claude --ai-skills"
echo "  2. Launch Claude Code in your project"
echo "  3. Available commands: /address-comments  /fix-ci  /iterate-pr"
echo "     Plus all /speckit.* commands from spec-kit"
