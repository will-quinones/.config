---
name: auto-pr-develop
description: "Trigger: auto-pr-develop, status:approved, seleccionar repos, PR a develop, CI verde. Automatiza aprobación necesaria, commit, sincronización y merge commit final."
license: Apache-2.0
metadata:
  author: "williamquinones"
  version: "1.0"
---

## Activation Contract

Use ONLY when the user explicitly invokes `auto-pr-develop` or requests the complete commit, PR to `develop`, and merge-if-green workflow. The invocation authorizes those operations, not unrelated changes.

## Hard Rules

- Run all mutations as `auto-pr-coordinator`; another agent must delegate before acting.
- Audit repository, auth, branch, and diff first. Never include secrets or unrelated work.
- Before branching from `develop`, `stage`, `test`, `main`, or `master`, follow `references/develop-preflight.md`. Keep local `develop` clean; align only safe equivalent divergence with a backup and stop on real local work.
- Fetch `origin/develop` before every push. Rebase only unpublished private linear branches; otherwise merge with `--no-ff`.
- Resolve conflicts hunk-by-hunk, never wholesale `ours`/`theirs`; abort only ambiguous resolutions. Rerun validation and `git diff --check` afterward.
- Use `develop` as PR base, reuse open PRs, and never push directly to protected branches.
- When approval is required, follow `references/approval-flow.md`; ask only repository scope with `multiple: false`.
- Wait for green CI with `gh pr checks <PR> --watch --fail-fast`. Final merge is only `gh pr merge <PR> --merge`; verify the extra two-parent merge commit.
- After a verified merge, follow `references/branch-cleanup.md` to remove only the merged topic branch. Cleanup is the final mutation and must never delete protected, fork-owned, or worktree-backed branches.

## Decision Gates

| Condition | Action |
| --- | --- |
| No changes, missing auth, unsafe protected-branch state, or failed validation | Stop and report. |
| `develop` only behind | Fast-forward it from `origin/develop`. |
| Equivalent divergence with clean tree | Create backup, align local `develop`, then branch. |
| Real local-only work or ambiguous conflict | Preserve it and stop without pushing. |
| Unpublished linear branch | Rebase onto `origin/develop`; otherwise merge `--no-ff`. |
| Approval policy required | Run the single-choice repository question and approval flow. |
| PR open, base `develop`, CI green, mergeable | Merge with `--merge` and verify two parents. |
| Merge verified and cleanup preconditions pass | Delete the merged remote and local topic branch safely. |
| Cleanup precondition or deletion fails | Keep the remaining branch and report exactly what was not removed. |

## Execution Steps

1. Read the applicable references, audit the worktree, infer the commit title, and complete the protected-branch preflight.
2. Create the topic branch, stage only audited files, validate, and commit.
3. Fetch `origin/develop`, synchronize the topic branch with the selected strategy, resolve conflicts, and validate again.
4. Run the approval/issue flow if required, then push and create or reuse the PR with base `develop`.
5. Re-fetch before merging; if the PR is behind, conflicting, or missing approval, repeat synchronization, approval, validation, push, and CI.
6. On successful checks, merge with `gh pr merge <PR> --merge`, verify the recorded two-parent merge commit, repeat the develop preflight, and run `references/branch-cleanup.md`.

## Output Contract

Return subagent, branch, commit, selected repositories/issues, issue/PR assignments and links, approval actions, PR URL, sync strategy, CI, merge commit, and skipped/failed steps. State explicitly when no merge occurred.

## References

- `../branch-pr/SKILL.md` — optional issue, label, PR body, and commit conventions.
- `references/develop-preflight.md` — safe local/remote `develop` synchronization.
- `references/approval-flow.md` — automatic issue, assignment, and approval handling.
- `references/branch-cleanup.md` — guarded cleanup of merged local and remote topic branches.
