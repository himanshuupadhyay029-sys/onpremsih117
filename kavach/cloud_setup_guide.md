# KAVACH Cloud Services Setup Guide
## Neon + Hugging Face + Render + Netlify — Step-by-Step

> This guide covers **only external service setup** — creating accounts, configuring services, and getting credentials.
> Code changes are documented separately in `implementation_plan_deployment1.md`.

---

## Table of Contents

1. [Hugging Face — Create 12 Accounts & Get API Tokens](#1-hugging-face)
2. [Neon — Create Postgres Database](#2-neon-postgres)
3. [Render — Deploy the FastAPI Backend](#3-render-backend)
4. [Netlify — Deploy the React Frontend](#4-netlify-frontend)
5. [Final Wiring — Connect Everything](#5-final-wiring)
6. [Quick Verification](#6-quick-verification)

---

## 1. Hugging Face

### Why 12 Accounts?

Each HF free account gets rate-limited at roughly 100–200 API requests per hour for shared GPU inference. For a live demo with multiple judges hitting the system simultaneously, one account per role will run out. We use **3 accounts per role × 4 roles = 12 accounts** and rotate between them on every 429 response.

The 4 roles and which model they use:

| Role | HF Model | Gated? |
| :--- | :--- | :--- |
| Reasoning | `Qwen/Qwen2.5-7B-Instruct` | No — open access |
| Code | `ibm-granite/granite-3.3-8b-instruct` | **Yes — must accept ToS** |
| Vision | `Qwen/Qwen2-VL-7B-Instruct` | **Yes — must accept ToS** |
| Embedding | `nomic-ai/nomic-embed-text-v1.5` | No — open access |

> [!CAUTION]
> Do NOT use Gmail "+" tricks like `myemail+1@gmail.com` on multiple accounts. HF detects this. Use 12 distinct email addresses (e.g. 12 different Google accounts, or other real email addresses you control).

---

### 1.1 Create Each Account

Repeat these steps for all 12 accounts. Use the naming table below to stay organized.

**Account naming for your own records:**

| Account | Purpose | Token env var it will fill |
| :--- | :--- | :--- |
| `kavach-reasoning-1` | Reasoning primary | `HF_REASONING_API_KEY_PRIMARY` |
| `kavach-reasoning-2` | Reasoning fallback 1 | `HF_REASONING_API_KEY_FALLBACK_1` |
| `kavach-reasoning-3` | Reasoning fallback 2 | `HF_REASONING_API_KEY_FALLBACK_2` |
| `kavach-code-1` | Code primary | `HF_CODE_API_KEY_PRIMARY` |
| `kavach-code-2` | Code fallback 1 | `HF_CODE_API_KEY_FALLBACK_1` |
| `kavach-code-3` | Code fallback 2 | `HF_CODE_API_KEY_FALLBACK_2` |
| `kavach-vision-1` | Vision primary | `HF_VISION_API_KEY_PRIMARY` |
| `kavach-vision-2` | Vision fallback 1 | `HF_VISION_API_KEY_FALLBACK_1` |
| `kavach-vision-3` | Vision fallback 2 | `HF_VISION_API_KEY_FALLBACK_2` |
| `kavach-embed-1` | Embedding primary | `HF_EMBEDDING_API_KEY_PRIMARY` |
| `kavach-embed-2` | Embedding fallback 1 | `HF_EMBEDDING_API_KEY_FALLBACK_1` |
| `kavach-embed-3` | Embedding fallback 2 | `HF_EMBEDDING_API_KEY_FALLBACK_2` |

**Steps (for each account):**

1. Open a browser in **private/incognito mode** (important — avoids auto-login from a previous account)
2. Go to: `https://huggingface.co/join`
3. Enter a unique email address, choose a username (e.g. `kavach-reasoning-1`), set a password
4. Click **Create Account**
5. Open the verification email and click the confirm link
6. You are now logged in as this account
7. Click your avatar (top right) → **Settings**
8. In the left sidebar, click **Access Tokens**
9. Click **"New token"** (blue button, top right of the tokens list)
10. In the dialog:
    - **Token name**: `kavach-inference`
    - **Token type**: select **Read** (Read is sufficient — write not needed for inference)
11. Click **"Create token"**
12. A dialog shows the token starting with `hf_...`
13. **Copy it immediately** and paste it into a safe document (password manager, spreadsheet, etc.)
    - ⚠️ You **cannot view this token again** after closing this dialog. If you lose it, you must create a new one.
14. Close the dialog

**Repeat steps 1–14 for all 12 accounts.**

---

### 1.2 Accept Terms of Service for Gated Models

For accounts that will call gated models (Code and Vision roles — accounts 4–9), you must accept ToS while logged in as each account.

**For accounts `kavach-code-1`, `kavach-code-2`, `kavach-code-3`:**

1. Log in as that account (incognito window)
2. Go to: `https://huggingface.co/ibm-granite/granite-3.3-8b-instruct`
3. You will see a yellow bar: "This model is gated. To access it, you need to agree to the terms"
4. Click **"Agree and access repository"**
5. If prompted, fill in the usage form (select "Research" or "Personal project") and submit
6. The page reloads and you should now see the model card without the yellow bar
7. ✅ Done for this account

**For accounts `kavach-vision-1`, `kavach-vision-2`, `kavach-vision-3`:**

1. Log in as that account (incognito window)
2. Go to: `https://huggingface.co/Qwen/Qwen2-VL-7B-Instruct`
3. Click **"Agree and access repository"**
4. ✅ Done for this account

> [!IMPORTANT]
> You must accept ToS while logged in as the **exact account whose token you will use**. Accepting on one account does NOT grant access to other accounts.
>
> `kavach-reasoning-1/2/3` and `kavach-embed-1/2/3` do NOT need ToS acceptance — their models are open access.

---

### 1.3 Verify Each Token Works

Test each token from your terminal before setting it on Render. Use the curl command below — replace `hf_xxx` with the actual token.

**For reasoning/embedding tokens (open models):**
```bash
curl -s https://api-inference.huggingface.co/models/Qwen/Qwen2.5-7B-Instruct \
  -H "Authorization: Bearer hf_xxx" \
  -H "Content-Type: application/json" \
  -d '{"inputs": "Say hello in one word", "parameters": {"max_new_tokens": 5}}' \
  | python -m json.tool
```

**Expected response:**
```json
[{"generated_text": "Say hello in one word\nHello"}]
```

If you get `{"error": "Authorization error"}` → the token is wrong.
If you get `{"error": "...is currently loading"}` → the model is cold-starting, wait 30s and retry.

**For code tokens (gated model):**
```bash
curl -s https://api-inference.huggingface.co/models/ibm-granite/granite-3.3-8b-instruct \
  -H "Authorization: Bearer hf_xxx" \
  -H "Content-Type: application/json" \
  -d '{"inputs": "Write hello world in Python", "parameters": {"max_new_tokens": 30}}' \
  | python -m json.tool
```

If you get `{"error": "...is not accessible"}` → the ToS was not accepted for this account.

---

### 1.4 Collect All 12 Tokens

At this point you should have a secure document with 12 tokens:

```
HF_REASONING_API_KEY_PRIMARY=hf_...
HF_REASONING_API_KEY_FALLBACK_1=hf_...
HF_REASONING_API_KEY_FALLBACK_2=hf_...
HF_CODE_API_KEY_PRIMARY=hf_...
HF_CODE_API_KEY_FALLBACK_1=hf_...
HF_CODE_API_KEY_FALLBACK_2=hf_...
HF_VISION_API_KEY_PRIMARY=hf_...
HF_VISION_API_KEY_FALLBACK_1=hf_...
HF_VISION_API_KEY_FALLBACK_2=hf_...
HF_EMBEDDING_API_KEY_PRIMARY=hf_...
HF_EMBEDDING_API_KEY_FALLBACK_1=hf_...
HF_EMBEDDING_API_KEY_FALLBACK_2=hf_...
```

You will paste these into Render's environment variables section in Step 3.

---

## 2. Neon Postgres

### What Neon Is

Neon is a serverless Postgres provider. It runs standard PostgreSQL 16 — your SQLAlchemy models, Alembic migrations, and psycopg2 connection code all work without any changes. The only difference is the connection string format.

### Neon Free Tier Limits

| Limit | Value | What Happens If Exceeded |
| :--- | :--- | :--- |
| Storage | 0.5 GB | Database becomes **read-only** — writes fail |
| Compute hours | 191.9 hours/month at 0.25 CU | Service suspends until next month |
| Inactivity timeout | 5 minutes | DB suspends; first query after wakes it (500ms–2s delay) |
| Max connections (pooled) | 100 | New connections refused |
| Projects | 1 per free account | Cannot create a second project |

> [!NOTE]
> The 5-minute inactivity suspension means the **first query after a period of no traffic has a 500ms–2s delay**. For a demo this is fine — it's not noticeable once traffic is flowing. Use the pooled (PgBouncer) connection string to reduce connection overhead.

---

### 2.1 Create a Neon Account and Project

1. Go to: `https://neon.tech`
2. Click **"Sign Up"**
3. Sign up with **GitHub** (recommended — one less password to manage) or with email
4. After signup you land on the Neon dashboard
5. If not already prompted, click **"Create a project"**
6. Fill in the project creation form:
   - **Project name**: `kavach-demo`
   - **Postgres version**: `16`
   - **Cloud provider**: `AWS`
   - **Region**: Choose the region **closest to where your Render service will run**
     - If Render → Singapore: choose `AWS ap-southeast-1`
     - If Render → Ohio (us-east): choose `AWS us-east-1`
     - If Render → Oregon (us-west): choose `AWS us-west-2`
   - **Database name**: `neondb` (leave as default)
   - **Role name**: `neondb_owner` (leave as default)
7. Click **"Create Project"**

Neon creates the project in a few seconds. You land on the project dashboard.

---

### 2.2 Get Your Two Connection Strings

> [!IMPORTANT]
> You need **two connection strings** — a pooled one for the app runtime, and a direct one for Alembic migrations. Using the wrong one for migrations causes silent DDL failures.

On the project dashboard, look for the **"Connection Details"** panel (usually in the top-right or center of the page).

**Get the Pooled Connection String:**

1. In the Connection Details panel, look for a toggle or dropdown labeled **"Connection type"** or **"Pooled"**
2. Select **"Pooled"** (or enable "Connection pooling")
3. The connection string will have `-pooler` in the hostname:
   ```
   postgresql://neondb_owner:AbCdEfGh@ep-cool-wind-a1b2c3d4-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
   ```
4. Click the copy icon next to the string
5. Save it as `DATABASE_URL` in your credentials document

**Get the Direct Connection String:**

1. In the same panel, select **"Direct"** (or disable connection pooling)
2. The hostname will NOT have `-pooler`:
   ```
   postgresql://neondb_owner:AbCdEfGh@ep-cool-wind-a1b2c3d4.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
   ```
3. Copy it
4. Save it as `DATABASE_URL_DIRECT` in your credentials document

> [!WARNING]
> **Why two strings? The pooler breaks Alembic DDL.**
>
> Neon's pooler runs PgBouncer in **transaction mode**. In transaction mode, each statement is processed independently — there is no persistent session between statements. Alembic runs `BEGIN; CREATE TABLE ...; COMMIT;` as a transaction, but PgBouncer in transaction mode intercepts the `BEGIN` and `COMMIT` differently, causing errors like:
> - `cannot run inside a transaction block`
> - `cannot execute ALTER TABLE in a read-only transaction`
>
> The direct (non-pooler) connection has a proper persistent session and works correctly with Alembic. Use it **only for migrations** (only in the build command, not the app runtime).

---

### 2.3 Run Alembic Migrations Against Neon

Do this **once from your local machine** to create all tables in the Neon database. You can also let Render do it in the build command, but testing locally first catches any issues before your first Render deploy.

```powershell
# In kavach/ directory, with your venv activated

# Set the DIRECT connection string (not pooled)
$env:DATABASE_URL = "postgresql://neondb_owner:PASSWORD@ep-XXXX.REGION.aws.neon.tech/neondb?sslmode=require"

# Run Alembic
.\.venv\Scripts\python.exe -m alembic upgrade head
```

**What you should see:**
```
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> abc123, Create users table
INFO  [alembic.runtime.migration] Running upgrade  abc123 -> def456, Create chat sessions
...
```

**If you see an error:**
- `FATAL: password authentication failed` → wrong password in connection string; copy it exactly from Neon dashboard
- `SSL connection is required` → add `?sslmode=require` to the end of the URL
- `could not connect to server` → check that the Neon project was created successfully and the hostname is correct
- `cannot run inside a transaction block` → you're using the pooled URL, not the direct one; switch to `DATABASE_URL_DIRECT`

**Verify tables were created:**

1. Go to the Neon dashboard
2. In the left sidebar, click **"Tables"** (or look for a database explorer/browser section)
3. You should see tables: `users`, `chat_sessions`, `messages`, `alembic_version`
4. If you don't see a "Tables" tab, click **"SQL Editor"** and run:
   ```sql
   SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';
   ```

---

### 2.4 Test Connectivity from Python (Optional but Recommended)

```powershell
# Quick connectivity test — run from kavach/ with venv active
.\.venv\Scripts\python.exe -c "
import psycopg2
conn_str = 'postgresql://neondb_owner:PASSWORD@ep-XXXX.REGION.aws.neon.tech/neondb?sslmode=require'
conn = psycopg2.connect(conn_str)
cur = conn.cursor()
cur.execute('SELECT version()')
print('Neon Postgres version:', cur.fetchone()[0])
cur.execute(\"SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'\")
print('Tables:', [r[0] for r in cur.fetchall()])
conn.close()
print('Connection closed OK')
"
```

---

## 3. Render — Backend

### Render Free Tier Limits

| Limit | Value | Impact |
| :--- | :--- | :--- |
| RAM | 512 MB | FAISS index + Python runtime fits; no `torch` models allowed |
| Disk | Ephemeral (wiped on restart/redeploy) | Generated files (.docx, .xlsx) lost on restart |
| Inactivity spin-down | 15 minutes | Service sleeps; cold start takes up to 60s on next request |
| Free compute hours | 750 hours/month (one free service) | Just enough to run one service 24/7 |
| Build timeout | 15 minutes | Cannot install `torch` — use `requirements-cloud.txt` |
| Outbound bandwidth | 100 GB/month | More than enough for demo |

> [!WARNING]
> **The 15-minute inactivity spin-down is the hardest limitation to work around.** When a judge visits the demo after a period of inactivity, they will see up to 60 seconds of wait time before the first response (Render waking + HF model cold start). There is no free way to prevent this on Render. Options:
> - Use a Netlify function to ping `/health` every 14 minutes (keeps Render awake but uses Netlify function minutes)
> - Accept it and show a clear "Waking up..." loading state in the frontend

---

### 3.1 Connect GitHub Repository

1. Go to: `https://render.com`
2. Click **"Sign Up"** → use **GitHub** (required to deploy from your repo)
3. Authorize Render to access your GitHub account
4. On the Render dashboard, click **"New +"** (top right)
5. Select **"Web Service"**
6. Under "Connect a repository", your GitHub repos will be listed
7. Find `onpremsih117` and click **"Connect"**

---

### 3.2 Configure the Service

After connecting, Render shows a configuration form:

| Field | Value to Enter | Notes |
| :--- | :--- | :--- |
| **Name** | `kavach-backend` | Used in your Render URL |
| **Region** | Match your Neon region | e.g., Singapore for ap-southeast-1 |
| **Branch** | `main` | Or your deployment branch |
| **Root Directory** | `kavach` | **Critical** — without this Render looks in the repo root and can't find `requirements.txt` |
| **Runtime** | `Python 3` | Auto-detected from files |
| **Build Command** | *(see below)* | |
| **Start Command** | `uvicorn backend.main:app --host 0.0.0.0 --port $PORT` | Do not hardcode port |
| **Plan** | `Free` | |

**Build Command** (copy exactly):
```
pip install -r requirements-cloud.txt && DATABASE_URL=$DATABASE_URL_DIRECT python -m alembic upgrade head
```

> This installs dependencies from the cloud-safe requirements file (no `torch`), then runs Alembic migrations using the direct DB connection (not pooled). The `$DATABASE_URL_DIRECT` is a Render env var you will set in the next step.

---

### 3.3 Add Environment Variables

**Before clicking "Create Web Service"**, scroll down to the **"Environment Variables"** section and add all of the following. Click **"Add Environment Variable"** for each one.

You can also use **"Add from .env"** if Render supports it — paste the block below.

```
DATABASE_URL=postgresql://neondb_owner:PASSWORD@ep-XXXX-pooler.REGION.aws.neon.tech/neondb?sslmode=require
DATABASE_URL_DIRECT=postgresql://neondb_owner:PASSWORD@ep-XXXX.REGION.aws.neon.tech/neondb?sslmode=require
LLM_PROVIDER=huggingface
CLOUD_DEPLOYMENT=true
ENABLE_DOCKER_SANDBOX=false
PYTHONPATH=.
HF_REASONING_API_KEY_PRIMARY=hf_...
HF_REASONING_API_KEY_FALLBACK_1=hf_...
HF_REASONING_API_KEY_FALLBACK_2=hf_...
HF_CODE_API_KEY_PRIMARY=hf_...
HF_CODE_API_KEY_FALLBACK_1=hf_...
HF_CODE_API_KEY_FALLBACK_2=hf_...
HF_VISION_API_KEY_PRIMARY=hf_...
HF_VISION_API_KEY_FALLBACK_1=hf_...
HF_VISION_API_KEY_FALLBACK_2=hf_...
HF_EMBEDDING_API_KEY_PRIMARY=hf_...
HF_EMBEDDING_API_KEY_FALLBACK_1=hf_...
HF_EMBEDDING_API_KEY_FALLBACK_2=hf_...
```

> [!NOTE]
> Leave `FRONTEND_ORIGIN` blank for now. You will add it after Netlify gives you the frontend URL in Step 4. Render allows you to add env vars after initial deployment.

---

### 3.4 Deploy

1. Click **"Create Web Service"**
2. Render starts the build. The build log streams live in the dashboard
3. Watch for these expected lines in the build log:
   ```
   ==> Installing dependencies...
   Collecting fastapi...
   ...
   ==> Running build command: pip install -r requirements-cloud.txt && ...
   ...
   INFO [alembic.runtime.migration] Running upgrade -> ..., Create users table
   ...
   ==> Build successful!
   ==> Starting service...
   INFO:     Application startup complete.
   ```

4. If the build fails:
   - **Build timed out**: `requirements-cloud.txt` still contains a heavy package. Check for `torch`, `sentence-transformers`, or `opencv-contrib-python` — remove or replace with lighter alternatives
   - **Alembic failed**: Check that `DATABASE_URL_DIRECT` is set correctly and uses the direct (non-pooled) URL
   - **Import error on startup**: Check the live service logs in Render's "Logs" tab for the Python traceback

5. Once deployed, note your Render URL at the top of the dashboard:
   ```
   https://kavach-backend-XXXX.onrender.com
   ```

---

### 3.5 Verify the Backend is Working

```bash
# Test health endpoint (replace with your actual Render URL)
curl https://kavach-backend-XXXX.onrender.com/health
```

**Expected response:**
```json
{
  "status": "ok",
  "cloud_mode": true,
  "llm_provider": "huggingface",
  "docker_sandbox": false
}
```

If you get a connection timeout → the service is still cold-starting, wait 60 seconds and try again.
If you get `{"detail": "Not Found"}` → the `/health` endpoint wasn't added to `main.py` yet.

---

## 4. Netlify — Frontend

### Netlify Free Tier Limits

| Limit | Value | Impact |
| :--- | :--- | :--- |
| Bandwidth | 100 GB/month | Not a concern for a demo |
| Build minutes | 300/month | Each Vite build takes ~2 min — 150 builds/month max |
| Sites | Unlimited | |
| `VITE_*` env vars | Embedded in the compiled JS bundle | Do not put secrets here — the Render URL is safe |

> [!IMPORTANT]
> **`VITE_API_BASE` will be visible in your browser's JavaScript bundle.** Anyone who opens DevTools can read the Render URL. This is fine — the Render URL is a public API endpoint. Do NOT put HF tokens, database passwords, or any secrets in `VITE_*` variables.

---

### 4.1 Connect Repository and Configure Build

1. Go to: `https://www.netlify.com`
2. Click **"Sign Up"** → use **GitHub**
3. On the Netlify dashboard, click **"Add new site"** → **"Import an existing project"**
4. Click **"Deploy with GitHub"**
5. Authorize Netlify to access your GitHub repositories
6. Find and select `onpremsih117`
7. On the build settings page:

| Field | Value |
| :--- | :--- |
| **Branch to deploy** | `main` |
| **Base directory** | `kavach/frontend-react` |
| **Build command** | `npm run build` |
| **Publish directory** | `kavach/frontend-react/dist` |

> [!NOTE]
> The "Base directory" and "Publish directory" paths are relative to your **repository root**, not the base directory. So even though Base directory is `kavach/frontend-react`, the Publish directory should be `kavach/frontend-react/dist` (full path from repo root).
>
> Some Netlify UI versions show publish directory relative to base. If so, just type `dist`.

---

### 4.2 Add Environment Variables

1. Click **"Show advanced"** (below the build settings)
2. Click **"New variable"** twice and add:

| Key | Value |
| :--- | :--- |
| `VITE_API_BASE` | `https://kavach-backend-XXXX.onrender.com` (your Render URL from Step 3.4) |
| `VITE_CLOUD_DEPLOYMENT` | `true` |

3. Click **"Deploy site"**

---

### 4.3 Wait for Build and Get Your Netlify URL

1. Netlify shows a build log as it runs `npm install` then `npm run build`
2. A successful build ends with:
   ```
   ✓ built in Xs
   Netlify Build Complete
   ```
3. At the top of the site overview, your URL is shown:
   ```
   https://kavach-demo-abc123.netlify.app
   ```
   Or similar — Netlify auto-generates a random subdomain name
4. You can rename it: **Site Settings → General → Site details → Change site name** → enter `kavach-demo` (if available)

**If the build fails:**
- `vite: command not found` → check that `package.json` has `"build": "vite build"` in scripts
- `Module not found` → a frontend dependency is missing; run `npm install` locally and commit `package-lock.json`
- Wrong base directory → double-check the base directory path is correct

---

## 5. Final Wiring

At this point you have:
- ✅ Render URL: `https://kavach-backend-XXXX.onrender.com`
- ✅ Netlify URL: `https://kavach-demo-XXXX.netlify.app`

Now you need to do two things to connect them:

### 5.1 Set FRONTEND_ORIGIN on Render (CORS)

1. Go to the Render dashboard → your `kavach-backend` service
2. Click **"Environment"** in the left sidebar
3. Click **"Add Environment Variable"**
4. Add:
   - Key: `FRONTEND_ORIGIN`
   - Value: `https://kavach-demo-XXXX.netlify.app` (your exact Netlify URL)
5. Click **"Save Changes"**
6. Render will ask if you want to redeploy — click **"Deploy latest commit"** (or "Manual Deploy")

> [!WARNING]
> The value must be the **exact URL with no trailing slash** and no wildcards. Example:
> - ✅ `https://kavach-demo.netlify.app`
> - ❌ `https://kavach-demo.netlify.app/`
> - ❌ `https://*.netlify.app`
>
> FastAPI's CORS middleware does string matching, not pattern matching. A trailing slash or wildcard will cause all cross-origin requests to fail with a CORS error in the browser.

### 5.2 Trigger a Netlify Rebuild (if needed)

If Netlify built before you had the final Render URL, the `VITE_API_BASE` in the built JS is wrong. Fix it:

1. Go to Netlify dashboard → your site → **Site configuration** → **Environment variables**
2. Update `VITE_API_BASE` with the correct Render URL if it wasn't right initially
3. Go to **Deploys** → **"Trigger deploy"** → **"Deploy site"** to rebuild with the correct URL

---

## 6. Quick Verification

### Backend Health Check
```bash
curl https://kavach-backend-XXXX.onrender.com/health
# Expected: {"status":"ok","cloud_mode":true,"llm_provider":"huggingface","docker_sandbox":false}
```

### Database Connectivity (via backend)
```bash
curl https://kavach-backend-XXXX.onrender.com/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser", "password": "testpass123"}'
# Expected: {"access_token": "...", "token_type": "bearer"}
# If this works, Neon DB is connected and tables exist
```

### HF Inference (via backend — slow on first call)
```bash
# First get a token from the register call above, then:
curl https://kavach-backend-XXXX.onrender.com/chat/message \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "What is 2+2?", "session_id": null}'
# Expected: JSON with an AI response (may take 30-90s on first call — HF cold start)
```

### Frontend CORS Check
1. Open `https://kavach-demo-XXXX.netlify.app` in a browser
2. Open DevTools → Network tab
3. Log in or register
4. Check that API calls go to `https://kavach-backend-XXXX.onrender.com` (not localhost)
5. Verify no CORS errors in the Console tab

### Complete Flow Test
1. Register a new user on the Netlify frontend
2. Ask: "What is network segmentation?"
3. Wait for response (first call may take 60+ seconds — model cold start)
4. Ask: "Write a Python function to sort a list"
5. Verify response includes `[Cloud Demo Mode]` note for the sandbox
6. Check the amber cloud-mode banner is visible in the top bar
7. Restart the Render service from the Render dashboard
8. Wait for it to restart (~60s)
9. Log back in and verify your chat history is still there (Neon persisted it)

---

## Troubleshooting Reference

| Symptom | Likely Cause | Fix |
| :--- | :--- | :--- |
| `/health` times out | Render service is cold-starting | Wait 60s and retry |
| `/health` returns 500 | `ctypes.wintypes` crash on import | Fix `shield/firewall.py` — see implementation plan |
| `/health` returns `{"detail":"Not Found"}` | `/health` endpoint not added to `main.py` | Add the health endpoint |
| CORS error in browser | `FRONTEND_ORIGIN` not set or has trailing slash | Set exact Netlify URL on Render, no trailing slash |
| `403 Forbidden` from HF | Model ToS not accepted on this account | Visit model page on HF and accept ToS while logged in as that account |
| `429 Too Many Requests` from HF | Rate limit on primary key | Token rotation should handle; if all 3 exhausted, wait 1 hour |
| `503 Model Loading` from HF | HF model is cold-starting | `hf_client.py` waits and retries automatically |
| Alembic fails on Render build | Using pooled URL for migrations | Ensure build command uses `$DATABASE_URL_DIRECT` |
| Chat history lost after restart | Using `outputs/` path for persistence | DB routes should use Neon; check `backend/chat/` routes write to DB not disk |
| Frontend shows blank page | SPA routing broken | Ensure `_redirects` file is in `public/` and `netlify.toml` has redirect rule |
| Build times out on Render | `torch` or `sentence-transformers` in requirements | Use `requirements-cloud.txt` that excludes them |
| Neon storage full | Too many chat messages | Clean up old sessions via Neon SQL Editor |
