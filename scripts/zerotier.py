#!/usr/bin/env python3

import json
import os
import re
import shutil
import subprocess
import sys
import time

CFG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EWW = ["eww", "-c", CFG]
VAR = "ztjson"
CLI = "zerotier-cli"
UNIT = "zerotierone"

STATE = os.path.join(
    os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state")),
    "phobos", "zerotier-last")

NWID_RE = re.compile(r"^[0-9a-f]{16}$")
UP = ("OK", "NETWORK_UP")


def run(args, timeout=60):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()
    except subprocess.TimeoutExpired:
        return 1, "timed out"
    except Exception as exc:
        return 1, str(exc)


def read_last():
    try:
        with open(STATE) as fh:
            nid = fh.read().strip().lower()
    except OSError:
        return ""
    return nid if NWID_RE.match(nid) else ""


def write_last(nid):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w") as fh:
        fh.write(nid)


def parse_networks(text):
    nets = []
    for line in text.splitlines():
        f = line.split()
        if len(f) < 8 or not NWID_RE.match(f[1]):
            continue
        assign = f[7] if f[7] != "-" else ""
        nets.append({
            "id": f[1],
            "name": "" if f[2] == "-" else f[2],
            "status": f[4],
            "ip": ",".join(a.split("/")[0] for a in assign.split(",") if a),
        })
    return nets


def snapshot():
    snap = {"ok": False, "on": False, "tone": "off", "state": "Not installed",
            "net": [], "last": read_last()}
    if not shutil.which(CLI):
        return snap
    snap["ok"] = True
    rc, out = run([CLI, "listnetworks"])
    if rc != 0:
        snap["state"] = "Off"
        return snap
    snap["on"] = True
    snap["net"] = parse_networks(out)
    if not snap["net"]:
        snap["tone"] = "idle"
        snap["state"] = "No network"
        return snap
    first = snap["net"][0]
    snap["state"] = first["name"] or first["id"]
    snap["tone"] = "on" if first["status"] in UP else "idle"
    return snap


def publish(snap):
    subprocess.run(EWW + ["update", "%s=%s" % (VAR, json.dumps(snap))],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def cmd_status():
    publish(snapshot())


def cmd_join(nid):
    nid = nid.strip().lower()
    if not NWID_RE.match(nid):
        sys.exit("zerotier.py: not a network id: %s" % nid)
    run([CLI, "join", nid], timeout=90)
    write_last(nid)
    for _ in range(5):
        snap = snapshot()
        publish(snap)
        if snap["tone"] == "on" and snap["net"] and snap["net"][0]["name"]:
            return
        time.sleep(1.5)


def cmd_leave(nid):
    run([CLI, "leave", nid.strip().lower()], timeout=90)
    publish(snapshot())


def cmd_power():
    snap = snapshot()
    if snap["ok"]:
        want = not snap["on"]
        run(["systemctl", "start" if want else "stop", UNIT], timeout=60)
        for _ in range(6):
            time.sleep(1)
            snap = snapshot()
            if snap["on"] == want:
                break
        if snap["on"] != want:
            snap["tone"] = "off"
            snap["state"] = "Blocked"
    publish(snap)


def selftest():
    got = parse_networks(
        "200 listnetworks 200\n"
        "200 8056c2e21c000001 oplan 5a5a5a5a5a5a5a5a OK broadcast zt0 10.147.17.5/24\n"
        "200 1a2b3c4d5e6f7788 - 5a5a5a5a5a5a5a5a ACCESS_DENIED broadcast - - -")
    assert [n["id"] for n in got] == ["8056c2e21c000001", "1a2b3c4d5e6f7788"]
    assert got[0]["name"] == "oplan" and got[0]["ip"] == "10.147.17.5"
    assert got[0]["status"] == "OK" and got[1]["status"] == "ACCESS_DENIED"
    assert got[1]["name"] == "" and got[1]["ip"] == ""
    assert parse_networks("") == []
    assert parse_networks("200 200 200\n") == []
    assert NWID_RE.match("8056c2e21c000001") and not NWID_RE.match("deadbeef")
    print("zerotier.py selftest: ok")


def main():
    argv = sys.argv[1:]
    verb = argv[0] if argv else "status"
    if verb == "status":
        cmd_status()
    elif verb == "join":
        cmd_join(argv[1] if len(argv) > 1 else "")
    elif verb == "leave":
        cmd_leave(argv[1] if len(argv) > 1 else "")
    elif verb == "power":
        cmd_power()
    elif verb == "selftest":
        selftest()
    else:
        sys.exit("unknown subcommand: %s" % verb)


if __name__ == "__main__":
    main()