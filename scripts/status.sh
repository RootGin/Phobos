#!/usr/bin/env bash

CFG="$HOME/.config/eww/Phobos-dev"
DIR="$(cd "$(dirname "$0")" && pwd)"

while true; do
    vol="$("$DIR/volume-status.sh" 2>/dev/null)"
    [[ "$vol" == \{* ]] || vol='{"volume": 0, "volumemute": false}'

    bright="$(brightnessctl -m 2>/dev/null | awk -F, '{print $4}' | tr -d '%')"
    [[ "$bright" =~ ^[0-9]+$ ]] || bright=0

    bt="$("$DIR/bluetooth.sh" --con_status 2>/dev/null)"
    [[ -n "$bt" ]] || bt=disconnected

    dnd="$("$DIR/dunstctl.sh" is-paused 2>/dev/null)"
    [[ "$dnd" == true || "$dnd" == false ]] || dnd=false

    eww -c "$CFG" update \
        volumejson="$vol" \
        brightness="$bright" \
        bluetooth="$bt" \
        dnd="$dnd" >/dev/null 2>&1

    sleep 2
done
