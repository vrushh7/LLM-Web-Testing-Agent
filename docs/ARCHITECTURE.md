# Architecture

The system intentionally does not ask the LLM to generate Playwright code. It uses a safer and cheaper two-stage design:

1. The AI orchestrator sends a compact planner prompt to Gemini Flash first.
2. If Gemini fails or is not configured, OpenAI GPT-4o-mini is used as fallback.
3. The response is validated as structured JSON steps.
4. A Playwright interpreter executes the allowed action set.
5. Results are persisted to SQLite and streamed over WebSockets.
6. The report generator creates a shareable HINSA AI evidence report with screenshots, metrics, and timeline charts.

## Backend Modules

- `app/ai`: prompt templates, Gemini REST integration, OpenAI REST fallback, JSON validation, prompt cache.
- `app/automation`: Playwright browser pool, dynamic locators, action interpreter, screenshots, retries, session state.
- `app/services`: orchestration, WebSocket broadcast, sessions, serialization.
- `app/database`: SQLAlchemy models and async SQLite session.
- `app/reports`: HTML report generation.
- `app/api`: REST and WebSocket routes.

## Low-Cost Controls

- Prompt cache keyed by prompt, base URL, and prompt version.
- Short JSON-only planner prompt.
- No raw code generation.
- Warm browser pool.
- Retry at the action layer instead of asking the LLM again.
- Deterministic rule fallback for common ecommerce tasks when cloud models are temporarily unavailable.

## Security Model

- API keys come from environment variables only.
- Saved login sessions are Playwright storage-state files stored server-side and never returned through the API.
- The app reuses authenticated sessions only when the user explicitly selects one.
- The tool does not bypass authentication systems; it fills credentials or reuses user-created browser state.
- Basic per-IP rate limiting protects local and demo deployments.
