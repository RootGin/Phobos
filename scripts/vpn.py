#!/usr/bin/env python3

import json
import os
import re
import subprocess
import sys

CFG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EWW = ["eww", "-c", CFG]
VAR = "vpnt"

OFF = {"state": "off", "server": "", "ip": ""}

IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def run(args, timeout=120):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()
    except subprocess.TimeoutExpired:
        return 1, "timed out"
    except Exception as exc:
        return 1, str(exc)


def parse_status(text):
    low = text.lower()
    if "disconnected" in low or "not connected" in low:
        state = "disconnected"
    elif "connected" in low:
        state = "connected"
    else:
        state = "disconnected"

    ip = ""
    m = IP_RE.search(text)
    if m:
        ip = m.group(0)

    server = ""
    for line in text.splitlines():
        line = line.strip()
        if line.lower().startswith("server"):
            server = line.split(":", 1)[-1].strip()
            break

    return {"state": state, "server": server, "ip": ip}


def current():
    p = subprocess.run(EWW + ["get", VAR], capture_output=True, text=True, timeout=15)
    try:
        got = json.loads(p.stdout)
    except ValueError:
        return dict(OFF)
    if not isinstance(got, dict) or "state" not in got:
        return dict(OFF)
    return got


def publish(state):
    subprocess.run(EWW + ["update", "%s=%s" % (VAR, json.dumps(state))],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def read_published():
    _, out = run(["protonvpn", "status"], timeout=30)
    return parse_status(out)


def cmd_status():
    if current()["state"] == "off":
        publish(dict(OFF))
    else:
        publish(read_published())


def cmd_toggle():
    if current()["state"] == "off":
        publish(read_published())
    else:
        publish(dict(OFF))


def cmd_connect(args):
    if current()["state"] == "off":
        publish(dict(OFF))
        return
    run(["protonvpn", "connect", *args], timeout=180)
    publish(read_published())


def cmd_disconnect():
    if current()["state"] != "connected":
        return
    run(["protonvpn", "disconnect"], timeout=60)
    publish(read_published())


def cmd_exit():
    run(["protonvpn", "disconnect"], timeout=60)
    publish(dict(OFF))


def selftest():
    assert parse_status("Status: Disconnected") == {
        "state": "disconnected", "server": "", "ip": ""}
    got = parse_status("Status: Connected\nServer: CH#13\nIP: 149.165.10.20")
    assert got["state"] == "connected" and got["server"] == "CH#13"
    assert got["ip"] == "149.165.10.20"
    assert parse_status("Status: Connected")["state"] == "connected"
    assert parse_status("") == {"state": "disconnected", "server": "", "ip": ""}
    assert parse_status("VPN is not connected")["state"] == "disconnected"
    print("vpn.py selftest: ok")


def main():
    argv = sys.argv[1:]
    verb = argv[0] if argv else "status"
    if verb == "status":
        cmd_status()
    elif verb == "toggle":
        cmd_toggle()
    elif verb == "connect":
        cmd_connect(argv[1:])
    elif verb == "disconnect":
        cmd_disconnect()
    elif verb == "exit":
        cmd_exit()
    elif verb == "selftest":
        selftest()
    else:
        sys.exit("unknown subcommand: %s" % verb)


if __name__ == "__main__":
    main()
