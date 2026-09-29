#!/usr/bin/env bash
# No args: print active profile.
# cycle:  power-saver -> balanced -> performance -> power-saver
# auto:   toggle battery-aware (saver on battery, performance on AC)
# Prints the active profile either way, so a click can also be the poll's data source.
case "$1" in
  cycle)
    case "$(powerprofilesctl get)" in
      power-saver) set=balanced ;;
      balanced)    set=performance ;;
      *)           set=power-saver ;;
    esac
    powerprofilesctl set "$set"
    ;;
  auto)
    if powerprofilesctl query-battery-aware | grep -q True; then
      powerprofilesctl configure-battery-aware --disable
    else
      powerprofilesctl configure-battery-aware --enable
    fi
    ;;
esac
powerprofilesctl get
