export default function StatCard({ icon: Icon, label, value, tone = 'text-white' }) {
  return (
    <div className="ios-panel metric-glow p-4">
      <div className="flex items-center gap-3">
        <div className="grid h-9 w-9 place-items-center rounded-lg border border-cyan-400/20 bg-cyan-400/10">
          <Icon className="h-4 w-4 text-cyan-200" />
        </div>
        <div>
          <p className="text-xs text-muted">{label}</p>
          <p className={`text-xl font-semibold ${tone}`}>{value}</p>
        </div>
      </div>
    </div>
  );
}
