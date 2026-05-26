# Deployment

Recommended free setup:

- Backend API: Render free web service using `render.yaml`
- Frontend UI: Vercel Hobby project with root directory `frontend`

## 1. Deploy Backend On Render

1. Go to Render and choose **New > Blueprint**.
2. Connect GitHub repo `vrushh7/LLM-Web-Testing-Agent`.
3. Render should detect `render.yaml` in the repo root.
4. Before deploying, set these environment variables:

```env
GEMINI_API_KEY=your_gemini_key
OPENAI_API_KEY=your_openai_key
FRONTEND_ORIGINS=https://your-vercel-app.vercel.app
```

Only one AI key is required, but Gemini is tried first by default.

After Render deploys, copy your backend URL. It will look like:

```text
https://llm-web-testing-agent-api.onrender.com
```

Health check:

```text
https://llm-web-testing-agent-api.onrender.com/api/health
```

## 2. Deploy Frontend On Vercel

1. Import GitHub repo `vrushh7/LLM-Web-Testing-Agent`.
2. Set **Root Directory** to:

```text
frontend
```

3. Use these build settings:

```text
Framework Preset: Vite
Install Command: npm install
Build Command: npm run build
Output Directory: dist
```

4. Add this environment variable in Vercel:

```env
VITE_API_URL=https://your-render-backend-url.onrender.com
```

5. Deploy.

## 3. Update Backend CORS

After Vercel gives you a frontend URL, go back to Render and update:

```env
FRONTEND_ORIGINS=https://your-vercel-app.vercel.app
```

Then redeploy the Render backend.

## Free Tier Notes

- Render free web services can spin down after inactivity, so the first request after a quiet period may be slow.
- The current backend uses SQLite and local storage. On free hosting, data and reports are best treated as temporary.
- Never commit `.env` files or API keys to GitHub.
