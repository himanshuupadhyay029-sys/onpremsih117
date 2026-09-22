"""calc.py — Deterministic engineering math calculator with transparent step-by-step verification.

Design Rule:
The LLM ONLY extracts the formula and variable inputs from the prompt/context.
A deterministic Python AST evaluator performs the real arithmetic, guaranteeing 100%
numerical precision, security (no raw eval()), and traceable substitution steps.
"""

import ast
import json
import operator
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple, Union

from backend.audit.logbook import log_event
from backend.engine import active_llm as ollama, registry
import time
from backend.terminal_logger import log_tool, _truncate

CALC_IDENTIFY_PROMPT = """You are an engineering and mathematical calculation assistant. Extract the mathematical formula, variable values, and units from the task and context.

Task: {task_description}
Context: {context}

CRITICAL RULES:
1. "formula_expression" must be a PURE, VALID Python arithmetic expression (e.g. "speed * (time_minutes / 60)" or "speed * time_hours" or "(current_thickness - min_thickness) / corrosion_rate" or "leg1_distance + leg2_distance").
2. NEVER include equals signs ('=') or variable assignment in "formula_expression" (e.g. write "speed * (time / 60)", NEVER "Distance = speed * time" or "60 * 0.75 = 45").
3. NEVER include unit words in "formula_expression" (e.g. write "60 * (45 / 60)", NEVER "60 mph * 45 mins").
4. Extract ONLY numeric values that are explicitly written in the task description or context into "inputs".
5. If any parameter needed for the formula is NOT mentioned, list that variable in "missing_inputs". If all required numbers are present, "missing_inputs" must be [].

Examples:

Example 1:
Task: Calculate distance traveled for a car at 60 mph for 45 minutes
Context: None
Output:
{{
  "formula_name": "Distance Traveled",
  "formula_expression": "speed * (time_minutes / 60)",
  "inputs": {{
    "speed": 60,
    "time_minutes": 45
  }},
  "unit": "miles",
  "missing_inputs": []
}}

Example 2:
Task: Calculate total distance: 45 miles + 20 miles
Context: None
Output:
{{
  "formula_name": "Total Distance",
  "formula_expression": "leg1 + leg2",
  "inputs": {{
    "leg1": 45,
    "leg2": 20
  }},
  "unit": "miles",
  "missing_inputs": []
}}

Example 3:
Task: Calculate remaining pipe life where current thickness is 12.5 mm, minimum required thickness is 8.0 mm, and corrosion rate is 0.4 mm/year.
Context: None
Output:
{{
  "formula_name": "Remaining Pipe Life",
  "formula_expression": "(current_thickness - min_thickness) / corrosion_rate",
  "inputs": {{
    "current_thickness": 12.5,
    "min_thickness": 8.0,
    "corrosion_rate": 0.4
  }},
  "unit": "years",
  "missing_inputs": []
}}

Return ONLY a raw JSON object matching this schema:
"""

# Supported safe arithmetic operators for AST evaluation
SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# Units to strip out of arithmetic expressions
_UNIT_WORDS = [
    "mph", "km/h", "kmh", "km", "miles", "mile", "meters", "meter", "m",
    "hours", "hour", "hrs", "hr", "h", "minutes", "minute", "mins", "min",
    "seconds", "second", "sec", "s", "years", "year", "yrs", "yr",
    "mm", "cm", "psi", "bar", "pa", "kpa", "mpa", "kg", "g", "liters", "litres", "l"
]


def _sanitize_expression(expr: str, inputs: Optional[Dict[str, float]] = None) -> str:
    """Robustly cleans LLM mathematical expressions into valid Python AST mode='eval' syntax."""
    if not expr:
        return ""

    s = expr.strip()
    # Strip markdown backticks
    s = re.sub(r"^`+|`+$", "", s).strip()

    # If the expression contains equality '=', extract the expression side
    if "=" in s:
        parts = [p.strip() for p in s.split("=")]
        # Check if first part is a variable assignment like "Distance = speed * time"
        if len(parts) >= 2:
            left, right = parts[0], parts[1]
            left_has_ops = any(op in left for op in ["+", "-", "*", "/", "^", "**"])
            right_has_ops = any(op in right for op in ["+", "-", "*", "/", "^", "**"])
            
            # If right side has operators or is a formula, take right side (e.g. Distance = speed * time)
            if right_has_ops and not left_has_ops:
                s = right
            # If left side has operators (e.g. 60 * 0.75 = 45 or 45 + 20 = 65), take left side
            elif left_has_ops and not right_has_ops:
                s = left
            else:
                # If both or neither have operators, check if left is a single identifier
                if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", left):
                    s = right
                else:
                    s = left

    # Replace mathematical symbols with Python operators
    s = s.replace("^", "**").replace("×", "*").replace("÷", "/")
    
    # Replace word operators if present
    s = re.sub(r"\bplus\b", "+", s, flags=re.IGNORECASE)
    s = re.sub(r"\bminus\b", "-", s, flags=re.IGNORECASE)
    s = re.sub(r"\btimes\b", "*", s, flags=re.IGNORECASE)
    s = re.sub(r"\bmultiplied\s+by\b", "*", s, flags=re.IGNORECASE)
    s = re.sub(r"\bdivided\s+by\b", "/", s, flags=re.IGNORECASE)

    # Strip standalone unit words from the expression (e.g. "60 mph * 0.75 hours" -> "60 * 0.75")
    for unit_w in _UNIT_WORDS:
        s = re.sub(rf"(?<=\d|\))\s*\b{re.escape(unit_w)}\b", "", s, flags=re.IGNORECASE)
        s = re.sub(rf"\b{re.escape(unit_w)}\b\s*(?=\d|\()", "", s, flags=re.IGNORECASE)

    s = s.strip()
    return s


def _ground_inputs_in_text(inputs: Dict[str, float], text_corpus: str) -> Tuple[Dict[str, float], List[str]]:
    """Strictly checks that every numeric value in inputs was explicitly mentioned in the task/context.
    Prevents the LLM from hallucinating missing numbers or copying prompt examples."""
    grounded_inputs: Dict[str, float] = {}
    hallucinated_missing: List[str] = []

    # Extract all numbers from the text corpus (integers and floats)
    found_numbers_str = re.findall(r"[-+]?\d*\.?\d+", text_corpus)
    found_numbers: List[float] = []
    for num_str in found_numbers_str:
        try:
            found_numbers.append(float(num_str))
        except ValueError:
            pass

    for var_name, val in inputs.items():
        # Check if float value matches any number in the text (within float epsilon)
        is_grounded = any(abs(val - fn) < 1e-5 for fn in found_numbers)
        if is_grounded:
            grounded_inputs[var_name] = val
        else:
            hallucinated_missing.append(var_name)

    return grounded_inputs, hallucinated_missing


def _parse_calc_json(raw: str, text_corpus: str = "") -> Dict[str, Any]:
    """Robustly extracts structured calculation parameters from model response."""
    text = (raw or "").strip()

    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    else:
        brace_match = re.search(r"(\{.*\})", text, re.DOTALL)
        if brace_match:
            text = brace_match.group(1)

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            raw_inputs = data.get("inputs", {})
            extracted_inputs: Dict[str, float] = {}
            for k, v in raw_inputs.items():
                try:
                    if v is not None:
                        extracted_inputs[str(k)] = float(v)
                except (ValueError, TypeError):
                    pass

            # Grounding check: ensure extracted numbers actually appear in the task text/context
            if text_corpus:
                grounded_inputs, hallucinated_vars = _ground_inputs_in_text(extracted_inputs, text_corpus)
            else:
                grounded_inputs, hallucinated_vars = extracted_inputs, []

            raw_missing = data.get("missing_inputs", [])
            missing_set = set(hallucinated_vars)
            for m in raw_missing:
                m_str = str(m).strip()
                if m_str and not any(re.sub(r"[^a-zA-Z0-9]", "", k).lower() == re.sub(r"[^a-zA-Z0-9]", "", m_str).lower() for k in grounded_inputs):
                    missing_set.add(m_str)

            formula_expr = _sanitize_expression(str(data.get("formula_expression", "")), grounded_inputs)

            return {
                "formula_name": str(data.get("formula_name", "Calculation")),
                "formula_expression": formula_expr,
                "inputs": grounded_inputs,
                "unit": str(data.get("unit", "")),
                "missing_inputs": sorted(list(missing_set)),
            }
    except Exception:
        pass

    return {
        "formula_name": "Unknown Formula",
        "formula_expression": "",
        "inputs": {},
        "unit": "",
        "missing_inputs": ["formula_parameters"],
    }


def identify_calculation(
    task_description: str,
    context: Optional[str] = None,
) -> Dict[str, Any]:
    """Asks the reasoning model to extract formula and variables into structured JSON."""
    reasoning_model = registry.get_model("reasoning")
    prompt = CALC_IDENTIFY_PROMPT.format(
        task_description=task_description,
        context=context or "None provided",
    )

    full_corpus = f"{task_description}\n{context or ''}"

    try:
        raw = ollama.generate(reasoning_model, prompt)
    except Exception as exc:
        raw = f'{{"formula_name": "Error", "missing_inputs": ["{exc}"]}}'

    return _parse_calc_json(raw, text_corpus=full_corpus)


class SafeEvaluator(ast.NodeVisitor):
    """Safely evaluates an AST arithmetic expression and records calculation steps."""

    def __init__(self, variables: Dict[str, float]):
        self.variables = variables
        self.sub_steps: List[str] = []

    def evaluate(self, expr_str: str) -> Tuple[float, List[str]]:
        clean_expr = expr_str.replace("^", "**").strip()
        tree = ast.parse(clean_expr, mode="eval")
        result = self.visit(tree.body)
        return float(result), self.sub_steps

    def visit_BinOp(self, node: ast.BinOp) -> float:
        left = self.visit(node.left)
        right = self.visit(node.right)
        op_type = type(node.op)
        if op_type not in SAFE_OPERATORS:
            raise ValueError(f"Unsupported mathematical operator: {op_type.__name__}")

        op_func = SAFE_OPERATORS[op_type]
        if op_type == ast.Div and right == 0:
            raise ZeroDivisionError("Division by zero in mathematical expression.")

        val = op_func(left, right)
        op_sym = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.Pow: "^"}.get(op_type, "?")
        self.sub_steps.append(f"{left} {op_sym} {right} = {round(val, 6)}")
        return val

    def visit_UnaryOp(self, node: ast.UnaryOp) -> float:
        operand = self.visit(node.operand)
        op_type = type(node.op)
        if op_type not in SAFE_OPERATORS:
            raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
        return SAFE_OPERATORS[op_type](operand)

    def visit_Constant(self, node: ast.Constant) -> float:
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise ValueError(f"Unexpected constant type: {type(node.value)}")

    def visit_Name(self, node: ast.Name) -> float:
        var_name = node.id
        if var_name in self.variables:
            return float(self.variables[var_name])
        # Exact match after alphanumeric normalization
        norm_target = re.sub(r"[^a-zA-Z0-9]", "", var_name).lower()
        for k, v in self.variables.items():
            norm_k = re.sub(r"[^a-zA-Z0-9]", "", k).lower()
            if norm_k == norm_target:
                return float(v)
        raise KeyError(f"Missing required variable input: '{var_name}'")

    def generic_visit(self, node):
        raise ValueError(f"Disallowed expression element: {type(node).__name__}")


def compute(structured_calc: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministically evaluates arithmetic formula using safe AST parsing."""
    formula_name = structured_calc.get("formula_name", "Calculation")
    raw_expr = structured_calc.get("formula_expression", "").strip()
    inputs = structured_calc.get("inputs", {})
    unit = structured_calc.get("unit", "")

    clean_expr = _sanitize_expression(raw_expr, inputs)

    if not clean_expr:
        return {
            "success": False,
            "error": "No valid formula expression identified for calculation.",
            "formula_name": formula_name,
            "steps": [],
            "result": None,
            "unit": unit,
        }

    try:
        tree = ast.parse(clean_expr, mode="eval")
    except Exception as exc:
        return {
            "success": False,
            "error": f"Invalid formula syntax: {exc}",
            "formula_name": formula_name,
            "steps": [],
            "result": None,
            "unit": unit,
        }

    # Verify all variables in the formula AST are present in inputs
    expr_vars = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    missing_vars: List[str] = []
    for var in expr_vars:
        norm_v = re.sub(r"[^a-zA-Z0-9]", "", var).lower()
        found = False
        for k in inputs:
            norm_k = re.sub(r"[^a-zA-Z0-9]", "", k).lower()
            if norm_k == norm_v:
                found = True
                break
        if not found:
            missing_vars.append(var)

    if missing_vars:
        return {
            "success": False,
            "error": f"Cannot calculate - missing required input(s): {', '.join(missing_vars)}",
            "missing_inputs": missing_vars,
            "formula_name": formula_name,
            "steps": [f"Missing required parameter: {m}" for m in missing_vars],
            "result": None,
            "unit": unit,
        }

    steps: List[str] = [
        f"1. Formula: {formula_name} = {clean_expr}",
    ]

    # Create substitution string
    subst_expr = clean_expr
    for var, val in inputs.items():
        subst_expr = re.sub(rf"\b{re.escape(var)}\b", str(val), subst_expr)
    steps.append(f"2. Substitution: {subst_expr}")

    try:
        evaluator = SafeEvaluator(inputs)
        result_num, sub_steps = evaluator.evaluate(clean_expr)

        for i, sub in enumerate(sub_steps, start=3):
            steps.append(f"{i}. Arithmetic: {sub}")

        rounded_res = round(result_num, 4)
        if rounded_res == int(rounded_res):
            rounded_res = int(rounded_res)

        formatted_final = f"{rounded_res} {unit}".strip()
        steps.append(f"Result: {formatted_final}")

        return {
            "success": True,
            "formula_name": formula_name,
            "formula_expression": clean_expr,
            "inputs": inputs,
            "steps": steps,
            "result": rounded_res,
            "unit": unit,
            "formatted_result": formatted_final,
        }
    except KeyError as exc:
        return {
            "success": False,
            "error": f"Cannot compute: {exc}",
            "formula_name": formula_name,
            "steps": steps,
            "result": None,
            "unit": unit,
        }
    except Exception as exc:
        return {
            "success": False,
            "error": f"Calculation error: {exc}",
            "formula_name": formula_name,
            "steps": steps,
            "result": None,
            "unit": unit,
        }


def calculate(
    task_description: str,
    context: Optional[str] = None,
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Main calculation orchestrator: extracts formula from LLM and computes deterministically."""
    t0 = time.perf_counter()
    structured = identify_calculation(task_description, context=context)

    missing = structured.get("missing_inputs", [])
    if missing:
        error_msg = f"Cannot calculate - missing required input(s): {', '.join(missing)}"
        log_tool("calc", "MISSING_INPUTS", f"Formula '{structured.get('formula_name')}' missing parameters: {missing}", is_error=True)
        log_event(
            task_id=task_id,
            event_type="calc",
            actor="calc_tool",
            summary=f"Incomplete calculation '{structured.get('formula_name')}': missing {missing}",
            metadata={
                "formula_name": structured.get("formula_name"),
                "missing_inputs": missing,
                "error": error_msg,
            },
            external_calls=0,
        )
        return {
            "success": False,
            "error": error_msg,
            "missing_inputs": missing,
            "formula_name": structured.get("formula_name"),
            "steps": [f"Missing required parameter: {m}" for m in missing],
            "result": None,
        }

    comp_res = compute(structured)
    elapsed = time.perf_counter() - t0

    if comp_res.get("success"):
        summary_str = f"Calculated '{comp_res['formula_name']}': {comp_res['formatted_result']}"
        log_tool("calc", "EVAL_OK", f"{comp_res['formula_name']} -> {comp_res['formatted_result']}", elapsed_s=elapsed)
    else:
        summary_str = f"Calculation failed for '{comp_res['formula_name']}': {comp_res.get('error')}"
        log_tool("calc", "EVAL_FAIL", f"{comp_res['formula_name']}: {comp_res.get('error')}", elapsed_s=elapsed, is_error=True)

    log_event(
        task_id=task_id,
        event_type="calc",
        actor="calc_tool",
        summary=summary_str,
        metadata={
            "formula_name": comp_res.get("formula_name"),
            "formula_expression": comp_res.get("formula_expression"),
            "inputs": comp_res.get("inputs"),
            "result": comp_res.get("result"),
            "unit": comp_res.get("unit"),
            "steps": comp_res.get("steps"),
            "success": comp_res.get("success"),
        },
        external_calls=0,
    )

    return comp_res
