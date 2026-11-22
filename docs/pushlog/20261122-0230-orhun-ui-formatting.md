**Task:** Sessions UI glitches on session 105 · **Agent:** Claude Code

# Sessions UI: no NaN response time, rounded kg, no "× ×× cm" without dimensions
- Who: Orhun (tool: Claude Code)
- Branch: orhun/ui-formatting
- `frontend/lib/format.ts`:
  - `responseSeconds` returns null when the quote has no `sent_at` (a hand-patched quote), so the UI shows "No quote sent yet" instead of "NaN:NaN / Past 6:00".
  - `totalWeight` is rounded to 0.1 kg (1841 / 6 per piece showed 1840.9999979999998).
  - New `dims()` helper.
- `frontend/components/detail/request.tsx`: pieces show "6 × 306.8 kg each" when there are no dimensions, and "6 × 120×80×100 cm, …" when there are.
- Frontend only, no agent/backend change. tsc and eslint clean.
