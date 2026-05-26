const styles = {
  queued: 'bg-slate-700 text-slate-100',
  planning: 'bg-blue-500/20 text-blue-200 border-blue-400/30',
  executing: 'bg-cyan-500/20 text-cyan-200 border-cyan-400/30',
  passed: 'bg-emerald-500/20 text-emerald-200 border-emerald-400/30',
  failed: 'bg-rose-500/20 text-rose-200 border-rose-400/30',
  cancelled: 'bg-amber-500/20 text-amber-200 border-amber-400/30'
};

export default function StatusPill({ status = 'queued' }) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold ${styles[status] || styles.queued}`}>
      {status}
    </span>
  );
}

