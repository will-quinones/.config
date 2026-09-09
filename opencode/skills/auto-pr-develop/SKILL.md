---
name: auto-pr-develop
description: "Trigger: auto-pr-develop, repositorios explícitos del agente principal, status:approved, PR a develop, CI verde, Jira listo para QA. Automatiza aprobación necesaria, commit, sincronización, merge commit final y actualización del ticket asociado."
license: Apache-2.0
metadata:
  author: "williamquinones"
  version: "1.4"
---

## Activation Contract

Use ONLY when the user explicitly invokes `auto-pr-develop` or requests the complete commit, PR to `develop`, and merge-if-green workflow. The invocation authorizes those operations, not unrelated changes.

## Hard Rules

- Run all mutations as `auto-pr-coordinator`; another agent must delegate before acting.
- Repository scope is supplied by the delegating main agent, which knows what work was just performed. The scope must contain the explicit repository paths or identifiers for every repository to process; the coordinator must not discover or infer them.
- The repository where OpenCode or the coordinator was launched is not implicit scope. Process only the repositories explicitly supplied by the delegating agent, including checkouts outside the launch directory, and never fall back to the launch repository.
- Do not ask the user which repositories were worked on, show repository candidates, recommend repositories, or silently select a repository. If explicit repository scope is missing or ambiguous, stop before mutations and report the missing scope.
- Audit every supplied repository, its auth, branch, worktrees, remotes, and diff before mutating it. A supplied repository with no audited commits or changes attributable to the requested work is skipped without a branch, commit, push, PR, or Jira update. If all supplied repositories have no work, stop and report without mutations.
- Never create a GitHub or Jira issue by default. Create an issue only when the repository policy or an explicit user requirement makes issue creation necessary; a missing issue link alone is not sufficient.
- Establish the audited work set per repository before branching. Never include secrets, unrelated work, or changes that appeared after the audit without re-auditing them.
- Before branching from `develop`, `stage`, `test`, `main`, or `master`, follow `references/develop-preflight.md`. Keep local `develop` clean; align only safe equivalent divergence with a backup and stop on real local work.
- Fetch `origin/develop` before every push. Rebase only unpublished private linear branches; otherwise merge with `--no-ff`.
- Resolve conflicts hunk-by-hunk, never wholesale `ours`/`theirs`; abort only ambiguous resolutions. Rerun validation and `git diff --check` afterward.
- Use `develop` as PR base, reuse open PRs, and never push directly to protected branches.
- When approval or issue handling is required, follow `references/approval-flow.md`; do not ask a repository-scope question.
- Wait for green CI with `gh pr checks <PR> --watch --fail-fast`. Final merge is only `gh pr merge <PR> --merge`; verify the extra two-parent merge commit.
- After all repository work associated with a high-confidence Jira issue has been verified merged, update that issue to `Ready for QA`/`Listo para QA`, then follow `references/branch-cleanup.md` for each merged topic branch. Jira completion happens before branch cleanup; cleanup remains the final Git mutation per repository and must never delete protected, fork-owned, or worktree-backed branches.

## Decision Gates

| Condition | Action |
| --- | --- |
| Missing or ambiguous explicit repository scope from the delegating agent | Stop and report without discovering, asking, or selecting repositories. |
| Supplied repository has no audited work | Skip that repository without mutation and report it. |
| All supplied repositories have no audited work, missing auth, unsafe protected-branch state, or failed validation | Stop and report. |
| `develop` only behind | Fast-forward it from `origin/develop`. |
| Equivalent divergence with clean tree | Create backup, align local `develop`, then branch. |
| Real local-only work or ambiguous conflict | Preserve it and stop without pushing. |
| Unpublished linear branch | Rebase onto `origin/develop`; otherwise merge `--no-ff`. |
| Approval policy required | Run the approval and issue flow for the supplied repositories without asking for repository selection. |
| PR open, base `develop`, CI green, mergeable | Merge with `--merge` and verify two parents. |
| No high-confidence Jira issue is linked to the audited work | Do not create or modify a Jira issue solely for this workflow; report Jira as not applicable. |
| Issue creation is not required by policy or explicit user request | Do not create an issue. |
| Jira issue spans selected repositories and not all associated work is merged | Do not transition it to QA; report the pending repository/PR. |
| Associated Jira issue is already `Ready for QA`/`Listo para QA` | Do not transition it again; verify and report it as complete. |
| Associated Jira issue has no safe transition to `Ready for QA`/`Listo para QA` | Do not force a status or edit a status field directly; report Jira completion as blocked. |
| Merge verified and cleanup preconditions pass | Delete the merged remote and local topic branch safely. |
| Cleanup precondition or deletion fails | Keep the remaining branch and report exactly what was not removed. |

## Execution Steps

1. Read the applicable references and consume the explicit repository paths or identifiers supplied by the delegating main agent. Do not discover repositories, ask a scope question, or use the launch directory as an implicit selection. Stop before any mutation if the scope is missing or ambiguous.
2. For each supplied repository, audit its worktree, commits, branch, worktrees, remotes, and PRs. Record the audited files/commits and associated Jira issue keys. Skip repositories with no attributable work; stop before any mutation if none remain.
3. For each remaining repository, infer the commit title, complete the protected-branch preflight, create its topic branch, stage only audited files, validate, and commit.
4. Fetch `origin/develop`, synchronize each topic branch with the selected strategy, resolve conflicts, and validate again.
5. Run the approval/issue flow if required for the supplied repositories, then push and create or reuse each PR with base `develop`.
6. Re-fetch before merging; if a PR is behind, conflicting, or missing approval, repeat synchronization, approval, validation, push, and CI for that repository.
7. On successful checks, merge each PR with `gh pr merge <PR> --merge` and verify its recorded two-parent merge commit.
8. Group high-confidence Jira issues across the supplied repositories. Once all audited repository work associated with an issue has a verified merge, call `atlassian_jira_get_issue` and `atlassian_jira_get_transitions`, select a transition whose target status is exactly `Ready for QA` or `Listo para QA` ignoring case, execute it with `atlassian_jira_transition_issue`, and verify the resulting status with `atlassian_jira_get_issue`. Never guess a transition ID or move an unrelated issue.
9. Repeat the develop preflight and run `references/branch-cleanup.md` for each repository only after its Jira updates are verified or explicitly reported as not applicable/blocked.

## Output Contract

Return subagent, launch repository, supplied repositories, per-repository audited work set, branches, commits, associated Jira issue keys and their before/after statuses, transition verification or blocking reason, issue/PR assignments and links, approval actions, PR URLs, sync strategies, CI, merge commits, cleanup results, skipped repositories, and failed steps. State explicitly when no repository scope, mutation, or merge occurred.

## References

- `../branch-pr/SKILL.md` — optional issue, label, PR body, and commit conventions.
- `references/develop-preflight.md` — safe local/remote `develop` synchronization.
- `references/approval-flow.md` — automatic issue, assignment, and approval handling.
- `references/branch-cleanup.md` — guarded cleanup of merged local and remote topic branches.
