---
name: review
description: Reviews the current branch's diff against origin/main with fresh eyes.
---
Review `git diff origin/main...HEAD`. Report only: bugs that could break the demo flow, mismatches with docs/CONTRACT.md, leaked keys/.env, changes outside the task's folder, and a missing or inaccurate docs/pushlog/ entry. No style comments.
