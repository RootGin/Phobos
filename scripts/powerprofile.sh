#!/usr/bin/env bash
# The panel's power-profile control. `auto` is applied by us, not left to the
# daemon: PPD only follows AC transitions when it happens to start after
# upower, and its unit declares no such dependency, so on a normal boot it never
# sees the plug event. `watch` follows AC over udev and re-applies the profile.

EWW="${EWW_CMD:-eww -c $(cd "$(dirname "$0")/.." && pwd)}"
SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
LOCK=/tmp/phobos-powerprofile.lock

on_ac() {
    local d
    for d in /sys/class/power_supply/*/; do
        [ "$(cat "$d/type" 2>/dev/null)" = Mains ] || continue
        [ "$(cat "$d/online" 2>/dev/null)" = 1 ] && return 0
    done
    return 1
}

push() { $EWW update "$@" >/dev/null 2>&1 & disown; }

# every command but `watch` takes the lock, so a cycle/auto click can't interleave
# with the watcher's re-apply; `watch` would otherwise hold it for its whole life
[ "$1" = watch ] || { exec 9>"$LOCK"; flock 9; }

# a no-op unless auto is on, so a manual `cycle` still sticks
follow_ac() {
    powerprofilesctl query-battery-aware | grep -q True || return 0
    if on_ac; then want=performance; else want=power-saver; fi
    [ "$(powerprofilesctl get)" = "$want" ] && return 0
    powerprofilesctl set "$want" && push powerprofile="$want"
}

case "$1" in
    watch)
        while true; do
            last=$(on_ac && echo 1 || echo 0)
            "$SELF" follow-ac
            udevadm monitor --subsystem-match=power_supply 2>/dev/null |
            while read -r line; do
                case "$line" in *power_supply*) ;; *) continue ;; esac
                sleep 1
                now=$(on_ac && echo 1 || echo 0)
                [ "$now" = "$last" ] && continue
                last=$now
                "$SELF" follow-ac
            done
        done
        ;;
    follow-ac)
        follow_ac
        ;;
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
