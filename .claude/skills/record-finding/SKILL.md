---
name: record-finding
description: Record something the lab revealed about the Kavrynt runtime or Cloud in docs/FINDINGS.md - next F-number, table row, evidence section with code references, owning repository, and a drafted issue for that repository. Use when a lab run shows a bug, gap, or surprising behaviour.
argument-hint: <one-line description of what the lab showed>
---

# Record a lab finding

Finding: `$ARGUMENTS`.

## 1. Check it is new

Read `docs/FINDINGS.md`. If an existing finding covers it, add the new evidence to that
section instead of creating a duplicate.

## 2. Pin down the evidence

- Reproduce it (`/lab-cycle`), and keep the exact command, output, or metric.
- Find the cause in the owning repository with `file:line` references, for example
  `internal/gateway/api/api.go:27` in `../kavrynt`. Note the commit:
  `git -C ../kavrynt rev-parse --short HEAD`. The file header records which runtime commit the
  references point to; say so if yours differ.
- Severity: **high** means a caller can do what policy forbids or data leaks; **medium** means
  wrong or missing behaviour with a workaround; **low** means docs, ergonomics, or a dev-only
  problem.
- Owner: `kavrynt` (runtime), `kavrynt-cloud`, `kavrynt-platform`, or `docs`.

## 3. Write it

Add a row to the table with the next number:

```markdown
| F11 | <short title> | medium | `kavrynt` | open |
```

Status values: `open`, `open (Phase N)` when a planned phase fixes it, `worked around`, `fixed`.

Then a section in the same style as the others:

```markdown
## F11. <Short title>

<What happens and why, with file:line references.>

**Seen in the lab:** <the observable symptom, with the command or dashboard panel>.
**Fix:** <the fix, and which ADR, LLD, or PLAN phase covers it>.
```

## 4. Draft the issue

Write the issue for the owning repository (title, the evidence, the proposed fix, a link back to
`azure-ai-labs/docs/FINDINGS.md#f11-...`). Show it to the owner. **Create it only when asked**:

```bash
gh issue create -R kavrynt/<repo> --title "…" --body-file /tmp/finding.md
```

Then add the issue link to the finding's section. Never put secrets or real customer data in a
finding: lab data is synthetic.
