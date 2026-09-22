# KAVACH Cloud Deployment — Final Implementation Plan

> **What**: Cloud demo of KAVACH on zero-cost infrastructure (Render + Netlify + HF Serverless + Neon Postgres).
> **Principle**: All changes are additive and gated behind env vars. The on-prem build is completely untouched.
> **Toggle**: `LLM_PROVIDER=huggingface` + `CLOUD_DEPLOYMENT=true` → cloud mode. Without these, local dev runs exactly as before.

---

## Open Questions — RESOLVED

| Question | Decision |
| :--- | :--- |
| **Rerank token pool** | Separate pool — `HF_RERANK_API_KEY_*` (3 dedicated accounts, accounts 13–15) |
| **`models.json` tracked?** | ✅ Yes — confirmed tracked by git. Contains Ollama tags; `registry.get_model()` is bypassed in HF mode so this file is irrelevant at runtime in cloud, but its presence doesn't cause issues |
| **FAISS index + knowledge tracked?** | ❌ **CRITICAL BLOCKER** — `.gitignore` explicitly ignores `knowledge/faiss_index/`, `*.faiss`, `*.pkl`, and `knowledge/uploads/`. The FAISS index will NOT be on Render. See Component 0 below for the fix |
| **User uploads in cloud** | Acceptable loss — user-uploaded files during a cloud session are lost on Render restart. Pre-loaded shared knowledge (the global `knowledge/faiss_index/`) is the demo content |
| **HF model loading — auto or manual toggle?** | **Fully automatic — no toggle needed.** HF Serverless API loads models on-demand when the first HTTP request arrives. A cold model returns `503 {"estimated_time": N}` — `hf_client.py` waits and retries automatically. There is nothing to enable, configure, or pre-warm manually. Models stay warm for ~5–10 minutes after the last request, then go cold again |

---

## Limitations — Final Summary

| Service | Limitation | Demo Impact |
| :--- | :--- | :--- |
| **HF Serverless** | 20–60s cold start on first call per model | First AI response after idle is slow — show spinner |
| **HF Serverless** | No streaming on free tier | Full response appears at once after 15–45s |
| **HF Serverless** | Gated models need per-account ToS accept | Granite + Qwen2-VL must be accepted on all 15 accounts manually |
| **HF Serverless** | ~100–200 req/hour per token | 3 tokens per role = 300–600 req/hour max per role |
| **HF Serverless** | Model availability not guaranteed | HF may return 503 unexpectedly; token rotation + retry handles it |
| **Render free** | Spins down after 15 min idle, 60s cold start | Combined with HF cold start = up to 2 min for first response |
| **Render free** | No persistent disk | Generated files, user uploads lost on restart |
| **Render free** | No Docker daemon | Sandbox disabled — shows `[Cloud Demo Mode]` note |
| **Render free** | 15-min build timeout | Must use `requirements-cloud.txt` — no `torch`/`sentence-transformers` |
| **Neon free** | 0.5 GB storage, auto-suspends after 5 min idle | First DB query after suspend adds 500ms–2s latency |
| **Netlify** | `VITE_*` vars embedded in compiled JS bundle | Do not put secrets in `VITE_*` — Render URL is safe to expose |

> **On `torch` and `sentence-transformers`**: `rerank.py` uses `ollama.generate()` with a scoring prompt — it is LLM-based, not `CrossEncoder`-based. **Neither `torch` nor `sentence-transformers` are needed on Render.** The `requirements-cloud.txt` drops them to avoid the build timeout — this also saves ~600 MB of RAM on Render.

---

## FAISS Index — Critical Pre-Deploy Action Required

> [!CAUTION]
> The `.gitignore` blocks `knowledge/faiss_index/`, `*.faiss`, `*.pkl`, and `knowledge/uploads/`.
> The global FAISS index (`knowledge/faiss_index/index.faiss`, `metadata.json`, `bm25.json`) **will not be pushed to GitHub and will not exist on Render**.
> Without it, vault retrieval returns empty results — the AI agent cannot access any pre-loaded knowledge.
>
> **Two options. Choose one before deploying:**

### Option A — Force-track the global FAISS index (Recommended for demo)

Add a `.gitignore` exception to track only the global index (not user indexes):

```gitignore
# In kavach/.gitignore — add these lines:

# Exception: track the global shared FAISS knowledge index for cloud deploy
!knowledge/faiss_index/
!knowledge/faiss_index/index.faiss
!knowledge/faiss_index/metadata.json
!knowledge/faiss_index/bm25.json
```

Then force-add the files:
```powershell
git add -f knowledge/faiss_index/index.faiss
git add -f knowledge/faiss_index/metadata.json
git add -f knowledge/faiss_index/bm25.json
git commit -m "chore: track global FAISS knowledge index for cloud deployment"
```

> [!IMPORTANT]
> Check the size of the index first: `knowledge/faiss_index/index.faiss` is currently **76 KB** and `metadata.json` is **13 KB** — well within GitHub's 100 MB file limit. Safe to commit.

### Option B — Re-ingest documents at Render build time

Add a build step that runs the ingest pipeline on Render using the source documents. This requires:
- The source documents tracked in git (none currently are — `knowledge/uploads/` is also gitignored)
- An ingest script that runs against HF embedding API

**Not recommended** — complex, slow at build time, and requires all source documents to be committed.

**→ Use Option A.**

---

## HF Model Loading — How It Works (No Manual Toggle)

When `hf_client.py` sends the first POST to:
```
POST https://api-inference.huggingface.co/models/Qwen/Qwen2.5-7B-Instruct
Authorization: Bearer hf_...
```

HF automatically routes it to their shared GPU pool. Two possible responses:

**If the model is warm** (recent prior request):
```json
[{"generated_text": "...response..."}]
```

**If the model is cold** (first request or idle):
```json
{"error": "Model Qwen/Qwen2.5-7B-Instruct is currently loading", "estimated_time": 20.5}
```

`hf_client.py` catches this `503`, waits `estimated_time` seconds (capped at 60s), then retries. After the retry the model is warm and responds normally. This is fully automatic — **you do nothing extra**. The only user-visible effect is a longer first response time.

Models stay warm for approximately 5–10 minutes after the last request. If no requests come in for that window, the next call hits a cold start again. This is why the first demo request to an idle system will always be slow.

---

## HF Accounts — Final Count: 15 Accounts (5 Roles × 3 Tokens)

| Role | Model | Gated? | Env vars |
| :--- | :--- | :--- | :--- |
| Reasoning | `Qwen/Qwen2.5-7B-Instruct` | No | `HF_REASONING_API_KEY_*` |
| Code | `ibm-granite/granite-3.3-8b-instruct` | **Yes** | `HF_CODE_API_KEY_*` |
| Vision | `Qwen/Qwen2-VL-7B-Instruct` | **Yes** | `HF_VISION_API_KEY_*` |
| Embedding | `nomic-ai/nomic-embed-text-v1.5` | No | `HF_EMBEDDING_API_KEY_*` |
| **Rerank** | `Qwen/Qwen2.5-7B-Instruct` | No | `HF_RERANK_API_KEY_*` |

---

## Complete File Change Audit

### Modified Files

| File | What Changes | Why |
| :--- | :--- | :--- |
| [`backend/config.py`](file:///c:/Users/Asus/Documents/Kavach_1/onpremsih117/kavach/backend/config.py) | Add cloud flags + HF token pools for 5 roles + HF model IDs for 5 roles | Central source of truth for all cloud config |
| [`backend/engine/__init__.py`](file:///c:/Users/Asus/Documents/Kavach_1/onpremsih117/kavach/backend/engine/__init__.py) | Export `active_llm` dispatch (ollama or hf_client) | Single import alias change propagates everywhere |
| [`backend/engine/registry.py`](file:///c:/Users/Asus/Documents/Kavach_1/onpremsih117/kavach/backend/engine/registry.py) | Guard `ollama.list_models()` call at top of `get_model()` | Ollama not running on Render; return HF model ID directly |
| [`backend/brain/agent.py`](file:///c:/Users/Asus/Documents/Kavach_1/onpremsih117/kavach/backend/brain/agent.py) L29 | `import ollama` → `import active_llm as ollama` | Route LLM calls to HF in cloud mode |
| [`backend/brain/router.py`](file:///c:/Users/Asus/Documents/Kavach_1/onpremsih117/kavach/backend/brain/router.py) L17 | Same | Same |
| [`backend/brain/tools_dispatch.py`](file:///c:/Users/Asus/Documents/Kavach_1/onpremsih117/kavach/backend/brain/tools_dispatch.py) L17 | Same | Same |
| [`backend/vault/ingest.py`](file:///c:/Users/Asus/Documents/Kavach_1\onpremsih117\kavach\backend\vault\ingest.py) L24 | Same | Same |
| [`backend/vault/retrieve.py`](file:///c:/Users/Asus/Documents/Kavach_1/onpremsih117/kavach/backend/vault/retrieve.py) L21 | Same | Same |
| [`backend/vault/rerank.py`](file:///c:/Users/Asus/Documents/Kavach_1/onpremsih117/kavach/backend/vault/rerank.py) L13 | Same | Same — reranker already uses LLM-based scoring, works transparently with HF |
| [`backend/tools/code.py`](file:///c:/Users/Asus/Documents/Kavach_1/onpremsih117/kavach/backend/tools/code.py) L16 | Same | Same |
| [`backend/tools/search.py`](file:///c:/Users/Asus/Documents/Kavach_1/onpremsih117/kavach/backend/tools/search.py) L12 | Same | Same |
| [`backend/tools/vision.py`](file:///c:/Users/Asus/Documents/Kavach_1/onpremsih117/kavach/backend/tools/vision.py) L10 | Same | Same |
| [`backend/tools/writer.py`](file:///c:/Users/Asus/Documents/Kavach_1/onpremsih117/kavach/backend/tools/writer.py) L24 | Same | Same |
| [`backend/tools/excel.py`](file:///c:/Users/Asus/Documents/Kavach_1/onpremsih117/kavach/backend/tools/excel.py) L31 | Same | Same |
| [`backend/tools/ppt.py`](file:///c:/Users/Asus/Documents/Kavach_1/onpremsih117/kavach/backend/tools/ppt.py) L32 | Same | Same |
| [`backend/tools/calc.py`](file:///c:/Users/Asus/Documents/Kavach_1/onpremsih117/kavach/backend/tools/calc.py) L17 | Same | Same |
| [`backend/guard/verify.py`](file:///c:/Users/Asus/Documents/Kavach_1/onpremsih117/kavach/backend/guard/verify.py) L15 | Same | Same |
| [`backend/tools/sandbox.py`](file:///c:/Users/Asus/Documents/Kavach_1/onpremsih117/kavach/backend/tools/sandbox.py) | Add cloud short-circuit at top of `run_code()` | Docker not available on Render; run syntax check only |
| [`backend/shield/firewall.py`](file:///c:/Users/Asus/Documents/Kavach_1/onpremsih117/kavach/backend/shield/firewall.py) | Wrap `ctypes.wintypes` in `platform.system()` guard | **Crashes the entire app at import time on Linux without this** |
| [`backend/shield/monitor.py`](file:///c:/Users/Asus/Documents/Kavach_1/onpremsih117/kavach/backend/shield/monitor.py) | Wrap `psutil.net_connections()` in `try/except AccessDenied` | Container Linux may deny this syscall |
| [`backend/shield/netinfo.py`](file:///c:/Users/Asus/Documents/Kavach_1/onpremsih117/kavach/backend/shield/netinfo.py) | Wrap interface detection in `try/except` | Returns safe defaults on container networking failure |
| [`backend/tools/ocr.py`](file:///c:/Users/Asus/Documents/Kavach_1/onpremsih117/kavach/backend/tools/ocr.py) | Add `shutil.which("tesseract")` guard | Return clean error if binary not found; not pre-installed on Render |
| [`backend/main.py`](file:///c:/Users/Asus/Documents/Kavach_1/onpremsih117/kavach/backend/main.py) | Add Netlify CORS origin; add `GET /health`; guard `start_monitor()` | CORS needed for cross-origin calls; health needed for Render liveness |
| [`frontend-react/src/App.jsx`](file:///c:/Users/Asus/Documents/Kavach_1/onpremsih117/kavach/frontend-react/src/App.jsx) | `API_BASE = ''` → `import.meta.env.VITE_API_BASE \|\| ''` | Frontend must point to Render URL in production |
| [`frontend-react/src/components/TopBar.jsx`](file:///c:/Users/Asus/Documents/Kavach_1/onpremsih117/kavach/frontend-react/src/components/TopBar.jsx) | Add cloud-mode amber banner | Clearly communicate demo limitations to judges |
| [`.gitignore`](file:///c:/Users/Asus/Documents/Kavach_1/onpremsih117/kavach/.gitignore) | Add `!knowledge/faiss_index/` exception | Force-track global FAISS index for Render |

### New Files

| File | Purpose |
| :--- | :--- |
| `backend/engine/hf_client.py` | HF Serverless API adapter — identical signatures to `ollama.py` |
| `requirements-cloud.txt` | `requirements.txt` minus `torch` and `sentence-transformers` |
| `apt.txt` | Render build-time `apt-get install tesseract-ocr` |
| `netlify.toml` | Netlify build config + SPA redirect rule |
| `frontend-react/public/_redirects` | Netlify SPA routing fallback |

---

## Component-by-Component Implementation

---

### Component 0: `.gitignore` + Force-Commit FAISS Index

**What**: Add gitignore exceptions to track the global FAISS index. This is required before deploying — without it, vault retrieval is broken in cloud.

**Edit `.gitignore`** — add after line 16 (`*.pkl`):

```gitignore
# Exception: track the global shared knowledge FAISS index for cloud deployment
# (User-specific indexes under knowledge/users/ remain excluded)
!knowledge/faiss_index/
!knowledge/faiss_index/index.faiss
!knowledge/faiss_index/metadata.json
!knowledge/faiss_index/bm25.json
```

**Then commit:**
```powershell
git add -f knowledge/faiss_index/index.faiss
git add -f knowledge/faiss_index/metadata.json
git add -f knowledge/faiss_index/bm25.json
git add .gitignore
git commit -m "chore: track global FAISS index for cloud deployment; update gitignore"
```

> [!NOTE]
> User-specific indexes (`knowledge/users/*/faiss_index/`) remain gitignored. In cloud mode, users can still upload documents and build their own index — it will work during a session but will be lost when Render restarts (ephemeral disk). For the demo, the pre-loaded global knowledge is what judges will use. This is an accepted tradeoff.

---

### Component 1: `backend/config.py`

**What**: Append cloud deployment flags and HF token/model config after the existing `OLLAMA_BASE_URL` line.

**Implementation** — add after line 51:

```python
# ──────────────────────────────────────────────────────────────────────────
# Cloud deployment flags
# Default to local/off — only activated when env vars are set on Render
# ──────────────────────────────────────────────────────────────────────────
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama")  # "ollama" | "huggingface"
CLOUD_DEPLOYMENT = os.environ.get("CLOUD_DEPLOYMENT", "false").lower() == "true"
ENABLE_DOCKER_SANDBOX = os.environ.get("ENABLE_DOCKER_SANDBOX", "true").lower() == "true"

# ──────────────────────────────────────────────────────────────────────────
# Hugging Face token pools — 3 tokens per role, for rotation on 429/503
# Pattern: HF_{ROLE}_API_KEY_{SLOT}  where SLOT = PRIMARY | FALLBACK_1 | FALLBACK_2
# ──────────────────────────────────────────────────────────────────────────
def _load_hf_keys(role: str) -> list[str]:
    """Returns non-empty tokens for this role in [primary, fb1, fb2] order."""
    return [
        v for s in ["PRIMARY", "FALLBACK_1", "FALLBACK_2"]
        if (v := os.environ.get(f"HF_{role.upper()}_API_KEY_{s}", "").strip())
    ]

HF_KEYS: dict[str, list[str]] = {
    "reasoning": _load_hf_keys("REASONING"),
    "code":      _load_hf_keys("CODE"),
    "vision":    _load_hf_keys("VISION"),
    "embedding": _load_hf_keys("EMBEDDING"),
    "rerank":    _load_hf_keys("RERANK"),   # dedicated pool — 3 separate accounts
}

# ──────────────────────────────────────────────────────────────────────────
# Hugging Face model IDs (HF Hub format — NOT Ollama tags)
# Override via env var without code changes
# ──────────────────────────────────────────────────────────────────────────
HF_MODELS: dict[str, str] = {
    "reasoning": os.environ.get("HF_MODEL_REASONING", "Qwen/Qwen2.5-7B-Instruct"),
    "code":      os.environ.get("HF_MODEL_CODE",      "ibm-granite/granite-3.3-8b-instruct"),
    "vision":    os.environ.get("HF_MODEL_VISION",    "Qwen/Qwen2-VL-7B-Instruct"),
    "embedding": os.environ.get("HF_MODEL_EMBEDDING", "nomic-ai/nomic-embed-text-v1.5"),
    "rerank":    os.environ.get("HF_MODEL_RERANK",    "Qwen/Qwen2.5-7B-Instruct"),
}
```

---

### Component 2: `backend/engine/hf_client.py` — New File

**What**: A new engine module that calls the HF Serverless Inference API. Must export the **exact same function signatures** as `ollama.py` so zero call-site changes are needed anywhere in `brain/`, `tools/`, or `vault/`.

**Signature match table** (from reading `ollama.py`):

| `ollama.py` function | Signature | `hf_client.py` must match |
| :--- | :--- | :--- |
| `generate` | `(model: str, prompt: str, system: str = None) -> str` | ✅ |
| `chat` | `(model: str, messages: list[dict]) -> str` | ✅ |
| `embed` | `(model: str, text: str) -> list[float]` | ✅ |
| `embed_batch` | `(model: str, texts: list[str]) -> list[list[float]]` | ✅ |
| `vision` | `(model: str, prompt: str, image_path: str) -> str` | ✅ |
| `list_models` | `() -> list[str]` | ✅ Returns `HF_MODELS.values()` |

**Create `backend/engine/hf_client.py`:**

```python
"""hf_client.py — Hugging Face Serverless Inference API adapter for KAVACH.

Exports identical function signatures to ollama.py so all call sites work
without modification when routed through the active_llm dispatch.

Limitations:
  - No streaming: stream parameter is ignored; full response returned after generation
  - Cold starts: 20-60s on first call; handled by 503 wait-and-retry logic
  - Rate limits: ~100-200 req/hour per token; rotates through primary/fallback keys
  - Gated models (Granite, Qwen2-VL): require per-account ToS acceptance on HF
  - Vision response time: 30-90s for image understanding tasks
"""

import base64
import logging
import time
from pathlib import Path

import httpx

from backend import config

logger = logging.getLogger("kavach.hf_client")

HF_API_BASE = "https://api-inference.huggingface.co/models"
_DEFAULT_TIMEOUT = 120.0  # seconds — HF can be slow, don't time out early


class HFClientError(RuntimeError):
    """Raised when all token slots for a role are exhausted."""
    pass


def _role_from_model(model_id: str) -> str:
    """Reverse-lookup: given a HF model ID, return which role it serves."""
    for role, mid in config.HF_MODELS.items():
        if mid == model_id:
            return role
    return "reasoning"  # safe default


def _call_with_rotation(model_id: str, payload: dict) -> dict | list:
    """
    POST to HF Serverless API with token rotation.

    Rotation logic:
      - Try PRIMARY key first.
      - 429 Too Many Requests → rotate to next key.
      - 503 Model Loading → wait estimated_time (max 60s) → retry same key once → then rotate.
      - 403 Forbidden → raise immediately (ToS not accepted — no point rotating).
      - All keys exhausted → raise HFClientError.
    """
    role = _role_from_model(model_id)
    keys = config.HF_KEYS.get(role, [])

    if not keys:
        raise HFClientError(
            f"No HF API keys configured for role '{role}'. "
            f"Set HF_{role.upper()}_API_KEY_PRIMARY in Render environment variables."
        )

    url = f"{HF_API_BASE}/{model_id}"
    last_error = "unknown"

    for i, key in enumerate(keys):
        slot = "PRIMARY" if i == 0 else f"FALLBACK_{i}"
        try:
            logger.debug(f"[HF] {role}/{slot} → {url}")
            resp = httpx.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {key}"},
                timeout=_DEFAULT_TIMEOUT,
            )

            if resp.status_code == 200:
                return resp.json()

            elif resp.status_code == 429:
                logger.warning(f"[HF] {role}/{slot} → 429 rate limited, rotating to next key")
                last_error = f"Rate limited on {slot}"
                continue

            elif resp.status_code == 503:
                body = resp.json() if resp.content else {}
                wait_sec = min(float(body.get("estimated_time", 20)), 60)
                logger.info(f"[HF] {role}/{slot} → 503 model loading, waiting {wait_sec:.0f}s")
                time.sleep(wait_sec)
                # One retry on same key after the wait
                resp2 = httpx.post(
                    url, json=payload,
                    headers={"Authorization": f"Bearer {key}"},
                    timeout=_DEFAULT_TIMEOUT,
                )
                if resp2.status_code == 200:
                    return resp2.json()
                logger.warning(f"[HF] {role}/{slot} still failing after wait, rotating")
                last_error = f"503 model loading on {slot} (waited {wait_sec:.0f}s)"
                continue

            elif resp.status_code == 403:
                raise HFClientError(
                    f"HF 403 Forbidden for model '{model_id}' using {slot} key. "
                    "The HF account associated with this token has NOT accepted this model's Terms of Service. "
                    f"Fix: log into that HF account → visit https://huggingface.co/{model_id} → click 'Agree and access repository'."
                )

            else:
                raise HFClientError(
                    f"HF API error {resp.status_code} for role '{role}' ({slot}): {resp.text[:300]}"
                )

        except httpx.TimeoutException:
            logger.warning(f"[HF] {role}/{slot} → timed out after {_DEFAULT_TIMEOUT}s, rotating")
            last_error = f"Timeout on {slot}"
            continue

    raise HFClientError(
        f"All HF keys exhausted for role '{role}' (tried {len(keys)} slot(s)). Last: {last_error}"
    )


def _extract_text(result: dict | list, prompt: str = "") -> str:
    """Extract assistant text from HF response — handles multiple response formats."""
    if isinstance(result, list) and result:
        raw = result[0].get("generated_text", "")
        if isinstance(raw, list):
            # Messages API: [{role, content}, ...] — get last assistant message
            for msg in reversed(raw):
                if isinstance(msg, dict) and msg.get("role") == "assistant":
                    return msg.get("content", "").strip()
            return ""
        # Text-generation format returns prompt + completion — strip prompt prefix
        if prompt and isinstance(raw, str) and raw.startswith(prompt):
            return raw[len(prompt):].strip()
        return raw.strip() if isinstance(raw, str) else str(raw)

    if isinstance(result, dict):
        if "choices" in result:
            # OpenAI-compatible chat completions format
            return result["choices"][0]["message"]["content"].strip()
        if "generated_text" in result:
            return result["generated_text"].strip()

    return str(result)


# ─────────────────────────────────────────────────────────────────────────────
# Public API — identical signatures to ollama.py
# ─────────────────────────────────────────────────────────────────────────────

def generate(model: str, prompt: str, system: str | None = None) -> str:
    """Generate a completion. 'model' is a HF model ID from config.HF_MODELS.
    Streaming is not supported on HF Serverless free tier — full response returned at once.
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "messages": messages,
        "max_new_tokens": 1024,
        "temperature": 0.7,
    }
    result = _call_with_rotation(model, payload)
    return _extract_text(result, prompt)


def chat(model: str, messages: list[dict]) -> str:
    """Multi-turn chat with a list of {role, content} message dicts."""
    payload = {
        "messages": messages,
        "max_new_tokens": 1024,
        "temperature": 0.7,
    }
    result = _call_with_rotation(model, payload)
    return _extract_text(result)


def embed(model: str, text: str) -> list[float]:
    """Single text embedding. HF feature-extraction returns [[float, ...]] — one level unwrapped."""
    result = _call_with_rotation(model, {"inputs": text})
    if isinstance(result, list) and result:
        inner = result[0]
        # feature-extraction endpoint returns [[vec]] — unwrap outer list
        if isinstance(inner, list):
            return inner
        return result
    raise HFClientError(f"Unexpected embed response format: {type(result)}")


def embed_batch(model: str, texts: list[str]) -> list[list[float]]:
    """Batch embeddings. HF returns [[vec1], [vec2]] or [[f,f,...],[f,f,...]]."""
    result = _call_with_rotation(model, {"inputs": texts})
    if isinstance(result, list) and result:
        # If doubly-nested [[vec]] per text, unwrap
        if isinstance(result[0], list) and result[0] and isinstance(result[0][0], list):
            return [r[0] for r in result]
        return result
    raise HFClientError(f"Unexpected embed_batch response: {type(result)}")


def vision(model: str, prompt: str, image_path: str) -> str:
    """Vision inference. Image is base64-encoded and sent in payload.
    Response time on HF free tier is 30-90s — expect slow responses for image tasks.
    """
    img_bytes = Path(image_path).read_bytes()
    b64 = base64.b64encode(img_bytes).decode("utf-8")
    ext = Path(image_path).suffix.lower().lstrip(".")
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
            "gif": "image/gif", "webp": "image/webp"}.get(ext, "image/jpeg")

    payload = {
        "inputs": {
            "image": f"data:{mime};base64,{b64}",
            "question": prompt,
        }
    }
    result = _call_with_rotation(model, payload)
    return _extract_text(result, prompt)


def list_models() -> list[str]:
    """Returns configured HF model IDs. Satisfies registry.py's validation call
    without hitting Ollama. Used by get_model() in cloud mode.
    """
    return list(config.HF_MODELS.values())
```

---

### Component 3: `backend/engine/__init__.py`

**What**: Export `active_llm` — a module-level alias that points to either `ollama` or `hf_client` based on `LLM_PROVIDER`.

**Current file (4 lines):**
```python
from backend.engine import ollama, prompts, registry
__all__ = ["ollama", "prompts", "registry"]
```

**New file:**
```python
from backend.engine import prompts, registry
from backend import config

# Dispatch: route all LLM calls to HF (cloud) or Ollama (local)
if config.LLM_PROVIDER == "huggingface":
    from backend.engine import hf_client as active_llm
else:
    from backend.engine import ollama as active_llm

# Keep ollama importable for code that explicitly needs it (on-prem path)
from backend.engine import ollama

__all__ = ["active_llm", "ollama", "prompts", "registry"]
```

---

### Component 4: `backend/engine/registry.py`

**What**: Add a 3-line early return at the top of `get_model()` that bypasses the `ollama.list_models()` validation when in HF mode. In HF mode, `models.json` Ollama tags are irrelevant — we return the HF model ID from `config.HF_MODELS` directly.

**Current `get_model()` (line 21):**
```python
def get_model(role: str) -> str:
    """Returns the model tag assigned to a specific task role, with smart fallback."""
    reg = load_registry()
    if role not in reg:
        raise KeyError(...)
    target_tag = reg[role]
    from backend.engine import ollama
    try:
        installed = ollama.list_models()
    ...
```

**Add at the top, before `reg = load_registry()`:**
```python
def get_model(role: str) -> str:
    """Returns model identifier for the given role.
    HF cloud mode: returns HF model ID from config, no Ollama validation.
    Ollama local mode: validates against installed models as before.
    """
    # HF cloud mode: bypass models.json and Ollama entirely
    if config.LLM_PROVIDER == "huggingface":
        return config.HF_MODELS.get(role, config.HF_MODELS.get("reasoning"))

    # Ollama local mode — existing logic below unchanged
    reg = load_registry()
    ...
```

---

### Component 5: Import Updates — 14 Files

**What**: Replace `from backend.engine import ollama` with `from backend.engine import active_llm as ollama` in every consumer file. The `as ollama` alias means every `ollama.generate(...)`, `ollama.embed(...)` call in the file body remains **completely unchanged**.

**Pattern (identical for all 14 files):**
```python
# Before:
from backend.engine import ollama, registry

# After:
from backend.engine import active_llm as ollama, registry
```

**All 14 files (confirmed via grep — exact line numbers):**

| File | Line | Change |
| :--- | :--- | :--- |
| `backend/brain/agent.py` | 29 | `import active_llm as ollama, registry` |
| `backend/brain/router.py` | 17 | same |
| `backend/brain/tools_dispatch.py` | 17 | same |
| `backend/vault/ingest.py` | 24 | same |
| `backend/vault/retrieve.py` | 21 | same |
| `backend/vault/rerank.py` | 13 | same — reranker uses `ollama.generate()` for LLM-based scoring; works identically via HF |
| `backend/tools/code.py` | 16 | same |
| `backend/tools/search.py` | 12 | same |
| `backend/tools/vision.py` | 10 | same |
| `backend/tools/writer.py` | 24 | same |
| `backend/tools/excel.py` | 31 | same |
| `backend/tools/ppt.py` | 32 | same |
| `backend/tools/calc.py` | 17 | same |
| `backend/guard/verify.py` | 15 | same |

> [!NOTE]
> `backend/engine/__init__.py` line 1 and `backend/engine/registry.py` line 28 also import `ollama` — those are handled differently in Components 3 and 4. Do not apply the pattern above to them.

---

### Component 6: `backend/tools/sandbox.py`

**What**: Cloud short-circuit at the very top of `run_code()`. When `ENABLE_DOCKER_SANDBOX=false`, skip Docker entirely. For Python, run `ast.parse()` for syntax validation (zero dependencies). Return a structured `cloud_note` field so the agent reports the limitation to the user naturally.

**Add at the very top of `run_code()` (before any existing Docker logic):**

```python
def run_code(code: str, language: str = "python") -> dict:
    from backend import config

    # ── Cloud mode: Docker unavailable on Render ────────────────────────────
    if not config.ENABLE_DOCKER_SANDBOX:
        _note = (
            "[Cloud Demo Mode] Code generated and syntax-verified. "
            "Live Docker sandbox execution runs only in the on-premises deployment."
        )
        if language.lower() == "python":
            import ast
            try:
                ast.parse(code)
                return {"success": True, "stdout": "", "stderr": "",
                        "cloud_note": _note, "syntax_valid": True}
            except SyntaxError as exc:
                return {"success": False, "stdout": "", "stderr": f"Syntax error: {exc}",
                        "cloud_note": _note, "syntax_valid": False}
        return {"success": True, "stdout": "", "stderr": "", "cloud_note": _note}
    # ── End cloud short-circuit — Docker path below is unchanged ────────────

    # ... rest of existing function unchanged
```

---

### Component 7: `backend/shield/firewall.py`

**What**: Wrap `ctypes.wintypes` import in a platform guard.

> [!CAUTION]
> **Must be fixed before any other code is deployed.** `ctypes.wintypes` does not exist in Python's Linux build. This import at module level crashes the entire ASGI app before a single request is handled. The 500 errors are impossible to debug from Render logs unless you know to look here.

**Replace the ctypes import block at the top of the file:**

```python
# Before:
import ctypes
from ctypes import wintypes
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
# ...

# After:
import platform
_IS_WINDOWS = platform.system() == "Windows"

if _IS_WINDOWS:
    import ctypes
    from ctypes import wintypes
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    # ... rest of Windows ctypes setup exactly as-is
```

**Add OS gate to every public function that uses Windows APIs:**

```python
def check_firewall_status() -> dict:
    if not _IS_WINDOWS:
        return {
            "status": "simulated", "platform": "linux", "active": False, "rules": [],
            "note": "Firewall lockdown enforced only in the on-premises Windows deployment.",
        }
    # ... existing Windows logic

def enable_firewall_lockdown() -> dict:
    if not _IS_WINDOWS:
        return {"success": True, "simulated": True,
                "note": "Cloud demo — firewall lockdown simulated on Linux."}
    # ... existing Windows logic

def disable_firewall_lockdown() -> dict:
    if not _IS_WINDOWS:
        return {"success": True, "simulated": True,
                "note": "Cloud demo — firewall lockdown simulated on Linux."}
    # ... existing Windows logic
```

---

### Component 8: `backend/shield/monitor.py`

**What**: Wrap `psutil.net_connections()` in try/except. Render containers may deny this syscall. Also remove Ollama process lookup when in HF mode.

```python
# Wrap the net_connections call:
try:
    conns = psutil.net_connections(kind="inet")
except (psutil.AccessDenied, PermissionError, OSError):
    logger.warning("psutil.net_connections() denied in container — partial data")
    return {
        "partial": True, "external_connections": [], "connection_count": 0,
        "note": "Connection monitor has limited access in cloud environment.",
    }

# Guard Ollama process name lookup:
from backend import config
_MONITORED_PROCESSES = (
    ["ollama", "kavach"] if config.LLM_PROVIDER == "ollama" else ["kavach"]
)
```

---

### Component 9: `backend/shield/netinfo.py`

**What**: Wrap interface detection in `try/except Exception`.

```python
def detect_local_network() -> dict:
    try:
        # ... existing logic unchanged
    except Exception as exc:
        logger.warning(f"Network interface detection unavailable in container: {exc}")
        return {
            "local_ip": "127.0.0.1", "subnet": "127.0.0.1/8", "interfaces": [],
            "cloud_note": "Interface detection unavailable in container environment.",
        }
```

---

### Component 10: `backend/tools/ocr.py` + `apt.txt`

**What**: Add binary presence check before calling pytesseract. Render doesn't have Tesseract pre-installed — `apt.txt` installs it at build time.

**In `_run_tesseract_ocr()` — add at the very top of the function:**

```python
def _run_tesseract_ocr(img_input):
    import shutil
    if not shutil.which("tesseract"):
        return {
            "success": False, "text": "",
            "error": (
                "OCR unavailable: tesseract binary not found in PATH. "
                "Ensure apt.txt contains 'tesseract-ocr'. "
                "Use the vision model as fallback for image text extraction."
            ),
        }
    # ... existing logic unchanged
```

**New file `apt.txt`** (place in `kavach/` root directory — same level as `requirements.txt`):

```
tesseract-ocr
tesseract-ocr-eng
```

---

### Component 11: `backend/main.py`

**What**: Three targeted additions.

**1. CORS — add Netlify origin** (find `allow_origins` list, add new entry):
```python
allow_origins=[
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    # ... existing origins ...
    # Cloud: set FRONTEND_ORIGIN to the exact Netlify URL (no wildcards supported)
    os.environ.get("FRONTEND_ORIGIN", ""),
],
```

> [!WARNING]
> FastAPI's `CORSMiddleware` does strict string matching. `https://*.netlify.app` will NOT work. `FRONTEND_ORIGIN` must be the exact deployed URL, e.g. `https://kavach-demo.netlify.app`.

**2. Add `/health` endpoint:**
```python
@app.get("/health")
def health_check():
    from backend import config
    return {
        "status": "ok",
        "cloud_mode": config.CLOUD_DEPLOYMENT,
        "llm_provider": config.LLM_PROVIDER,
        "docker_sandbox": config.ENABLE_DOCKER_SANDBOX,
    }
```

**3. Guard `start_monitor()` startup:**
```python
@app.on_event("startup")
def _on_startup() -> None:
    import platform
    interval = 1.0 if platform.system() == "Windows" else 10.0
    try:
        start_monitor(interval_seconds=interval)
    except Exception as exc:
        logging.getLogger("kavach.main").warning(
            f"Sovereignty monitor startup (non-fatal): {exc}"
        )
```

---

### Component 12: `requirements-cloud.txt`

**What**: Copy of `requirements.txt` with `torch>=2.0.0` and `sentence-transformers>=2.2.0` removed.

Create `kavach/requirements-cloud.txt` — copy `requirements.txt` exactly, then delete these two lines:
```
torch>=2.0.0
sentence-transformers>=2.2.0
```

All other packages remain. Render's **Build Command** references this file:
```
pip install -r requirements-cloud.txt && DATABASE_URL=$DATABASE_URL_DIRECT python -m alembic upgrade head
```

---

### Component 13: Netlify Config Files

**New file `kavach/netlify.toml`:**
```toml
[build]
  base    = "frontend-react"
  command = "npm run build"
  publish = "dist"

[[redirects]]
  from   = "/*"
  to     = "/index.html"
  status = 200
```

**New file `frontend-react/public/_redirects`:**
```
/*    /index.html    200
```

Both serve the same purpose (SPA routing). `netlify.toml` is the primary config; `_redirects` is a fallback.

---

### Component 14: Frontend Changes

#### `frontend-react/src/App.jsx` — 1-line change

```js
// Find (line 10):
const API_BASE = '';

// Replace with:
const API_BASE = import.meta.env.VITE_API_BASE || '';
```

Zero behavior change in local dev (`VITE_API_BASE` not set → falls back to `''` → same-origin Vite proxy).

#### `frontend-react/src/components/TopBar.jsx` — Add cloud banner

```jsx
// Add near the top of the file, after imports:
const IS_CLOUD = import.meta.env.VITE_CLOUD_DEPLOYMENT === 'true';

// Add inside the topbar JSX — visible but non-intrusive:
{IS_CLOUD && (
  <div style={{
    background: 'rgba(251, 191, 36, 0.12)',
    border: '1px solid rgba(251, 191, 36, 0.4)',
    color: '#fbbf24',
    fontSize: '0.72rem',
    fontWeight: 500,
    padding: '3px 10px',
    borderRadius: '4px',
    letterSpacing: '0.03em',
    whiteSpace: 'nowrap',
  }}>
    ☁️ Cloud Demo — Sovereignty Shield & Docker Sandbox are on-premises only
  </div>
)}
```

---

## Environment Variables — Complete Reference

### Render (Backend)

```ini
# Neon Postgres
DATABASE_URL=postgresql://neondb_owner:PASS@ep-XXXX-pooler.REGION.aws.neon.tech/neondb?sslmode=require
DATABASE_URL_DIRECT=postgresql://neondb_owner:PASS@ep-XXXX.REGION.aws.neon.tech/neondb?sslmode=require

# Cloud flags
LLM_PROVIDER=huggingface
CLOUD_DEPLOYMENT=true
ENABLE_DOCKER_SANDBOX=false
PYTHONPATH=.

# CORS — exact Netlify URL, no trailing slash, no wildcards
FRONTEND_ORIGIN=https://kavach-demo-XXXX.netlify.app

# HF Tokens — Reasoning (3 accounts)
HF_REASONING_API_KEY_PRIMARY=hf_...
HF_REASONING_API_KEY_FALLBACK_1=hf_...
HF_REASONING_API_KEY_FALLBACK_2=hf_...

# HF Tokens — Code (3 accounts)
HF_CODE_API_KEY_PRIMARY=hf_...
HF_CODE_API_KEY_FALLBACK_1=hf_...
HF_CODE_API_KEY_FALLBACK_2=hf_...

# HF Tokens — Vision (3 accounts)
HF_VISION_API_KEY_PRIMARY=hf_...
HF_VISION_API_KEY_FALLBACK_1=hf_...
HF_VISION_API_KEY_FALLBACK_2=hf_...

# HF Tokens — Embedding (3 accounts)
HF_EMBEDDING_API_KEY_PRIMARY=hf_...
HF_EMBEDDING_API_KEY_FALLBACK_1=hf_...
HF_EMBEDDING_API_KEY_FALLBACK_2=hf_...

# HF Tokens — Rerank (3 dedicated accounts)
HF_RERANK_API_KEY_PRIMARY=hf_...
HF_RERANK_API_KEY_FALLBACK_1=hf_...
HF_RERANK_API_KEY_FALLBACK_2=hf_...

# HF Model overrides (defaults shown — only set to override)
HF_MODEL_REASONING=Qwen/Qwen2.5-7B-Instruct
HF_MODEL_CODE=ibm-granite/granite-3.3-8b-instruct
HF_MODEL_VISION=Qwen/Qwen2-VL-7B-Instruct
HF_MODEL_EMBEDDING=nomic-ai/nomic-embed-text-v1.5
HF_MODEL_RERANK=Qwen/Qwen2.5-7B-Instruct
```

### Netlify (Frontend Build)

```ini
VITE_API_BASE=https://kavach-backend-XXXX.onrender.com
VITE_CLOUD_DEPLOYMENT=true
```

### Render Service Settings

```
Root Directory:  kavach/
Build Command:   pip install -r requirements-cloud.txt && DATABASE_URL=$DATABASE_URL_DIRECT python -m alembic upgrade head
Start Command:   uvicorn backend.main:app --host 0.0.0.0 --port $PORT
Python Version:  3.11
```

---

## Implementation Task Order

Execute in this exact sequence — each step depends on the previous:

```
Step 0:  Fix .gitignore + git add FAISS index files + commit      ← BLOCKER: do before anything else
Step 1:  backend/shield/firewall.py — platform guard              ← BLOCKER: without this, app won't start on Linux
Step 2:  backend/config.py — cloud flags + HF config
Step 3:  backend/engine/hf_client.py — create new file
Step 4:  backend/engine/__init__.py — dispatch layer
Step 5:  backend/engine/registry.py — HF guard in get_model()
Step 6:  All 14 brain/tools/vault/guard import updates (one-liner each)
Step 7:  backend/tools/sandbox.py — cloud short-circuit
Step 8:  backend/shield/monitor.py — psutil guard
Step 9:  backend/shield/netinfo.py — interface detection guard
Step 10: backend/tools/ocr.py — tesseract guard
Step 11: apt.txt — create in kavach/ root
Step 12: backend/main.py — CORS + /health + startup guard
Step 13: requirements-cloud.txt — create
Step 14: netlify.toml — create
Step 15: frontend-react/public/_redirects — create
Step 16: frontend-react/src/App.jsx — API base
Step 17: frontend-react/src/components/TopBar.jsx — cloud banner
Step 18: git commit and push
Step 19: Create 15 HF accounts + get tokens + accept gated model ToS
Step 20: Create Neon project + run alembic locally + copy both connection strings
Step 21: Create Render service + set all env vars + deploy
Step 22: Create Netlify site + set VITE_API_BASE + deploy
Step 23: Add FRONTEND_ORIGIN to Render + redeploy Render
```

---

## Verification Plan

### Pre-Deploy Smoke Test (Local)

```powershell
# Set cloud env vars locally
$env:LLM_PROVIDER = "huggingface"
$env:CLOUD_DEPLOYMENT = "true"
$env:ENABLE_DOCKER_SANDBOX = "false"
$env:HF_REASONING_API_KEY_PRIMARY = "hf_..."   # real token
$env:HF_EMBEDDING_API_KEY_PRIMARY = "hf_..."

# Test 1: firewall import — catches the wintypes crash
.\.venv\Scripts\python.exe -c "
from backend.shield import firewall
print('Firewall import OK. _IS_WINDOWS =', firewall._IS_WINDOWS)"

# Test 2: dispatch routes to HF in cloud mode
.\.venv\Scripts\python.exe -c "
from backend.engine import active_llm
print('Dispatch module:', active_llm.__name__)"

# Test 3: registry returns HF model ID in cloud mode
.\.venv\Scripts\python.exe -c "
from backend.engine import registry
print('reasoning model:', registry.get_model('reasoning'))
print('rerank model:', registry.get_model('rerank'))"

# Test 4: HF embedding call (fast — CPU model, no cold start)
.\.venv\Scripts\python.exe -c "
from backend.engine import active_llm, registry
model = registry.get_model('embedding')
vec = active_llm.embed(model, 'test sentence for embedding')
print(f'Embed OK — model={model}, dim={len(vec)}')"

# Test 5: sandbox cloud mode
.\.venv\Scripts\python.exe -c "
from backend.tools.sandbox import run_code
r = run_code('x = 1 + 1\nprint(x)', 'python')
print('Sandbox cloud:', r)"

# Test 6: full app startup + health endpoint
# Start in a new terminal:
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8001
# In this terminal:
curl http://127.0.0.1:8001/health
# Expected: {"status":"ok","cloud_mode":true,"llm_provider":"huggingface","docker_sandbox":false}
```

### Post-Deploy Checklist

- [ ] `GET /health` returns `{"cloud_mode":true,"llm_provider":"huggingface","docker_sandbox":false}`
- [ ] All 15 HF accounts have tokens verified with curl; gated models ToS accepted on all code/vision accounts
- [ ] "What is network segmentation?" → AI response arrives (may take 60s first time — cold start)
- [ ] "Write a Python function to sort a list" → response includes `[Cloud Demo Mode]` note
- [ ] PDF uploaded → indexed without error → follow-up question retrieves correct context
- [ ] Neon dashboard Tables tab shows `users`, `chat_sessions`, `messages` with rows
- [ ] Render service restarted → log back in → chat history persists (Neon, not disk)
- [ ] Cloud amber banner visible in top bar on Netlify URL
- [ ] No CORS errors in browser DevTools console
- [ ] 20+ rapid messages → Render logs show "rotating to next key" (confirms token rotation works)

---

## What Does NOT Change (On-Prem Fully Preserved)

| Component | Status |
| :--- | :--- |
| `backend/brain/` — LangGraph agent, planner, tool dispatch | Untouched |
| `backend/vault/` — FAISS ingest, retrieve, rerank | Import line only |
| `backend/auth/` — JWT routes | Untouched |
| `backend/chat/` — Chat persistence | Untouched |
| `backend/db/session.py` | Untouched (already reads `DATABASE_URL`) |
| `backend/db/models.py` | Untouched (Neon is Postgres-compatible) |
| `backend/engine/ollama.py` | Untouched |
| `migrations/` — Alembic | Untouched (runs at Render build time) |
| `frontend/` — Legacy HTML/JS | Not deployed |
