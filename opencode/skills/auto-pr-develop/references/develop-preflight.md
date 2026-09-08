# Develop Preflight

Use this protocol before creating a topic branch from a protected branch and after merging a PR.

1. Run `git fetch origin develop` and inspect `git status --porcelain`.
2. Measure `develop...origin/develop` with `git rev-list --left-right --count`. Treat `origin/develop` as the base of record.
3. If local `develop` is only behind and clean, update it with `git merge --ff-only origin/develop`.
4. If both sides have commits, compare `git diff --quiet develop origin/develop` and inspect `git log --left-right --cherry-mark develop...origin/develop`. If the trees match and all local-only commits are patch-equivalent (`=`), create `backup/develop-local-<timestamp>` and move `develop` to `origin/develop` only while `develop` is not checked out.
5. If local-only commits contain real unique work, or the tree differs, preserve the branch and stop with the commits and files reported. Do not create a topic from `origin/develop` while hiding that work.
6. If the protected branch has uncommitted changes but no unique commits, create the topic from `origin/develop` and carry the audited changes without stashing, dropping, or overwriting them. Once the topic is committed and the worktree is clean, complete the safe local `develop` alignment.
7. Never delete the backup. Do not use `reset --hard`, `git push --force`, or blind `pull --rebase`.

After a remote merge, repeat the same protocol before switching local `develop`; if it is dirty or contains real unique work, report that local synchronization remains pending.
