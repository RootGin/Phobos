#!/usr/bin/env python3
import json
import os

PREV = "/tmp/phobos-cpu-prev"


def cpu():
    with open("/proc/stat") as f:
        parts = f.readline().split()[1:]
    vals = [int(x) for x in parts]
    idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
    return sum(vals), idle


def ram():
    info = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, _, rest = line.partition(":")
            info[k] = int(rest.split()[0])
    used = info["MemTotal"] - info["MemAvailable"]
    return round(used / info["MemTotal"] * 100)


def main():
    total, idle = cpu()
    prev = None
    if os.path.exists(PREV):
        try:
            with open(PREV) as f:
                prev = tuple(int(x) for x in f.read().split())
        except ValueError:
            prev = None
    with open(PREV, "w") as f:
        f.write(f"{total} {idle}")
    if prev is None:
        pct = 0
    else:
        dt = total - prev[0]
        pct = round((dt - (idle - prev[1])) / dt * 100) if dt > 0 else 0
    print(json.dumps({"cpu": max(0, min(pct, 100)), "ram": ram()}))


if __name__ == "__main__":
    main()
