**Task:** portal down by hand, faster · **Agent:** Claude Code

# main (#245–#247, PORTAL_MEMORY) and PR #248 (T+0 portal probe, helper userscript, pasted-rate endpoint) into the live branch
- Who: Orhun (tool: Claude Code)
- Branch: orhun/requote
- Merged main 815a6ad and orhun/portal-cache (#248). Conflict in agent/conftest.py resolved by keeping both fixtures (BOOK_GRACE_S=0 and PORTAL_PROBE off in tests).
- Checked: the userscript never reads, solves or fills the captcha sum (a person does). It closes the ad pop-ups with their own X and picks "necessary only" on the cookie wall. Its POST to localhost goes through GM_xmlhttpRequest (@connect localhost), so CORS doesn't apply; the backend has CORSMiddleware anyway.
- Kept: CANCEL_AUTO and the night fixes. .env: PORTAL_RETRY_LAST_SECONDS=310.
- Tests: agent 2549 passed, backend 259.
