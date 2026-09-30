#!/usr/bin/env python3

import json
import os
import subprocess
import sys
import time

CFG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EWW = ["eww", "-c", CFG]
VAR = "battjson"
BAT = "/sys/class/power_supply/BAT0"
THR_FILE = os.path.expanduser("~/.local/state/phobos/battery-threshold")
DEFAULT_THR = 20
LO, HI = 5, 95


def rd(name, default=""):
    try:
        with open(os.path.join(BAT, name)) as f:
            return f.read().strip()
    except OSError:
        return default


def num(name):
    try:
        return int(rd(name, "0") or 0)
    except ValueError:
        return 0


def fmt_time(sec):
    sec = int(sec)
    h, m = sec // 3600, (sec % 3600) // 60
    return ("%dh %02dm" % (h, m)) if h else ("%dm" % m)


def threshold():
    try:
        with open(THR_FILE) as f:
            return max(LO, min(HI, int(f.read().strip())))
    except (OSError, ValueError):
        return DEFAULT_THR


def snapshot():
    status = rd("status", "Unknown")
    full = num("energy_full")
    design = num("energy_full_design")
    now = num("energy_now")
    pw = num("power_now")

    left = 0
    if pw > 0:
        left = (now / pw) if status == "Discharging" else ((full - now) / pw)

    return {
        "status": status,
        "charge": "%d%%" % num("capacity"),
        "time": fmt_time(left) if left > 60 else "--",
        "draw": "%.2f W" % (pw / 1e6) if pw > 0 else "--",
        "health": "%.1f%%" % (full / design * 100) if design else "--",
        "cycles": rd("cycle_count", "--"),
        "thr": threshold(),
    }


def publish(payload):
    subprocess.run(EWW + ["update", "%s=%s" % (VAR, json.dumps(payload))],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def alert(payload):
    subprocess.run(["notify-send", "Low battery",
                    "Charge is at %s, below your %d%% alert level."
                    % (payload["charge"], payload["thr"])],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def cmd_threshold(value):
    try:
        want = int(value)
    except (TypeError, ValueError):
        sys.exit("threshold: not a number: %s" % value)
    want = max(LO, min(HI, want))
    os.makedirs(os.path.dirname(THR_FILE), exist_ok=True)
    with open(THR_FILE, "w") as f:
        f.write(str(want))
    publish(snapshot())


def stream():
    def emit(previous):
        payload = snapshot()
        if previous >= payload["thr"] and num("capacity") < payload["thr"]:
            alert(payload)
        return num("capacity")

    capacity = emit(-1)
    print(json.dumps(snapshot()), flush=True)
    while True:
        mon = subprocess.Popen(
            ["udevadm", "monitor", "--subsystem-match=power_supply"],
            stdout=subprocess.PIPE, text=True)
        for line in mon.stdout:
            if "power_supply" not in line:
                continue
            capacity = emit(capacity)
            print(json.dumps(snapshot()), flush=True)
        mon.wait()
        time.sleep(1)


def selftest():
    assert fmt_time(3600 * 2 + 60 * 14) == "2h 14m"
    assert fmt_time(60 * 14) == "14m"
    assert fmt_time(59) == "0m"
    snap = snapshot()
    assert set(snap) == {"status", "charge", "time", "draw", "health",
                         "cycles", "thr"}
    assert snap["charge"].endswith("%")
    assert LO <= snap["thr"] <= HI
    print("battery.py selftest: ok", json.dumps(snap))


def main():
    argv = sys.argv[1:]
    verb = argv[0] if argv else "stream"
    if verb == "stream":
        stream()
    elif verb == "threshold":
        cmd_threshold(argv[1] if len(argv) > 1 else None)
    elif verb == "status":
        print(json.dumps(snapshot()))
    elif verb == "selftest":
        selftest()
    else:
        sys.exit("unknown subcommand: %s" % verb)


if __name__ == "__main__":
    main()