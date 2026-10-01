#!/usr/bin/env bash
# The panel's power-profile control. `auto` is applied by us, not left to the
# daemon: PPD only follows AC transitions when it happens to start after
# upower, and its unit declares no such dependency, so on a normal boot it never
# sees the plug event. `watch` follows AC over udev and re-applies the profile.
# PPD keeps no battery-aware setting across reboots, so `sync` reads the user's
# intent from $AUTO_FILE and re-enables it.

EWW="${EWW_CMD:-eww -c $(cd "$(dirname "$0")/.." && pwd)}"
SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
LOCK=/tmp/phobos-powerprofile.lock
AUTO_FILE="$HOME/.local/state/phobos/powerauto"

on_ac() {
    local d
    for d in /sys/class/power_supply/*/; do
        [ "$(cat "$d/type" 2>/dev/null)" = Mains ] || continue
        [ "$(cat "$d/online" 2>/dev/null)" = 1 ] && return 0
    done
    return 1
}

auto_on() {
    if [ -f "$AUTO_FILE" ]; then
        [ "$(cat "$AUTO_FILE")" = true ]
        return
    fi
    powerprofilesctl query-battery-aware | grep -q True
}

remember() {
    mkdir -p "$(dirname "$AUTO_FILE")"
    printf '%s\n' "$1" >"$AUTO_FILE"
}

push() {
    local i
    for ((i = 0; i < 30; i++)); do
        $EWW update "$@" >/dev/null 2>&1 && return 0
        sleep 1
    done
}

# every command but `watch` takes the lock, so a cycle/auto click can't interleave
# with the watcher's re-apply; `watch` would otherwise hold it for its whole life
case "$1" in watch | sync) ;; *) exec 9>"$LOCK"; flock 9 ;; esac

# idempotent: re-applies the profile auto implies, and republishes both vars
follow_ac() {
    if auto_on; then
        powerprofilesctl configure-battery-aware --enable 2>/dev/null
        if on_ac; then want=performance; else want=power-saver; fi
        [ "$(powerprofilesctl get)" = "$want" ] || powerprofilesctl set "$want"
        push powerauto=true powerprofile="$(powerprofilesctl get)"
    else
        push powerauto=false
    fi
}

case "$1" in
    watch)
        "$SELF" follow-ac
        while true; do
            udevadm monitor --subsystem-match=power_supply 2>/dev/null |
            while read -r line; do
                case "$line" in *power_supply*) ;; *) continue ;; esac
                sleep 1
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
        if auto_on; then
            powerprofilesctl configure-battery-aware --disable 2>/dev/null
            remember false
            push powerauto=false
        else
            powerprofilesctl configure-battery-aware --enable 2>/dev/null
            remember true
            if on_ac; then want=performance; else want=power-saver; fi
            powerprofilesctl set "$want"
            push powerauto=true powerprofile="$want"
        fi
        ;;
    sync)
        "$SELF" follow-ac
        ;;
esac
powerprofilesctl get
