#!/usr/bin/env python3
# Polls niri over its IPC and emits the workspacejson the bars expect, and
# reveals the workspace OSD while the focused workspace changes.
# The wsosd window must already be open (start.sh opens it) -- calling
# `eww open wsosd` from here makes eww restart this very deflisten and kill us
# mid-update.
# ponytail: 0.4s poll instead of `niri msg event-stream`; swap if it shows up
# in a profile.

import json
import os
import subprocess
import time

EWW = ["eww", "-c", os.path.expanduser("~/.config/eww/Phobos-dev")]
BOXES = 5
POLL = 0.4
OSD_HOLD = 2.0


def niri(*args):
    try:
        out = subprocess.run(["niri", "msg", "--json", *args],
                             capture_output=True, text=True, timeout=2)
        if out.returncode != 0 or not out.stdout.strip():
            return []
        return json.loads(out.stdout)
    except Exception:
        return []


def snapshot():
    windows = niri("windows")
    counts = {}
    for w in windows:
        wid = w.get("workspace_id")
        counts[wid] = counts.get(wid, 0) + 1

    found = {}
    focused = 1
    for ws in niri("workspaces"):
        idx = ws.get("idx")
        if idx is None:
            continue
        found[idx] = {
            "focused": bool(ws.get("is_focused")),
            "empty": counts.get(ws.get("id"), 0) == 0,
            "name": idx,
        }
        if ws.get("is_focused"):
            focused = idx

    boxes = [found.get(i, {"focused": False, "empty": True, "name": i})
             for i in range(1, BOXES + 1)]
    return {"workspaces": boxes, "focused": focused - 1}


def eww(*args):
    subprocess.run(EWW + list(args),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    last = None
    last_focus = None
    hide_at = 0.0
    while True:
        snap = snapshot()
        if snap != last:
            print(json.dumps(snap), flush=True)
            last = snap

        focus = snap["focused"]
        if last_focus is not None and focus != last_focus:
            eww("update", "revealwsosd=true")
            hide_at = time.time() + OSD_HOLD
        last_focus = focus

        if hide_at and time.time() >= hide_at:
            eww("update", "revealwsosd=false")
            hide_at = 0.0

        time.sleep(POLL)


if __name__ == "__main__":
    main()
