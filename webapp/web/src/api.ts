// Thin API client for the omp-agent webapp backend.
// v1: localhost only (the backend binds 127.0.0.1).

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

async function req<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new Error(`${res.status} ${res.statusText}: ${body.slice(0, 200)}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => req<{ ok: boolean }>('/api/health'),

  listProjects: () => req<Project[]>('/api/projects'),

  createProject: (name: string, repoPath: string, scratchPath: string) =>
    req<Project>('/api/projects', {
      method: 'POST',
      body: JSON.stringify({ name, repo_path: repoPath, scratch_path: scratchPath }),
    }),

  startSession: (projectId: number) =>
    req<Session>(`/api/projects/${projectId}/sessions`, { method: 'POST' }),

  newTask: (sessionId: number, message: string) =>
    req<Task>(`/api/sessions/${sessionId}/tasks`, {
      method: 'POST',
      body: JSON.stringify({ message }),
    }),

  decide: (taskId: number, decision: string, note = '') =>
    req<Task>(`/api/tasks/${taskId}/decide`, {
      method: 'POST',
      body: JSON.stringify({ decision, note }),
    }),

  clarify: (taskId: number, answers: string) =>
    req<Task>(`/api/tasks/${taskId}/clarify`, {
      method: 'POST',
      body: JSON.stringify({ answers }),
    }),

  taskEvents: (taskId: number) => req<Event[]>(`/api/tasks/${taskId}/events`),

  taskArtifacts: (taskId: number) =>
    req<{ design_path: string | null; recipe_path: string | null }>(
      `/api/tasks/${taskId}/artifacts`
    ),

  denyLog: () => req<{ entries: string[] }>('/api/deny-log'),
};
