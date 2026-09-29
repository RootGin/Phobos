#!/usr/bin/env bash
# Volume only. Brightness used to ride along here, but it is a udev `backlight`
# event source now (scripts/brightness-watch.sh) — a 2s poll would redraw the bar
# and its 3-state icon for nothing.
CFG="$(cd "$(dirname "$0")/.." && pwd)"
EWW=(eww -c "$CFG")

while true; do
    vol="$("$CFG/scripts/volume-status.sh" 2>/dev/null)"
    [[ "$vol" == \{* ]] || vol='{"volume": 0, "volumemute": false}'

    "${EWW[@]}" update volumejson="$vol" >/dev/null 2>&1

    sleep 2
done
