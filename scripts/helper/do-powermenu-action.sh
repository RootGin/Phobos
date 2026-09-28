#!/usr/bin/env bash

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EWW=(eww -c "$DIR")
action="${1:-}"
click="${2:-}"

kill-key-reader() {
  [[ -f /tmp/phobos-eww-powermenu-keys.pid ]] || return 0
  kill "$(cat /tmp/phobos-eww-powermenu-keys.pid)" 2>/dev/null
  rm -f /tmp/phobos-eww-powermenu-keys.pid
}

enter_lock() {
  kill-key-reader
  "${EWW[@]}" update \
    screen-locked=true powermenu-button-selected= powermenu-status= \
    screen-lock-input= screen-lock-input-masked= \
    screen-lock-input-last-action=clear screen-lock-auth-failed=false
  echo lockscreen > /tmp/phobos-eww-input-active
  rm -f /tmp/phobos-eww-lock-prev
}

run() {
  case "$1" in
    poweroff)  systemctl poweroff  || loginctl poweroff ;;
    reboot)    systemctl reboot    || loginctl reboot ;;
    suspend)   "$DIR/scripts/powermenu.sh" hide; systemctl suspend ;;
    hibernate) "$DIR/scripts/powermenu.sh" hide; systemctl hibernate ;;
    exit)      niri msg action quit ;;
    lock)      enter_lock ;;
  esac
}

case "$action" in
  confirm)
    sel="$("${EWW[@]}" get powermenu-button-selected)"
    [[ -n "$sel" ]] && exec "$DIR/scripts/helper/do-powermenu-action.sh" "$sel" click
    ;;

  clear)
    "${EWW[@]}" update powermenu-button-selected= powermenu-status=
    ;;

  nav)
    order=(poweroff reboot suspend hibernate exit lock)
    dir="${2:-down}"
    cur="$("${EWW[@]}" get powermenu-button-selected)"
    enabled=()
    for a in "${order[@]}"; do
      [[ "$("${EWW[@]}" get "power-can-$a" 2>/dev/null)" == "false" ]] || enabled+=("$a")
    done
    ((${#enabled[@]})) || exit 0
    idx=-1
    for i in "${!enabled[@]}"; do
      [[ "${enabled[$i]}" == "$cur" ]] && idx=$i
    done
    if ((idx < 0)); then
      if [[ "$dir" == up ]]; then idx=$((${#enabled[@]} - 1)); else idx=0; fi
    elif [[ "$dir" == up ]]; then
      idx=$(( (idx - 1 + ${#enabled[@]}) % ${#enabled[@]} ))
    else
      idx=$(( (idx + 1) % ${#enabled[@]} ))
    fi
    sel="${enabled[$idx]}"
    "${EWW[@]}" update powermenu-button-selected="$sel" \
      powermenu-status="$sel armed — press again to confirm"
    ;;

  poweroff|reboot|suspend|hibernate|exit|lock)
    if [[ "$("${EWW[@]}" get "power-can-$action" 2>/dev/null)" == "false" ]]; then
      reason="$("${EWW[@]}" get "power-reason-$action" 2>/dev/null)"
      [[ -n "$reason" ]] || reason="$action is disabled"
      "${EWW[@]}" update powermenu-status="$reason"
      [[ "$click" == click ]] && notify-send -a "powermenu" "${action^} unavailable" "$reason" 2>/dev/null
      exit 0
    fi
    if [[ "$click" == click && "$action" == "$("${EWW[@]}" get powermenu-button-selected)" ]]; then
      run "$action"
    else
      "${EWW[@]}" update powermenu-button-selected="$action" \
        powermenu-status="$action armed — press again to confirm"
    fi
    ;;

  *)
    "${EWW[@]}" update powermenu-button-selected= powermenu-status=
    ;;
esac
