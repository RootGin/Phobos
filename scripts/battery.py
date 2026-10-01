#!/usr/bin/env python3

import glob
import json
import os
import subprocess
import sys
import time

CFG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EWW = ["eww", "-c", CFG]
VAR = "battjson"
SUPPLY = "/sys/class/power_supply"
THR_FILE = os.path.expanduser("~/.local/state/phobos/battery-threshold")
DEFAULT_THR = 20
LO, HI = 0, 40
SEGMENTS = 20


def rd(base, name, default=""):
    try:
        with open(os.path.join(base, name)) as f:
            return f.read().strip()
    except OSError:
        return default


def num(base, name):
    try:
        return int(rd(base, name, "0") or 0)
    except ValueError:
        return 0


def upower_time(name, status):
    """upower's own rate-based estimate; it omits the field when unknown."""
    key = {"Discharging": "time to empty:",
           "Charging": "time to full:"}.get(status)
    if not key:
        return "--"
    try:
        listing = subprocess.run(["upower", "-e"], capture_output=True,
                                 text=True, timeout=10).stdout
        dev = next((l.strip() for l in listing.splitlines()
                    if "/battery_" + name in l), None)
        if not dev:
            return "--"
        info = subprocess.run(["upower", "-i", dev], capture_output=True,
                              text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return "--"
    for line in info.splitlines():
        if line.strip().lower().startswith(key):
            value = line.split(":", 1)[1].strip()
            return value if value and value != "--" else "--"
    return "--"


def threshold():
    try:
        with open(THR_FILE) as f:
            return max(LO, min(HI, int(f.read().strip())))
    except (OSError, ValueError):
        return DEFAULT_THR


def supplies(kind):
    return sorted(p for p in glob.glob(os.path.join(SUPPLY, "*"))
                  if rd(p, "type") == kind)


def ac_online():
    return any(num(p, "online") == 1 for p in supplies("Mains"))


def energy(base, name):
    """charge_* in µAh, energy_* in µWh — both read as µW against power_now."""
    val = num(base, name)
    if val:
        return val
    scaled = num(base, name.replace("charge", "energy"))
    return scaled


def read_battery(path, ac):
    status = rd(path, "status", "Unknown")
    cap = num(path, "capacity")
    level = rd(path, "capacity_level", "")
    full = energy(path, "charge_full")
    design = energy(path, "charge_full_design")
    pw = num(path, "power_now")

    state = status
    if status == "Not charging":
        state = ("AC, full" if cap >= 99 else "AC, capped") if ac else "Not charging"
    elif status == "Full":
        state = "Full"

    return {
        "name": os.path.basename(path),
        "cap": cap,
        "status": status,
        "present": rd(path, "present", "1") == "1",
        "state": state,
        "charge": ("%d%%" % cap) if cap else (level or "--"),
        "time": upower_time(os.path.basename(path), status),
        "draw": "%.2f W" % (pw / 1e6) if pw > 0 else "--",
        "health": "%.1f%%" % (full / design * 100) if full and design else "--",
        "cycles": rd(path, "cycle_count", "--"),
        "model": rd(path, "model_name", "") or rd(path, "manufacturer", ""),
    }


def snapshot():
    ac = ac_online()
    bats = [read_battery(p, ac) for p in supplies("Battery")]
    main = next((b for b in bats if b["name"].startswith("BAT")), None)
    if main is None:
        main = next((b for b in bats if b["present"]), None)
    extra = [b for b in bats if b is not main]

    cap = main["cap"] if main else 0
    if not bats:
        brief = tip = "No battery detected"
    else:
        brief = "%s · %s" % (main["charge"], main["state"])
        extra_bits = [b for b in (main["time"], main["draw"]) if b != "--"]
        tip = "%s — %s%s" % (main["name"], brief, " · " + " · ".join(extra_bits) if extra_bits else "")

    return {
        "thr": threshold(),
        "ac": ac,
        "main": main or {"name": "none", "present": False, "state": "No battery",
                         "charge": "--", "time": "--", "draw": "--",
                         "health": "--", "cycles": "--", "model": ""},
        "extra": extra,
        "segments": ["on" if (i + 1) * (100.0 / SEGMENTS) <= cap else "off"
                     for i in range(SEGMENTS)],
        "brief": brief,
        "tip": tip,
    }


def publish(payload):
    subprocess.run(EWW + ["update", "%s=%s" % (VAR, json.dumps(payload))],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def alert(payload):
    main = payload["main"]
    subprocess.run(["notify-send", "Low battery",
                    "%s is at %s, below your %d%% alert level."
                    % (main["name"], main["charge"], payload["thr"])],
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
        cap = payload["main"]["cap"]
        if previous >= payload["thr"] and cap < payload["thr"]:
            alert(payload)
        return cap

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
    snap = snapshot()
    assert set(snap) == {"thr", "ac", "main", "extra", "segments", "brief", "tip"}
    assert len(snap["segments"]) == SEGMENTS
    assert set(snap["main"]) == {"name", "cap", "status", "present", "state",
                                 "charge", "time", "draw", "health", "cycles",
                                 "model"}
    assert snap["main"]["time"] == "--" or ":" in snap["main"]["time"]
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
