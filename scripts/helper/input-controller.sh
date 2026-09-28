#!/usr/bin/env bash

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
kind="${1:-}"
value="${2:-}"

sink="$(cat /tmp/phobos-eww-input-active 2>/dev/null)"
case "$sink" in powermenu|lockscreen) ;; *) exit 0 ;; esac

printf '%s\t%s\n' "$kind" "$value" > "/tmp/phobos-eww-input-pipe-$sink"
