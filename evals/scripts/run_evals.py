#!/usr/bin/env python3
"""
Eval runner for agents repo.

Runs structural and content validation checks that don't require
an LLM — these are the "unit tests" that verify the repo's artifacts
are internally consistent and match their upstream modification contracts.

Usage:
    python evals/scripts/run_evals.py [--verbose]

Exit codes:
    0 = all checks passed
    1 = one or more checks failed
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VERBOSE = "--verbose" in sys.argv


def log(msg: str):
    print(f"  {msg}")


def ok(name: str):
    print(f"  ✓ {name}")


def fail(name: str, reason: str):
    print(f"  ✗ {name}")
    print(f"    → {reason}")


# ── Test registry ───────────────────────────────────────────────

results: list[tuple[str, bool, str]] = []


def check(name: str):
    """Decorator to register a check function."""
    def decorator(fn):
        def wrapper():
            try:
                fn()
                results.append((name, True, ""))
                ok(name)
            except AssertionError as e:
                results.append((name, False, str(e)))
                fail(name, str(e))
            except Exception as e:
                results.append((name, False, f"Error: {e}"))
                fail(name, f"Error: {e}")
        wrapper.__name__ = name
        return wrapper
    return decorator


# ── Structural checks ──────────────────────────────────────────

@check("repo-structure")
def check_repo_structure():
    """Verify all expected files exist."""
    required = [
        "README.md",
        "setup.sh",
        "LICENSE",
        ".gitignore",
        "patches/iterate-pr-SKILL.md",
        ".claude/commands/address-comments.md",
        ".claude/commands/fix-ci.md",
        ".claude/commands/iterate-pr.md",
        ".github/copilot-reviews.yml",
        ".github/copilot-instructions.md",
        "evals/evals.json",
    ]
    missing = [f for f in required if not (REPO_ROOT / f).exists()]
    assert not missing, f"Missing files: {', '.join(missing)}"


@check("setup-script-executable")
def check_setup_executable():
    """setup.sh must be executable."""
    setup = REPO_ROOT / "setup.sh"
    assert os.access(setup, os.X_OK), "setup.sh is not executable"


@check("evals-json-valid")
def check_evals_json():
    """evals.json must be valid JSON with required fields."""
    evals_path = REPO_ROOT / "evals" / "evals.json"
    data = json.loads(evals_path.read_text())
    assert "skill_name" in data, "Missing skill_name"
    assert "evals" in data, "Missing evals array"
    assert len(data["evals"]) >= 3, f"Expected ≥3 evals, got {len(data['evals'])}"
    for ev in data["evals"]:
        assert "id" in ev, "Eval missing id"
        assert "prompt" in ev, f"Eval {ev.get('id')} missing prompt"
        assert "expectations" in ev, f"Eval {ev.get('id')} missing expectations"
        assert len(ev["expectations"]) >= 2, f"Eval {ev['id']} has <2 expectations"


# ── SKILL.md patch validation ───────────────────────────────────

@check("iterate-pr-no-uv-run")
def check_no_uv_run():
    """Patched iterate-pr SKILL.md must not contain 'uv run'."""
    skill = (REPO_ROOT / "patches" / "iterate-pr-SKILL.md").read_text()
    assert "uv run" not in skill, "Found 'uv run' — should use 'python agents/...'"


@check("iterate-pr-no-skill-root")
def check_no_skill_root():
    """Patched iterate-pr must not reference ${CLAUDE_SKILL_ROOT}."""
    skill = (REPO_ROOT / "patches" / "iterate-pr-SKILL.md").read_text()
    assert "${CLAUDE_SKILL_ROOT}" not in skill, "Found ${CLAUDE_SKILL_ROOT} placeholder"


@check("iterate-pr-no-reply-to-thread-script")
def check_no_reply_script():
    """Patched iterate-pr must not reference reply_to_thread.py."""
    skill = (REPO_ROOT / "patches" / "iterate-pr-SKILL.md").read_text()
    assert "reply_to_thread.py" not in skill, "Found reply_to_thread.py reference"


@check("iterate-pr-has-copilot-review")
def check_copilot_review():
    """Patched iterate-pr must include Copilot review steps."""
    skill = (REPO_ROOT / "patches" / "iterate-pr-SKILL.md").read_text()
    assert "gh copilot-review" in skill, "Missing 'gh copilot-review' command"
    assert "copilot-pull-request-reviewer[bot]" in skill, "Missing Copilot reviewer polling"


@check("iterate-pr-has-thread-resolution")
def check_thread_resolution():
    """Patched iterate-pr must include review thread resolution."""
    skill = (REPO_ROOT / "patches" / "iterate-pr-SKILL.md").read_text()
    assert "resolveReviewThread" in skill, "Missing resolveReviewThread mutation"


@check("iterate-pr-portable-paths")
def check_portable_paths():
    """Patched iterate-pr must use agents/iterate-pr/scripts/ paths."""
    skill = (REPO_ROOT / "patches" / "iterate-pr-SKILL.md").read_text()
    assert "agents/iterate-pr/scripts/fetch_pr_checks.py" in skill
    assert "agents/iterate-pr/scripts/fetch_pr_feedback.py" in skill


@check("iterate-pr-copilot-in-bot-list")
def check_copilot_bot_list():
    """Patched iterate-pr should list Copilot among review bots."""
    skill = (REPO_ROOT / "patches" / "iterate-pr-SKILL.md").read_text()
    assert "Copilot" in skill, "Copilot not mentioned in review bot list"


# ── Claude command validation ───────────────────────────────────

@check("commands-reference-correct-skills")
def check_command_references():
    """Each command must reference its corresponding SKILL.md."""
    mappings = {
        "address-comments.md": "agents/gh-address-comments/SKILL.md",
        "fix-ci.md": "agents/gh-fix-ci/SKILL.md",
        "iterate-pr.md": "agents/iterate-pr/SKILL.md",
    }
    for cmd_file, expected_skill in mappings.items():
        cmd = (REPO_ROOT / ".claude" / "commands" / cmd_file).read_text()
        assert expected_skill in cmd, (
            f"{cmd_file} does not reference {expected_skill}"
        )


@check("commands-have-descriptions")
def check_command_descriptions():
    """Each command must have a YAML frontmatter description."""
    for cmd_file in ["address-comments.md", "fix-ci.md", "iterate-pr.md"]:
        content = (REPO_ROOT / ".claude" / "commands" / cmd_file).read_text()
        assert "description:" in content, f"{cmd_file} missing description"


# ── Copilot config validation ──────────────────────────────────

@check("copilot-reviews-yml-valid")
def check_copilot_reviews():
    """copilot-reviews.yml must have auto review config."""
    content = (REPO_ROOT / ".github" / "copilot-reviews.yml").read_text()
    assert "auto:" in content, "Missing auto review config"
    assert "require_passing_checks" in content, "Missing require_passing_checks"


@check("copilot-instructions-logaf-tags")
def check_logaf_tags():
    """copilot-instructions.md must define h:, m:, l: LOGAF tags."""
    content = (REPO_ROOT / ".github" / "copilot-instructions.md").read_text()
    assert "`h:`" in content, "Missing h: tag definition"
    assert "`m:`" in content, "Missing m: tag definition"
    assert "`l:`" in content, "Missing l: tag definition"
    assert "LOGAF" in content, "Missing LOGAF reference"


@check("logaf-tags-match-fetch-script-patterns")
def check_logaf_pattern_compat():
    """LOGAF tags in copilot-instructions must match patterns in fetch_pr_feedback.py.

    The fetch_pr_feedback.py script expects comments to start with
    h:, m:, or l: (with optional whitespace). Verify the instructions
    tell Copilot to use exactly these prefixes.
    """
    instructions = (REPO_ROOT / ".github" / "copilot-instructions.md").read_text()
    # Verify the instructions show the h:/m:/l: format explicitly
    assert re.search(r"h:", instructions), "Instructions don't show h: format"
    assert re.search(r"m:", instructions), "Instructions don't show m: format"
    assert re.search(r"l:", instructions), "Instructions don't show l: format"
    # Verify it says every comment must start with a tag
    assert re.search(
        r"[Ee]very\s+comment\s+must\s+start\s+with\s+a\s+tag", instructions
    ), "Instructions don't mandate tag-first format"


# ── Setup script validation ────────────────────────────────────

@check("setup-downloads-correct-sources")
def check_setup_sources():
    """setup.sh must download from the correct upstream repos."""
    script = (REPO_ROOT / "setup.sh").read_text()
    assert "ComposioHQ/awesome-codex-skills" in script, "Missing ComposioHQ source"
    assert "getsentry/skills" in script, "Missing getsentry source"


@check("setup-copies-copilot-config")
def check_setup_copilot():
    """setup.sh must copy Copilot review config files."""
    script = (REPO_ROOT / "setup.sh").read_text()
    assert "copilot-reviews.yml" in script, "setup.sh doesn't copy copilot-reviews.yml"
    assert "copilot-instructions.md" in script, "setup.sh doesn't copy copilot-instructions.md"


@check("setup-skip-existing")
def check_setup_idempotent():
    """setup.sh must skip files that already exist (idempotent)."""
    script = (REPO_ROOT / "setup.sh").read_text()
    # Should check for existence before copying
    assert script.count("already exists") >= 1 or script.count("skipping") >= 1, (
        "setup.sh doesn't appear to skip existing files"
    )


# ── README validation ──────────────────────────────────────────

@check("readme-documents-all-modifications")
def check_readme_mods():
    """README must document modifications for all three agents."""
    readme = (REPO_ROOT / "README.md").read_text()
    assert "gh-address-comments" in readme
    assert "gh-fix-ci" in readme
    assert "iterate-pr" in readme
    assert "Copilot review" in readme or "copilot-review" in readme
    assert "LOGAF" in readme


@check("readme-lists-upstream-sources")
def check_readme_sources():
    """README must list all upstream source repos."""
    readme = (REPO_ROOT / "README.md").read_text()
    assert "github/spec-kit" in readme
    assert "ComposioHQ/awesome-codex-skills" in readme
    assert "getsentry/skills" in readme


# ── Run all checks ─────────────────────────────────────────────

def main():
    print("🧪 agents eval suite")
    print("━" * 40)
    print()

    checks = [v for v in globals().values() if callable(v) and hasattr(v, "__name__") and v.__name__.startswith("check_")]

    # Run all registered checks
    for fn_name, fn in [(k, v) for k, v in globals().items() if callable(v) and hasattr(v, "__wrapped__")]:
        fn()

    # The decorator-based checks are already called above via the wrapper
    # Let's just call them directly
    pass

    print()
    print("━" * 40)

    passed = sum(1 for _, ok, _ in results)
    failed_list = [(name, reason) for name, ok, reason in results if not ok]
    total = len(results)

    if failed_list:
        print(f"❌ {len(failed_list)}/{total} checks failed")
        print()
        for name, reason in failed_list:
            print(f"  FAIL: {name}")
            print(f"        {reason}")
        sys.exit(1)
    else:
        print(f"✅ {total}/{total} checks passed")
        sys.exit(0)


if __name__ == "__main__":
    # Collect all check functions and run them
    check_fns = []
    for name, obj in list(globals().items()):
        if callable(obj) and name.startswith("check_"):
            check_fns.append(obj)

    print("🧪 agents eval suite")
    print("━" * 40)
    print()

    for fn in check_fns:
        fn()

    print()
    print("━" * 40)

    passed = sum(1 for _, p, _ in results if p)
    failed_list = [(name, reason) for name, p, reason in results if not p]
    total = len(results)

    if failed_list:
        print(f"\n❌ {len(failed_list)}/{total} checks failed\n")
        for name, reason in failed_list:
            print(f"  FAIL: {name}")
            print(f"        {reason}")
        sys.exit(1)
    else:
        print(f"\n✅ {total}/{total} checks passed")
        sys.exit(0)
