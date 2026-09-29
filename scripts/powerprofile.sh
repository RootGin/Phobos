#!/usr/bin/env bash
# cycle:  power-saver -> balanced -> performance -> power-saver
# auto:   toggle battery-aware (saver on battery, performance on AC)
# sync:   push current state into eww (called once at daemon start)
# No args: print active profile.
#
# The lock is load-bearing, not defensive: cycle and auto are read-modify-write
# (read current state -> decide next -> write), so two rapid clicks would both
# read the same value, compute the same next step, and collapse into one step's
# worth of progress. Same flock pattern as scripts/helper/input-buffer.sh.
exec 9>/tmp/phobos-powerprofile.lock
flock 9

# Push the value the daemon actually accepted (re-read after the write), never
# the one we intended: powerprofilesctl exits non-zero on a rejected set
# ("battery_aware is already set to FALSE"), and the UI must never show a state
# the daemon refused. Commands stay synchronous for the same reason.
EWW="${EWW_CMD:-eww -c $HOME/.config/eww/Phobos-dev}"

case "$1" in
  sync)
    $EWW update powerprofile="$(powerprofilesctl get)"
    if powerprofilesctl query-battery-aware | grep -q True; then
      $EWW update powerauto=true
    else
      $EWW update powerauto=false
    fi
    ;;
  cycle)
    case "$(powerprofilesctl get)" in
      power-saver) set=balanced ;;
      balanced)    set=performance ;;
      *)           set=power-saver ;;
    esac
    if powerprofilesctl set "$set"; then
      $EWW update powerprofile="$set"
    fi
    ;;
  auto)
    if powerprofilesctl query-battery-aware | grep -q True; then
      powerprofilesctl configure-battery-aware --disable \
        && $EWW update powerauto=false
    else
      powerprofilesctl configure-battery-aware --enable \
        && $EWW update powerauto=true
    fi
    ;;
esac
powerprofilesctl get
