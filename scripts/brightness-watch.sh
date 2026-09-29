#!/usr/bin/env bash
# Streams brightness on change instead of polling it. The backlight is a sysfs
# device, so udev fires a `backlight` uevent on every write to
# /sys/class/backlight/*/brightness — that is the event source (brightnessctl 0.5
# has no -w, and inotifywait isn't installed). Emits the same bare percentage the
# slider binds, so eww gets one value per real change.
CFG="$(cd "$(dirname "$0")/.." && pwd)"
EWW=(eww -c "$CFG")

read_pct() {
    brightnessctl -m 2>/dev/null | awk -F, '{print $4}' | tr -d '%'
}

emit() {
    local b
    b="$(read_pct)"
    [[ "$b" =~ ^[0-9]+$ ]] || return 0
    "${EWW[@]}" update brightness="$b" >/dev/null 2>&1
}

emit
while true; do
    udevadm monitor --subsystem-match=backlight 2>/dev/null |
    while read -r line; do
        case "$line" in *backlight*) ;; *) continue ;; esac
        emit
    done
done
