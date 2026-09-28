#!/usr/bin/env bash

DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
EWW=(eww -c "$DIR")

kill_key_reader() {
  [[ -f /tmp/phobos-eww-powermenu-keys.pid ]] || return 0
  kill "$(cat /tmp/phobos-eww-powermenu-keys.pid)" 2>/dev/null
  rm -f /tmp/phobos-eww-powermenu-keys.pid
}

case "${1:-show}" in
  show)
    "$DIR/scripts/helper/check-power-capabilities.sh" >/dev/null 2>&1
    "${EWW[@]}" update \
      revealpowermenu=false screen-locked=false powermenu-button-selected= \
      powermenu-status= screen-lock-input= screen-lock-input-masked= \
      screen-lock-auth-failed=false
    echo powermenu > /tmp/phobos-eww-input-active
    rm -f /tmp/phobos-eww-lock-prev /tmp/phobos-eww-menu-prev
    "${EWW[@]}" close topbar bottombar 2>/dev/null
    "$DIR/scripts/hackslide.sh" powermenu
    kill_key_reader
    nohup "$DIR/scripts/helper/powermenu-keys.py" >/dev/null 2>/tmp/phobos-eww-powermenu-keys.err &
    echo $! > /tmp/phobos-eww-powermenu-keys.pid
    ;;

  hide)
    kill_key_reader
    [[ "$("${EWW[@]}" get revealpowermenu)" == "true" ]] && "$DIR/scripts/hackslide.sh" powermenu
    "${EWW[@]}" open-many topbar bottombar 2>/dev/null
    ;;

  toggle)
    if [[ "$("${EWW[@]}" get revealpowermenu)" == "true" ]]; then
      "$0" hide
    else
      "$0" show
    fi
    ;;
esac
