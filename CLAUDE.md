# Jobbi

## Merge gate

- The gate before opening or merging a PR = `/pre-merge` **and** `/security-review`, run one after the other (pre-merge first).
- `/security-review` reviews the session's primary working directory. From the main checkout on master it sees an empty diff, and a subagent's `cd` does not change that. So either the main session `cd`s into the branch worktree before invoking it, or the reviewer follows the skill's steps by hand on `git diff origin/master...HEAD` and says so in the report.
- If both pass with no findings, the gate is done: do not run it again.
- If findings were fixed, re-run the gate only on the fix commits.
