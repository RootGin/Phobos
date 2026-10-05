#!/usr/bin/env bash
STATE="${XDG_STATE_HOME:-$HOME/.local/state}/phobos/dnd"
EWWC=(eww -c "$(cd "$(dirname "$0")/.." && pwd)")

dnd_state() {
    [ -f "$STATE" ] && cat "$STATE" || echo false
}

push_dnd() {
    local i state
    state=$(dnd_state)
    for ((i = 0; i < 30; i++)); do
        "${EWWC[@]}" update dnd="$state" >/dev/null 2>&1 && return 0
        sleep 1
    done
}

set_dnd() {
    mkdir -p "$(dirname "$STATE")"
    case "$1" in
        true|on|1)  echo true > "$STATE" ;;
        false|off|0) echo false > "$STATE" ;;
        toggle)
            if [ "$(dnd_state)" = true ]; then echo false > "$STATE"; else echo true > "$STATE"; fi
            ;;
        *) echo "endctl: bad dnd value: $1" >&2; return 1 ;;
    esac
    push_dnd
    [ "$(dnd_state)" = true ] && "${EWWC[@]}" update end-notifications='' >/dev/null 2>&1
    return 0
}

case "$1" in
    dnd-status)
        dnd_state
        ;;
    dnd-set)     set_dnd "$2" ;;
    dnd-toggle)  set_dnd toggle ;;
    close)       exec end-rs close "$2" ;;
    action)      exec end-rs action "$2" "$3" ;;
    history)     exec end-rs history "$2" ;;
    sync)        push_dnd ;;
    *)           exec end-rs "$@" ;;
esac
