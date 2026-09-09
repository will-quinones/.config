# Approval, Issue, and Jira Flow

Use this protocol for issue handling whenever the work is tied to Jira, and for approval handling when a supplied repository's PR policy, template, workflow, or checks require an approved issue. Repository scope is supplied by the delegating main agent.

1. Consume the explicit repository paths or identifiers supplied by the delegating main agent. Do not discover repositories, ask a repository-scope question, use the launch directory as an implicit selection, or process an unsupplied checkout. If the scope is missing or ambiguous, stop and report before mutations.
2. Process only the supplied repositories, including checkouts outside the directory where OpenCode was launched. Audit each supplied repository independently and skip any supplied repository with no attributable work. Never create a PR or modify Jira for a skipped repository.
3. Inspect audited changed paths, commits, worktrees, remotes, PRs, branch names, commit messages, PR title/body, and repository policy. Search Jira only for keys supported by that evidence.
4. Use only a high-confidence Jira match. A key in the branch name, commit message, PR title/body, explicit user request, or existing issue link is evidence; an unrelated recent/open issue is not. If multiple keys conflict and the correct issue cannot be established, stop the Jira portion and report the ambiguity.
5. If work or a PR exists but no suitable issue does, create one only when the repository approval policy or an explicit user requirement requires issue creation, and only for the audited work. Never create or modify a Jira issue just to manufacture an association or QA transition.
6. Preserve assignments. Prefer one unambiguous `CODEOWNERS`/PR/history owner; otherwise use `@me`. Apply it with `gh issue edit` and, when the PR has no owner, `gh pr edit`.
7. Create `status:approved` with `gh label create` only when missing, then add it to the issue. Link the issue to its PR with `Closes #<issue>` without deleting useful PR content.
8. After all audited repository work associated with a high-confidence Jira issue has a verified merge, update that issue:
   - Call `atlassian_jira_get_issue` to read the current status.
   - If it is already `Ready for QA` or `Listo para QA` (case-insensitive), leave it unchanged and verify it.
   - Otherwise call `atlassian_jira_get_transitions` and select only a transition whose destination status is `Ready for QA` or `Listo para QA` (case-insensitive). Never guess IDs or write the status field directly.
   - Call `atlassian_jira_transition_issue`, then call `atlassian_jira_get_issue` again to verify the destination status.
   - If the transition is unavailable or fails, do not retry with an arbitrary transition; report the issue, current status, and exact blocker.

Infer issue, title, assignee, and strategy from the supplied repositories and the delegating agent's context. If a safe Jira decision is impossible, stop and report instead of moving a guessed issue.
