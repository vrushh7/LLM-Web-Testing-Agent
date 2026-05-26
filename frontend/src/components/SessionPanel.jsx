import { KeyRound, Trash2 } from 'lucide-react';
import { formatDate } from '../utils/date.js';

export default function SessionPanel({ sessions, onDelete }) {
  return (
    <section className="ios-panel p-4">
      <div className="mb-3 flex items-center gap-2">
        <KeyRound className="h-4 w-4 text-blue-200" />
        <h2 className="text-sm font-semibold">Saved Sessions</h2>
      </div>
      <div className="space-y-2">
        {sessions.length === 0 ? (
          <p className="rounded-lg border border-dashed border-slate-700 p-4 text-sm text-slate-500">
            Save login state after a successful authenticated run.
          </p>
        ) : (
          sessions.map((session) => (
            <div key={session.id} className="flex items-center justify-between gap-3 rounded-lg border border-slate-800 bg-slate-950/50 p-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-slate-100">{session.name}</p>
                <p className="text-xs text-muted">
                  {session.browser} · {formatDate(session.last_used_at || session.created_at)}
                </p>
              </div>
              <button
                type="button"
                className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-slate-700 text-slate-300 hover:border-rose-400 hover:text-rose-200"
                onClick={() => onDelete(session.id)}
                title="Delete session"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))
        )}
      </div>
    </section>
  );
}

