#!/usr/bin/env bash
# deflisten source for `brightness`: prints the current percentage on start, then
# again on every backlight uevent -- the kernel fires one on each write to
# /sys/class/backlight/*/brightness (brightnessctl 0.5 has no -w, inotifywait
# isn't installed). eww re-runs this on reload, so the first line re-seeds the
# var: no seeder script and no poll.

pct() {
    brightnessctl -m 2>/dev/null | awk -F, '{print $4}' | tr -d '%'
}

emit() {
    local b
    b="$(pct)"
    [[ "$b" =~ ^[0-9]+$ ]] && printf '%s\n' "$b"
}

emit
udevadm monitor --subsystem-match=backlight 2>/dev/null |
while read -r line; do
    case "$line" in *backlight*) emit ;; esac
done