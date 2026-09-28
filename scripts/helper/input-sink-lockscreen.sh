#!/usr/bin/env bash

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EWW=(eww -c "$DIR")
kind="${1:-}"
value="${2:-}"

base="$(cat /tmp/phobos-eww-menu-prev 2>/dev/null)"

case "$kind" in
  change)
    raw="${value:${#base}}"
    prev="$(cat /tmp/phobos-eww-lock-prev 2>/dev/null)"
    printf '%s' "$raw" > /tmp/phobos-eww-lock-prev
    input="${raw:0:16}"
    if [[ -z "$input" ]]; then
      action=clear
    elif [[ ${#raw} -lt ${#prev} ]]; then
      action=delete
    else
      action=insert
    fi
    masked="$(printf '%*s' "${#input}" '' | tr ' ' '*')"
    "${EWW[@]}" update \
      screen-lock-input="$input" screen-lock-input-masked="$masked" \
      screen-lock-input-last-action="$action" screen-lock-auth-failed=false
    ;;

  submit)
    raw="${value:${#base}}"
    if [[ "$raw" == "$("${EWW[@]}" get screen-lock-password)" ]]; then
      printf '%s' "$value" > /tmp/phobos-eww-menu-prev
      rm -f /tmp/phobos-eww-lock-prev
      "${EWW[@]}" update screen-locked=false screen-lock-input= \
        screen-lock-input-masked= screen-lock-auth-failed=false
      "$DIR/scripts/powermenu.sh" hide
    else
      "${EWW[@]}" update screen-lock-auth-failed=true
    fi
    ;;
esac
