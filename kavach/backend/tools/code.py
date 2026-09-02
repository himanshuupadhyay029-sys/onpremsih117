"""code.py — code GENERATION (kept separate from execution in sandbox.py).

generate_code() asks the CODE model role (qwen2.5-coder:3b via the existing
registry/ollama engine) for a self-contained script in the detected or specified
language (Python, JavaScript/Node, or C), stripping any markdown fences defensively.

write_and_run() wires generation to the sandbox: on retry, the previous run's
REAL stderr is passed back into the prompt so the model fixes the actual
failure it produced, instead of blindly regenerating and hoping.
"""

from datetime import datetime
import re
from typing import Dict, Optional

from backend.engine import ollama, registry
from backend.tools.sandbox import run_code

GENERATE_PROMPTS = {
    "python": """Write a complete, self-contained Python script that accomplishes the following task:

{task_description}

Requirements:
- Return ONLY the raw Python code. No markdown code fences, no explanation, no comments about what you are doing.
- The script must run standalone with `python script.py` and print its result(s) to stdout.
- Use only the Python standard library — the execution sandbox has no network access, so third-party packages cannot be installed.
""",
    "javascript": """Write a complete, self-contained Node.js / JavaScript script that accomplishes the following task:

{task_description}

Requirements:
- Return ONLY the raw JavaScript code. No markdown code fences, no explanation, no comments about what you are doing.
- The script must run standalone with `node script.js` and print its result(s) to stdout using console.log.
- Use only built-in Node.js standard modules — no external npm packages can be installed.
""",
    "c": """Write a complete, self-contained C source file that accomplishes the following task:

{task_description}

Requirements:
- Return ONLY the raw C source code. No markdown code fences, no explanation.
- Include all necessary standard headers (e.g. #include <stdio.h>, #include <stdlib.h>, #include <string.h>, #include <math.h>).
- Implement a complete int main() entry function that prints its result(s) to stdout via printf and returns 0.
- Use only the C standard library.
""",
}

RETRY_PROMPTS = {
    "python": """Write a complete, self-contained Python script that accomplishes the following task:

{task_description}

Your PREVIOUS attempt failed when actually run. Here is the exact error it produced:
---
{prior_error}
---
Fix the specific problem shown in that error and write a corrected, complete script.

Requirements:
- Return ONLY the raw Python code. No markdown code fences, no explanation.
- The script must run standalone with `python script.py` and print its result(s) to stdout.
- Use only the Python standard library — no network access is available to install packages.
""",
    "javascript": """Write a complete, self-contained Node.js / JavaScript script that accomplishes the following task:

{task_description}

Your PREVIOUS attempt failed when actually run. Here is the exact error it produced:
---
{prior_error}
---
Fix the specific problem shown in that error and write a corrected, complete script.

Requirements:
- Return ONLY the raw JavaScript code. No markdown code fences, no explanation.
- The script must run standalone with `node script.js` and print its result(s) to stdout using console.log.
- Use only built-in Node.js standard modules.
""",
    "c": """Write a complete, self-contained C source file that accomplishes the following task:

{task_description}

Your PREVIOUS attempt failed when compiled or run. Here is the exact error it produced:
---
{prior_error}
---
Fix the specific compilation or runtime error shown above and write a corrected, complete C program.

Requirements:
- Return ONLY the raw C source code. No markdown code fences, no explanation.
- Include all necessary standard headers and `int main()`.
- Print results to stdout via printf.
""",
}


def _log_terminal(msg: str) -> None:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now_str}] [CodeGen] {msg}", flush=True)


def detect_language(task_description: str) -> str:
    """Detects target programming language from prompt keywords. Defaults to 'python'."""
    text = (task_description or "").lower()

    # JavaScript / Node.js checks
    if any(kw in text for kw in ["javascript", "node.js", "nodejs", "node js", "in js", "js script", "typescript"]):
        return "javascript"

    # C checks (deliberate boundary checks to prevent matching words like 'calculate')
    if (
        re.search(r"\b(?:in c|c program|c code|c language|gcc|clang)\b", text)
        or "#include" in text
        or re.search(r"\bwrite (?:a |an )?c\b", text)
    ):
        return "c"

    # Default to primary language: Python
    return "python"


def _strip_code_fences(text: str) -> str:
    s = (text or "").strip()
    fence_match = re.search(r"```(?:\w+)?\s*(.*?)```", s, re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()
    return s


def generate_code(
    task_description: str,
    language: str = "python",
    prior_error: Optional[str] = None,
) -> str:
    lang = (language or "python").lower().strip()
    if lang not in GENERATE_PROMPTS:
        lang = "python"

    model = registry.get_model("code")
    _log_terminal(
        f"Generating code for task: lang='{lang}', model='{model}', is_retry={bool(prior_error)}"
    )

    if prior_error:
        template = RETRY_PROMPTS.get(lang, RETRY_PROMPTS["python"])
        prompt = template.format(task_description=task_description, prior_error=prior_error)
    else:
        template = GENERATE_PROMPTS.get(lang, GENERATE_PROMPTS["python"])
        prompt = template.format(task_description=task_description)

    raw = ollama.generate(model, prompt)
    code = _strip_code_fences(raw)
    _log_terminal(f"Generated {len(code)} characters of {lang} source code.")
    return code


def write_and_run(
    task_description: str,
    language: Optional[str] = None,
    prior_error: Optional[str] = None,
    timeout_seconds: int = 15,
    task_id: Optional[str] = None,
) -> Dict:
    """Generates code in the detected or specified language (fixing prior_error if given)
    and executes it in the network-isolated Docker sandbox.
    """
    lang = language or detect_language(task_description)
    _log_terminal(f"write_and_run invoked: language='{lang}'")

    code = generate_code(task_description, language=lang, prior_error=prior_error)
    sandbox_result = run_code(code, language=lang, timeout_seconds=timeout_seconds, task_id=task_id)

    return {
        "language": lang,
        "code": code,
        "success": sandbox_result["success"],
        "stdout": sandbox_result["stdout"],
        "stderr": sandbox_result["stderr"],
        "exit_code": sandbox_result["exit_code"],
        "timed_out": sandbox_result["timed_out"],
        "duration_seconds": sandbox_result.get("duration_seconds", 0.0),
    }
