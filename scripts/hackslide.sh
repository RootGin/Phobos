#!/usr/bin/env bash

PWD="$HOME/.config/eww/Phobos-dev"

WINDOW="$1"
CTRL="reveal$1"

STAT="$(eww -c $PWD get $CTRL)"
if [[ $STAT == "true" || $2 == "close" ]]; then
    eww -c $PWD update $CTRL=false
    sleep 0.5
    STAT="$(eww -c $PWD get $CTRL)"
    OPEN="$(eww -c $PWD active-windows | grep $WINDOW)"
    if [[ $STAT == "false" && $OPEN ]]; then 
        eww -c $PWD close $WINDOW
    fi
else
    eww -c $PWD open $WINDOW
    eww -c $PWD update $CTRL=true
    if [[ "$WINDOW" == "systemint" ]]; then
        "$PWD/scripts/sysstat-poll.sh" --once
        "$PWD/scripts/vpn.py" status
    fi
fi

