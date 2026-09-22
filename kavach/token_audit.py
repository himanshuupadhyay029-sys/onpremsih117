"""token_audit.py — KAVACH Token Audit Tool.

Runs three benchmark prompts against the configured Ollama reasoning/code models
and reports per-question and aggregate token statistics.

Metrics captured from Ollama /api/generate response:
  - prompt_eval_count  → input  tokens
  - eval_count         → output tokens
  - total              → input + output

Run from the kavach/ directory:
    python token_audit.py
"""

import json
import sys
import time
from pathlib import Path
from typing import Optional

import httpx

# ---------------------------------------------------------------------------
# Config — mirrors backend/config.py but works standalone (no FastAPI import)
# ---------------------------------------------------------------------------
OLLAMA_BASE_URL = "http://localhost:11434"
MODELS_JSON_PATH = Path(__file__).parent / "backend" / "models.json"

# Load model registry
try:
    with open(MODELS_JSON_PATH, "r", encoding="utf-8") as _f:
        _registry: dict = json.load(_f)
    REASONING_MODEL = _registry.get("reasoning", "gemma3:4b")
    CODE_MODEL      = _registry.get("code",      "granite4.1:3b")
except FileNotFoundError:
    REASONING_MODEL = "gemma3:4b"
    CODE_MODEL      = "granite4.1:3b"

# ---------------------------------------------------------------------------
# System prompts (standalone copy, mirrors backend/engine/prompts.py)
# ---------------------------------------------------------------------------
REASONING_SYSTEM_PROMPT = """You are a local, confidential AI assistant for general conversation, knowledge assistance, and reasoning.

Your current mode is TEXT / GENERAL REASONING.

Answer the user's request using the information provided in the conversation and your learned knowledge.

Rules:
1. Understand the user's actual request before answering.
2. Provide accurate, relevant, and concise responses.
3. Do not invent facts, sources, data, quotations, events, or technical specifications.
4. Clearly distinguish established facts from assumptions or uncertain conclusions.
5. If the user's information is insufficient to answer reliably, say what is missing instead of inventing it.
7. Do not assume that an image, document, file, or external source exists unless it is actually provided or available through a tool.
8. Do not claim to have performed an action, searched a source, accessed a file, or verified information unless it was actually performed.
9. Treat all organizational information provided by the user as confidential and do not recommend sending it to external AI or cloud services.
10. Do not unnecessarily apply visual or engineering interpretations to ordinary text requests.

Prioritize correctness and evidence over producing a longer or more confident answer."""

CODING_SYSTEM_PROMPT = """You are a local, confidential software engineering assistant operating entirely within an organization's on-premise environment.

Your current mode is CODING / SOFTWARE ENGINEERING.

Help the user write, understand, debug, modify, test, and improve software according to the user's requirements.

Rules:
1. Understand the requirements before implementing them.
2. Follow the requested programming language, framework, environment, and constraints.
3. Generate practical, maintainable, secure, and executable code.
4. Do not invent requirements, APIs, libraries, functions, schemas, configuration options, or system behavior.
5. If an important requirement is missing, identify it rather than silently inventing one.
6. Clearly identify assumptions when an assumption is necessary.
7. Preserve existing functionality when modifying code unless the user explicitly requests otherwise.
8. Do not claim that code was executed, compiled, tested, or verified unless it was actually executed using an available tool or sandbox.
9. Never fabricate test results, console output, benchmark results, or execution status.
10. When code is actually executed, report the real result.
11. Consider relevant edge cases and error handling.
12. Treat source code, files, credentials, configurations, and organizational information as confidential.
13. Do not recommend sending proprietary code or confidential data to external AI or cloud services.

Prioritize correctness, reliability, and adherence to the user's requirements over unnecessary complexity."""

# ---------------------------------------------------------------------------
# Audit questions
# ---------------------------------------------------------------------------
AUDIT_QUESTIONS = [
    {
        "id": 1,
        "label": "Student Management System (Python + DOCX)",
        "model": CODE_MODEL,
        "system": CODING_SYSTEM_PROMPT,
        "prompt": (
            "Write a Python program to create a basic student management system that handles "
            "a student's class and their personal information (name, age, roll number, address, "
            "phone number, email). The program should support adding, viewing, updating, and "
            "deleting student records stored in memory. After demonstrating the system, also "
            "export the student records into a formatted .docx file using the python-docx library, "
            "with a proper table layout including headers: Roll No, Name, Age, Class, Address, "
            "Phone, Email."
        ),
    },
    {
        "id": 2,
        "label": "Meaning of Knowledge Hub",
        "model": REASONING_MODEL,
        "system": REASONING_SYSTEM_PROMPT,
        "prompt": "What is the meaning of knowledge hub?",
    },
    {
        "id": 3,
        "label": "Print N Prime Numbers (Python)",
        "model": CODE_MODEL,
        "system": CODING_SYSTEM_PROMPT,
        "prompt": "Write a Python program to print N prime numbers where N is given by the user.",
    },
]

# ---------------------------------------------------------------------------
# Core: call Ollama and extract token metrics
# ---------------------------------------------------------------------------

def call_ollama(
    model: str,
    prompt: str,
    system: Optional[str] = None,
    timeout: float = 300.0,
) -> dict:
    """
    Calls Ollama /api/generate and returns:
        response, input_tokens, output_tokens, total_tokens, duration_s, raw
    """
    payload: dict = {
        "model":  model,
        "prompt": prompt,
        "stream": False,
    }
    if system:
        payload["system"] = system

    t0 = time.perf_counter()
    try:
        with httpx.Client(base_url=OLLAMA_BASE_URL, timeout=timeout) as client:
            resp = client.post("/api/generate", json=payload)
            resp.raise_for_status()
            data: dict = resp.json()
    except httpx.ConnectError:
        raise RuntimeError(
            f"Cannot connect to Ollama at {OLLAMA_BASE_URL}. "
            "Ensure Ollama is running: `ollama serve`"
        )
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(
            f"Ollama HTTP error {exc.response.status_code}: {exc.response.text}"
        )
    except Exception as exc:
        raise RuntimeError(f"Ollama call failed: {exc}")

    elapsed = time.perf_counter() - t0

    return {
        "response":      data.get("response", "").strip(),
        "input_tokens":  data.get("prompt_eval_count", 0),
        "output_tokens": data.get("eval_count", 0),
        "total_tokens":  data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
        "duration_s":    round(elapsed, 2),
        "raw":           data,
    }


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------
LINE  = "-" * 80
DLINE = "=" * 80


def banner(text: str) -> None:
    print(f"\n{DLINE}")
    print(f"  {text}")
    print(f"{DLINE}")


def section(text: str) -> None:
    print(f"\n{LINE}")
    print(f"  {text}")
    print(LINE)


def print_result(q: dict, result: dict) -> None:
    section(f"Q{q['id']}: {q['label']}")
    print(f"  Model   : {q['model']}")
    print(f"  Elapsed : {result['duration_s']:.2f}s")
    print()
    print(f"  +---------- Token Breakdown ----------------+")
    print(f"  |  Input  tokens (prompt_eval_count) : {result['input_tokens']:>5} |")
    print(f"  |  Output tokens (eval_count)        : {result['output_tokens']:>5} |")
    print(f"  |  Total  tokens                     : {result['total_tokens']:>5} |")
    print(f"  +--------------------------------------------+")
    print()
    preview = result["response"]
    if len(preview) > 1000:
        preview = preview[:1000] + "\n  ... [truncated]"
    print("  -- Response Preview --")
    for line in preview.splitlines():
        print(f"  {line}")


def print_summary(results: list) -> None:
    banner("TOKEN AUDIT SUMMARY")
    header = f"  {'Q#':<4} {'Question':<42} {'Input':>8} {'Output':>8} {'Total':>8} {'Sec':>7}  Model"
    print(header)
    print("  " + "-" * 88)

    grand_input = grand_output = grand_total = 0

    for r in results:
        q  = r["question"]
        it = r["metrics"]["input_tokens"]
        ot = r["metrics"]["output_tokens"]
        tt = r["metrics"]["total_tokens"]
        el = r["metrics"]["duration_s"]
        grand_input  += it
        grand_output += ot
        grand_total  += tt
        label = q["label"][:42]
        print(
            f"  {q['id']:<4} {label:<42} {it:>8,} {ot:>8,} {tt:>8,} {el:>6.1f}s  {q['model']}"
        )

    print("  " + "-" * 88)
    print(
        f"  {'GRAND TOTAL':<47} {grand_input:>8,} {grand_output:>8,} {grand_total:>8,}"
    )
    print()
    print(f"  Grand Total Input  Tokens : {grand_input:>10,}")
    print(f"  Grand Total Output Tokens : {grand_output:>10,}")
    print(f"  Grand Total Tokens        : {grand_total:>10,}")
    print(f"\n{DLINE}\n")


# ---------------------------------------------------------------------------
# Save audit JSON
# ---------------------------------------------------------------------------

def save_audit_json(results: list) -> Path:
    out_dir = Path(__file__).parent / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"token_audit_{ts}.json"

    payload = {
        "audit_timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "questions": [
            {
                "id":            r["question"]["id"],
                "label":         r["question"]["label"],
                "model":         r["question"]["model"],
                "prompt":        r["question"]["prompt"],
                "response":      r["metrics"]["response"],
                "input_tokens":  r["metrics"]["input_tokens"],
                "output_tokens": r["metrics"]["output_tokens"],
                "total_tokens":  r["metrics"]["total_tokens"],
                "duration_s":    r["metrics"]["duration_s"],
            }
            for r in results
        ],
        "grand_total": {
            "input_tokens":  sum(r["metrics"]["input_tokens"]  for r in results),
            "output_tokens": sum(r["metrics"]["output_tokens"] for r in results),
            "total_tokens":  sum(r["metrics"]["total_tokens"]  for r in results),
        },
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    return out_path


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    banner("KAVACH TOKEN AUDIT  -  3-Question Benchmark")
    print(f"  Reasoning model : {REASONING_MODEL}")
    print(f"  Code model      : {CODE_MODEL}")
    print(f"  Ollama endpoint : {OLLAMA_BASE_URL}")

    results = []
    errors  = []

    for q in AUDIT_QUESTIONS:
        print(f"\n  [Running] Q{q['id']}: {q['label']} ...")
        try:
            metrics = call_ollama(
                model=q["model"],
                prompt=q["prompt"],
                system=q.get("system"),
                timeout=300.0,
            )
            print_result(q, metrics)
            results.append({"question": q, "metrics": metrics})
        except RuntimeError as exc:
            print(f"\n  [FAILED] Q{q['id']}: {exc}")
            errors.append({"question": q, "error": str(exc)})

    if not results:
        print("\n  No successful results. Exiting.")
        sys.exit(1)

    print_summary(results)

    try:
        out_path = save_audit_json(results)
        print(f"  Full audit saved to: {out_path}\n")
    except Exception as exc:
        print(f"  [Warning] Could not save audit JSON: {exc}\n")

    if errors:
        print(f"  WARNING: {len(errors)} question(s) failed:")
        for e in errors:
            print(f"    Q{e['question']['id']}: {e['error']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
