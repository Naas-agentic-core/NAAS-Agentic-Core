import { useEffect, useMemo, useReducer } from "react";

const PHASE_MAPPING = {
  'CONTEXT_ENRICHMENT': 'contextualize',
  'PLANNING': 'plan',
  'DESIGN': 'design',
  'EXECUTION': 'execute',
  'REFLECTION': 'review',
  'RE-PLANNING': 'replan',
  'RESEARCH': 'research',
};

const initialState = {
  activeRunId: null,
  lastSeq: -1,
  runs: {} // { [runId]: { phases: { [mappedPhase]: status } } }
};

function timelineReducer(state, action) {
  const { type, payload } = action;

  // Global Reset
  if (type === 'RESET_ALL') {
    return initialState;
  }

  // Idempotency / Ordering Check (Monotonic Sequence)
  // We only enforce strict ordering if seq is provided.
  if (payload.seq !== undefined && payload.seq <= state.lastSeq) {
    // Duplicate or out-of-order event, ignore for state consistency
    return state;
  }

  // Update lastSeq
  const nextSeq = payload.seq !== undefined ? payload.seq : state.lastSeq;

  // 1. Handle New Run Start (Run Isolation)
  if (type === 'RUN_STARTED') {
    const runId = payload.run_id;
    // CRITICAL FIX: Always switch activeRunId on new run start to force UI update
    // This allows iteration loops to be visualized as distinct runs if they share IDs with iteration suffix
    return {
      ...state,
      lastSeq: nextSeq,
      activeRunId: runId,
      runs: {
        ...state.runs,
        [runId]: state.runs[runId] || { phases: {} }
      }
    };
  }

  // 2. Handle Phase Updates (Canonical & Legacy)
  if (type === 'PHASE_UPDATE') {
    const rawPhase = payload.phase;
    const mappedPhase = PHASE_MAPPING[rawPhase] || rawPhase?.toLowerCase();

    if (!mappedPhase) return { ...state, lastSeq: nextSeq };

    // Determine Run Context
    // Prefer payload.run_id, fallback to activeRunId, fallback to 'default'
    const runId = payload.run_id || state.activeRunId || 'default_run';

    // Auto-switch active run if we receive a strongly typed run_id
    // This ensures we follow the backend's lead on which run is active
    const newActiveRunId = (payload.run_id && payload.run_id !== state.activeRunId)
        ? payload.run_id
        : state.activeRunId;

    const currentRunState = state.runs[runId] || { phases: {} };
    const newStatus = payload.status; // 'running' | 'completed'

    // State Transition Validation (Simple FSM)
    // Prevent regression from 'completed' to 'running' within the SAME run/phase
    const currentStatus = currentRunState.phases[mappedPhase];
    if (currentStatus === 'completed' && newStatus === 'running') {
       // Illegal transition within same run -> Ignore
       return { ...state, lastSeq: nextSeq };
    }

    return {
      ...state,
      lastSeq: nextSeq,
      activeRunId: newActiveRunId || runId,
      runs: {
        ...state.runs,
        [runId]: {
          ...currentRunState,
          phases: {
            ...currentRunState.phases,
            [mappedPhase]: newStatus
          }
        }
      }
    };
  }

  return state;
}

/**
 * هاد الخطاف (Hook) يقوم بإدارة ومتابعة الجدول الزمني لمراحل عمل الوكيل (Agent).
 * يقوم بتجميع الحالات من جميع الدورات (Runs) لضمان إظهار التقدم التراكمي بشكل صحيح.
 */
export function useAgentTimeline() {
  const [state, dispatch] = useReducer(timelineReducer, initialState);

  useEffect(() => {
    const handler = (e) => {
      const data = e.detail;
      if (!data || !data.type) return;

      // --- Canonical Events (New Backend) ---
      if (data.type === 'RUN_STARTED') {
        dispatch({ type: 'RUN_STARTED', payload: data.payload });
        return;
      }

      if (data.type === 'PHASE_STARTED') {
        dispatch({
          type: 'PHASE_UPDATE',
          payload: { ...data.payload, status: 'running' }
        });
        return;
      }

      if (data.type === 'PHASE_COMPLETED') {
        dispatch({
          type: 'PHASE_UPDATE',
          payload: { ...data.payload, status: 'completed' }
        });
        return;
      }

      // --- Legacy Support (Old Backend / Fallbacks) ---
      if (data.type === 'phase_start') {
         dispatch({
           type: 'PHASE_UPDATE',
           payload: { ...data.payload, status: 'running' }
         });
      } else if (data.type === 'phase_completed') {
         dispatch({
           type: 'PHASE_UPDATE',
           payload: { ...data.payload, status: 'completed' }
         });
      } else if (data.type === 'conversation_init') {
         dispatch({ type: 'RESET_ALL', payload: {} });
      }
    };

    window.addEventListener("agent:event", handler);
    return () => window.removeEventListener("agent:event", handler);
  }, []);

  // Transform State to flat Events Array for Component Compatibility
  // Fix: Aggregate phases from ALL runs to show cumulative progress
  return useMemo(() => {
    const allPhases = {};

    // Sort runs to ensure later runs overwrite earlier ones if needed (chronological order)
    // We use numeric localeCompare to correctly handle mission:9 vs mission:10
    Object.keys(state.runs)
      .sort((a, b) => a.localeCompare(b, undefined, { numeric: true }))
      .forEach((runId) => {
        const runPhases = state.runs[runId].phases;
        Object.assign(allPhases, runPhases);
      });

    return Object.entries(allPhases).map(([phase, status]) => ({
      phase,
      status,
    }));
  }, [state.runs]);
}
