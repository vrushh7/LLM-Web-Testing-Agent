import { ExternalLink, FileText } from 'lucide-react';
import { assetUrl } from '../services/api.js';

export default function ReportViewer({ run }) {
  const report = run?.report_url ? assetUrl(run.report_url) : '';

  return (
    <section className="ios-panel p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-blue-200" />
          <h2 className="text-sm font-semibold">Evidence Report</h2>
        </div>
        {report && (
          <a className="inline-flex items-center gap-1 text-xs text-blue-200 hover:text-blue-100" href={report} target="_blank" rel="noreferrer">
            <ExternalLink className="h-3.5 w-3.5" />
            Open
          </a>
        )}
      </div>
      {report ? (
        <iframe title="HTML report" src={report} className="h-[420px] w-full rounded-lg border border-slate-800 bg-slate-950" />
      ) : (
        <div className="grid h-[420px] place-items-center rounded-lg border border-dashed border-slate-700 bg-slate-950/60 text-sm text-slate-500">
          The HTML report loads when execution finishes.
        </div>
      )}
    </section>
  );
}
