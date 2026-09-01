# KAVACH — Laptop Setup Plan (per person)
### Decisions locked · plain steps · exact commands

## The setup at a glance

| Person | Laptop | Role | Runs |
|---|---|---|---|
| **Himanshu (you)** | RTX 3050 Ti, 4GB, 1TB | **SERVER + DRIVER** | The code, the IDE (Antigravity), all 4 models, Docker, the live demo |
| **Harshit** | RTX 3050, 4GB, 512GB | **BACKUP SERVER + offline-proof owner** | Identical setup (hot spare) + builds/tests the firewall + network monitor |
| **Mokshit** | RTX 2050, 4GB, 512GB | **DEV/TEST + Docker + demo data** | Pushes code to git, gets Docker running, preps demo docs, tests features |

**Golden rules:**
- Only ONE machine runs the demo (Himanshu's). Models load one at a time — a few seconds to swap between them is normal and expected, not a bug.
- Code lives in **git**, not on one person's laptop. Everyone clones from GitHub.
- Server uses **Python 3.11** (NOT 3.14 — it breaks the scanned-doc reader later).
- All three laptops must be on the **same WiFi**.

---

## STEP 0 — Move the code to git (Mokshit does this once, first)

The code is on Mokshit's laptop. Get it into a shared place so everyone works from the same source.

**Mokshit:**
1. Create a **private** GitHub repo called `kavach`.
2. In the project folder, before pushing, make a `.gitignore` with these lines (so you don't upload junk/huge files):
   ```
   .venv/
   __pycache__/
   faiss_index/
   outputs/
   audit_log.jsonl
   *.pyc
   ```
3. Push it:
   ```
   git init
   git add .
   git commit -m "baseline - Alok's working skeleton"
   git branch -M main
   git remote add origin https://github.com/<your-username>/kavach.git
   git push -u origin main
   ```
> Your IDE agent (Antigravity/Claude Code) can do all of this for you — just tell it "initialise git, create a .gitignore for a Python project, and push to this GitHub repo." Share the repo link with Himanshu and Harshit.

---

## HIMANSHU (you) — SERVER + DRIVER · the main machine

This laptop becomes everything: code, demo, AI. Do these in order.

**1. Install Python 3.11** (not 3.14)
- Download Python **3.11** from python.org, install it (tick "Add to PATH").

**2. Get the code**
```
git clone https://github.com/<mokshit-username>/kavach.git
cd kavach
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**3. Install Ollama + pull the 4 models** (this is the big download — do it on your 1TB machine)
```
ollama pull qwen2.5:3b-instruct
ollama pull qwen2.5-coder:3b
ollama pull qwen2.5-vl:3b
ollama pull nomic-embed-text
ollama list          (confirm all 4 show up)
```

**4. Set the fast model as default**
- Open `model_registry.json`, set `"reasoning"` to `"qwen2.5:3b-instruct"` (keep 7b out of the default — too slow on 4GB). It should read roughly:
  ```json
  { "code": "qwen2.5-coder:3b", "reasoning": "qwen2.5:3b-instruct", "fast": "qwen2.5:3b-instruct" }
  ```

**5. Expose Ollama to the other laptops** (so their browsers can reach the demo)
- Set a system environment variable `OLLAMA_HOST` = `0.0.0.0`, then restart Ollama.
- Find your laptop's IP: run `ipconfig`, note the **IPv4 Address** under your WiFi adapter (e.g. `192.168.1.20`). This is your **server IP** — share it with the team.

**6. Install Docker Desktop** (needed so the code sandbox actually runs)
- Install Docker Desktop (it will enable WSL2 — accept). Then:
  ```
  docker run hello-world           (should print a success message)
  docker pull python:3.11-slim     (pre-download so the sandbox works offline + fast)
  ```
- If Docker fights your machine for more than an hour, stop — we have a fallback. Tell me.

**7. Run the app + confirm baseline**
```
uvicorn app.main:app --reload --port 8000
```
- Open `http://localhost:8000/ui` — should load.
- Test `POST /agent/run` with `"Write a python script to print the first 10 primes and run it"` — you want to see **real prime-number output**, which proves Docker works.

**8. Install your IDE** (Antigravity) on this laptop — this is where all coding happens from now on.

---

## HARSHIT — BACKUP SERVER + offline-proof owner

Do the **exact same steps 1–7 as Himanshu** (Python 3.11, clone, venv, install, pull all 4 models, Docker). Goal: your laptop is a perfect twin, so if the demo laptop dies, we plug in yours in 2 minutes.

**Then, your special job — the offline-proof (our #1 graded feature):** you're setting up a clean Windows machine anyway, so you figure out and document these two things (we'll turn them into code later):
1. **Windows Firewall block:** how to make a rule that blocks all outgoing internet except local WiFi. (Windows Defender Firewall → Outbound Rules → block all, allow local subnet.) Just get it working and note the exact steps.
2. **Network monitor:** install `psutil` in the venv (`pip install psutil`) and confirm you can run a tiny Python snippet that lists active network connections. This is the seed of the live "0 external connections" monitor.

You don't need to build the final feature yet — just prove both work on Windows and write down how, so it drops cleanly into the code.

---

## MOKSHIT — DEV/TEST + Docker + demo data

You already have the working baseline, so your jobs are the practical de-risking ones.

**1. After pushing to git (Step 0), get Docker actually running** — this is currently blocking the code sandbox for everyone:
```
(install Docker Desktop, enable WSL2)
docker run hello-world
docker pull python:3.11-slim
```
Then test the sandbox via `/agent/run` with a "print 2+2 and run it" task — confirm you see real output, not a "daemon offline" message. **Report the exact steps that made Docker work** so Himanshu and Harshit can copy them. If it won't cooperate after an hour, tell Himanshu — there's a no-Docker fallback.

**2. Prepare the demo documents** (we need these to test scanned-doc reading soon). Collect/create **public or fake** samples only — no real MRPL data:
- 2–3 fake but realistic **refinery SOPs** (like an inspection SOP, a confined-space-entry SOP) as PDFs.
- 1–2 **scanned inspection reports** (print a fake report, scan or photograph it, save as PDF/image).
- 1 **engineering drawing / P&ID** image from an open dataset.
Keep them in a `test_data/` folder to share.

**3. Be the tester:** as Himanshu builds each feature, you try to break it with the unseen demo docs above.

---

## HOW THE LAPTOPS TALK (keep it simple)

- All three on the **same WiFi**.
- Himanshu's laptop runs the app; its IP (from `ipconfig`, step 5) is the **server address**.
- Anyone can open the demo in a browser at `http://<server-ip>:8000/ui`.
- That's it. No laptop-to-laptop model sharing. One server, everyone else is a browser.
- *(The fully-unplugged offline demo — where the server makes its own hotspot — is a later step. Not now.)*

---

## WHAT "DONE WITH SETUP" LOOKS LIKE

- [ ] Code is on GitHub; Himanshu + Harshit have cloned it.
- [ ] Himanshu's laptop: Python 3.11, all 4 models pulled, app runs, `/ui` loads, and the prime-numbers task returns **real output** (Docker working).
- [ ] Harshit's laptop: identical twin working + firewall block and psutil both proven on Windows (steps written down).
- [ ] Mokshit: Docker steps documented, demo documents collected in `test_data/`.

When all four boxes are ticked, setup is finished — and the **first real feature we build is the offline-proof** (Prompt 2).

---

## TWO THINGS TO WATCH

- **Python 3.11, not 3.14** — on all machines that run the code. This is the most common thing that'll waste your time later if skipped.
- **Docker on Windows** is the fiddliest install. That's why Mokshit does it first and documents it — so the server (Himanshu) doesn't discover the problem for the first time on demo day.
