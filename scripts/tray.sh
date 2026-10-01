#!/usr/bin/env bash
# Topbar tray button: flip the running-task strip, then spin the icon one turn.
EWW=(eww -c "$(cd "$(dirname "$0")/.." && pwd)")

if [ "$("${EWW[@]}" get trayopen 2>/dev/null)" = true ]; then
    "${EWW[@]}" update trayopen=false >/dev/null 2>&1
else
    "${EWW[@]}" update trayopen=true >/dev/null 2>&1
fi

for ((i = 1; i <= 18; i++)); do
    "${EWW[@]}" update "trayspin=$i" >/dev/null 2>&1
    sleep 0.03
done
"${EWW[@]}" update trayspin=0 >/dev/null 2>&1
