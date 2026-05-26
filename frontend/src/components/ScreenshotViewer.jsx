import { Camera, Maximize2 } from 'lucide-react';
import { useMemo, useState } from 'react';
import { assetUrl } from '../services/api.js';

export default function ScreenshotViewer({ run }) {
  const screenshots = useMemo(() => (run?.steps || []).filter((step) => step.screenshot_url), [run]);
  const [selected, setSelected] = useState(0);
  const active = screenshots[selected] || screenshots[0];

  return (
    <section className="ios-panel p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Camera className="h-4 w-4 text-cyan-200" />
          <h2 className="text-sm font-semibold">Proof Gallery</h2>
        </div>
        <span className="text-xs text-muted">{screenshots.length} captured</span>
      </div>

      {active ? (
        <div>
          <a href={assetUrl(active.screenshot_url)} target="_blank" rel="noreferrer" className="group block overflow-hidden rounded-lg border border-slate-800 bg-slate-950">
            <img src={assetUrl(active.screenshot_url)} alt={`Step ${active.step_index}`} className="h-72 w-full object-cover object-top transition group-hover:scale-[1.01]" />
            <span className="flex items-center gap-2 border-t border-slate-800 px-3 py-2 text-xs text-slate-300">
              <Maximize2 className="h-3.5 w-3.5" />
              Step {active.step_index}: {active.message}
            </span>
          </a>
          <div className="mt-3 flex gap-2 overflow-x-auto pb-1">
            {screenshots.map((shot, index) => (
              <button
                key={shot.id}
                type="button"
                className={`h-16 w-24 shrink-0 overflow-hidden rounded-lg border ${index === selected ? 'border-blue-400' : 'border-slate-800'}`}
                onClick={() => setSelected(index)}
              >
                <img src={assetUrl(shot.screenshot_url)} alt="" className="h-full w-full object-cover" />
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="grid h-56 place-items-center rounded-lg border border-dashed border-slate-700 bg-slate-950/60 text-sm text-slate-500">
          Step-by-step proof screenshots appear here.
        </div>
      )}
    </section>
  );
}
