#!/usr/bin/env bash
# Night light toggle for the system panel's brightness row.
#
# gammastep has no usable one-shot mode here: `-o` still blocks instead of
# exiting, and `-m drm` fails outright (no /dev/dri/card0, and the eDP panel
# exposes no sysfs gamma). Only `-m wayland` works, against niri's
# zwlr_gamma_control_manager_v1.
#
# So "off" means killing the process, not `gammastep -x`: wlr-gamma-control
# restores the original ramp when its last client disconnects. The state file
# is ours alone -- gammastep writes none of its own in one-shot manual mode --
# and doubles as the pidfile, so status is just "is that pid alive".
#
# `status` is a one-shot seed for the deflisten (the value sticks in eww until
# reload, so nothing needs to poll it); on/off/toggle push the new value
# themselves, since the click already knows the answer.
STATE="${XDG_STATE_HOME:-$HOME/.local/state}/phobos/nightlight"
TEMP=4000
EWWC=(eww -c "$(cd "$(dirname "$0")/.." && pwd)")

running() {
    local pid
    [ -f "$STATE" ] || return 1
    pid=$(cat "$STATE") || return 1
    [ -n "$pid" ] && [ -d "/proc/$pid" ] && grep -qa gammastep "/proc/$pid/cmdline"
}

on() {
    mkdir -p "$(dirname "$STATE")"
    running && return 0
    setsid gammastep -m wayland -O "$TEMP" -r >/dev/null 2>&1 </dev/null &
    echo $! > "$STATE"
}

off() {
    if running; then
        kill "$(cat "$STATE")" 2>/dev/null
        sleep 0.3
        kill -9 "$(cat "$STATE")" 2>/dev/null
    fi
    rm -f "$STATE"
}

state() {
    running && echo true || echo false
}

push() {
    "${EWWC[@]}" update nightlight="$(state)" >/dev/null 2>&1
}

case "$1" in
    status) state ;;
    on)     on;  push ;;
    off)    off; push ;;
    toggle) running && off || on; push ;;
    temp)   echo "$TEMP" ;;
    *)      echo "nightlight: unknown command '$1'" >&2; exit 1 ;;
esac
