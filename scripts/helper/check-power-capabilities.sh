#!/usr/bin/env bash

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EWW=(eww -c "$DIR")

login1() {
  busctl call org.freedesktop.login1 /org/freedesktop/login1 \
    org.freedesktop.login1.Manager "$1" 2>/dev/null
}
can() {
  local r; r="$(login1 "$1")"
  [[ "$r" == *'"yes"'* || "$r" == *'"challenge"'* ]] && echo true || echo false
}

suspend="$(can CanSuspend)"
hibernate="$(can CanHibernate)"

reason_suspend=""
[[ "$suspend" == false ]] && reason_suspend="suspend unavailable — logind reports no"

reason_hibernate=""
if [[ "$hibernate" == false ]]; then
  if ! swapon --show 2>/dev/null | grep -q .; then
    reason_hibernate="hibernate unavailable — no swap space"
  else
    reason_hibernate="hibernate unavailable — logind reports no"
  fi
fi

"${EWW[@]}" update \
  power-can-poweroff="$(can CanPowerOff)" \
  power-can-reboot="$(can CanReboot)" \
  power-can-suspend="$suspend" \
  power-can-hibernate="$hibernate" \
  power-reason-suspend="$reason_suspend" \
  power-reason-hibernate="$reason_hibernate"
echo ok
