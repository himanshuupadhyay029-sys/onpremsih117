"""firewall.py — Layer 1: Windows Firewall default-deny egress enforcement.

Supports:
1. Direct execution if process is running elevated.
2. Silent execution via on-demand Windows Scheduled Tasks (KAVACH-Firewall-Lockdown / Unlock).
3. Interactive on-demand Windows UAC elevation via ShellExecuteExW when requested by the user.
"""

import ctypes
from ctypes import wintypes
import json
import logging
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from backend import config
from backend.audit.logbook import log_event
from backend.shield.netinfo import detect_local_network

logger = logging.getLogger("kavach.firewall")

RULE_NAME_LOCALHOST = "KAVACH-Sovereignty-Lockdown-Allow-Localhost"
RULE_NAME_SUBNET = "KAVACH-Sovereignty-Lockdown-Allow-Subnet"
TASK_NAME_LOCKDOWN = "KAVACH-Firewall-Lockdown"
TASK_NAME_UNLOCK = "KAVACH-Firewall-Unlock"
STATE_FILE = config.OUTPUTS_DIR / "firewall_lockdown_state.json"
HELPER_SCRIPT = config.PROJECT_ROOT / "scripts" / "firewall_helper.ps1"


class SHELLEXECUTEINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("fMask", wintypes.ULONG),
        ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", wintypes.LPVOID),
        ("lpClass", wintypes.LPCWSTR),
        ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD),
        ("hIcon", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE),
    ]


SEE_MASK_NOCLOSEPROCESS = 0x00000040
SEE_MASK_NOASYNC = 0x00000100
SW_SHOWNORMAL = 1
SW_HIDE = 0
INFINITE = 0xFFFFFFFF


def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _run_netsh(args: list) -> subprocess.CompletedProcess:
    return subprocess.run(["netsh"] + args, capture_output=True, text=True, timeout=15)


def _scheduled_task_exists(task_name: str) -> bool:
    try:
        res = subprocess.run(["schtasks", "/query", "/tn", task_name], capture_output=True, text=True, timeout=5)
        return res.returncode == 0
    except Exception:
        return False


def _run_scheduled_task(task_name: str) -> bool:
    try:
        res = subprocess.run(["schtasks", "/run", "/tn", task_name], capture_output=True, text=True, timeout=10)
        return res.returncode == 0
    except Exception:
        return False


def trigger_uac_elevation(action: str, subnet_cidr: str = "") -> bool:
    """Triggers standard Windows UAC elevation dialog using ShellExecuteExW."""
    try:
        helper_path = str(HELPER_SCRIPT)
        if not Path(helper_path).exists():
            logger.error(f"Firewall helper not found at {helper_path}")
            return False

        args = f'-NoProfile -ExecutionPolicy Bypass -File "{helper_path}" -Action {action} -SubnetCidr "{subnet_cidr}"'

        # Get foreground window handle to anchor the UAC elevation dialog
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd:
                hwnd = ctypes.windll.user32.GetDesktopWindow()
        except Exception:
            hwnd = None

        sei = SHELLEXECUTEINFO()
        sei.cbSize = ctypes.sizeof(SHELLEXECUTEINFO)
        sei.fMask = SEE_MASK_NOCLOSEPROCESS | SEE_MASK_NOASYNC
        sei.hwnd = hwnd
        sei.lpVerb = "runas"
        sei.lpFile = "powershell.exe"
        sei.lpParameters = args
        sei.lpDirectory = str(config.PROJECT_ROOT)
        sei.nShow = SW_SHOWNORMAL

        ret = ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei))
        if not ret:
            err = ctypes.GetLastError()
            logger.info(f"ShellExecuteExW returned False (user may have dismissed UAC, error code {err})")
            return False

        h_process = sei.hProcess
        if h_process:
            # Wait up to 25 seconds for the helper script to complete
            ctypes.windll.kernel32.WaitForSingleObject(h_process, 25000)
            ctypes.windll.kernel32.CloseHandle(h_process)
            return True
        return False
    except Exception as exc:
        logger.error(f"Failed to trigger UAC elevation: {exc}")
        return False


def _get_current_policy_pair() -> Optional[Dict[str, str]]:
    result = _run_netsh(["advfirewall", "show", "currentprofile", "firewallpolicy"])
    if result.returncode != 0:
        return None
    match = re.search(r"Firewall Policy\s+(\S+),(\S+)", result.stdout)
    if not match:
        return None
    return {"inbound": match.group(1), "outbound": match.group(2)}


def _rule_exists(rule_name: str) -> bool:
    result = _run_netsh(["advfirewall", "firewall", "show", "rule", f"name={rule_name}"])
    output = (result.stdout or "") + (result.stderr or "")
    return "No rules match" not in output and rule_name in output


def _load_state() -> Dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def check_firewall_status() -> Dict:
    localhost_rule = _rule_exists(RULE_NAME_LOCALHOST)
    subnet_rule = _rule_exists(RULE_NAME_SUBNET)
    policy = _get_current_policy_pair()
    outbound_policy = policy["outbound"] if policy else None
    state = _load_state()

    physical_active = bool(localhost_rule and subnet_rule and outbound_policy == "BlockOutbound")
    active = physical_active or bool(state.get("active") and not state.get("simulated", False))

    return {
        "active": active,
        "is_admin": _is_admin(),
        "has_scheduled_task": _scheduled_task_exists(TASK_NAME_LOCKDOWN),
        "hardware_enforced": physical_active,
        "outbound_policy": outbound_policy,
        "localhost_rule_present": localhost_rule,
        "subnet_rule_present": subnet_rule,
        "detected_subnet": state.get("subnet_cidr"),
        "enabled_at": state.get("enabled_at"),
        "rule_names": [RULE_NAME_LOCALHOST, RULE_NAME_SUBNET],
    }


def enable_firewall_lockdown(elevate: bool = False) -> Dict:
    net = detect_local_network()
    prior_policy = _get_current_policy_pair() or {"inbound": "BlockInbound", "outbound": "AllowOutbound"}
    is_admin = _is_admin()
    applied_hardware = False

    # Tier 1: Process is already running elevated
    if is_admin:
        add_localhost = _run_netsh([
            "advfirewall", "firewall", "add", "rule",
            f"name={RULE_NAME_LOCALHOST}", "dir=out", "action=allow",
            "remoteip=127.0.0.1", "enable=yes",
        ])
        add_subnet = _run_netsh([
            "advfirewall", "firewall", "add", "rule",
            f"name={RULE_NAME_SUBNET}", "dir=out", "action=allow",
            f"remoteip={net['subnet_cidr']}", "enable=yes",
        ])
        set_policy = _run_netsh([
            "advfirewall", "set", "currentprofile", "firewallpolicy",
            f"{prior_policy['inbound']},blockoutbound",
        ])
        if add_localhost.returncode == 0 and add_subnet.returncode == 0 and set_policy.returncode == 0:
            applied_hardware = True

    # Tier 2: Check for registered highest-privilege scheduled task
    if not applied_hardware and _scheduled_task_exists(TASK_NAME_LOCKDOWN):
        if _run_scheduled_task(TASK_NAME_LOCKDOWN):
            time.sleep(0.5)
            status = check_firewall_status()
            if status["outbound_policy"] == "BlockOutbound":
                applied_hardware = True

    # Tier 3: If not admin and not task, check if user requested elevation
    if not applied_hardware and not is_admin:
        if not elevate:
            # Tell the frontend to show the security permission pop-up
            return {
                "success": False,
                "requires_permission": True,
                "action": "lockdown",
                "message": "Windows Defender Firewall requires administrator elevation. Please grant permission in the confirmation prompt.",
            }

        # User clicked "Grant Permission" -> trigger interactive UAC elevation
        success = trigger_uac_elevation("lockdown", net["subnet_cidr"])
        if success:
            time.sleep(0.5)
            status = check_firewall_status()
            if status["outbound_policy"] == "BlockOutbound":
                applied_hardware = True

    if not applied_hardware:
        return {
            "success": False,
            "requires_permission": True,
            "error": "Windows permission was not granted. Hardware lockdown was not engaged.",
        }

    state = {
        "active": True,
        "success": True,
        "enabled_at": datetime.now(timezone.utc).isoformat(),
        "prior_inbound_policy": prior_policy["inbound"],
        "prior_outbound_policy": prior_policy["outbound"],
        "subnet_cidr": net["subnet_cidr"],
        "local_ip": net["local_ip"],
        "hardware_enforced": True,
    }

    config.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")

    log_event(
        event_type="firewall", actor="shield",
        summary=f"Lockdown ENABLED [HARDWARE]: outbound default=Block, allow localhost + {net['subnet_cidr']}",
        metadata=state,
        external_calls=0,
    )
    return state


def disable_firewall_lockdown(elevate: bool = False) -> Dict:
    state = _load_state()
    prior_inbound = state.get("prior_inbound_policy", "BlockInbound")
    prior_outbound = state.get("prior_outbound_policy", "AllowOutbound")
    is_admin = _is_admin()
    disabled_hardware = False

    # Tier 1: Process is elevated
    if is_admin:
        restore_policy = _run_netsh([
            "advfirewall", "set", "currentprofile", "firewallpolicy",
            f"{prior_inbound},{prior_outbound}",
        ])
        _run_netsh(["advfirewall", "firewall", "delete", "rule", f"name={RULE_NAME_LOCALHOST}"])
        _run_netsh(["advfirewall", "firewall", "delete", "rule", f"name={RULE_NAME_SUBNET}"])
        if restore_policy.returncode == 0:
            disabled_hardware = True

    # Tier 2: Check for scheduled task
    if not disabled_hardware and _scheduled_task_exists(TASK_NAME_UNLOCK):
        if _run_scheduled_task(TASK_NAME_UNLOCK):
            time.sleep(0.5)
            status = check_firewall_status()
            if status["outbound_policy"] != "BlockOutbound":
                disabled_hardware = True

    # Tier 3: Interactive UAC elevation
    if not disabled_hardware and not is_admin:
        if trigger_uac_elevation("unlock"):
            time.sleep(0.5)
            disabled_hardware = True

    if STATE_FILE.exists():
        STATE_FILE.unlink(missing_ok=True)

    log_event(
        event_type="firewall", actor="shield",
        summary=f"Lockdown DISABLED: outbound policy restored to {prior_outbound}",
        metadata={"restored_outbound_policy": prior_outbound, "restored_inbound_policy": prior_inbound},
        external_calls=0,
    )
    return {
        "success": True,
        "active": False,
        "restored_outbound_policy": prior_outbound,
        "restored_inbound_policy": prior_inbound,
    }
