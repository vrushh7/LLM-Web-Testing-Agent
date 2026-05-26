import { CheckCircle2, Gauge, History, Layers, Orbit, ShieldCheck, Sparkles, XCircle } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import ExecutionConsole from '../components/ExecutionConsole.jsx';
import HistoryPanel from '../components/HistoryPanel.jsx';
import PromptPanel from '../components/PromptPanel.jsx';
import ReportViewer from '../components/ReportViewer.jsx';
import RunAnalytics from '../components/RunAnalytics.jsx';
import ScreenshotViewer from '../components/ScreenshotViewer.jsx';
import SessionPanel from '../components/SessionPanel.jsx';
import StatCard from '../components/StatCard.jsx';
import StatusPill from '../components/StatusPill.jsx';
import StepTimeline from '../components/StepTimeline.jsx';
import { useRunSocket } from '../hooks/useRunSocket.js';
import { useTestStore } from '../store/useTestStore.js';

export default function Dashboard() {
  const [socketUrl, setSocketUrl] = useState('');
  const {
    prompt,
    baseUrl,
    browser,
    sessionId,
    saveSessionName,
    maxRetries,
    activeRun,
    events,
    history,
    sessions,
    loading,
    error,
    setField,
    startRun,
    handleEvent,
    fetchRun,
    fetchHistory,
    fetchSessions,
    deleteSession
  } = useTestStore();

  useEffect(() => {
    fetchHistory();
    fetchSessions();
  }, [fetchHistory, fetchSessions]);

  const onEvent = useCallback(
    (event) => {
      handleEvent(event);
    },
    [handleEvent]
  );
  const connected = useRunSocket(socketUrl, onEvent);

  const runTest = async () => {
    const queued = await startRun();
    setSocketUrl(queued.websocket_url);
  };

  const status = activeRun?.status || 'idle';
  const passed = activeRun?.passed_steps || 0;
  const failed = activeRun?.failed_steps || 0;
  const total = activeRun?.total_steps || 0;

  return (
    <main className="min-h-screen px-4 py-5 md:px-6 lg:px-8">
      <header className="mx-auto mb-5 max-w-[1660px]">
        <div className="ios-panel flex flex-col gap-5 overflow-hidden p-5 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-4">
            <div className="grid h-14 w-14 place-items-center rounded-lg border border-cyan-300/30 bg-cyan-300/10">
              <Orbit className="h-7 w-7 text-cyan-200" />
            </div>
            <div>
              <div className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-cyan-200">
                <Sparkles className="h-3.5 w-3.5" />
                Autonomous QA SaaS
              </div>
              <h1 className="text-2xl font-semibold tracking-normal text-white md:text-4xl">HINSA AI</h1>
              <p className="text-sm text-muted">Browser missions with live proof, analytics, and visual evidence.</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <div className="inline-flex items-center gap-2 rounded-lg border border-emerald-400/20 bg-emerald-400/10 px-3 py-2 text-xs text-emerald-100">
              <ShieldCheck className="h-4 w-4" />
              Evidence screenshots enabled
            </div>
            <StatusPill status={status === 'idle' ? 'queued' : status} />
            <span className="rounded-lg border border-slate-700 bg-slate-950/60 px-3 py-2 text-xs text-slate-300">
              {connected ? 'Live socket active' : 'Socket idle'}
            </span>
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-[1660px] gap-4 xl:grid-cols-[320px_1fr_470px]">
        <aside className="space-y-4 xl:sticky xl:top-5 xl:self-start">
          <HistoryPanel history={history} activeRunId={activeRun?.id} onSelect={fetchRun} onRefresh={fetchHistory} />
          <SessionPanel sessions={sessions} onDelete={deleteSession} />
        </aside>

        <section className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard icon={Layers} label="Total Steps" value={total} />
            <StatCard icon={CheckCircle2} label="Passed" value={passed} tone="text-emerald-200" />
            <StatCard icon={XCircle} label="Failed" value={failed} tone="text-rose-200" />
            <StatCard icon={Gauge} label="Retries" value={maxRetries} />
          </div>

          <PromptPanel
            prompt={prompt}
            baseUrl={baseUrl}
            browser={browser}
            sessionId={sessionId}
            saveSessionName={saveSessionName}
            maxRetries={maxRetries}
            sessions={sessions}
            loading={loading}
            onChange={setField}
            onRun={runTest}
          />

          {error && <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-100">{error}</div>}

          <ExecutionConsole events={events} connected={connected} />
        </section>

        <aside className="space-y-4 xl:sticky xl:top-5 xl:self-start">
          <RunAnalytics run={activeRun} />
          <ScreenshotViewer run={activeRun} />
          <ReportViewer run={activeRun} />
          <StepTimeline run={activeRun} />
          <section className="ios-panel p-4">
            <div className="flex items-center gap-2">
              <History className="h-4 w-4 text-blue-200" />
              <h2 className="text-sm font-semibold">Run ID</h2>
            </div>
            <p className="mt-3 break-all rounded-lg border border-slate-800 bg-slate-950/60 p-3 font-mono text-xs text-slate-300">
              {activeRun?.id || 'No active run'}
            </p>
          </section>
        </aside>
      </div>
    </main>
  );
}
