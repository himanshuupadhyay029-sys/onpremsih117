"""code.py — code GENERATION (kept separate from execution in sandbox.py).

generate_code() asks the CODE model role (qwen2.5-coder:3b via the existing
registry/ollama engine) for a self-contained Python script, stripping any
markdown fences defensively even though the prompt already asks for none.

write_and_run() wires generation to the sandbox: on retry, the previous run's
REAL stderr is passed back into the prompt so the model fixes the actual
failure it produced, instead of blindly regenerating and hoping.
"""

import re
from typing import Dict, Optional

from backend.engine import ollama, registry
from backend.tools.sandbox import run_code

GENERATE_PROMPT_TEMPLATE = """Write a complete, self-contained Python script that accomplishes the following task:

{task_description}

Requirements:
- Return ONLY the raw Python code. No markdown code fences, no explanation, no comments about what you are doing.
- The script must run standalone with `python script.py` and print its result(s) to stdout.
- Use only the Python standard library — the execution sandbox has no network access, so third-party packages cannot be installed.
"""

RETRY_PROMPT_TEMPLATE = """Write a complete, self-contained Python script that accomplishes the following task:

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
"""


def _strip_code_fences(text: str) -> str:
    text = (text or "").strip()
    fence_match = re.search(r"```(?:python)?\s*(.*?)```", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()
    return text


def generate_code(task_description: str, prior_error: Optional[str] = None) -> str:
    model = registry.get_model("code")
    if prior_error:
        prompt = RETRY_PROMPT_TEMPLATE.format(task_description=task_description, prior_error=prior_error)
    else:
        prompt = GENERATE_PROMPT_TEMPLATE.format(task_description=task_description)

    raw = ollama.generate(model, prompt)
    return _strip_code_fences(raw)


def write_and_run(
    task_description: str,
    prior_error: Optional[str] = None,
    timeout_seconds: int = 15,
    task_id: Optional[str] = None,
) -> Dict:
    """Generates code (fixing prior_error if given) and runs it in the sandbox.
    Returns the full result including the generated code itself, for
    logging/display."""
    code = generate_code(task_description, prior_error=prior_error)
    sandbox_result = run_code(code, timeout_seconds=timeout_seconds, task_id=task_id)

    return {
        "code": code,
        "success": sandbox_result["success"],
        "stdout": sandbox_result["stdout"],
        "stderr": sandbox_result["stderr"],
        "exit_code": sandbox_result["exit_code"],
        "timed_out": sandbox_result["timed_out"],
    }
