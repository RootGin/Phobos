#!/usr/bin/env python3
"""Notification history table: a dedicated record of every notification.

end-rs has a history too, but it only pushes it to eww while its own window is
open, and its records carry no timestamp -- so it cannot back a table.

There is also no event stream to subscribe to: end-rs never emits the
org.freedesktop.Notifications Notify *signal*, only receives the client method
call, so signal_subscribe sees nothing, and busctl's BecomeMonitor is denied on
this bus. What end-rs does leave behind is its own log, which appends one
timestamped line per arrival carrying the full notification JSON. That log is
the feed; entries are appended to $XDG_STATE_HOME so history survives the
window being closed and the daemon restarting.

Rows are emitted newest-first as one JSON array on stdout, which is what eww's
deflisten wants. Startup seeks to the end of the log: the JSONL is the store, so
replaying the log's history would only duplicate what is already there.
"""

import json
import os
import sys
import time

STATE = os.path.join(os.environ.get("XDG_STATE_HOME",
                                    os.path.expanduser("~/.local/state")),
                     "phobos")
LOG = os.path.join(STATE, "notifications.jsonl")
FEED = "/tmp/end.log"
KEEP = 500
SHOW = 50
BODY_MAX = 400
POLL = 0.4
MARKER = ":notification '"


def esc(text):
    return (str(text).replace("&#34;", '"')
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def notes(line):
    decoder = json.JSONDecoder()
    pos = 0
    while True:
        found = line.find(MARKER, pos)
        if found < 0:
            return
        start = found + len(MARKER)
        try:
            note, pos = decoder.raw_decode(line, start)
        except ValueError:
            return
        yield note


def entries():
    try:
        with open(LOG, encoding="utf-8", errors="replace") as handle:
            rows = [json.loads(line) for line in handle if line.strip()]
    except (FileNotFoundError, ValueError):
        return []
    return rows[-KEEP:][::-1]


def emit():
    sys.stdout.write(json.dumps(entries()[:SHOW]) + "\n")
    sys.stdout.flush()


def parse(line):
    stamp = line[1:line.find("]")]
    rows = []
    for note in notes(line):
        rows.append({
            "id": note.get("id"),
            "t": stamp[11:16] if len(stamp) >= 16 else "",
            "ts": stamp,
            "app": esc(note.get("application", "")),
            "icon": note.get("app_icon", ""),
            "summary": esc(note.get("summary", "")),
            "body": esc(str(note.get("body", ""))[:BODY_MAX]),
            "urgency": note.get("urgency", "normal"),
        })
    return rows


def append(entry):
    os.makedirs(STATE, exist_ok=True)
    if any(row.get("id") == entry["id"] for row in entries()):
        return False
    with open(LOG, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")
    if len(entries()) > KEEP:
        kept = entries()[:KEEP]
        tmp = LOG + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            for row in kept:
                handle.write(json.dumps(row) + "\n")
        os.replace(tmp, LOG)
    return True


def main():
    emit()
    feed = None
    while True:
        if feed is None:
            try:
                feed = open(FEED, encoding="utf-8", errors="replace")
                feed.seek(0, os.SEEK_END)
            except OSError:
                feed = None
        line = feed.readline() if feed else ""
        if not line:
            if feed and os.fstat(feed.fileno()).st_size < feed.tell():
                feed.close()
                feed = None
            time.sleep(POLL)
            continue
        added = [append(entry) for entry in parse(line)]
        if any(added):
            emit()


if __name__ == "__main__":
    main()