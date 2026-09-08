# Merged Branch Cleanup

Run this protocol only after CI is green, `gh pr merge --merge` succeeds, the PR is confirmed `MERGED`, and its merge commit has two parents.

1. Fetch `origin/develop` and repeat `develop-preflight.md`. If local synchronization is unsafe or the worktree is dirty, do not delete either branch; report cleanup as pending.
2. Read the PR head repository and branch. Never delete `develop`, `main`, `master`, `stage`, `test`, or a branch owned by another repository/fork.
3. Check `git worktree list --porcelain`. If the topic branch is checked out in another worktree, leave both branches and report the path.
4. Delete the merged remote head branch only when it belongs to the current repository and still exists: `git push <remote> --delete <branch>`. Treat an already missing remote branch as clean.
5. Switch to the synchronized local `develop`, then delete the local topic branch with `git branch -d <branch>`. Never use `-D`.
6. If any cleanup operation fails, do not force it or delete another branch. Report exactly what was cleaned and what remains.
