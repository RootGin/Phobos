#!/usr/bin/env bash
# cycle:  power-saver -> balanced -> performance -> power-saver
# auto:   toggle battery-aware (saver on battery, performance on AC)
# sync:   push current state into eww (called once at daemon start)
# No args: print active profile.
#
# Both onclicks run this via `setsid -f`, so the click returns immediately and
# eww's 200ms command timeout cannot kill it part-way. (powerprofilesctl is a
# Python D-Bus client; startup plus the round-trip is ~500-750ms, comfortably
# past that limit, which is why the click used to die with a BrokenPipeError.)
exec 9>/tmp/phobos-powerprofile.lock
flock 9

# Resolve the config from $0 rather than $HOME. Absolute too, since the click
# may run with an unexpected cwd.
EWW="${EWW_CMD:-eww -c $(cd "$(dirname "$0")/.." && pwd)}"

# True when a mains adapter is connected. power-profiles-daemon's battery-aware
# mode only reacts to AC/battery *events*, so enabling it does not re-evaluate
# the state you are in right now -- it leaves you on power-saver while plugged
# in. So on enable, apply the profile for the current AC state.
on_ac() {
  local d
  for d in /sys/class/power_supply/*/; do
    [ "$(cat "$d/type" 2>/dev/null)" = Mains ] || continue
    [ "$(cat "$d/online" 2>/dev/null)" = 1 ] && return 0
  done
  return 1
}

# Detached so this never blocks (or is killed by) the click handler.
push() { $EWW update "$@" >/dev/null 2>&1 & disown; }

case "$1" in
  cycle)
    case "$(powerprofilesctl get)" in
      power-saver) set=balanced ;;
      balanced)    set=performance ;;
      *)           set=power-saver ;;
    esac
    if powerprofilesctl set "$set"; then
      push powerprofile="$set"
    fi
    ;;
  auto)
    if powerprofilesctl query-battery-aware | grep -q True; then
      powerprofilesctl configure-battery-aware --disable && push powerauto=false
    else
      powerprofilesctl configure-battery-aware --enable && push powerauto=true
      if on_ac; then want=performance; else want=power-saver; fi
      if powerprofilesctl set "$want"; then push powerprofile="$want"; fi
    fi
    ;;
  sync)
    push powerprofile="$(powerprofilesctl get)"
    if powerprofilesctl query-battery-aware | grep -q True; then
      push powerauto=true
    else
      push powerauto=false
    fi
    ;;
esac
powerprofilesctl get
