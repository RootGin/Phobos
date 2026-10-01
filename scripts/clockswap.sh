#!/usr/bin/env bash
# Flip the topbar clock between time and date.
EWW=(eww -c "$(cd "$(dirname "$0")/.." && pwd)")

if [ "$("${EWW[@]}" get showdate 2>/dev/null)" = true ]; then
    "${EWW[@]}" update showdate=false >/dev/null 2>&1
else
    "${EWW[@]}" update showdate=true >/dev/null 2>&1
fi