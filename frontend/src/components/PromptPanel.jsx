import { Filter, Play, RotateCcw, Save, ShieldCheck, SlidersHorizontal } from 'lucide-react';

const samplePrompts = [
  'Go to Amazon and search iPhone 16',
  'Go to Amazon, search iPhone 16, sort price low to high',
  'Go to Amazon, search iPhone 16, open the 3rd product, set quantity to 2, add it to cart, and verify checkout button exists',
  'Go to Amazon, search phone case, open the 10th product and click Buy Now',
  'Open Make My Trip search flights for 3 adults economy class from Hubli to Goa',
  'Open Make My Trip and search hotels in Goa for 2 adults 1 room'
];

export default function PromptPanel({
  prompt,
  baseUrl,
  browser,
  maxRetries,
  sessionId,
  saveSessionName,
  sessions,
  loading,
  onChange,
  onRun
}) {
  return (
    <section className="ios-panel p-4 md:p-5">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Mission Builder</h2>
          <p className="text-sm text-muted">Search, sort, filter, verify, and capture evidence from one prompt.</p>
        </div>
        <div className="hidden items-center gap-2 rounded-lg border border-slate-700 bg-slate-950/60 px-3 py-2 text-xs text-slate-300 sm:flex">
          <ShieldCheck className="h-4 w-4 text-emerald-300" />
          Cloud LLM only
        </div>
      </div>

      {browser === 'chromium' && (
        <div className="mb-3 rounded-lg border border-cyan-400/20 bg-cyan-400/10 px-3 py-2 text-xs text-cyan-100">
          Live Chromium is visible during execution, so you can watch HINSA AI operate the browser.
        </div>
      )}

      <textarea
        className="control min-h-[150px] w-full resize-y p-4 text-sm leading-6"
        value={prompt}
        onChange={(event) => onChange('prompt', event.target.value)}
        placeholder="Describe the browser test to run..."
      />

      <div className="mt-3 flex flex-wrap gap-2">
        {samplePrompts.map((sample) => (
          <button
            key={sample}
            type="button"
            className="rounded-full border border-slate-700 bg-slate-950/60 px-3 py-1.5 text-xs text-slate-300 transition hover:border-blue-400 hover:text-blue-100"
            onClick={() => onChange('prompt', sample)}
          >
            {sample}
          </button>
        ))}
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <div className="rounded-lg border border-cyan-400/20 bg-cyan-400/10 p-3">
          <div className="mb-1 flex items-center gap-2 text-sm font-medium text-cyan-100">
            <SlidersHorizontal className="h-4 w-4" />
            Sorting
          </div>
          <p className="text-xs leading-5 text-cyan-100/75">Try price low to high, high to low, newest, or customer review.</p>
        </div>
        <div className="rounded-lg border border-emerald-400/20 bg-emerald-400/10 p-3">
          <div className="mb-1 flex items-center gap-2 text-sm font-medium text-emerald-100">
            <Filter className="h-4 w-4" />
            Filtering
          </div>
          <p className="text-xs leading-5 text-emerald-100/75">Use brand, price, rating, or category filters when the page exposes them.</p>
        </div>
      </div>

      <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-muted">Base URL</span>
          <input
            className="control h-11 w-full px-3 text-sm"
            value={baseUrl}
            onChange={(event) => onChange('baseUrl', event.target.value)}
            placeholder="https://your-app.com"
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-muted">Browser</span>
          <select className="control h-11 w-full px-3 text-sm" value={browser} onChange={(event) => onChange('browser', event.target.value)}>
            <option value="chromium">Chromium</option>
            <option value="firefox">Firefox</option>
            <option value="webkit">WebKit</option>
          </select>
        </label>
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-muted">Saved Session</span>
          <select className="control h-11 w-full px-3 text-sm" value={sessionId} onChange={(event) => onChange('sessionId', event.target.value)}>
            <option value="">No session</option>
            {sessions.map((session) => (
              <option key={session.id} value={session.id}>
                {session.name}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-muted">Retries</span>
          <input
            className="control h-11 w-full px-3 text-sm"
            type="number"
            min="0"
            max="5"
            value={maxRetries}
            onChange={(event) => onChange('maxRetries', event.target.value)}
          />
        </label>
      </div>

      <div className="mt-3 grid gap-3 md:grid-cols-[1fr_auto_auto]">
        <input
          className="control h-11 px-3 text-sm"
          value={saveSessionName}
          onChange={(event) => onChange('saveSessionName', event.target.value)}
          placeholder="Save login state as..."
        />
        <button
          type="button"
          className="inline-flex h-11 items-center justify-center gap-2 rounded-lg border border-slate-700 bg-slate-950/60 px-4 text-sm text-slate-200 transition hover:border-slate-500"
          onClick={() => onChange('saveSessionName', '')}
        >
          <RotateCcw className="h-4 w-4" />
          Clear
        </button>
        <button
          type="button"
          className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-cyan-400 px-5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-60"
          disabled={loading || !prompt.trim()}
          onClick={onRun}
        >
          {saveSessionName ? <Save className="h-4 w-4" /> : <Play className="h-4 w-4" />}
          {loading ? 'Starting...' : 'Run Test'}
        </button>
      </div>
    </section>
  );
}
