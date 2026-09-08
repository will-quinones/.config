# Approval and Issue Flow

Use this protocol only when the repository's PR policy, template, workflow, or checks require an approved issue.

1. Inspect changed paths, commits, worktrees, remotes, PRs, and repository policy. Build concrete repository candidates supported by that evidence.
2. Ask one `question` with `multiple: false`. Put the evidence-based recommendation first, then individual alternatives, `Todos los repositorios afectados` when useful, and `Cancelar`.
3. For each selected repository and corresponding PR, search by issue keys, branch, commits, PR text, summary, and changed area. Use only a high-confidence match.
4. If work or a PR exists but no suitable issue does, create one with scope, files, reason, and validation details. Never create an issue in a selected repository with no corresponding work.
5. Preserve assignments. Prefer one unambiguous `CODEOWNERS`/PR/history owner; otherwise use `@me`. Apply it with `gh issue edit` and, when the PR has no owner, `gh pr edit`.
6. Create `status:approved` with `gh label create` only when missing, then add it to the issue. Link the issue to its PR with `Closes #<issue>` without deleting useful PR content.

Ask only for repository scope. Infer issue, title, assignee, and strategy; if a safe decision is impossible, stop and report instead of asking another question.
