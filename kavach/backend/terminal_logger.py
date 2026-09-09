"""terminal_logger.py — Universal, high-visibility terminal logger for KAVACH.

Provides structured, colored, readable console output across every component, tool,
and LangGraph node in the KAVACH autonomous architecture.

Handles Windows console VT100 initialization, safe UTF-8/ASCII fallback to prevent
encoding crashes, duration profiling, and data truncation for clean presentation.
"""

from datetime import datetime
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Union

# Thread safety lock for terminal printing
_print_lock = threading.Lock()

# Windows VT100 color initialization
_COLORS_ENABLED = True
if os.name == "nt":
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # Enable ENABLE_VIRTUAL_TERMINAL_PROCESSING (0x0004)
        h_stdout = kernel32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(h_stdout, ctypes.byref(mode))
        mode.value |= 0x0004
        kernel32.SetConsoleMode(h_stdout, mode)
    except Exception:
        # If running in environment where console mode cannot be set
        pass

if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
    _COLORS_ENABLED = False


class Style:
    """ANSI color and style constants with automatic disable support."""
    RESET = "\033[0m" if _COLORS_ENABLED else ""
    BOLD = "\033[1m" if _COLORS_ENABLED else ""
    DIM = "\033[2m" if _COLORS_ENABLED else ""
    ITALIC = "\033[3m" if _COLORS_ENABLED else ""
    UNDERLINE = "\033[4m" if _COLORS_ENABLED else ""

    # Foreground colors
    BLACK = "\033[30m" if _COLORS_ENABLED else ""
    RED = "\033[31m" if _COLORS_ENABLED else ""
    GREEN = "\033[32m" if _COLORS_ENABLED else ""
    YELLOW = "\033[33m" if _COLORS_ENABLED else ""
    BLUE = "\033[34m" if _COLORS_ENABLED else ""
    MAGENTA = "\033[35m" if _COLORS_ENABLED else ""
    CYAN = "\033[36m" if _COLORS_ENABLED else ""
    WHITE = "\033[37m" if _COLORS_ENABLED else ""

    # Bright variants
    BRIGHT_RED = "\033[91m" if _COLORS_ENABLED else ""
    BRIGHT_GREEN = "\033[92m" if _COLORS_ENABLED else ""
    BRIGHT_YELLOW = "\033[93m" if _COLORS_ENABLED else ""
    BRIGHT_BLUE = "\033[94m" if _COLORS_ENABLED else ""
    BRIGHT_MAGENTA = "\033[95m" if _COLORS_ENABLED else ""
    BRIGHT_CYAN = "\033[96m" if _COLORS_ENABLED else ""
    BRIGHT_WHITE = "\033[97m" if _COLORS_ENABLED else ""


def _now_str() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def _safe_print(text: str) -> None:
    """Prints text safely, falling back to ASCII replacement if terminal encoding fails."""
    with _print_lock:
        try:
            print(text, flush=True)
        except UnicodeEncodeError:
            safe = text.encode("ascii", errors="replace").decode("ascii")
            print(safe, flush=True)
        except Exception:
            pass


def _truncate(text: Any, max_len: int = 120) -> str:
    if text is None:
        return ""
    s = str(text).strip().replace("\r", " ").replace("\n", " ")
    if len(s) > max_len:
        return s[:max_len - 3] + "..."
    return s


# ---------------------------------------------------------------------------
# Core Logging Functions
# ---------------------------------------------------------------------------

def _can_encode(chars: str) -> bool:
    try:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        chars.encode(enc)
        return True
    except Exception:
        return False


_UNICODE_BOX = _can_encode("┌─└│├")
_CAN_EM_DASH = _can_encode("—")
BOX_TL = "┌" if _UNICODE_BOX else "+"
BOX_BL = "└" if _UNICODE_BOX else "+"
BOX_H = "─" if _UNICODE_BOX else "-"
BOX_V = "│" if _UNICODE_BOX else "|"
BOX_BRANCH = "├─" if _UNICODE_BOX else "|--"
BOX_CORNER = "└─" if _UNICODE_BOX else "\\--"
SEP = " -- "


def log_terminal(category: str, msg: str, level: str = "INFO") -> None:
    """General backward-compatible logging function with colored category."""
    color = Style.CYAN
    cat_lower = category.lower()
    if "error" in cat_lower or level == "ERROR":
        color = Style.BRIGHT_RED
    elif "warn" in cat_lower or level == "WARN":
        color = Style.BRIGHT_YELLOW
    elif "planner" in cat_lower:
        color = Style.BRIGHT_CYAN
    elif "router" in cat_lower:
        color = Style.MAGENTA
    elif "executor" in cat_lower:
        color = Style.BLUE
    elif "observer" in cat_lower:
        color = Style.YELLOW
    elif "finalizer" in cat_lower or "complete" in cat_lower:
        color = Style.BRIGHT_GREEN
    elif "guard" in cat_lower or "approve" in cat_lower:
        color = Style.BRIGHT_MAGENTA

    line = f"{Style.DIM}[{_now_str()}]{Style.RESET} {color}[{category}]{Style.RESET} {msg}"
    _safe_print(line)


def log_gateway(action: str, task_id: Optional[str] = None, details: Optional[str] = None) -> None:
    """Logs API gateway request arrival, streaming, or response."""
    t_id = f" [ID: {task_id[:8]}]" if task_id else ""
    dt = f"{SEP}{details}" if details else ""
    line = f"{Style.DIM}[{_now_str()}]{Style.RESET} {Style.BRIGHT_WHITE}[GATEWAY]{Style.RESET} {Style.BOLD}{action}{Style.RESET}{t_id}{dt}"
    _safe_print(line)


def log_gateway_event(event_type: str, task_id: Optional[str] = None, details: Optional[str] = None) -> None:
    """Logs an SSE event emitted to the client."""
    t_id = f" [ID: {task_id[:8]}]" if task_id else ""
    dt = f" ({details})" if details else ""
    line = f"{Style.DIM}[{_now_str()}]{Style.RESET} {Style.DIM}[GATEWAY:SSE]{Style.RESET} Emitted event {Style.CYAN}'{event_type}'{Style.RESET}{t_id}{dt}"
    _safe_print(line)


def log_graph_start(task_id: str, task: str, history_len: int = 0, facts_count: int = 0) -> None:
    """Logs the entry point into the LangGraph state graph."""
    divider = f"{Style.DIM}{BOX_TL}{BOX_H * 77}{Style.RESET}"
    line1 = f"{Style.DIM}[{_now_str()}]{Style.RESET} {Style.BRIGHT_CYAN}{Style.BOLD}[GRAPH:START]{Style.RESET} Task ID: {Style.BOLD}{task_id[:8]}{Style.RESET}"
    line2 = f"  {Style.DIM}Task   :{Style.RESET} \"{_truncate(task, 90)}\""
    line3 = f"  {Style.DIM}Context:{Style.RESET} {history_len} history turns, {facts_count} memory facts"
    _safe_print(f"{divider}\n{line1}\n{line2}\n{line3}")


def log_graph_complete(task_id: str, status: str, models_used: List[str], elapsed_s: Optional[float] = None) -> None:
    """Logs the completion of the LangGraph execution."""
    status_color = Style.BRIGHT_GREEN if status == "complete" else (Style.BRIGHT_YELLOW if "clarif" in status or "approv" in status else Style.BRIGHT_RED)
    el_str = f" in {elapsed_s:.2f}s" if elapsed_s is not None else ""
    models_str = ", ".join(models_used) if models_used else "none"
    line1 = f"{Style.DIM}[{_now_str()}]{Style.RESET} {status_color}{Style.BOLD}[GRAPH:COMPLETE]{Style.RESET} Task {Style.BOLD}{task_id[:8]}{Style.RESET} -> {status_color}{status.upper()}{Style.RESET}{el_str}"
    line2 = f"  {Style.DIM}Models Engaged:{Style.RESET} [{models_str}]"
    divider = f"{Style.DIM}{BOX_BL}{BOX_H * 77}{Style.RESET}"
    _safe_print(f"{line1}\n{line2}\n{divider}")


def log_node_enter(node_name: str, task_id: Optional[str] = None, details: Optional[str] = None) -> None:
    """Logs entrance into a LangGraph node."""
    dt = f"{SEP}{details}" if details else ""
    line = f"{Style.DIM}[{_now_str()}]{Style.RESET} {Style.CYAN}[NODE:{node_name.upper()}]{Style.RESET} {Style.DIM}[ENTER]{Style.RESET}{dt}"
    _safe_print(line)


def log_node_exit(node_name: str, task_id: Optional[str] = None, status: str = "OK", elapsed_s: Optional[float] = None, summary: Optional[str] = None) -> None:
    """Logs exit from a LangGraph node."""
    stat_color = Style.GREEN if status == "OK" else Style.RED
    el = f" ({elapsed_s:.2f}s)" if elapsed_s is not None else ""
    summ = f"{SEP}{summary}" if summary else ""
    line = f"{Style.DIM}[{_now_str()}]{Style.RESET} {Style.CYAN}[NODE:{node_name.upper()}]{Style.RESET} {stat_color}[{status}]{Style.RESET}{el}{summ}"
    _safe_print(line)


def log_plan(task_id: str, steps: List[Dict[str, Any]], is_resume: bool = False, current_step: int = 1) -> None:
    """Logs the decomposed plan produced by Master Planner."""
    header = "Resumed Existing Plan" if is_resume else "Master Plan Established"
    count = len(steps)
    start_info = f" (Resuming from Step {current_step})" if is_resume else ""
    _safe_print(f"{Style.DIM}[{_now_str()}]{Style.RESET} {Style.BRIGHT_CYAN}[NODE:PLANNER]{Style.RESET} {Style.BOLD}{header}{Style.RESET} ({count} sub-task(s)){start_info}:")
    for s in steps:
        s_num = s.get("step_num", "?")
        tool = s.get("tool", "general")
        inp = _truncate(s.get("input") or s.get("description") or "", 85)
        stat = s.get("status", "pending")
        bullet = BOX_BRANCH if s != steps[-1] else BOX_CORNER
        _safe_print(f"  {Style.DIM}{bullet}{Style.RESET} Step {s_num}: {Style.BLUE}[{tool}]{Style.RESET} {inp} {Style.DIM}({stat}){Style.RESET}")


def log_route(step_num: int, total_steps: int, tool: str, model_role: str, model_tag: str, reason: Optional[str] = None) -> None:
    """Logs routing decision for a sub-task."""
    box_header = f"{Style.DIM}{BOX_TL}{BOX_H * 2}{Style.RESET} {Style.MAGENTA}[STEP {step_num}/{total_steps}]{Style.RESET} {Style.BOLD}[NODE:ROUTER]{Style.RESET}"
    line1 = f"{Style.DIM}{BOX_V}{Style.RESET} Sub-task Tool: {Style.BLUE}{tool}{Style.RESET} | Role: {Style.CYAN}{model_role}{Style.RESET} -> Model: {Style.BOLD}{model_tag}{Style.RESET}"
    box_footer = f"{Style.DIM}{BOX_BL}{BOX_H * 2}{Style.RESET}"
    if reason:
        line2 = f"{Style.DIM}{BOX_V}{Style.RESET} Routing Reason: {Style.DIM}{_truncate(reason, 80)}{Style.RESET}"
        _safe_print(f"{box_header}\n{line1}\n{line2}\n{box_footer}")
    else:
        _safe_print(f"{box_header}\n{line1}\n{box_footer}")


def log_tool(tool_name: str, action: str, details: Optional[str] = None, elapsed_s: Optional[float] = None, is_error: bool = False) -> None:
    """Logs tool execution details with timing."""
    stat_color = Style.BRIGHT_RED if is_error else Style.BLUE
    el = f" {Style.DIM}({elapsed_s:.2f}s){Style.RESET}" if elapsed_s is not None else ""
    dt = f"{SEP}{details}" if details else ""
    line = f"{Style.DIM}[{_now_str()}]{Style.RESET} {stat_color}[TOOL:{tool_name.upper()}]{Style.RESET} {Style.BOLD}{action}{Style.RESET}{el}{dt}"
    _safe_print(line)


def log_observe(action: str, reasoning: str, new_steps: Optional[List[dict]] = None, retry_count: Optional[int] = None) -> None:
    """Logs observation assessment decision."""
    act_upper = action.upper()
    if act_upper in ("DONE", "CONTINUE"):
        act_color = Style.BRIGHT_GREEN
    elif act_upper in ("RETRY", "REPLAN"):
        act_color = Style.BRIGHT_YELLOW
    elif act_upper == "CLARIFY":
        act_color = Style.BRIGHT_MAGENTA
    else:
        act_color = Style.WHITE

    retry_info = f" (Attempt #{retry_count})" if retry_count is not None else ""
    steps_info = f" [+{len(new_steps)} step(s)]" if new_steps else ""
    line = f"{Style.DIM}[{_now_str()}]{Style.RESET} {Style.YELLOW}[NODE:OBSERVER]{Style.RESET} {act_color}{Style.BOLD}[ACTION: {act_upper}]{Style.RESET}{retry_info}{steps_info}{SEP}{_truncate(reasoning, 95)}"
    _safe_print(line)


def log_guard(guard_name: str, action: str, details: Optional[str] = None, level: str = "INFO") -> None:
    """Logs guardrail, approval gate, or risk assessment actions."""
    color = Style.BRIGHT_MAGENTA if level == "INFO" else (Style.BRIGHT_YELLOW if level == "WARN" else Style.BRIGHT_RED)
    dt = f"{SEP}{details}" if details else ""
    line = f"{Style.DIM}[{_now_str()}]{Style.RESET} {color}[GUARD:{guard_name.upper()}]{Style.RESET} {Style.BOLD}{action}{Style.RESET}{dt}"
    _safe_print(line)


def log_fact_update(facts_dict: Dict[str, Any]) -> None:
    """Logs memory updates from key facts."""
    if not facts_dict:
        return
    keys = ", ".join(f"{k}={_truncate(str(v), 25)}" for k, v in list(facts_dict.items())[:4])
    line = f"{Style.DIM}[{_now_str()}]{Style.RESET} {Style.DIM}[MEMORY:FACTS]{Style.RESET} Updated key facts: {keys}"
    _safe_print(line)
