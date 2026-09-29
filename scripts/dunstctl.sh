#!/usr/bin/env bash
# dunstctl isn't on PATH (niri spawns dunst via full store path).
# Resolve it from the running dunst process; skip if dunst isn't up.
pid=$(pgrep -o dunst) || exit 0
DUNSTCTL="$(dirname "$(readlink -f "/proc/$pid/exe")")/dunstctl"

if [ "$1" == "set-paused" ]; then
    "$DUNSTCTL" "$@" || exit 0
    eww -c "$(cd "$(dirname "$0")/.." && pwd)" update dnd="$("$DUNSTCTL" is-paused)" >/dev/null 2>&1
else
    exec "$DUNSTCTL" "$@"
fi
