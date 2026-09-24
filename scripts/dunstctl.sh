#!/usr/bin/env bash
# dunstctl isn't on PATH (niri spawns dunst via full store path).
# Resolve it from the running dunst process; skip if dunst isn't up.
pid=$(pgrep -o dunst) || exit 0
exec "$(dirname "$(readlink -f "/proc/$pid/exe")")/dunstctl" "$@"