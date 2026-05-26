import { Activity, Circle, Terminal } from 'lucide-react';
import { formatTime } from '../utils/date.js';

const eventColor = {
  status: 'text-blue-200',
  log: 'text-slate-300',
  step_started: 'text-cyan-200',
  step_finished: 'text-emerald-200',
  report: 'text-violet-200'
};

export default function ExecutionConsole({ events, connected }) {
  return (
    <section className="ios-panel flex min-h-[360px] flex-col p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Terminal className="h-4 w-4 text-blue-200" />
          <h2 className="text-sm font-semibold">Live Execution</h2>
        </div>
        <span className={`inline-flex items-center gap-2 text-xs ${connected ? 'text-emerald-300' : 'text-slate-400'}`}>
          <Circle className={`h-2.5 w-2.5 ${connected ? 'fill-emerald-300' : 'fill-slate-500'}`} />
          {connected ? 'Connected' : 'Idle'}
        </span>
      </div>
      <div className="min-h-0 flex-1 overflow-auto rounded-lg border border-slate-800 bg-slate-950/80 p-3 font-mono text-xs">
        {events.length === 0 ? (
          <div className="flex h-full min-h-[260px] items-center justify-center text-slate-500">
            <div className="text-center">
              <Activity className="mx-auto mb-3 h-7 w-7" />
              Execution logs will appear here.
            </div>
          </div>
        ) : (
          <div className="space-y-2">
            {events.map((event, index) => (
              <div key={`${event.timestamp}-${index}`} className="grid grid-cols-[76px_1fr] gap-3">
                <span className="text-slate-500">{formatTime(event.timestamp)}</span>
                <span className={eventColor[event.type] || 'text-slate-300'}>{event.message}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

