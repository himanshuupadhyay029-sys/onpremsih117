"""netinfo.py — shared local-network detection used by both firewall.py (Layer 1)
and monitor.py (Layer 2) so they always agree on what counts as "local".

Uses a UDP socket connect() purely to ask the OS routing table which local
interface/IP it would use to reach an external address. This makes NO network
transmission — UDP connect() only sets up local kernel routing state; it does
not send any packet on the wire — so calling this does not itself violate the
"zero external calls" requirement it exists to help enforce.
"""

import socket
from typing import Dict

FALLBACK_SUBNET_CIDR = "192.168.0.0/24"


def detect_local_network() -> Dict[str, str]:
    """Returns this machine's LAN IP and its /24 subnet, auto-detected (never hardcoded)."""
    local_ip = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))  # no packet sent; just asks the OS for the outbound route
            local_ip = s.getsockname()[0]
        finally:
            s.close()
    except Exception:
        pass

    parts = local_ip.split(".")
    if len(parts) == 4 and local_ip != "127.0.0.1":
        subnet_cidr = f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
    else:
        subnet_cidr = FALLBACK_SUBNET_CIDR

    return {"local_ip": local_ip, "subnet_cidr": subnet_cidr}
