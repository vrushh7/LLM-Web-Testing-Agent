# LLM Web Testing Agent

A production-structured student-friendly SaaS-style autonomous browser testing platform. Users type plain English test commands, a cloud LLM converts them into compact JSON steps, and a Playwright interpreter executes the steps with live logs, proof screenshots, saved sessions, retries, visual analytics, and HTML evidence reports.

The LLM never generates raw Playwright code.

## Stack

- Frontend: React, Vite, Tailwind CSS, Zustand, Axios
- Backend: FastAPI, async SQLAlchemy, SQLite
- Automation: Playwright Python async API
- AI: Gemini 1.5 Flash first, OpenAI GPT-4o-mini fallback
- Reporting: HTML reports, screenshots, execution timeline
- Realtime: WebSockets

## Folder Structure

```text
backend/
  app/
    api/
    core/
    services/
    automation/
    ai/
    reports/
    database/
    models/
    schemas/
    utils/
  requirements.txt
frontend/
  src/
    pages/
    components/
    services/
    hooks/
    utils/
    store/
samples/
docs/
```

## 1. API Key Setup

Copy the environment file:

```bash
cp .env.example .env
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

Set at least one cloud LLM key:

```env
GEMINI_API_KEY=your_gemini_key
OPENAI_API_KEY=your_openai_key
```

Gemini is tried first by default:

```env
AI_PROVIDER_PRIORITY=gemini,openai
GEMINI_MODEL=gemini-2.5-flash
GEMINI_FALLBACK_MODELS=gemini-2.5-flash,gemini-2.0-flash
OPENAI_MODEL=gpt-4o-mini
```

## 2. Backend Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
python run.py
```

Backend runs at `http://localhost:8000`.

API docs are available at `http://localhost:8000/docs`.

On Windows, prefer `python run.py` because it forces the Proactor event loop required by Playwright. If you use raw uvicorn, run without reload:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

For multi-browser support:

```bash
playwright install chromium firefox webkit
```

## 3. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

If your global `npm` launcher is broken, Vite can be started directly:

```bash
node .\node_modules\vite\bin\vite.js --host 127.0.0.1 --port 5173
```

Frontend runs at `http://localhost:5173`.

## 4. Docker Setup

```bash
cp .env.example .env
docker compose up --build
```

Open:

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000`

## Sample Prompts

- Go to Amazon and search iPhone 16
- Login with valid credentials and verify dashboard
- Test invalid password login
- Add first product to cart
- Verify checkout button exists
- Go to Amazon, search iPhone 16, sort price low to high
- Go to Amazon, search iPhone 16, filter by Apple
- Go to Amazon, search phone case, open the 10th product, set quantity to 2, add it to cart, and verify checkout button exists
- Go to Amazon, search phone case, open the 3rd product and click Buy Now
- Open Make My Trip search flights for 3 adults economy class from Hubli to Goa
- Open Make My Trip and search hotels in Goa for 2 adults 1 room
- Open Make My Trip and search cabs from Hubli to Goa

For login tests, either include credentials in the prompt or select a saved session. The app does not bypass authentication systems.

When Chromium is selected in the frontend, HINSA AI runs Playwright in visible headed mode so you can watch the live browser execution on your screen.

Amazon prompts default to `https://www.amazon.in`.

## Supported Actions

- `open_url`
- `click`
- `type`
- `search`
- `wait`
- `scroll`
- `screenshot`
- `verify_text`
- `verify_element`
- `add_to_cart`
- `login`
- `hover`
- `select_dropdown`
- `press_key`
- `sort_results`
- `filter_results`
- `verify_url`
- `open_product`
- `set_quantity`
- `buy_now`
- `click_button`
- `signup`
- `search_flights`
- `search_hotels`
- `search_cabs`

## How Execution Works

1. Frontend posts the prompt to `POST /api/tests/run`.
2. Backend creates a queued run and returns a WebSocket URL.
3. AI orchestrator calls Gemini Flash first and validates JSON.
4. Prompt cache stores repeated plans to avoid repeated LLM calls.
5. Playwright executes each allowed action with retries and dynamic locators.
6. Live logs stream through WebSockets.
7. Successful and failed step evidence screenshots are saved under `backend/storage/screenshots`.
8. HTML evidence reports with charts and proof cards are saved under `backend/storage/reports`.

## Reports

After a run finishes, open the report in the dashboard or visit:

```text
http://localhost:8000/api/reports/{run_id}
```

An example report is included at `samples/example-report.html`.

## API Documentation

See `docs/API.md`.

## Notes For Production

- Put FastAPI behind a reverse proxy with TLS.
- Replace the in-memory rate limiter with Redis for multi-instance deployments.
- Use a managed database if multiple workers need shared state.
- Rotate API keys regularly.
- Treat saved browser sessions like secrets.
