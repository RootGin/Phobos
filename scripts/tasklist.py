#!/usr/bin/env python3

import json
import os
import select
import subprocess
import time

from iconfetch import fetch

EWW = ["eww", "-c", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))]
SLOTS = 10
BOXES = 5
OSD_HOLD = 2.0
CANVAS_W = 1920
CANVAS_H = 1080

TRANSLATE = {
    "com.github.xournalpp.xournalpp": "xournalpp",
    "sterm": "foot",
    "sranger": "folder",
    "sncmpcpp": "music",
}


def niri(*args):
    try:
        out = subprocess.run(["niri", "msg", "--json", *args],
                             capture_output=True, text=True, timeout=2)
        if out.returncode != 0 or not out.stdout.strip():
            return []
        return json.loads(out.stdout)
    except Exception:
        return []


def workspace_rects(windows):
    """Lay windows out as niri shows them (columns left to right, stacked
    rows top to bottom) and scale to a 1920x1080 canvas so the yuck /5 maths
    still holds."""
    cols = {}
    for w in windows:
        layout = w.get("layout") or {}
        pos = layout.get("pos_in_scrolling_layout") or [1, 1]
        size = layout.get("window_size") or [CANVAS_W, CANVAS_H]
        cols.setdefault(pos[0], []).append({"row": pos[1], "w": w, "size": size})
    if not cols:
        return {}

    order = sorted(cols)
    x = {}
    offset = 0
    for c in order:
        x[c] = offset
        offset += max((it["size"][0] for it in cols[c]), default=CANVAS_W)
    total_w = offset

    total_h = 0
    for c in order:
        y = 0
        for it in sorted(cols[c], key=lambda i: i["row"]):
            it["_x"], it["_y"] = x[c], y
            y += it["size"][1]
        total_h = max(total_h, y)

    scale = min(CANVAS_W / total_w, CANVAS_H / total_h, 1.0) if total_w and total_h else 1.0

    rects = {}
    for c in order:
        for it in cols[c]:
            rects[it["w"]["id"]] = {
                "x": it["_x"] * scale,
                "y": it["_y"] * scale,
                "width": it["size"][0] * scale,
                "height": it["size"][1] * scale,
            }
    return rects


def entry(w, rects, focused_id, idx):
    app_id = (w.get("app_id") or "").lower()
    app_id = TRANSLATE.get(app_id, app_id)
    return {
        "id": w.get("id"),
        "app_id": app_id,
        "name": w.get("title") or app_id,
        "pid": w.get("pid"),
        "focused": w.get("id") == focused_id,
        "rect": rects.get(w.get("id"), {"x": 0, "y": 0, "width": 0, "height": 0}),
        "path": fetch(app_id) or "./assets/icons/file.svg",
        "workspace": idx,
    }


def snapshot():
    workspaces = niri("workspaces")
    windows = niri("windows")
    idx_of = {ws.get("id"): ws.get("idx") for ws in workspaces}
    focused_id = next((w["id"] for w in windows if w.get("is_focused")), None)

    slots = [[] for _ in range(SLOTS)]
    for w in windows:
        idx = idx_of.get(w.get("workspace_id"))
        if not idx or idx < 1 or idx > SLOTS:
            continue
        slots[idx - 1].append(w)

    windowsjson = []
    for i, slot in enumerate(slots):
        rects = workspace_rects(slot)
        windowsjson.append([entry(w, rects, focused_id, i + 1) for w in slot])

    tasklistjson = [e for slot in windowsjson for e in slot]

    counts = {}
    for w in windows:
        wid = w.get("workspace_id")
        counts[wid] = counts.get(wid, 0) + 1

    found = {}
    focused = 1
    for ws in workspaces:
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
    workspacejson = {"workspaces": boxes, "focused": focused - 1}

    return windowsjson, tasklistjson, workspacejson


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


def eww(*args):
    subprocess.run(EWW + list(args),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    stream = subprocess.Popen(["niri", "msg", "--json", "event-stream"],
                              stdout=subprocess.PIPE, bufsize=0)
    fd = stream.stdout.fileno()
    last = None
    last_focus = None
    hide_at = 0.0
    dirty = False
    quiet_since = 0.0
    pending = b""

    def publish():
        nonlocal last, last_focus, hide_at
        windowsjson, tasklistjson, workspacejson = snapshot()
        payload = json.dumps(workspacejson)
        if payload != last:
            print(payload, flush=True)
            last = payload
            eww("update",
                "windowsjson=" + json.dumps(windowsjson),
                "tasklistjson=" + json.dumps(tasklistjson))

        focus = workspacejson["focused"]
        if last_focus is not None and focus != last_focus:
            eww("update", "revealwsosd=true")
            hide_at = time.time() + OSD_HOLD
        last_focus = focus

    publish()

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
                publish()
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
