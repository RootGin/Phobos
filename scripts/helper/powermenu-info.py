#!/usr/bin/env python3
"""Left-card system facts for the powermenu, as one JSON object for the `pm-info`
defpoll. Cosmetic only (greeting / user / OS / CPU / RAM / battery + the classes
for the segmented battery bar) — nothing here is on the control path.
Re-run periodically so the greeting tracks the time of day."""
import json
import os
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

def os_name():
    data = {}
    try:
        with open("/etc/os-release") as fh:
            for line in fh:
                if "=" in line:
                    k, v = line.rstrip().split("=", 1)
                    data[k] = v.strip('"')
    except OSError:
        pass
    return f"{data.get('NAME', 'Linux')} {data.get('VERSION_ID', '')}".strip()

hour = time.localtime().tm_hour
greeting = (
    "GOOD MORNING," if hour < 12
    else "GOOD AFTERNOON," if hour < 18
    else "GOOD EVENING,"
)
model = cpu_model()
ghz = cpu_ghz()
cap = int(read(BAT, "0"))

print(json.dumps({
    "greeting": greeting,
    "user": (os.environ.get("USER") or "user").upper(),
    "os": os_name(),
    "cpu": f"{model} @ {ghz:.2f}GHz" if ghz else model,
    "ram": f"{ram_gib():.2f} GiB",
    "batt": f"{cap:03d}",
    "segments": ["on" if (i + 1) * (100 / SEGMENTS) <= cap else "off"
                 for i in range(SEGMENTS)],
}))
