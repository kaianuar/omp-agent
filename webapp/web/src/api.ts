// Thin API client for the omp-agent webapp — WebSocket-only JSON-RPC.
//
// All calls travel over ONE websocket as JSON messages:
//   Request:  {"id": 1, "method": "projects.list", "params": {}}
//   Response: {"id": 1, "result": [...]}
//   Event:    {"type": "event", "event": {...}}   (live push, handled by onEvent)
//
// The method signatures match the old REST client, so callers are unchanged.

export interface Project {
  id: number;
  name: string;
  repo_path: string;
  scratch_path: string;
  created_at: string;
}

export interface Session {
  id: number;
  project_id: number;
  status: string;
  started_at: string;
}

export interface Task {
  id: number;
  session_id: number;
  intent: string | null;
  state: string;
  design_path: string | null;
  recipe_path: string | null;
  pr_url: string | null;
  created_at: string;
}

export interface Event {
  id: number;
  task_id: number;
  kind: string;
  payload: Record<string, unknown>;
  ts: string;
}

type Handler = (ev: Event) => void;

class RpcClient {
  private ws: WebSocket | null = null;
  private nextId = 1;
  private pending = new Map<number, { resolve: (v: unknown) => void; reject: (e: Error) => void }>();
  private onEventHandler: Handler | null = null;
  private connected: Promise<void> | null = null;

  /** Connect (idempotent). Resolves when the socket is open. */
  connect(): Promise<void> {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) return Promise.resolve();
    if (this.connected) return this.connected;

    this.connected = new Promise((resolve, reject) => {
      const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
      const ws = new WebSocket(`${proto}://${window.location.host}/ws`);
      this.ws = ws;
      ws.onopen = () => resolve();
      ws.onerror = () => reject(new Error('ws connection failed'));
      ws.onmessage = (msg) => {
        let data: Record<string, unknown>;
        try { data = JSON.parse(msg.data as string); } catch { return; }
        if (data.type === 'event') {
          this.onEventHandler?.(data.event as Event);
          return;
        }
        const id = data.id as number;
        const p = this.pending.get(id);
        if (!p) return;
        this.pending.delete(id);
        if (data.error) p.reject(new Error(String(data.error)));
        else p.resolve(data.result);
      };
      ws.onclose = () => {
        this.ws = null;
        this.connected = null;
        // Reject all pending (the caller can retry).
        for (const [, p] of this.pending) p.reject(new Error('ws closed'));
        this.pending.clear();
      };
    });
    return this.connected;
  }

  /** Set the live-event handler (called for every pushed event). */
  onEvent(h: Handler) { this.onEventHandler = h; }

  /** Call an RPC method and await its correlated response. */
  async call<T>(method: string, params: Record<string, unknown> = {}): Promise<T> {
    await this.connect();
    const id = this.nextId++;
    return new Promise<T>((resolve, reject) => {
      this.pending.set(id, { resolve: resolve as (v: unknown) => void, reject });
      this.ws?.send(JSON.stringify({ id, method, params }));
      // Safety timeout (builds can take minutes; RPC itself is fast).
      setTimeout(() => {
        if (this.pending.has(id)) {
          this.pending.delete(id);
          reject(new Error(`rpc timeout: ${method}`));
        }
      }, 30_000);
    });
  }

  /** Bind the socket to a session (starts live event push + history replay). */
  bind(sessionId: number) {
    void this.call('sessions.bind', { session_id: sessionId }).catch(() => undefined);
  }
}

const rpc = new RpcClient();

export const api = {
  onEvent: (h: Handler) => rpc.onEvent(h),

  bind: (sessionId: number) => rpc.bind(sessionId),

  health: () => rpc.call<{ ok: boolean }>('health'),

  listModels: () =>
    rpc.call<{ models: { id: string; name: string; provider: string }[] }>('models.list'),

  getRoles: () =>
    rpc.call<{
      configured: boolean;
      roles: Record<string, string>;
      defaults: Record<string, string>;
    }>('roles.get'),

  setRoles: (roles: Record<string, string>) =>
    rpc.call<{
      configured: boolean;
      roles: Record<string, string>;
      defaults: Record<string, string>;
    }>('roles.set', { roles }),

  listProjects: () => rpc.call<Project[]>('projects.list'),

  createProject: (name: string, repoPath: string, scratchPath: string) =>
    rpc.call<Project>('projects.create', { name, repo_path: repoPath, scratch_path: scratchPath }),

  fsList: (path = '') =>
    rpc.call<{ path: string; dirs: { name: string; path: string }[] }>('fs.list', { path }),

  startSession: (projectId: number) =>
    rpc.call<Session>('sessions.create', { project_id: projectId }),

  listSessions: (projectId: number) =>
    rpc.call<Session[]>('sessions.list', { project_id: projectId }),

  sessionTasks: (sessionId: number) =>
    rpc.call<Task[]>('sessions.tasks', { session_id: sessionId }),

  newTask: (sessionId: number, message: string) =>
    rpc.call<Task>('tasks.create', { session_id: sessionId, message }),

  decide: (taskId: number, decision: string, note = '') =>
    rpc.call<Task>('tasks.decide', { task_id: taskId, decision, note }),

  clarify: (taskId: number, answers: string) =>
    rpc.call<Task>('tasks.clarify', { task_id: taskId, answers }),

  taskEvents: (taskId: number) => rpc.call<Event[]>('tasks.events', { task_id: taskId }),

  cancelTask: (taskId: number) => rpc.call<{ cancelled: boolean }>('tasks.cancel', { task_id: taskId }),

  getTask: (taskId: number) => rpc.call<Task>('tasks.get', { task_id: taskId }),

  denyLog: () => rpc.call<{ entries: string[] }>('deny.log'),
};
