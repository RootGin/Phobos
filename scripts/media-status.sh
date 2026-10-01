#!/usr/bin/env bash
# Volume only. Brightness is a defpoll in eww.yuck and nothing outside eww
# mutates it, so it needs no seeder here.
CFG="$(cd "$(dirname "$0")/.." && pwd)"
EWW=(eww -c "$CFG")

while true; do
    vol="$("$CFG/scripts/volume-status.sh" 2>/dev/null)"
    [[ "$vol" == \{* ]] || vol='{"volume": 0, "volumemute": false}'

    "${EWW[@]}" update volumejson="$vol" >/dev/null 2>&1

    sleep 2
done
