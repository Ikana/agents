# agents

Bootstrap any project with spec-driven development and GitHub PR automation for AI coding agents.

This repo wires together three upstream skill sources and documents the modifications needed to make them work seamlessly with Claude Code (or any coding agent) without Codex-specific tooling or Sentry-specific infrastructure.

## What's Included

### 1. Spec-Driven Development — [github/spec-kit](https://github.com/github/spec-kit)

A structured workflow for going from idea → spec → plan → tasks → implementation:

| Command | Purpose |
|---------|---------|
| `/speckit.constitution` | Set project principles and quality gates |
| `/speckit.specify` | Create feature specs from natural language |
| `/speckit.clarify` | Resolve ambiguities in specs (≤5 targeted questions) |
| `/speckit.plan` | Generate technical implementation plans |
| `/speckit.tasks` | Break plans into ordered, dependency-aware task lists |
| `/speckit.checklist` | Generate "unit tests for English" — validate requirements quality |
| `/speckit.analyze` | Cross-artifact consistency analysis |
| `/speckit.implement` | Execute all tasks phase by phase |
| `/speckit.taskstoissues` | Convert tasks to GitHub Issues |

### 2. GitHub PR Agents

| Agent | Source | Purpose |
|-------|--------|---------|
| `gh-address-comments` | [ComposioHQ/awesome-codex-skills](https://github.com/ComposioHQ/awesome-codex-skills/tree/master/gh-address-comments) | Address PR review comments interactively |
| `gh-fix-ci` | [ComposioHQ/awesome-codex-skills](https://github.com/ComposioHQ/awesome-codex-skills/tree/master/gh-fix-ci) | Debug and fix failing CI checks |
| `iterate-pr` | [getsentry/skills](https://github.com/getsentry/skills/tree/main/plugins/sentry-skills/skills/iterate-pr) | Full feedback-fix-push cycle until CI is green |

### 3. Copilot Review Configuration

Two files in `.github/` make the `iterate-pr` workflow fully automated:

- **`copilot-reviews.yml`** — enables automatic Copilot code review on PRs (triggers after CI passes)
- **`copilot-instructions.md`** — tells Copilot to tag every review comment with [LOGAF priority markers](https://develop.sentry.dev/engineering-practices/code-review/#logaf-scale) (`h:`, `m:`, `l:`) so `fetch_pr_feedback.py` can categorize them automatically

Without these files, `iterate-pr` still works but Copilot comments won't have priority tags — the script falls back to heuristic classification (keyword matching on "blocker", "nit", etc.).

## Quick Setup

### Prerequisites

- [GitHub CLI](https://cli.github.com/) (`gh`) — authenticated
- [uv](https://docs.astral.sh/uv/getting-started/installation/) — Python package runner
- Python 3.10+

### 1. Install spec-kit

```bash
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git
```

### 2. Initialize your project

```bash
cd your-project
specify init --here --ai claude --ai-skills
```

This creates `.specify/` (templates, scripts, constitution) and `.claude/` (commands + skills) for the full speckit workflow.

### 3. Install PR agents

From your project root:

```bash
# Clone this repo somewhere convenient
git clone https://github.com/Ikana/agents.git /tmp/agents-bootstrap

# Run the setup script
/tmp/agents-bootstrap/setup.sh
```

Or manually:

```bash
# 0. Copy Copilot review config
mkdir -p .github
cp /tmp/agents-bootstrap/.github/copilot-reviews.yml .github/
cp /tmp/agents-bootstrap/.github/copilot-instructions.md .github/

# 1. Download upstream skills
mkdir -p agents
# gh-address-comments
git archive --remote=https://github.com/ComposioHQ/awesome-codex-skills.git HEAD gh-address-comments | tar -x -C agents/
# gh-fix-ci
git archive --remote=https://github.com/ComposioHQ/awesome-codex-skills.git HEAD gh-fix-ci | tar -x -C agents/
# iterate-pr
git archive --remote=https://github.com/getsentry/skills.git HEAD plugins/sentry-skills/skills/iterate-pr | tar -x --strip-components=4 -C agents/

# 2. Apply modifications (see "Modifications" section below)

# 3. Copy the Claude commands
cp /tmp/agents-bootstrap/.claude/commands/address-comments.md .claude/commands/
cp /tmp/agents-bootstrap/.claude/commands/fix-ci.md .claude/commands/
cp /tmp/agents-bootstrap/.claude/commands/iterate-pr.md .claude/commands/
```

## Modifications from Upstream

The upstream skills assume Codex (OpenAI) or Sentry-specific infrastructure. These modifications make them portable:

### gh-address-comments (from ComposioHQ)

**Minimal change** — only script path:

- `scripts/fetch_comments.py` → `python agents/gh-address-comments/scripts/fetch_comments.py`

### gh-fix-ci (from ComposioHQ)

1. **Remove Codex sandbox escalation** — replace `sandbox_permissions=require_escalated` references with standard `gh auth status`
2. **Portable script paths** — replace `<path-to-skill>/scripts/` with `agents/gh-fix-ci/scripts/`
3. **Remove hard dependency on `plan` skill** — change to: *"If a plan-oriented skill (for example `create-plan`) is available, use it; otherwise draft a concise plan inline and request approval before implementing."*
4. **Add `gh` existence check** — the `inspect_pr_checks.py` script gains a `shutil.which("gh")` guard at the top

### iterate-pr (from getsentry)

The most significant modifications — adds Copilot review automation and removes `uv`/`reply_to_thread.py` dependencies:

1. **Add Copilot review steps** (new steps 2-3):
   - Request review via `gh copilot-review <pr-number>`
   - Poll with exponential backoff (`120s → 240s → 300s`) checking `copilot-pull-request-reviewer` on latest HEAD
   - Fallback: retry once, then proceed without Copilot review

2. **Add step 10: Close addressed review threads** — resolve threads via `gh api graphql` mutation after fixes are committed

3. **Remove `uv` requirement** — replace `uv run ${CLAUDE_SKILL_ROOT}/scripts/...` with `python agents/iterate-pr/scripts/...`

4. **Remove `reply_to_thread.py` dependency** — replace batched script calls with inline `addPullRequestReviewThreadReply` GraphQL mutation via `gh api`

5. **Add Copilot to review bot list** — append `Copilot` to the recognized review bots alongside Sentry, Warden, Cursor, etc.

6. **Update exit conditions** — success requires Copilot review complete on latest HEAD (with fallback note for older `gh` versions)

7. **Step renumbering** — original 8 steps become 11 to accommodate Copilot review insertion and thread resolution

## Claude Commands

The `.claude/commands/` files wire the agents to Claude Code slash commands:

- `/address-comments` — reads `agents/gh-address-comments/SKILL.md` and follows it
- `/fix-ci` — reads `agents/gh-fix-ci/SKILL.md` and follows it
- `/iterate-pr` — reads `agents/iterate-pr/SKILL.md` and follows it

## Project Structure

```
your-project/
├── .github/
│   ├── copilot-reviews.yml       # ← auto-review config (from this repo)
│   ├── copilot-instructions.md   # ← LOGAF tagging instructions (from this repo)
│   └── workflows/                # ← your CI/CD workflows
├── .specify/                     # ← from spec-kit (specify init)
│   ├── templates/
│   ├── scripts/bash/
│   └── memory/
├── .claude/
│   ├── commands/                 # ← speckit.* from spec-kit, PR agents from this repo
│   └── skills/                   # ← speckit-* from spec-kit (with --ai-skills)
├── agents/                       # ← PR automation agents
│   ├── gh-address-comments/
│   ├── gh-fix-ci/
│   └── iterate-pr/
└── ...
```

## Evals

The repo includes an eval suite that runs on every push and PR via GitHub Actions. Three jobs:

### Structural & Content Evals (`evals/scripts/run_evals.py`)

20 checks verifying internal consistency:
- **Repo structure** — all required files exist
- **Patch validation** — iterate-pr SKILL.md has no `uv run`, no `${CLAUDE_SKILL_ROOT}`, no `reply_to_thread.py`, includes Copilot review steps and thread resolution
- **Command validation** — each `/command` references the correct SKILL.md
- **Copilot config** — LOGAF tags in `copilot-instructions.md` match the patterns `fetch_pr_feedback.py` parses
- **Setup script** — downloads from correct sources, copies Copilot config, skips existing files

Run locally:
```bash
python evals/scripts/run_evals.py
```

### Setup Dry Run

Runs `setup.sh --dry-run` in a fresh directory to verify the script doesn't error out.

### Upstream Drift Detection

Checks whether upstream repos have changed in ways that make our patches obsolete or redundant:
- Did getsentry remove `uv run` or add `copilot-review` themselves?
- Did ComposioHQ remove `sandbox_permissions`?

Informational only — drift doesn't block the build, but flags when patches need review.

The eval prompts in `evals/evals.json` follow the [Anthropic skill-creator](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md) schema and can be used with the skill-creator's eval runner for LLM-graded evaluation of agent behavior.

## Upstream Sources

| Component | Repository | License |
|-----------|-----------|---------|
| spec-kit | [github/spec-kit](https://github.com/github/spec-kit) | MIT |
| gh-address-comments | [ComposioHQ/awesome-codex-skills](https://github.com/ComposioHQ/awesome-codex-skills) | Apache 2.0 |
| gh-fix-ci | [ComposioHQ/awesome-codex-skills](https://github.com/ComposioHQ/awesome-codex-skills) | Apache 2.0 |
| iterate-pr | [getsentry/skills](https://github.com/getsentry/skills) | Apache 2.0 |

## License

MIT — the glue, commands, and documentation in this repo.  
Upstream skills retain their original licenses (see table above).
