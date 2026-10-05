#!/usr/bin/env bash
# Toggle the notification history panel, closing whatever else is open first.
#
# hackslide.sh tears the window down on close, which kills any deflisten/defpoll
# the panel references -- historyint has to keep listening with every panel shut
# (see docs/SESSION.md, the dnd trap), so it is never closed this way. This
# script only moves reveal vars, which collapse a panel to zero width without
# destroying it.
PWD="$HOME/.config/eww/Phobos-dev"
E=(eww -c "$PWD")

if [ "$("${E[@]}" get "$1")" = true ]; then
    "${E[@]}" update "$1=false"
    exit 0
fi

"${E[@]}" update revealsystemint=false revealtasklistint=false \
                  revealbattint=false revealmediaint=false \
                  reveallauncherint=false revealwsosd=false
sleep 0.25
"${E[@]}" update "$1=true"