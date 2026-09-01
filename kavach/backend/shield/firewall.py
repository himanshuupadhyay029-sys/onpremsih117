"""firewall.py — Layer 1: Windows Firewall default-deny egress enforcement.

Mechanism: Windows Firewall processes rules such that an explicit BLOCK rule
always wins over an explicit ALLOW rule for the same traffic, regardless of
rule order — so a single "block all outbound" rule plus "allow localhost/LAN"
rules would NOT work (the block rule would also match, and block, the local
traffic). The correct way to get "default-deny egress" on Windows is instead
to flip the ACTIVE firewall profile's default OUTBOUND policy to Block, then
add explicit ALLOW rules for the exceptions — explicit rules always beat the
ambient default policy, so the allow rules work correctly against that default.

Two named firewall rules (the actual exceptions):
  KAVACH-Sovereignty-Lockdown-Allow-Localhost   (dir=out action=allow remoteip=127.0.0.1)
  KAVACH-Sovereignty-Lockdown-Allow-Subnet      (dir=out action=allow remoteip=<detected>/24)

The default-outbound-policy flip itself is a profile SETTING, not a named rule
(Windows has no name for it) — its exact prior value (whatever it was before
KAVACH touched it) is saved to outputs/firewall_lockdown_state.json before
enabling, so disable_firewall_lockdown() restores EXACTLY what was there
before, not an assumed default.

Requires an elevated (Administrator) shell to mutate anything. Querying status
does NOT require elevation. If not elevated, every mutating function returns
success=False with a clear error message containing the exact netsh commands
to run manually in an elevated PowerShell.
"""

import ctypes
import json
import re
import subprocess
from datetime import datetime, timezone
from typing import Dict, Optional

from backend import config
from backend.audit.logbook import log_event
from backend.shield.netinfo import detect_local_network

RULE_NAME_LOCALHOST = "KAVACH-Sovereignty-Lockdown-Allow-Localhost"
RULE_NAME_SUBNET = "KAVACH-Sovereignty-Lockdown-Allow-Subnet"
STATE_FILE = config.OUTPUTS_DIR / "firewall_lockdown_state.json"


def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _run_netsh(args: list) -> subprocess.CompletedProcess:
    return subprocess.run(["netsh"] + args, capture_output=True, text=True, timeout=15)


def _get_current_policy_pair() -> Optional[Dict[str, str]]:
    """Parses `netsh advfirewall show currentprofile firewallpolicy` — this is a
    read-only query and does NOT require elevation."""
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


def _manual_commands(subnet_cidr: str, prior_inbound: str) -> str:
    return (
        f'netsh advfirewall firewall add rule name="{RULE_NAME_LOCALHOST}" dir=out action=allow remoteip=127.0.0.1 enable=yes\n'
        f'netsh advfirewall firewall add rule name="{RULE_NAME_SUBNET}" dir=out action=allow remoteip={subnet_cidr} enable=yes\n'
        f'netsh advfirewall set currentprofile firewallpolicy {prior_inbound},blockoutbound'
    )


def _load_state() -> Dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def check_firewall_status() -> Dict:
    """Read-only — does not require elevation."""
    localhost_rule = _rule_exists(RULE_NAME_LOCALHOST)
    subnet_rule = _rule_exists(RULE_NAME_SUBNET)
    policy = _get_current_policy_pair()
    outbound_policy = policy["outbound"] if policy else None
    state = _load_state()

    active = bool(localhost_rule and subnet_rule and outbound_policy == "BlockOutbound")

    return {
        "active": active,
        "outbound_policy": outbound_policy,
        "localhost_rule_present": localhost_rule,
        "subnet_rule_present": subnet_rule,
        "detected_subnet": state.get("subnet_cidr"),
        "enabled_at": state.get("enabled_at"),
        "rule_names": [RULE_NAME_LOCALHOST, RULE_NAME_SUBNET],
    }


def enable_firewall_lockdown() -> Dict:
    net = detect_local_network()
    prior_policy = _get_current_policy_pair() or {"inbound": "BlockInbound", "outbound": "AllowOutbound"}

    if not _is_admin():
        error = (
            "[firewall error] Not running elevated (Administrator) — cannot change firewall policy.\n"
            "Open Start menu -> type 'PowerShell' -> right-click 'Windows PowerShell' -> "
            "'Run as administrator', then paste these commands exactly:\n\n"
            + _manual_commands(net["subnet_cidr"], prior_policy["inbound"])
        )
        log_event(
            event_type="firewall", actor="shield",
            summary="Enable FAILED: not elevated",
            metadata={"admin": False, "subnet_cidr": net["subnet_cidr"]},
            external_calls=0,
        )
        return {"success": False, "error": error, "manual_commands": _manual_commands(net["subnet_cidr"], prior_policy["inbound"])}

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

    if add_localhost.returncode != 0 or add_subnet.returncode != 0:
        error_text = (add_localhost.stderr or add_localhost.stdout or "") + "\n" + (add_subnet.stderr or add_subnet.stdout or "")
        log_event(
            event_type="firewall", actor="shield",
            summary="Enable FAILED: could not add allow rules",
            metadata={"error": error_text[:500]},
            external_calls=0,
        )
        return {"success": False, "error": f"[firewall error] Failed to add allow rules:\n{error_text}"}

    set_policy = _run_netsh([
        "advfirewall", "set", "currentprofile", "firewallpolicy",
        f"{prior_policy['inbound']},blockoutbound",
    ])
    if set_policy.returncode != 0:
        # Roll back the allow rules we just added, since the lockdown didn't actually take effect
        _run_netsh(["advfirewall", "firewall", "delete", "rule", f"name={RULE_NAME_LOCALHOST}"])
        _run_netsh(["advfirewall", "firewall", "delete", "rule", f"name={RULE_NAME_SUBNET}"])
        error_text = set_policy.stderr or set_policy.stdout or ""
        log_event(
            event_type="firewall", actor="shield",
            summary="Enable FAILED: could not set outbound policy to Block",
            metadata={"error": error_text[:500]},
            external_calls=0,
        )
        return {"success": False, "error": f"[firewall error] Failed to set outbound policy to Block:\n{error_text}"}

    state = {
        "enabled_at": datetime.now(timezone.utc).isoformat(),
        "prior_inbound_policy": prior_policy["inbound"],
        "prior_outbound_policy": prior_policy["outbound"],
        "subnet_cidr": net["subnet_cidr"],
        "local_ip": net["local_ip"],
    }
    config.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")

    log_event(
        event_type="firewall", actor="shield",
        summary=f"Lockdown ENABLED: outbound default=Block, allow localhost + {net['subnet_cidr']}",
        metadata=state,
        external_calls=0,
    )
    return {"success": True, **state}


def disable_firewall_lockdown() -> Dict:
    state = _load_state()
    prior_inbound = state.get("prior_inbound_policy", "BlockInbound")
    prior_outbound = state.get("prior_outbound_policy", "AllowOutbound")

    if not _is_admin():
        error = (
            "[firewall error] Not running elevated (Administrator) — cannot change firewall policy.\n"
            "Open an elevated PowerShell and paste:\n\n"
            f'netsh advfirewall set currentprofile firewallpolicy {prior_inbound},{prior_outbound}\n'
            f'netsh advfirewall firewall delete rule name="{RULE_NAME_LOCALHOST}"\n'
            f'netsh advfirewall firewall delete rule name="{RULE_NAME_SUBNET}"\n\n'
            "Or via the GUI: open 'Windows Defender Firewall with Advanced Security' -> right-click the "
            "root node -> Properties -> the active profile tab (e.g. 'Public Profile' or 'Private Profile') -> "
            "set 'Outbound connections' back to 'Allow' -> OK. Then delete the two "
            "KAVACH-Sovereignty-Lockdown-* rules under 'Outbound Rules'."
        )
        log_event(
            event_type="firewall", actor="shield",
            summary="Disable FAILED: not elevated",
            metadata={"admin": False},
            external_calls=0,
        )
        return {"success": False, "error": error}

    restore_policy = _run_netsh([
        "advfirewall", "set", "currentprofile", "firewallpolicy",
        f"{prior_inbound},{prior_outbound}",
    ])
    _run_netsh(["advfirewall", "firewall", "delete", "rule", f"name={RULE_NAME_LOCALHOST}"])
    _run_netsh(["advfirewall", "firewall", "delete", "rule", f"name={RULE_NAME_SUBNET}"])

    if STATE_FILE.exists():
        STATE_FILE.unlink(missing_ok=True)

    success = restore_policy.returncode == 0
    log_event(
        event_type="firewall", actor="shield",
        summary=f"Lockdown DISABLED: outbound policy restored to {prior_outbound}",
        metadata={"restored_outbound_policy": prior_outbound, "restored_inbound_policy": prior_inbound, "success": success},
        external_calls=0,
    )
    return {"success": success, "restored_outbound_policy": prior_outbound, "restored_inbound_policy": prior_inbound}
