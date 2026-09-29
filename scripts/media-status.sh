#!/usr/bin/env bash

CFG="$(cd "$(dirname "$0")/.." && pwd)"
EWW=(eww -c "$CFG")

while true; do
    vol="$("$CFG/scripts/volume-status.sh" 2>/dev/null)"
    [[ "$vol" == \{* ]] || vol='{"volume": 0, "volumemute": false}'

    bright="$(brightnessctl -m 2>/dev/null | awk -F, '{print $4}' | tr -d '%')"
    [[ "$bright" =~ ^[0-9]+$ ]] || bright=0

    "${EWW[@]}" update volumejson="$vol" brightness="$bright" >/dev/null 2>&1

    sleep 2
done
