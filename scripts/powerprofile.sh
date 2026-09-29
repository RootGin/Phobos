#!/usr/bin/env bash

exec 9>/tmp/phobos-powerprofile.lock
flock 9

EWW="${EWW_CMD:-eww -c $(cd "$(dirname "$0")/.." && pwd)}"

on_ac() {
    local d
    for d in /sys/class/power_supply/*/; do
        [ "$(cat "$d/type" 2>/dev/null)" = Mains ] || continue
        [ "$(cat "$d/online" 2>/dev/null)" = 1 ] && return 0
    done
    return 1
}

push() { $EWW update "$@" >/dev/null 2>&1 & disown; }

case "$1" in
    cycle)
        case "$(powerprofilesctl get)" in
            power-saver) set=balanced ;;
            balanced) set=performance ;;
            *) set=power-saver ;;
        esac
        if powerprofilesctl set "$set"; then
            push powerprofile="$set"
        fi
        ;;
    auto)
        if powerprofilesctl query-battery-aware | grep -q True; then
            powerprofilesctl configure-battery-aware --disable && push powerauto=false
        else
            powerprofilesctl configure-battery-aware --enable && push powerauto=true
            if on_ac; then want=performance; else want=power-saver; fi
            if powerprofilesctl set "$want"; then push powerprofile="$want"; fi
        fi
        ;;
    sync)
        push powerprofile="$(powerprofilesctl get)"
        if powerprofilesctl query-battery-aware | grep -q True; then
            push powerauto=true
        else
            push powerauto=false
        fi
        ;;
esac
powerprofilesctl get
