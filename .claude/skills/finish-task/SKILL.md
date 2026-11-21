---
name: finish-task
description: Finishes the current task - rebase, make check, writes the push log entry, pushes, opens a PR, updates TASKS.md.
disable-model-invocation: true
---
Follow AI_GUIDELINES.md §3 and §4. If make check fails, do not push; fix it or report to the user.
Write the push log entry from the actual diff (`git diff origin/main...HEAD --stat`), not from memory. Paste it into the PR description.
