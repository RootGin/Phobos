#!/usr/bin/env python3

import json
import os
import shutil
import subprocess
import sys
import time

CFG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EWW = ["eww", "-c", CFG]
VAR = "nbt"
CLI = "netbird"
UNIT = "netbird"

TONE = {
    "Connected": ("on", "Connected"),
    "Connecting": ("idle", "Connecting"),
    "NeedsLogin": ("idle", "Login needed"),
    "Idle": ("idle", "Disconnected"),
    "Disconnected": ("idle", "Disconnected"),
}


def run(args, timeout=60):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()
    except subprocess.TimeoutExpired:
        return 1, "timed out"
    except Exception as exc:
        return 1, str(exc)


def daemon_up():
    rc, out = run(["systemctl", "is-active", UNIT], timeout=10)
    return rc == 0 and out.strip() == "active"


def parse_status(text):
    try:
        got = json.loads(text)
    except ValueError:
        return {}
    return got if isinstance(got, dict) else {}


def snapshot():
    snap = {"ok": False, "on": False, "state": "off", "tone": "off", "text": "Off"}
    if not shutil.which(CLI):
        snap["text"] = "Not installed"
        return snap
    snap["ok"] = True
    snap["on"] = daemon_up()
    if not snap["on"]:
        return snap
    rc, out = run([CLI, "status", "--json"], timeout=30)
    got = parse_status(out) if rc == 0 else {}
    daemon = got.get("daemonStatus", "")
    tone, label = TONE.get(daemon, ("idle", "Unknown"))
    if tone == "on" and got.get("netbirdIp"):
        label = got["netbirdIp"].split("/")[0]
    snap["state"] = "connected" if tone == "on" else (
        "login" if daemon == "NeedsLogin" else "disconnected")
    snap["tone"] = tone
    snap["text"] = label
    return snap


def publish(snap):
    subprocess.run(EWW + ["update", "%s=%s" % (VAR, json.dumps(snap))],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def cmd_status():
    publish(snapshot())


def cmd_up():
    if not daemon_up():
        publish(snapshot())
        return
    subprocess.Popen([CLI, "up"], stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
    poll(6)


def cmd_down():
    if not daemon_up():
        publish(snapshot())
        return
    run([CLI, "down"], timeout=60)
    publish(snapshot())


def cmd_power():
    snap = snapshot()
    if not snap["ok"]:
        publish(snap)
        return
    want = not snap["on"]
    run(["systemctl", "start" if want else "stop", UNIT], timeout=60)
    poll(6, want)


def poll(ticks, want=None):
    for _ in range(ticks):
        time.sleep(1.5)
        snap = snapshot()
        publish(snap)
        if want is not None:
            if snap["on"] == want:
                return
        elif snap["state"] == "connected":
            return


def selftest():
    assert snapshot()["text"] in ("Off", "Not installed", "Login needed",
                                  "Disconnected", "Connecting")
    body = ('{"daemonStatus":"Connected","netbirdIp":"100.102.3.4/16",'
            '"peers":{"total":4,"connected":2}}')
    got = parse_status(body)
    assert got["daemonStatus"] == "Connected"
    assert got["netbirdIp"].split("/")[0] == "100.102.3.4"
    assert TONE["Connected"][0] == "on"
    assert TONE["Connecting"] == ("idle", "Connecting")
    assert TONE["NeedsLogin"][1] == "Login needed"
    assert TONE["Idle"] == TONE["Disconnected"]
    assert TONE.get("Bogus", ("idle", "Unknown")) == ("idle", "Unknown")
    assert parse_status("not json") == {}
    assert parse_status("[]") == {}
    print("netbird.py selftest: ok")


def main():
    argv = sys.argv[1:]
    verb = argv[0] if argv else "status"
    if verb == "status":
        cmd_status()
    elif verb == "up":
        cmd_up()
    elif verb == "down":
        cmd_down()
    elif verb == "power":
        cmd_power()
    elif verb == "selftest":
        selftest()
    else:
        sys.exit("unknown subcommand: %s" % verb)


if __name__ == "__main__":
    main()