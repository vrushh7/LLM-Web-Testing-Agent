import { CheckCircle2, ListChecks, XCircle } from 'lucide-react';

export default function StepTimeline({ run }) {
  const steps = run?.steps || [];

  return (
    <section className="ios-panel p-4">
      <div className="mb-3 flex items-center gap-2">
        <ListChecks className="h-4 w-4 text-cyan-200" />
        <h2 className="text-sm font-semibold">Evidence Timeline</h2>
      </div>
      {steps.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-700 p-4 text-sm text-slate-500">Steps appear after the first result is recorded.</div>
      ) : (
        <div className="space-y-2">
          {steps.map((step) => (
            <div key={step.id} className="grid grid-cols-[28px_1fr_auto] items-start gap-3 rounded-lg border border-slate-800 bg-slate-950/50 p-3">
              {step.status === 'passed' ? <CheckCircle2 className="mt-0.5 h-4 w-4 text-emerald-300" /> : <XCircle className="mt-0.5 h-4 w-4 text-rose-300" />}
              <div className="min-w-0">
                <p className="text-sm font-medium text-slate-100">
                  {step.step_index}. {step.action}
                </p>
                <p className="mt-1 text-xs leading-5 text-muted">{step.message || step.target}</p>
              </div>
              <span className="text-xs text-slate-500">{step.duration_ms}ms</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
