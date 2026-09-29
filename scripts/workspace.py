#!/usr/bin/env python3
# Emits the workspacejson the bars expect and reveals the workspace OSD while
# the focused workspace changes. event-stream is a change trigger only; data
# still comes from a snapshot.
#
# The wsosd window must already be open (start.sh opens it) -- calling
# `eww open wsosd` from here makes eww restart this very deflisten and kill us
# mid-update.

import json
import os
import select
import subprocess
import time

EWW = ["eww", "-c", os.path.expanduser("~/.config/eww/Phobos-dev")]
BOXES = 5
OSD_HOLD = 2.0

# Includes WindowOpenedOrChanged/WorkspaceActiveWindowChanged -- a plain window
# open fires those two, and the tasklist goes stale without them.
RELEVANT = {
    "WindowsChanged",
    "WorkspacesChanged",
    "WindowOpenedOrChanged",
    "WorkspaceActiveWindowChanged",
    "WorkspaceActivated",
    "WorkspaceDeactivated",
    "WindowFocusChanged",
    "WindowFocusTimestampChanged",
}

COALESCE = 0.08


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


def publish(state, last, last_focus, hide_at):
    """Emit the snapshot if it changed, and handle the OSD reveal/hold.
    Returns the new (last, last_focus, hide_at)."""
    if state != last:
        print(json.dumps(state), flush=True)
        last = state

    focus = state["focused"]
    if last_focus is not None and focus != last_focus:
        eww("update", "revealwsosd=true")
        hide_at = time.time() + OSD_HOLD
    return last, focus, hide_at


def main():
    # bufsize=0: a buffered reader hides bytes from select().
    stream = subprocess.Popen(["niri", "msg", "--json", "event-stream"],
                              stdout=subprocess.PIPE, bufsize=0)
    fd = stream.stdout.fileno()
    last = last_focus = None
    hide_at = 0.0
    dirty = False
    quiet_since = 0.0
    pending = b""

    state = snapshot()
    last, last_focus, hide_at = publish(state, last, last_focus, hide_at)

    try:
        while True:
            now = time.time()
            timeout = 0.1
            if hide_at:
                timeout = min(timeout, max(0.0, hide_at - now))
            if dirty:
                timeout = min(timeout, max(0.0, quiet_since + COALESCE - now))

            ready, _, _ = select.select([fd], [], [], timeout)
            if ready:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                pending += chunk
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    try:
                        if set(json.loads(line)) & RELEVANT:
                            dirty = True
                            quiet_since = time.time()
                    except ValueError:
                        pass
                continue

            now = time.time()
            if dirty and now - quiet_since >= COALESCE:
                state = snapshot()
                last, last_focus, hide_at = publish(state, last, last_focus, hide_at)
                dirty = False
            if hide_at and now >= hide_at:
                eww("update", "revealwsosd=false")
                hide_at = 0.0
    except (BrokenPipeError, KeyboardInterrupt):
        pass
    finally:
        stream.kill()


if __name__ == "__main__":
    main()
