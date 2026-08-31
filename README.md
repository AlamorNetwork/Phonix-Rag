# Phoenix Forge

AI Engineering & Infrastructure Command Center — a web platform that runs a team of AI agents
(analysis, planning, coding, review, security, infra) against a project idea, with every
sensitive action gated by a Policy → Permission → Approval → Sandbox chain. No agent gets
unrestricted shell/filesystem/git/network access.

## Status: Phase 0

This is the first vertical slice of the system: one agent (Manager), a handful of tools
(`filesystem.read`, `filesystem.write`, `git.status`, `git.commit`), the full
Policy/Permission/Approval/Sandbox pipeline, cost & token tracking against a single model
provider (Liara AI Gateway, OpenAI-compatible), and a real-time web UI. Everything else in the
full spec (Security/Red Team/Blue Team/Infra/Monitoring agents, Docker-per-workspace sandboxing,
GitHub PR automation, more providers) is deliberately deferred to later phases — see
`docs/` (added as later phases land) for the full architecture spec.

## Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy (async), Alembic, PostgreSQL, Redis, WebSocket
- **Frontend**: Next.js, React, TypeScript, Tailwind CSS
- **Infra**: Docker Compose (Postgres, Redis, backend, frontend, nginx)

## Local development

```bash
cp .env.example .env
# fill in LIARA_API_KEY, LIARA_BASE_URL, JWT_SECRET, ADMIN_EMAIL, ADMIN_PASSWORD

docker compose up -d postgres redis

cd backend
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000

cd ../frontend
npm install
npm run dev
```

Backend: http://localhost:8000 (docs at `/docs`)
Frontend: http://localhost:3000

## Tests

```bash
cd backend
pytest
```

Tests use an in-memory SQLite database and a mocked model provider — no live API calls or
external services are required to run the test suite.

## Deploying on a server

```bash
cp .env.example .env
# set POSTGRES_PASSWORD, JWT_SECRET, ADMIN_EMAIL/PASSWORD, LIARA_API_KEY
# set NEXT_PUBLIC_API_BASE=http://<server-ip-or-domain>
# set NEXT_PUBLIC_WS_BASE=ws://<server-ip-or-domain>

docker compose up -d --build
```

`nginx` is the only container published on the public interface (port 80 by default, see
`PUBLIC_HTTP_PORT`); it routes `/api/*` and `/ws/*` to the backend and everything else to the
frontend (config in `docker/nginx.conf`). Postgres, Redis, backend, and frontend are only bound
to `127.0.0.1` on the host — reach them directly (for debugging) via an SSH tunnel, not
directly from the internet. This is plain HTTP; put a domain + TLS (certbot) in front before
using this for anything beyond testing.

## Security notes

- `LIARA_API_KEY` and `JWT_SECRET` are read from environment only — never hard-coded, never
  logged, never sent to the frontend. A masking helper (`app/core/logging.py`) redacts anything
  key-shaped before it reaches logs, audit records, or WebSocket events.
- All filesystem/git tools are hard-restricted to `workspaces/<project_id>/` — path traversal is
  covered by tests.
- Tools above `READ` risk (`filesystem.write`, `git.commit`) require an explicit human approval
  via the API/UI before they execute.
