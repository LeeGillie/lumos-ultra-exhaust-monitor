"""Send a command to a node over UDP (handy without the desktop app).

    python tools/send_command.py laser zero
    python tools/send_command.py fan set_level 7
    python tools/send_command.py laser update
    python tools/send_command.py --listen          # watch telemetry
"""

import argparse
import json
import socket
import sys


def send(command: str, extra: dict, port: int, host: str) -> None:
    payload = {"cmd": command}
    payload.update(extra)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.sendto(json.dumps(payload).encode(), (host, port))
    print(f"sent {payload} to {host}:{port}")


def listen(port: int) -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", port))
    print(f"listening on UDP {port} — ctrl-c to stop")
    while True:
        data, addr = s.recvfrom(2048)
        try:
            msg = json.loads(data)
        except ValueError:
            continue
        chans = " ".join(f"{k}={v.get('pa', '--')}" for k, v in (msg.get("ch") or {}).items())
        print(f"{addr[0]:>15}  {msg.get('node', '?'):>6}  seq={msg.get('seq', 0):<6} {chans}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("node", nargs="?", help="node id (informational; UDP goes to the LAN)")
    ap.add_argument("command", nargs="?",
                    choices=["zero", "clear_zero", "info", "reboot", "update", "set_level"])
    ap.add_argument("value", nargs="?", help="level for set_level, url for update")
    ap.add_argument("--host", default="255.255.255.255")
    ap.add_argument("--port", type=int, default=47811)
    ap.add_argument("--listen", action="store_true", help="print telemetry instead")
    ap.add_argument("--telemetry-port", type=int, default=47810)
    a = ap.parse_args()

    if a.listen:
        listen(a.telemetry_port)
        return 0
    if not a.command:
        ap.print_help()
        return 2
    extra: dict = {}
    if a.command == "set_level":
        extra["level"] = int(a.value or 10)
    elif a.command == "update" and a.value:
        extra["url"] = a.value
    send(a.command, extra, a.port, a.host)
    return 0


if __name__ == "__main__":
    sys.exit(main())
