# API
Interactive documentation: `http://localhost:8000/docs` (disabled when `APP_ENV=production`). All routes are under `/api/v1`
except `/health` and `/ready`. Errors: `{"code","message","details","request_id"}`; send `X-Request-ID` to correlate.
Long operations (`POST /projects/{id}/analysis-runs`) return `202` with a `Location` header; poll `GET /analysis-runs/{id}`.
