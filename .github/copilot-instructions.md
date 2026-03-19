# Copilot Code Review Instructions

## LOGAF Priority Tagging

When reviewing pull requests, prefix every inline comment with a priority tag using the [LOGAF scale](https://develop.sentry.dev/engineering-practices/code-review/#logaf-scale):

- **`h:`** — High priority. Must address before merge. Use for: bugs, security vulnerabilities, data loss risks, breaking API changes, missing error handling that will cause runtime failures.
- **`m:`** — Medium priority. Should address. Use for: code clarity improvements, missing edge case handling, suboptimal patterns, inconsistent naming, missing or weak tests.
- **`l:`** — Low priority. Optional / nit. Use for: style preferences, minor readability suggestions, alternative approaches that are roughly equivalent, documentation wording.

### Format

```
h: This null check is missing — `user.id` can be undefined when the session expires.
```

```
m: Consider extracting this into a helper function — it's duplicated in three places.
```

```
l: Nit: prefer `const` over `let` here since the value isn't reassigned.
```

### Rules

1. **Every comment must start with a tag** (`h:`, `m:`, or `l:`).
2. Be specific about *what* the problem is and *why* it matters.
3. For `h:` items, explain the failure mode or risk.
4. For `m:` items, suggest a concrete improvement.
5. For `l:` items, keep it brief — one line is fine.
6. Do not tag general praise or acknowledgments — only actionable feedback.

## Review Focus Areas

- Correctness: Will this code work as intended? Are there edge cases?
- Security: Are inputs validated? Are secrets handled properly?
- Performance: Any obvious N+1 queries, unbounded loops, or memory leaks?
- Tests: Are changes covered by tests? Are the tests meaningful?
- API compatibility: Do changes break existing contracts?
