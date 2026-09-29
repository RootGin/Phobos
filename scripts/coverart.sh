#!/usr/bin/env bash
# --follow blocks and prints on every metadata change, so this is a stream, not a
# poll: it exits only when the followed player goes away, hence the respawn.
while true; do
    playerctl metadata --format '{{ mpris:artUrl }}' -F | while read -r location; do
        echo "${location#file://}"
    done
    sleep 1
done
