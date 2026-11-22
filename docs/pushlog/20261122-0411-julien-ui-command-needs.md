# ui-command-needs: "Needs you" items as full-width rows (prototype only)
- Who: Julien (tool: Claude Code)
- Branch: julien/ui-command (draft PR #279, do not merge)
- What changed: frontend/app/command/command.css only: each "Needs you" item is a slim full-width row (customer, route and reason left; price box and buttons right; red left edge) instead of a half-width box; stacks to one column under 860px.
- Files touched: frontend/app/command/command.css
- Contract/API changes: none
- New env vars / packages: none
- How verified: eslint + tsc clean; checked in the running prototype at 1440px
- Known issues / TODO: none
- Heads-up for teammates: none
