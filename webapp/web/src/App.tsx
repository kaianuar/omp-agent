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
      return <div className="card card-design" key={ev.id} data-testid="card-design">
        <b>Design proposal</b>
        <pre className="doc">{String(p.content ?? '').slice(0, 3000)}</pre>
        <div className="actions">
          <button data-testid="approve" onClick={() => onDecide('approve')}>Approve</button>
          <button data-testid="reject" onClick={() => onDecide('reject')}>Reject</button>
        </div>
      </div>;
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
  const [task, setTask] = useState<Task | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [denyLog, setDenyLog] = useState<string[]>([]);
  const [showNewProject, setShowNewProject] = useState(false);
  const [newProjName, setNewProjName] = useState('');
  const [newProjPath, setNewProjPath] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);

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
        setProject(p);
        const s = await api.startSession(p.id);
        setSession(s);
      } else {
        setProject(unique[0]);
        const s = await api.startSession(unique[0].id);
        setSession(s);
      }
    })();
  }, []);

  // Switch project → new session, reset task state.
  const switchProject = async (pid: number) => {
    const p = projects.find((x) => x.id === pid);
    if (!p) return;
    await selectProject(p);
  };

  // Select a project directly (no lookup needed).
  const selectProject = async (p: Project) => {
    setProject(p);
    setTask(null);
    setEvents([]);
    const s = await api.startSession(p.id);
    setSession(s);
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

  /** Poll events + task state until a checkpoint state (user must act again). */
  const pollUntilCheckpoint = async (taskId: number) => {
    const terminal = new Set(['awaiting_result', 'awaiting_fix_decision', 'error']);
    for (let i = 0; i < 200; i++) {  // ~33 min cap at 10s intervals
      await new Promise((r) => setTimeout(r, 10_000));
      const [evs, t] = await Promise.all([api.taskEvents(taskId), api.getTask(taskId)]);
      setEvents(evs);
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
      <aside className="rail" data-testid="rail">
        <h2>omp</h2>
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
              + New project
            </button>
          ) : (
            <div className="new-project">
              <input
                data-testid="new-proj-name"
                placeholder="name"
                value={newProjName}
                onChange={(e) => setNewProjName(e.target.value)}
              />
              <input
                data-testid="new-proj-path"
                placeholder="/path/to/repo"
                value={newProjPath}
                onChange={(e) => setNewProjPath(e.target.value)}
              />
              <div className="actions">
                <button data-testid="new-proj-create" onClick={() => void createProject()}>Create</button>
                <button onClick={() => setShowNewProject(false)}>Cancel</button>
              </div>
            </div>
          )}
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
