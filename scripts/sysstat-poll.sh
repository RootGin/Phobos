#!/usr/bin/env bash
# Drives the panel's stat readings, but only while they are on screen. eww's
# :interval scheduler does not fire in this build (see commit ec7e620), so the
# loop lives here and the visibility gate is checked in-shell instead of by
# :run-while. Nothing here runs when the panel is closed.

CFG="$(cd "$(dirname "$0")/.." && pwd)"
EWW=(eww -c "$CFG")

tick() {
    [[ "$("${EWW[@]}" get revealsystemint 2>/dev/null)" == "true" ]] || return
    [[ "$("${EWW[@]}" get sysect 2>/dev/null)" == "0" ]] || return
    "${EWW[@]}" update sysstat="$("$CFG/scripts/sysstat.py")" >/dev/null 2>&1
}

tick_disk() {
    [[ "$("${EWW[@]}" get revealsystemint 2>/dev/null)" == "true" ]] || return
    [[ "$("${EWW[@]}" get sysect 2>/dev/null)" == "0" ]] || return
    "${EWW[@]}" update diskstat="$("$CFG/scripts/diskstat.py")" >/dev/null 2>&1
}

while true; do
    tick
    sleep 2
    tick_disk
    sleep 13
done
