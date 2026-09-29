#!/usr/bin/env bash
# One-shot seeder for the two values nothing outside eww mutates: dnd and
# bluetooth. Both are pushed on click, so they only need seeding at startup
# to reflect the state the machine booted into.

DIR="$(cd "$(dirname "$0")" && pwd)"
EWW=(eww -c "$HOME/.config/eww/Phobos-dev")

dnd="$("$DIR/dunstctl.sh" is-paused 2>/dev/null)"
[[ "$dnd" == true || "$dnd" == false ]] || dnd=false

bt="$("$DIR/bluetooth.sh" --con_status 2>/dev/null)"
[[ "$bt" == connected || "$bt" == disabled ]] || bt=disabled

"${EWW[@]}" update dnd="$dnd" bluetooth="$bt" >/dev/null 2>&1
