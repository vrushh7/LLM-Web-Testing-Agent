import { BarChart3, Camera, Clock3, Target } from 'lucide-react';

export default function RunAnalytics({ run }) {
  const steps = run?.steps || [];
  const passed = steps.filter((step) => step.status === 'passed').length;
  const failed = steps.filter((step) => step.status === 'failed').length;
  const total = Math.max(steps.length, run?.total_steps || 0, 1);
  const passRate = Math.round((passed / total) * 100);
  const screenshots = steps.filter((step) => step.screenshot_url).length;
  const duration = steps.reduce((sum, step) => sum + (step.duration_ms || 0), 0);
  const radius = 38;
  const circumference = 2 * Math.PI * radius;
  const dash = (passRate / 100) * circumference;
  const maxStep = Math.max(...steps.map((step) => step.duration_ms || 0), 1);

  return (
    <section className="ios-panel overflow-hidden p-4">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <BarChart3 className="h-4 w-4 text-cyan-200" />
          <h2 className="text-sm font-semibold">Run Analytics</h2>
        </div>
        <span className="rounded-full border border-cyan-400/20 bg-cyan-400/10 px-2.5 py-1 text-xs text-cyan-100">
          {passRate}% pass
        </span>
      </div>

      <div className="grid gap-4 lg:grid-cols-[126px_1fr]">
        <div className="grid place-items-center rounded-lg border border-slate-800 bg-slate-950/60 p-3">
          <svg viewBox="0 0 100 100" className="h-24 w-24">
            <circle cx="50" cy="50" r={radius} stroke="#1f2a44" strokeWidth="10" fill="none" />
            <circle
              cx="50"
              cy="50"
              r={radius}
              stroke="#5eead4"
              strokeWidth="10"
              fill="none"
              strokeLinecap="round"
              strokeDasharray={`${dash} ${circumference}`}
              transform="rotate(-90 50 50)"
            />
            <text x="50" y="54" textAnchor="middle" className="fill-white text-[18px] font-bold">
              {passRate}%
            </text>
          </svg>
        </div>

        <div className="grid gap-2 sm:grid-cols-3">
          <Metric icon={Target} label="Assertions" value={`${passed}/${total}`} />
          <Metric icon={Camera} label="Evidence" value={screenshots} />
          <Metric icon={Clock3} label="Duration" value={`${Math.round(duration / 1000)}s`} />
        </div>
      </div>

      <div className="mt-4 space-y-2">
        {steps.length === 0 ? (
          <div className="h-24 rounded-lg border border-dashed border-slate-700 bg-slate-950/50" />
        ) : (
          steps.map((step) => {
            const width = Math.max(8, Math.round(((step.duration_ms || 0) / maxStep) * 100));
            return (
              <div key={step.id} className="grid grid-cols-[64px_1fr_54px] items-center gap-2 text-xs">
                <span className="text-muted">Step {step.step_index}</span>
                <div className="h-2 overflow-hidden rounded-full bg-slate-800">
                  <div
                    className={`h-full rounded-full ${step.status === 'passed' ? 'bg-cyan-300' : 'bg-rose-300'}`}
                    style={{ width: `${width}%` }}
                  />
                </div>
                <span className="text-right text-slate-400">{step.duration_ms}ms</span>
              </div>
            );
          })
        )}
      </div>

      {failed > 0 && <p className="mt-3 text-xs text-rose-200">{failed} step needs attention. Open the report for full evidence.</p>}
    </section>
  );
}

function Metric({ icon: Icon, label, value }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
      <Icon className="mb-2 h-4 w-4 text-blue-200" />
      <p className="text-xs text-muted">{label}</p>
      <p className="mt-1 text-lg font-semibold text-white">{value}</p>
    </div>
  );
}

