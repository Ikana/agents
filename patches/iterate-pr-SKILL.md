---
name: iterate-pr
description: Iterate on a PR until CI passes and review feedback is addressed. Requests Copilot review via CLI, waits for completion, then addresses findings. Automates the feedback-fix-push-wait cycle.
---

## Iterate on PR Until CI Passes

Continuously iterate on the current branch until all CI checks pass and review feedback is addressed.

**Requires**: GitHub CLI (`gh`) authenticated.

**Important**: All scripts must be run from the repository root directory (where `.git` is located).

> **⚠️ GitHub Bot logins always include `[bot]`.**
> When filtering API responses by `user.login`, use the full suffix: `copilot-pull-request-reviewer[bot]`, `dependabot[bot]`, `github-actions[bot]`, etc. Without `[bot]`, jq `select()` silently returns nothing.

## Bundled Scripts

### `scripts/fetch_pr_checks.py`

Fetches CI check status and extracts failure snippets from logs.

```bash
python agents/iterate-pr/scripts/fetch_pr_checks.py [--pr NUMBER]
```

Returns JSON:
```json
{
  "pr": {"number": 123, "branch": "feat/foo"},
  "summary": {"total": 5, "passed": 3, "failed": 2, "pending": 0},
  "checks": [
    {"name": "tests", "status": "fail", "log_snippet": "...", "run_id": 123},
    {"name": "lint", "status": "pass"}
  ]
}
```

### `scripts/fetch_pr_feedback.py`

Fetches and categorizes PR review feedback using the [LOGAF scale](https://develop.sentry.dev/engineering-practices/code-review/#logaf-scale).

```bash
python agents/iterate-pr/scripts/fetch_pr_feedback.py [--pr NUMBER]
```

Returns JSON with feedback categorized as:
- `high` - Must address before merge (`h:`, blocker, changes requested)
- `medium` - Should address (`m:`, standard feedback)
- `low` - Optional (`l:`, nit, style, suggestion)
- `bot` - Informational automated comments (Codecov, Dependabot, etc.)
- `resolved` - Already resolved threads

Review bot feedback (from Sentry, Warden, Cursor, Bugbot, CodeQL, Copilot, etc.) appears in `high`/`medium`/`low` with `review_bot: true` — it is NOT placed in the `bot` bucket.

Each feedback item may also include:
- `thread_id` - GraphQL node ID for inline review comments (used for replies)

## Workflow

### 1. Identify PR

```bash
gh pr view --json number,url,headRefName
```

Stop if no PR exists for the current branch.

### 2. Request Copilot Review

Use the CLI to request a Copilot code review:

```bash
gh copilot-review <pr-number>
```

**Important**: Do not use `@copilot` comments to request reviews — that triggers Copilot coding-agent sub-PRs instead of review.

### 3. Wait for Copilot Review

Poll for the review with exponential backoff:

1. Start at `120s`, back off exponentially (`120s → 240s → 300s`), cap at `300s`
2. After each wait, check for a new review from `copilot-pull-request-reviewer[bot]` on the latest HEAD commit:
   ```bash
   gh api repos/{owner}/{repo}/pulls/{pr}/reviews --jq '[.[] | select(.user.login == "copilot-pull-request-reviewer[bot]")] | sort_by(.submitted_at) | last | .commit_id'
   ```
3. Compare against the current HEAD SHA (`git rev-parse HEAD`)
4. Stop when a matching review appears

**Failure handling:**
- If no review arrives within the polling window, retry `gh copilot-review` once
- If retry also fails or stalls, log that Copilot review request failed and proceed with manual feedback check

### 4. Gather Review Feedback

Run `agents/iterate-pr/scripts/fetch_pr_feedback.py` to get categorized feedback already posted on the PR.

This picks up Copilot's inline comments (tagged with LOGAF markers via `.github/copilot-instructions.md`) alongside any human reviewer feedback.

### 5. Handle Feedback by LOGAF Priority

**Auto-fix (no prompt):**
- `high` - must address (blockers, security, changes requested)
- `medium` - should address (standard feedback)

When fixing feedback:
- Understand the root cause, not just the surface symptom
- Check for similar issues in nearby code or related files
- Fix all instances, not just the one mentioned

This includes review bot feedback (items with `review_bot: true`). Treat it the same as human feedback:
- Real issue found → fix it
- False positive → skip, but explain why in a brief comment
- Never silently ignore review bot feedback — always verify the finding

**Prompt user for selection:**
- `low` - present numbered list and ask which to address:

```
Found 3 low-priority suggestions:
1. [l] "Consider renaming this variable" - @reviewer in api.py:42
2. [nit] "Could use a list comprehension" - @reviewer in utils.py:18
3. [style] "Add a docstring" - @reviewer in models.py:55

Which would you like to address? (e.g., "1,3" or "all" or "none")
```

**Skip silently:**
- `resolved` threads
- `bot` comments (informational only — Codecov, Dependabot, etc.)

#### Replying to Comments

After processing each inline review comment, reply on the PR thread to acknowledge the action taken. Only reply to items with a `thread_id` (inline review comments).

**When to reply:**
- `high` and `medium` items — whether fixed or determined to be false positives
- `low` items — whether fixed or declined by the user

**How to reply:** Use the `addPullRequestReviewThreadReply` GraphQL mutation with `pullRequestReviewThreadId` and `body` inputs.

**Reply format:**
- 1-2 sentences: what was changed, why it's not an issue, or acknowledgment of declined items
- End every reply with `\n\n*— Claude Code*`
- Before replying, check if the thread already has a reply ending with `*- Claude Code*` or `*— Claude Code*` to avoid duplicates on re-loops
- If the `gh api` call fails, log and continue — do not block the workflow

### 6. Check CI Status

Run `agents/iterate-pr/scripts/fetch_pr_checks.py` to get structured failure data.

**Wait if pending:** If review bot checks (sentry, warden, cursor, bugbot, seer, codeql) are still running, wait before proceeding—they post actionable feedback that must be evaluated. Informational bots (codecov) are not worth waiting for.

### 7. Fix CI Failures

For each failure in the script output:
1. Read the `log_snippet` and trace backwards from the error to understand WHY it failed — not just what failed
2. Read the relevant code and check for related issues (e.g., if a type error in one call site, check other call sites)
3. Fix the root cause with minimal, targeted changes
4. Find existing tests for the affected code and run them. If the fix introduces behavior not covered by existing tests, extend them to cover it (add a test case, not a whole new test file)

Do NOT assume what failed based on check name alone—always read the logs. Do NOT "quick fix and hope" — understand the failure thoroughly before changing code.

### 8. Verify Locally, Then Commit and Push

Before committing, verify your fixes locally:
- If you fixed a test failure: re-run that specific test locally
- If you fixed a lint/type error: re-run the linter or type checker on affected files
- For any code fix: run existing tests covering the changed code

If local verification fails, fix before proceeding — do not push known-broken code.

```bash
git add <files>
git commit -m "fix: <descriptive message>"
git push
```

### 9. Request Copilot Re-Review and Monitor

After pushing, request a fresh Copilot review and poll CI + feedback in a loop:

1. Run `gh copilot-review <pr-number>` to request re-review on the new HEAD
2. Run `python agents/iterate-pr/scripts/fetch_pr_checks.py` to get current CI status
3. If all checks passed → wait for Copilot review to land (step 3 polling), then proceed to exit conditions
4. If any checks failed (none pending) → return to step 7
5. If checks are still pending:
   a. Run `python agents/iterate-pr/scripts/fetch_pr_feedback.py` for new review feedback
   b. Address any new high/medium feedback immediately (same as step 5)
   c. If changes were needed, commit and push (this restarts CI and requires a new `gh copilot-review`), then continue polling
   d. Sleep 30 seconds, then repeat from sub-step 2
6. After all checks pass and Copilot review has landed, do a final feedback check: `sleep 10`, then run `python agents/iterate-pr/scripts/fetch_pr_feedback.py`. Address any new high/medium feedback — if changes are needed, return to step 8.

### 10. Close Addressed Review Threads

Before declaring success, close out previously addressed review threads. For each thread where a fix was committed and a reply was posted, resolve the thread if it is still open:

```bash
gh api graphql -f query='mutation($id: ID!) { resolveReviewThread(input: {threadId: $id}) { thread { isResolved } } }' -F id=<thread_id>
```

### 11. Repeat

If step 9 required code changes (from new feedback after CI passed), return to step 4 for a fresh cycle. CI failures during monitoring are already handled within step 9's polling loop.

## Exit Conditions

**Success:** All checks pass, Copilot review is complete on latest HEAD, post-CI feedback re-check is clean (no new unaddressed high/medium feedback including review bot findings), user has decided on low-priority items.

**Ask for help:** Same failure after 2 attempts, feedback needs clarification, infrastructure issues.

**Stop:** No PR exists, branch needs rebase.

## Fallback

If scripts fail, use `gh` CLI directly:
- `gh pr checks name,state,bucket,link`
- `gh run view <run-id> --log-failed`
- `gh api repos/{owner}/{repo}/pulls/{number}/comments`

If `gh copilot-review` is not available (older CLI version), fall back to the `pull_request_review` event approach: push and wait for Copilot's automatic review if enabled via repository rulesets.
