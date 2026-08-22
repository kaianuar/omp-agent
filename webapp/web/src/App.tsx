// omp-agent webapp — chat with the orchestrator, cards-in-stream.
// v1: one project, one session, tasks run sequentially.

import { useEffect, useRef, useState } from 'react';
import { api, Event, Project, Session, Task } from './api';
import './styles.css';

// ── Event → card rendering ────────────────────────────────────────────

/** Inline answer box for the clarify card. */
function ClarifyBox({ taskId, onClarify }: { taskId: number; onClarify: (taskId: number, answers: string) => void }) {
  const [answers, setAnswers] = useState('');
  return (
    <div className="clarify-box">
      <textarea
        data-testid="clarify-input"
        placeholder="Answer each question (e.g. 1. older than 180 days, 2. as a new tab, 3. reveal and delete)"
        value={answers}
        onChange={(e) => setAnswers(e.target.value)}
        rows={2}
      />
      <div className="actions">
        <button data-testid="clarify-submit" onClick={() => onClarify(taskId, answers)} disabled={!answers.trim()}>
          Answer
        </button>
      </div>
    </div>
  );
}

/** Design proposal card — Approve, or Reject with feedback (adjust path). */
function DesignCard({ ev, onDecide }: { ev: Event; onDecide: (d: string, note?: string) => void }) {
  const [rejecting, setRejecting] = useState(false);
  const [feedback, setFeedback] = useState('');
  const p = ev.payload;
  return (
    <div className="card card-design" data-testid="card-design">
      <b>Design proposal</b>
      <pre className="doc">{String(p.content ?? '').slice(0, 3000)}</pre>
      {!rejecting ? (
        <div className="actions">
          <button data-testid="approve" onClick={() => onDecide('approve')}>Approve</button>
          <button data-testid="reject" onClick={() => setRejecting(true)}>Adjust…</button>
        </div>
      ) : (
        <div className="clarify-box">
          <textarea
            data-testid="design-feedback"
            placeholder="What should change? e.g. use a sidebar instead of a tab, keep it read-only…"
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            rows={2}
          />
          <div className="actions">
            <button
              data-testid="reject-submit"
              onClick={() => onDecide('reject', feedback)}
              disabled={!feedback.trim()}
            >
              Regenerate design
            </button>
            <button onClick={() => setRejecting(false)}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  );
}

/** The three roles a user must assign models to. */
const ROLES = ['orchestrator', 'builder', 'critic'] as const;

/** Role → model picker (shared by the setup wizard + settings panel).
 * Includes a provider filter + model search (461+ models needs it). */
function RolePicker({
  roles, models, onChange,
}: {
  roles: Record<string, string>;
  models: { id: string; name: string; provider: string }[];
  onChange: (roles: Record<string, string>) => void;
}) {
  const [filter, setFilter] = useState('all');
  const [query, setQuery] = useState('');

  const ROLE_LABELS: Record<string, string> = {
    orchestrator: 'Orchestrator (brain: intake/design/recipe)',
    builder: 'Builder (writes code)',
    critic: 'Critic (adversarial review)',
  };

  // Providers derived from the model ids (deduped, sorted).
  const providers = Array.from(new Set(models.map((m) => m.provider))).sort();

  // Apply provider filter + name/id search.
  const visible = models.filter((m) => {
    if (filter !== 'all' && m.provider !== filter) return false;
    if (query.trim()) {
      const q = query.trim().toLowerCase();
      if (!m.name.toLowerCase().includes(q) && !m.id.toLowerCase().includes(q)) return false;
    }
    return true;
  });

  const set = (role: string, id: string) => onChange({ ...roles, [role]: id });
  return (
    <div className="role-picker" data-testid="role-picker">
      <div className="model-tools">
        <select
          className="provider-filter"
          data-testid="provider-filter"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        >
          <option value="all">All providers ({models.length})</option>
          {providers.map((p) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>
        <input
          className="model-search"
          data-testid="model-search"
          placeholder="Search model…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>
      {Object.keys(ROLE_LABELS).map((role) => (
        <div className="role-row" key={role}>
          <label>{ROLE_LABELS[role]}</label>
          <select
            data-testid={`role-${role}`}
            value={roles[role] ?? ''}
            onChange={(e) => set(role, e.target.value)}
          >
            <option value="" disabled>— select a model —</option>
            {visible.map((m) => (
              <option key={m.id} value={m.id}>{m.name} — {m.provider}</option>
            ))}
          </select>
        </div>
      ))}
    </div>
  );
}

function cardFor(ev: Event, onDecide: (d: string, note?: string) => void, onClarify: (taskId: number, answers: string) => void) {
  const p = ev.payload;
  switch (ev.kind) {
    case 'intake':
      return <div className="card" key={ev.id} data-testid="card-intake">
        <b>Orchestrator:</b> understood — {(p.intent as { goal?: string })?.goal ?? 'request received'}
      </div>;
    case 'clarify_needed':
      return <div className="card card-question" key={ev.id} data-testid="card-clarify">
        <b>A few questions:</b>
        <ul>{(p.questions as string[] ?? []).map((q, i) => <li key={i}>{q}</li>)}</ul>
        <ClarifyBox taskId={ev.task_id} onClarify={onClarify} />
      </div>;
    case 'design_ready':
      return <DesignCard key={ev.id} ev={ev} onDecide={onDecide} />;
    case 'recipe_ready':
      return <div className="card" key={ev.id} data-testid="card-recipe">
        <b>Recipe ready</b>
        <pre className="doc">{String(p.content ?? '').slice(0, 1500)}</pre>
        <div className="actions">
          <button data-testid="approve-recipe" onClick={() => onDecide('approve')}>Build it</button>
        </div>
      </div>;
    case 'build_started':
      return <div className="card card-build" key={ev.id} data-testid="card-build">
        <b>Building…</b> <span className="muted">recipe dispatched to builder</span>
      </div>;
    case 'build_progress':
      return <div className="card card-build card-progress" key={ev.id} data-testid="card-progress">
        <span className="muted">▸</span> <code>{String(p.line ?? '')}</code>
      </div>;
    case 'pr_ready':
      return <div className="card" key={ev.id} data-testid="card-pr">
        <b>PR open:</b> <a href={String(p.url)} target="_blank" rel="noreferrer">{String(p.url)}</a>
      </div>;
    case 'critic_verdict':
      return <div className="card" key={ev.id} data-testid="card-critic">
        <b>Critic review:</b> {p.passed ? <span className="ok">PASS</span> : <span className="fail">FAIL</span>}
        <pre className="doc">{String(p.text ?? '').slice(0, 2000)}</pre>
      </div>;
    case 'critic_passed':
      return <div className="card card-ok" key={ev.id} data-testid="card-critic-pass">
        <b>Critic passed</b> (round {String(p.round)}) — moving to verify.
      </div>;
    case 'fix_round_started':
      return <div className="card card-build" key={ev.id} data-testid="card-fix">
        <b>Fix round {String(p.round)}</b> — re-dispatching builder with critic verdicts.
      </div>;
    case 'verify_result':
      return <div className="card" key={ev.id} data-testid="card-verify">
        <b>Verification</b>
        <pre className="doc">{JSON.stringify(p.results, null, 2).slice(0, 1500)}</pre>
      </div>;
    case 'fix_exhausted':
      return <div className="card card-warn" key={ev.id} data-testid="card-exhausted">
        <b>Fix rounds exhausted — needs your decision.</b>
        <pre className="doc">{String(p.verdict ?? '').slice(0, 1500)}</pre>
      </div>;
    case 'no_pr':
      return <div className="card" key={ev.id} data-testid="card-nopr">
        <b>Note:</b> {String(p.note ?? '')}
      </div>;
    default:
      return <div className="card card-dim" key={ev.id} data-testid="card-other">
        <span className="muted">{ev.kind}</span>
      </div>;
  }
}

// ── App ───────────────────────────────────────────────────────────────

export default function App() {
  const [project, setProject] = useState<Project | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [session, setSession] = useState<Session | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [task, setTask] = useState<Task | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [denyLog, setDenyLog] = useState<string[]>([]);
  const [showNewProject, setShowNewProject] = useState(false);
  const [newProjName, setNewProjName] = useState('');
  const [newProjPath, setNewProjPath] = useState('');
  const [browsePath, setBrowsePath] = useState('');
  const [browseDirs, setBrowseDirs] = useState<{ name: string; path: string }[]>([]);
  const [browsing, setBrowsing] = useState(false);
  const [theme, setTheme] = useState<'dark' | 'light'>(
    () => (localStorage.getItem('omp-theme') as 'dark' | 'light') || 'dark'
  );
  const [rolesConfig, setRolesConfig] = useState<{
    configured: boolean;
    roles: Record<string, string>;
    defaults: Record<string, string>;
  } | null>(null);
  const [models, setModels] = useState<{ id: string; name: string; provider: string }[]>([]);
  const [showSettings, setShowSettings] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Apply + persist the theme.
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('omp-theme', theme);
  }, [theme]);

  const toggleTheme = () => setTheme((t) => (t === 'dark' ? 'light' : 'dark'));

  // Load role config + model list on startup.
  useEffect(() => {
    void (async () => {
      try {
        const [rc, ml] = await Promise.all([api.getRoles(), api.listModels()]);
        setRolesConfig(rc);
        setModels(ml.models);
      } catch { /* non-fatal; wizard can't show but app still works */ }
    })();
  }, []);

  // Save role assignments (from wizard or settings) and mark configured.
  const saveRoles = async (roles: Record<string, string>) => {
    const rc = await api.setRoles(roles);
    setRolesConfig(rc);
    setShowSettings(false);
  };

  // Subscribe to live events over the shared WS RPC socket.
  useEffect(() => {
    api.onEvent((ev) => {
      setEvents((prev) => {
        if (prev.some((e) => e.id === ev.id)) return prev;
        return [...prev, ev];
      });
    });
  }, []);

  // Bind the socket to the current session (starts live push + replay).
  useEffect(() => {
    if (session) api.bind(session.id);
  }, [session?.id]);

  // Load all projects; auto-select the first (or create a default).
  useEffect(() => {
    void (async () => {
      const projects = await api.listProjects();
      // Dedupe by repo_path (a repo bound twice is the same project).
      const seen = new Set<string>();
      const unique = projects.filter((p) => {
        if (seen.has(p.repo_path)) return false;
        seen.add(p.repo_path);
        return true;
      });
      setProjects(unique);
      if (unique.length === 0) {
        const p = await api.createProject('diskscope', '/home/kaianuar/code/diskscope', '/tmp/omp-web-scratch');
        setProjects([p]);
        await selectProject(p);
      } else {
        await selectProject(unique[0]);
      }
    })();
  }, []);

  // Switch project → load its sessions, select the most recent.
  const switchProject = async (pid: number) => {
    const p = projects.find((x) => x.id === pid);
    if (!p) return;
    await selectProject(p);
  };

  // Select a project: load its sessions, pick the newest (or create one).
  const selectProject = async (p: Project) => {
    setProject(p);
    setTask(null);
    setEvents([]);
    setSessions([]);
    const sessions = await api.listSessions(p.id);
    setSessions(sessions);
    if (sessions.length > 0) {
      await selectSession(sessions[0]);
    } else {
      const s = await api.startSession(p.id);
      setSessions([s]);
      await selectSession(s);
    }
  };

  // Select a session: load its tasks + the latest task's events.
  const selectSession = async (s: Session) => {
    setSession(s);
    setTask(null);
    setEvents([]);
    const tasks = await api.sessionTasks(s.id);
    const latest = tasks[tasks.length - 1];
    if (latest) {
      setTask(latest);
      const evs = await api.taskEvents(latest.id);
      setEvents(evs);
    }
  };

  // New session for the current project (fresh conversation).
  const newSession = async () => {
    if (!project) return;
    const s = await api.startSession(project.id);
    setSessions((prev) => [s, ...prev]);
    await selectSession(s);
  };

  const createProject = async () => {
    if (!newProjName.trim() || !newProjPath.trim()) return;
    const p = await api.createProject(newProjName.trim(), newProjPath.trim(), `/tmp/omp-web-${newProjName.trim()}`);
    setProjects((prev) => [...prev, p]);
    setShowNewProject(false);
    setNewProjName('');
    setNewProjPath('');
    await selectProject(p);
  };

  // Open the browse dialog at a path (defaults to home).
  const openBrowse = async (path = '') => {
    setBrowsing(true);
    setBrowsePath('');
    try {
      const res = await api.fsList(path);
      setBrowsePath(res.path);
      setBrowseDirs(res.dirs);
    } catch { setBrowseDirs([]); }
  };

  // Navigate into a directory in the browse dialog.
  const browseInto = async (dirPath: string) => {
    setBrowsing(true);
    try {
      const res = await api.fsList(dirPath);
      setBrowsePath(res.path);
      setBrowseDirs(res.dirs);
    } catch { setBrowseDirs([]); }
  };

  // Pick a folder from the browse dialog as the project path.
  const browsePick = (dirPath: string) => {
    setNewProjPath(dirPath);
    setBrowsing(false);
  };

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events]);

  const refreshDenyLog = async () => {
    try {
      const d = await api.denyLog();
      setDenyLog(d.entries);
    } catch { /* non-fatal */ }
  };
  useEffect(() => { void refreshDenyLog(); }, [events]);

  const send = async () => {
    if (!input.trim() || !session || busy) return;
    setBusy(true);
    const msg = input;
    setInput('');
    try {
      const t = await api.newTask(session.id, msg);
      setTask(t);
      const evs = await api.taskEvents(t.id);
      setEvents(evs);
    } catch (e) {
      setEvents((prev) => [...prev, {
        id: Date.now(), task_id: 0, kind: 'error', ts: new Date().toISOString(),
        payload: { note: String(e) },
      } as Event]);
    } finally {
      setBusy(false);
    }
  };

  const clarifyTask = async (taskId: number, answers: string) => {
    if (!answers.trim() || busy) return;
    setBusy(true);
    try {
      await api.clarify(taskId, answers);
      // After answering, proceed like decide: poll until next checkpoint.
      await pollUntilCheckpoint(taskId);
    } catch (e) {
      setEvents((prev) => [...prev, {
        id: Date.now(), task_id: taskId, kind: 'error', ts: new Date().toISOString(),
        payload: { note: String(e) },
      } as Event]);
    } finally {
      setBusy(false);
    }
  };

  /** Wait until the task reaches a checkpoint state (events arrive via WS). */
  const pollUntilCheckpoint = async (taskId: number) => {
    // Any state where the user must act again (or the task ended).
    const terminal = new Set([
      'awaiting_design_approval', 'awaiting_recipe_approval',
      'awaiting_result', 'awaiting_fix_decision', 'error',
    ]);
    for (let i = 0; i < 200; i++) {  // ~33 min cap at 10s intervals
      await new Promise((r) => setTimeout(r, 10_000));
      const t = await api.getTask(taskId);
      setTask(t);
      if (terminal.has(t.state)) break;
    }
  };

  const decide = async (decision: string, note = '') => {
    if (!task) return;
    setBusy(true);
    try {
      await api.decide(task.id, decision, note);
      await pollUntilCheckpoint(task.id);
    } catch (e) {
      setEvents((prev) => [...prev, {
        id: Date.now(), task_id: task.id, kind: 'error', ts: new Date().toISOString(),
        payload: { note: String(e) },
      } as Event]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="app" data-testid="app">
      {rolesConfig && !rolesConfig.configured && (
        <div className="wizard-overlay" data-testid="setup-wizard">
          <div className="wizard-card">
            <h2>Set up your models</h2>
            <p className="muted">Pick which model plays each role. These are the models omp has configured.</p>
            <RolePicker
              roles={rolesConfig.roles}
              models={models}
              onChange={(r) => setRolesConfig({ ...rolesConfig, roles: r })}
            />
            <p className="hint muted">
              No models listed? See the{' '}
              <a href="https://github.com/can1357/oh-my-pi/blob/main/docs/models.md" target="_blank" rel="noreferrer">
                omp docs on configuring providers &amp; models
              </a>{' '}
              (~/.omp/agent/models.yml).
            </p>
            <div className="actions">
              <button
                data-testid="wizard-save"
                onClick={() => void saveRoles(rolesConfig.roles)}
                disabled={models.length === 0 || Object.keys(ROLES).some((r) => !rolesConfig.roles[r])}
              >
                Save
              </button>
            </div>
          </div>
        </div>
      )}

      {showSettings && rolesConfig && (
        <div className="wizard-overlay" data-testid="settings-panel">
          <div className="wizard-card">
            <h2>Settings — model roles</h2>
            <RolePicker
              roles={rolesConfig.roles}
              models={models}
              onChange={(r) => setRolesConfig({ ...rolesConfig, roles: r })}
            />
            <div className="actions">
              <button
                data-testid="settings-save"
                onClick={() => void saveRoles(rolesConfig.roles)}
                disabled={Object.keys(ROLES).some((r) => !rolesConfig.roles[r])}
              >
                Save
              </button>
              <button onClick={() => setShowSettings(false)}>Cancel</button>
            </div>
          </div>
        </div>
      )}

      <aside className="rail" data-testid="rail">
        <div className="rail-header">
          <h2>omp</h2>
          <div className="rail-actions">
            {rolesConfig?.configured && (
              <button className="icon-btn" data-testid="settings-btn" onClick={() => setShowSettings(true)} title="Settings">⚙️</button>
            )}
            <button className="theme-toggle" data-testid="theme-toggle" onClick={toggleTheme} title="Toggle light/dark">
              {theme === 'dark' ? '☀️' : '🌙'}
            </button>
          </div>
        </div>
        <div className="rail-section">
          <b>Project</b>
          <select
            data-testid="project-select"
            value={project?.id ?? ''}
            onChange={(e) => void switchProject(Number(e.target.value))}
          >
            {projects.map((p) => (
              <option key={p.id} value={p.id}>{p.name} — {p.repo_path}</option>
            ))}
          </select>
          <div className="tiny muted" title={project?.repo_path ?? ''}>
            {project?.repo_path ?? ''}
          </div>
          {!showNewProject ? (
            <button className="link-btn" data-testid="new-project-btn" onClick={() => setShowNewProject(true)}>
              + Open project
            </button>
          ) : (
            <div className="new-project">
              <input
                data-testid="new-proj-name"
                placeholder="name"
                value={newProjName}
                onChange={(e) => setNewProjName(e.target.value)}
              />
              <div className="path-row">
                <input
                  data-testid="new-proj-path"
                  placeholder="/path/to/repo"
                  value={newProjPath}
                  onChange={(e) => setNewProjPath(e.target.value)}
                />
                <button data-testid="browse-btn" onClick={() => void openBrowse()}>Browse…</button>
              </div>
              {browsing && (
                <div className="browse-dialog" data-testid="browse-dialog">
                  <div className="browse-path">{browsePath || '…'}</div>
                  <div className="browse-dirs">
                    {browsePath && (
                      <button className="browse-up" data-testid="browse-up" onClick={() => void browseInto(browsePath.replace(/\/[^/]+$/, '') || '/')}>
                        ↑ ..
                      </button>
                    )}
                    {browseDirs.map((d) => (
                      <div key={d.path} className="browse-item">
                        <button className="browse-into" data-testid={`browse-into-${d.name}`} onClick={() => void browseInto(d.path)}>
                          📁 {d.name}
                        </button>
                        <button className="browse-pick" data-testid={`browse-pick-${d.name}`} onClick={() => browsePick(d.path)}>
                          Select
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              <div className="actions">
                <button data-testid="new-proj-create" onClick={() => void createProject()} disabled={!newProjName.trim() || !newProjPath.trim()}>
                  Create
                </button>
                <button onClick={() => setShowNewProject(false)}>Cancel</button>
              </div>
            </div>
          )}
        </div>
        <div className="rail-section">
          <b>Session</b>
          <select
            data-testid="session-select"
            value={session?.id ?? ''}
            onChange={(e) => {
              const s = sessions.find((x) => x.id === Number(e.target.value));
              if (s) void selectSession(s);
            }}
          >
            {sessions.map((s) => (
              <option key={s.id} value={s.id}>session #{s.id}</option>
            ))}
          </select>
          <button className="link-btn" data-testid="new-session-btn" onClick={() => void newSession()}>
            + New session
          </button>
        </div>
        <div className="rail-section">
          <b>Task</b>
          <div className="muted">{task?.state ?? 'idle'}</div>
        </div>
        <div className="rail-section">
          <b>Scratch deny-log</b>
          <div className="tiny muted">
            {denyLog.length === 0 ? '(none — no blocked writes)' : denyLog.slice(-3).map((l, i) => <div key={i}>{l}</div>)}
          </div>
        </div>
      </aside>

      <main className="chat" data-testid="chat">
        <header className="chat-header">
          <h1>Orchestrator</h1>
          <span className="muted">local-first AI product builder</span>
        </header>

        <div className="messages" data-testid="messages">
          {events.length === 0 && (
            <div className="card card-dim">
              Tell me what you want built or improved. I'll design it, get your approval, and run the build + review pipeline.
            </div>
          )}
          {events.map((ev) => cardFor(ev, decide, clarifyTask))}
          {busy && <div className="card card-build"><b>Working…</b></div>}
          <div ref={bottomRef} />
        </div>

        <footer className="composer">
          <input
            data-testid="composer-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && void send()}
            placeholder="e.g. add a forgotten-files view"
            disabled={busy || !session}
          />
          <button data-testid="composer-send" onClick={() => void send()} disabled={busy || !input.trim()}>
            Send
          </button>
        </footer>
      </main>
    </div>
  );
}
