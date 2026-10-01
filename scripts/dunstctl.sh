#!/usr/bin/env bash
# dunstctl isn't on PATH (niri spawns dunst via full store path).
# Resolve it from the running dunst process; skip if dunst isn't up.
pid=$(pgrep -o dunst) || exit 0
DUNSTCTL="$(dirname "$(readlink -f "/proc/$pid/exe")")/dunstctl"
EWWC=(eww -c "$(cd "$(dirname "$0")/.." && pwd)")

push_dnd() {
    local i
    for ((i = 0; i < 30; i++)); do
        "${EWWC[@]}" update dnd="$("$DUNSTCTL" is-paused)" >/dev/null 2>&1 && return 0
        sleep 1
    done
}

case "$1" in
    set-paused)
        "$DUNSTCTL" "$@" || exit 0
        push_dnd
        ;;
    sync)
        push_dnd
        ;;
    *)
        exec "$DUNSTCTL" "$@"
        ;;
esac
