# Projects built with omp-agent

Live apps built end-to-end with the omp-agent pipeline (plan → build → test gate →
adversarial review → visual/e2e gate → deploy).

---

## Family Todo

A shared, real-time to-do list for families — add tasks and everyone on the same
list sees changes live, no login needed.

- **Live:** https://family-todo-i7zjvw81c-khairull-jamlus-projects.vercel.app
- **Code:** https://github.com/kaianuar/family-todo

| | |
|---|---|
| Client | React + Vite (mobile-first), static on Vercel |
| API | Vercel serverless functions |
| Database | Neon (serverless Postgres) |
| Realtime | Ably pub/sub (per-list channels, live sync) |
| Architecture | Hexagonal — domain → application (ports) → adapters |

Built and verified through all three gates: 30 tests (incl. 8 Neon adapter against
real Postgres), independent adversarial review, and 8/8 Playwright e2e including
live cross-page sync.
