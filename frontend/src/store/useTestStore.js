import { create } from 'zustand';
import { api } from '../services/api.js';

const defaultPrompt = 'Go to Amazon and search iPhone 16';

export const useTestStore = create((set, get) => ({
  prompt: defaultPrompt,
  baseUrl: '',
  browser: 'chromium',
  sessionId: '',
  saveSessionName: '',
  maxRetries: 2,
  activeRun: null,
  events: [],
  history: [],
  sessions: [],
  loading: false,
  error: '',

  setField: (key, value) => set({ [key]: value }),

  startRun: async () => {
    const state = get();
    set({ loading: true, error: '', events: [], activeRun: null });
    try {
      const payload = {
        prompt: state.prompt,
        base_url: state.baseUrl || null,
        browser: state.browser,
        session_id: state.sessionId || null,
        save_session_name: state.saveSessionName || null,
        headless: state.browser === 'chromium' ? false : null,
        max_retries: Number(state.maxRetries)
      };
      const { data } = await api.post('/tests/run', payload);
      set({
        activeRun: {
          id: data.run_id,
          status: data.status,
          prompt: state.prompt,
          steps: []
        },
        loading: false
      });
      return data;
    } catch (error) {
      set({ loading: false, error: error.response?.data?.detail || error.message });
      throw error;
    }
  },

  handleEvent: async (event) => {
    set((state) => ({
      events: [...state.events.slice(-299), event],
      activeRun: state.activeRun
        ? {
            ...state.activeRun,
            status: event.status || state.activeRun.status,
            report_url: event.payload?.report_url || state.activeRun.report_url
          }
        : state.activeRun
    }));

    if (['passed', 'failed', 'cancelled'].includes(event.status)) {
      await get().fetchRun(event.run_id);
      await get().fetchHistory();
      await get().fetchSessions();
    }
  },

  fetchRun: async (runId) => {
    if (!runId) return;
    const { data } = await api.get(`/tests/${runId}`);
    set({ activeRun: data });
  },

  fetchHistory: async () => {
    const { data } = await api.get('/tests?limit=30');
    set({ history: data });
  },

  fetchSessions: async () => {
    const { data } = await api.get('/sessions');
    set({ sessions: data });
  },

  deleteSession: async (sessionId) => {
    await api.delete(`/sessions/${sessionId}`);
    await get().fetchSessions();
    if (get().sessionId === sessionId) {
      set({ sessionId: '' });
    }
  }
}));
