#!/usr/bin/env python3
"""Left-card system facts for the powermenu, as one JSON object for the `pm-info`
defpoll. Cosmetic only (greeting / user / OS / CPU / RAM / uptime / kernel /
battery + the classes for the segmented HUD meters) — nothing here is on the
control path. Re-run periodically so the greeting and uptime stay current."""
import json
import os
import platform
import sys
import time

BAT = "/sys/class/power_supply/BAT0/capacity"
SEGMENTS = 20

def read(path, default=""):
    try:
        with open(path) as fh:
            return fh.read().strip()
    except OSError:
        return default

def cpu_model():
    for line in read("/proc/cpuinfo").splitlines():
        if line.startswith("model name"):
            return line.split(":", 1)[1].strip().split(" with ")[0]
    return "CPU"

def cpu_ghz():
    for line in read("/proc/cpuinfo").splitlines():
        if line.startswith("cpu MHz"):
            return float(line.split(":", 1)[1]) / 1000
    return 0.0

def ram_gib():
    for line in read("/proc/meminfo").splitlines():
        if line.startswith("MemTotal"):
            return int(line.split()[1]) / 1048576
    return 0.0

def uptime_secs():
    return float(read("/proc/uptime", "0").split()[0] or 0)

def fmt_uptime(secs):
    d, rem = divmod(int(secs), 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d}d {h:02d}h"
    if h:
        return f"{h}h {m:02d}m"
    return f"{m}m"

def os_release():
    data = {}
    try:
        with open("/etc/os-release") as fh:
            for line in fh:
                if "=" in line:
                    k, v = line.rstrip().split("=", 1)
                    data[k] = v.strip('"')
    except OSError:
        pass
    return data

def os_name():
    d = os_release()
    return f"{d.get('NAME', 'Linux')} {d.get('VERSION_ID', '')}".strip()

def generation():
    """NixOS system generation, e.g. 26.11.20260919.20b1ddd. BUILD_ID is that
    string; on anything else fall back to the plain version."""
    d = os_release()
    return d.get("BUILD_ID") or d.get("VERSION_ID", "")

hour = time.localtime().tm_hour
greeting = (
    "GOOD MORNING," if hour < 12
    else "GOOD AFTERNOON," if hour < 18
    else "GOOD EVENING,"
)
model = cpu_model()
ghz = cpu_ghz()
cap = int(read(BAT, "0"))
up = uptime_secs()
rel = platform.release().split("-")[0]

def _selftest():
    assert fmt_uptime(0) == "0m"
    assert fmt_uptime(59) == "0m"
    assert fmt_uptime(3600) == "1h 00m"
    assert fmt_uptime(8 * 3600 + 28 * 60) == "8h 28m"
    assert fmt_uptime(2 * 86400 + 3 * 3600 + 4 * 60) == "2d 03h"
    print("powermenu-info selftest ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
        sys.exit(0)
    print(json.dumps({
        "greeting": greeting,
        "user": (os.environ.get("USER") or "user").upper(),
        "os": os_name(),
        "cpu": f"{model} @ {ghz:.2f}GHz" if ghz else model,
        "ram": f"{ram_gib():.2f} GiB",
        "uptime": fmt_uptime(up),
        "generation": generation(),
        "kernel": rel,
        "batt": f"{cap:03d}",
        "segments": ["on" if (i + 1) * (100 / SEGMENTS) <= cap else "off"
                     for i in range(SEGMENTS)],
    }))

