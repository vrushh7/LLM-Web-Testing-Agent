# API Documentation

Base URL: `http://localhost:8000`

## Health

`GET /api/health`

Returns:

```json
{"status":"ok"}
```

## Start a Test Run

`POST /api/tests/run`

```json
{
  "prompt": "Go to Amazon and search iPhone 16",
  "base_url": null,
  "session_id": null,
  "save_session_name": null,
  "browser": "chromium",
  "headless": false,
  "max_retries": 2
}
```

Set `headless` to `false` to watch Chromium execute live on screen. The frontend does this automatically when Chromium is selected.

Returns immediately while the run continues in the background:

```json
{
  "run_id": "abc123",
  "status": "queued",
  "websocket_url": "ws://localhost:8000/ws/runs/abc123"
}
```

## Live Events

`WS /ws/runs/{run_id}`

Event shape:

```json
{
  "run_id": "abc123",
  "type": "status",
  "message": "Executing 4 planned steps",
  "status": "executing",
  "step_index": null,
  "payload": {},
  "timestamp": "2026-05-18T10:00:00Z"
}
```

Event types: `status`, `log`, `step_started`, `step_finished`, `report`.

## Fetch Runs

`GET /api/tests`

`GET /api/tests/{run_id}`

The detail endpoint includes step results and screenshot URLs.

## Reports

`GET /api/reports/{run_id}`

Returns the HTML report.

`GET /api/reports/{run_id}/download`

Downloads the report as an HTML file.

## Sessions

`GET /api/sessions`

Lists saved Playwright storage-state sessions.

`DELETE /api/sessions/{session_id}`

Deletes a saved session file and database record.
