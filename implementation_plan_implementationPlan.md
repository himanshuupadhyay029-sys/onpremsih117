# Persistent Chat, Auth & Multi-Language Sandbox for KAVACH (Revised)

## Overview
This implementation plan covers:
1. **Host-Native Backend with Shield Integrity & Admin Check:** Keeping the FastAPI backend running directly on the Windows host (`.venv`) so `psutil` monitors physical sockets and `netsh advfirewall` controls Windows Defender Firewall without container namespace barriers. `run_backend.ps1` checks for Administrator elevation and warns if non-elevated.
2. **Containerized Infrastructure & Frontend:** Running `postgres:16-alpine` (health-checked, port `5432:5432`, volume `pgdata`) and `frontend` (`node:20-alpine` Vite dev server with anonymous `node_modules` volume for live HMR) via `docker-compose.yml`.
3. **Multi-Language Isolated Sandbox (Python, JavaScript, C):** Expanding `backend/tools/sandbox.py` to support Python (`python:3.11-slim`), JavaScript (`node:20-slim`), and C (`gcc:13-slim`). For C, compilation and execution happen in a **single container invocation** with distinct stage error markers to distinguish `stage="compile"` vs `stage="runtime"`.
4. **Database-Backed Persistent Chat & Authentication:** PostgreSQL models (`users`, `chats`, `messages` with `meta` JSONB column), JWT httpOnly cookies, Claude-style sidebar, and message history hydration across tabs.

---

## Key Architecture & Design Decisions

> [!IMPORTANT]
> 1. **Single-Container C Compilation & Execution Pipeline:**
>    - For C, compilation (`gcc -O2 script.c -o /tmp/out -lm`) and binary execution (`/tmp/out`) run within a **single `docker run` execution** using chained shell commands:
>      ```bash
>      sh -c "gcc -O2 script.c -o /tmp/out -lm 2> /tmp/compile_err || { echo '__COMPILE_FAILED__'; cat /tmp/compile_err; exit 1; }; /tmp/out"
>      ```
>    - The output parser checks for the boundary marker `__COMPILE_FAILED__` to report `stage: "compile"` with compiler diagnostics, or `stage: "runtime"` if execution failed.
>    - All languages enforce: `--network none`, `--cpus=1.0`, `--memory=256m`, 15-second timeout.
> 2. **Windows Administrator Elevation Check:**
>    - `run_backend.ps1` performs a `[Security.Principal.WindowsPrincipal]` check at startup. If non-elevated, it prints:
>      `[WARNING] Not running as Administrator: /shield/firewall/toggle and Windows Firewall lockdown will fail.`
> 3. **SQLAlchemy Model Field Naming:** `Message.meta` (JSONB, default `{}`) avoids collision with `Base.metadata`.
> 4. **Turn-Based Message Integrity:** Exactly 2 rows per interaction in `messages` (`user` and `assistant`), storing reasoning traces, intermediate steps, and attachments inside `assistant.meta`.
> 5. **Audit Trail Kept File-Based:** `outputs/audit_log.jsonl` remains an append-only SHA-256 hash-chained file.

---

## Proposed Changes by Stage

### STAGE 1 — Postgres, Frontend Docker, Host Runner & Migrations

#### [NEW] [docker-compose.yml](file:///c:/Users/Mohammad%20Kaif/Documents/onpremsih117/kavach/docker-compose.yml)
- **`postgres` service**:
  - Image: `postgres:16-alpine`
  - Ports: `5432:5432`
  - Environment: `POSTGRES_USER=kavach`, `POSTGRES_PASSWORD=kavach_secret`, `POSTGRES_DB=kavach_db`
  - Volumes: `pgdata:/var/lib/postgresql/data`
  - Healthcheck: `test: ["CMD-SHELL", "pg_isready -U kavach -d kavach_db"]`, `interval: 3s`, `timeout: 3s`, `retries: 5`
- **`frontend` service**:
  - Image: `node:20-alpine`
  - Working directory: `/app`
  - Ports: `5173:5173`
  - Environment: `VITE_API_URL=http://localhost:8000`
  - Command: `sh -c "npm install && npm run dev -- --host 0.0.0.0 --port 5173"`
  - Volumes:
    - `./frontend-react:/app`
    - `/app/node_modules` (anonymous volume to protect host OS dependencies)

#### [NEW] [run_backend.ps1](file:///c:/Users/Mohammad%20Kaif/Documents/onpremsih117/kavach/run_backend.ps1)
- Elevation check: warns if PowerShell is not running as Administrator.
- Checks Docker daemon and waits for `postgres` container health.
- Runs `alembic upgrade head` using host `.venv`.
- Launches `uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000`.

#### [NEW] [backend/db/session.py](file:///c:/Users/Mohammad%20Kaif/Documents/onpremsih117/kavach/backend/db/session.py)
- `create_engine` connected to `DATABASE_URL` (default: `postgresql://kavach:kavach_secret@localhost:5432/kavach_db`).
- `sessionmaker` and `get_db` dependency for FastAPI routes.

#### [NEW] [backend/db/models.py](file:///c:/Users/Mohammad%20Kaif/Documents/onpremsih117/kavach/backend/db/models.py)
- **`User`**: `id` (UUID PK), `name`, `email` (unique index), `password_hash`, `created_at`.
- **`Chat`**: `id` (UUID PK), `user_id` (FK to `users.id` ondelete CASCADE), `title`, `chat_type`, `created_at`, `updated_at`.
- **`Message`**: `id` (UUID PK), `chat_id` (FK to `chats.id` ondelete CASCADE), `role` (`user`/`assistant`), `content` (Text), `meta` (`JSONB`, default `{}`), `created_at`.

#### [NEW] [alembic.ini](file:///c:/Users/Mohammad%20Kaif/Documents/onpremsih117/kavach/alembic.ini) & [migrations/](file:///c:/Users/Mohammad%20Kaif/Documents/onpremsih117/kavach/migrations/)
- Alembic configuration pointing to `backend.db.models.Base.metadata`.
- Initial revision `001_initial_schema.py`.

---

### STAGE 2 — Multi-Language Sandbox (Python, JS, C)

#### [MODIFY] [backend/tools/sandbox.py](file:///c:/Users/Mohammad%20Kaif/Documents/onpremsih117/kavach/backend/tools/sandbox.py)
- Support language parameter (`python`, `javascript` / `js`, `c`) with auto-detection.
- Docker image mappings:
  - `python`: `python:3.11-slim`
  - `javascript`: `node:20-slim`
  - `c`: `gcc:13-slim`
- For C: Chained single-container compile and execution (`gcc ... || { echo '__COMPILE_FAILED__'; ... } && /tmp/out`).
- Output parsing returns `stage: "compile" | "runtime"`, `compile_output`, `runtime_output`, `stdout`, `stderr`, `exit_code`, and `language`.
- Audit logging with `external_calls: 0`.

---

### STAGE 3 — Auth (Register / Login / Middleware)

#### [NEW] [backend/auth/security.py](file:///c:/Users/Mohammad%20Kaif/Documents/onpremsih117/kavach/backend/auth/security.py)
- Password hashing using `passlib.context.CryptContext(schemes=["bcrypt"])`.
- JWT encoding & decoding with `python-jose` / `pyjwt`.

#### [NEW] [backend/auth/routes.py](file:///c:/Users/Mohammad%20Kaif/Documents/onpremsih117/kavach/backend/auth/routes.py)
- `POST /auth/register`: name, email, password; returns 409 for duplicate emails.
- `POST /auth/login`: verifies password, sets `httpOnly` `access_token` cookie with `SameSite=Lax`.
- `POST /auth/logout`: clears auth cookie.
- `GET /auth/me`: returns authenticated profile.
- `get_current_user` FastAPI dependency.

#### [MODIFY] [backend/main.py](file:///c:/Users/Mohammad%20Kaif/Documents/onpremsih117/kavach/backend/main.py)
- Configure `CORSMiddleware`: `allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173", "http://127.0.0.1:8000"]`, `allow_credentials=True`.
- Mount auth router under `/auth`.

#### [NEW] [frontend-react/src/components/AuthModal.jsx](file:///c:/Users/Mohammad%20Kaif/Documents/onpremsih117/kavach/frontend-react/src/components/AuthModal.jsx)
- Modal for login & registration with state switching and validation.

#### [MODIFY] [frontend-react/src/components/Sidebar.jsx](file:///c:/Users/Mohammad%20Kaif/Documents/onpremsih117/kavach/frontend-react/src/components/Sidebar.jsx)
- User profile block at bottom of sidebar (Avatar initials + Name + Email + Logout button).

---

### STAGE 4 — Chat Persistence + Claude-Style Sidebar

#### [NEW] [backend/chat/routes.py](file:///c:/Users/Mohammad%20Kaif/Documents/onpremsih117/kavach/backend/chat/routes.py)
- `POST /chats`: creates new chat (`title="New Chat"`).
- `GET /chats`: lists user chats ordered by `updated_at DESC`.
- `GET /chats/{id}/messages`: returns message history for conversation hydration.
- `POST /chats/{id}/messages`: appends message row and updates `chats.updated_at`.
- `PATCH /chats/{id}`: updates title (used by auto-titling logic).
- `DELETE /chats/{id}`: deletes chat.

#### [MODIFY] [backend/brain/agent.py](file:///c:/Users/Mohammad%20Kaif/Documents/onpremsih117/kavach/backend/brain/agent.py) & [backend/main.py](file:///c:/Users/Mohammad%20Kaif/Documents/onpremsih117/kavach/backend/main.py)
- When `POST /run` receives `chat_id`:
  - Inserts 1 `role="user"` message (`content=task`, `meta={"attached_file": ...}`).
  - Runs LangGraph agent.
  - Inserts 1 `role="assistant"` message (`content=final_answer`, `meta={"trace": ..., "steps": ..., "sources": ...}`).
  - Auto-titles chat on first turn.

#### [MODIFY] [frontend-react/src/components/Sidebar.jsx](file:///c:/Users/Mohammad%20Kaif/Documents/onpremsih117/kavach/frontend-react/src/components/Sidebar.jsx)
- Top **"+ New Chat"** button.
- Scrollable list of past conversations with active highlighting.

#### [MODIFY] [frontend-react/src/components/NewTaskScreen.jsx](file:///c:/Users/Mohammad%20Kaif/Documents/onpremsih117/kavach/frontend-react/src/components/NewTaskScreen.jsx)
- Hydrates messages from `GET /chats/{id}/messages` on chat selection or tab switch.

---

## Verification Plan

### Stage 1 Verification
1. Launch `docker compose up -d` (starts `postgres` and `frontend`).
2. Run `.\run_backend.ps1` in an **elevated (Administrator)** PowerShell terminal.
3. Check table creation in Postgres:
   ```powershell
   docker compose exec postgres psql -U kavach -d kavach_db -c '\dt'
   ```
   Confirm `users`, `chats`, `messages`, and `alembic_version` tables exist.
4. Verify Shield integrity:
   - Call `GET http://localhost:8000/shield/status` and confirm real host socket counts.
   - Verify Windows Defender Firewall toggle via `POST /shield/firewall/toggle` (confirmed working in elevated process).
5. Verify Frontend HMR:
   - Access `http://localhost:5173`. Edit `frontend-react/src/components/TopBar.jsx` and confirm instant browser update.

### Stage 2 Verification (Multi-Language Sandbox)
1. Run Python test snippet (corrosion rate calculation) ➔ verify stdout, exit_code 0.
2. Run JavaScript test snippet (JSON manipulation) ➔ verify stdout, exit_code 0.
3. Run C test snippet (compile and arithmetic execution in single container) ➔ verify compile output and runtime stdout.
4. Run invalid C snippet (syntax error) ➔ verify `stage="compile"`, compiler error output, exit_code != 0.
5. Verify `--network none` isolation on all three.

### Stage 3 Verification (Auth)
1. Register user via `POST /auth/register` (confirm duplicate 409 conflict).
2. Login user via `POST /auth/login` (confirm `Set-Cookie` header with `httpOnly; SameSite=Lax`).
3. Call `GET /auth/me` with cookie to verify user identity.
4. Verify Login/Register modal in UI.

### Stage 4 Verification (Chat Persistence)
1. Click **"+ New Chat"** ➔ submit query with attachment.
2. Verify only 2 rows inserted in `messages` (`user` and `assistant`).
3. Verify auto-titling updates chat title in sidebar.
4. Switch to "Knowledge Vault" and back to "Chat" ➔ verify chat messages remain intact and hydrated from DB.
