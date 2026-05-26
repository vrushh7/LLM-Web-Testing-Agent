import { Clock, RefreshCw } from 'lucide-react';
import { formatDate } from '../utils/date.js';
import StatusPill from './StatusPill.jsx';

export default function HistoryPanel({ history, activeRunId, onSelect, onRefresh }) {
  return (
    <section className="ios-panel p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Clock className="h-4 w-4 text-blue-200" />
          <h2 className="text-sm font-semibold">History</h2>
        </div>
        <button
          type="button"
          className="grid h-8 w-8 place-items-center rounded-lg border border-slate-700 bg-slate-950/60 text-slate-300 hover:border-blue-400 hover:text-blue-100"
          onClick={onRefresh}
          title="Refresh history"
        >
          <RefreshCw className="h-4 w-4" />
        </button>
      </div>
      <div className="space-y-2">
        {history.length === 0 ? (
          <p className="rounded-lg border border-dashed border-slate-700 p-4 text-sm text-slate-500">No runs yet.</p>
        ) : (
          history.map((run) => (
            <button
              key={run.id}
              type="button"
              className={`w-full rounded-lg border p-3 text-left transition ${
                activeRunId === run.id ? 'border-blue-400 bg-blue-500/10' : 'border-slate-800 bg-slate-950/50 hover:border-slate-600'
              }`}
              onClick={() => onSelect(run.id)}
            >
              <div className="mb-2 flex items-center justify-between gap-2">
                <StatusPill status={run.status} />
                <span className="text-xs text-muted">{formatDate(run.created_at)}</span>
              </div>
              <p className="line-clamp-2 text-sm text-slate-200">{run.prompt}</p>
            </button>
          ))
        )}
      </div>
    </section>
  );
}

