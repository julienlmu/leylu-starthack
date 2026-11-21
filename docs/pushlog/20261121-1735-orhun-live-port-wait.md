# live.sh waits up to 30 s for the port before giving up
- Who: Orhun (tool: Claude Code)
- Branch: orhun/live-port-wait
- What changed: scripts/live.sh refused to start when :8000 was still held by the backend that was just stopped (graceful shutdown), which twice left the live Mac without a runner for 35-70 s after a restart. It now waits up to 30 s for the port and only then gives up
- Files touched: scripts/live.sh
- How verified: bash -n; the restarts on the Mac use the same wait
