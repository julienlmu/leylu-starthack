# CONTRACT.md — interfaces between modules
Changes only via PR approved by the Lead. Agents never edit this file directly.

## Endpoints
### `GET /health` → `{ "ok": true }`

### `POST /api/<name>`
Request:
```json
{ "example_field": "string" }
```
Response:
```json
{ "result": "string" }
```

## Shared types
- `<Type>`: fields and meaning

## Env vars (keep in sync with .env.example)
- `LLM_API_KEY`, `PORT`, `MOCK_API`
