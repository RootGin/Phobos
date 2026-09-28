#!/usr/bin/env bash

exec 9>"${TMPDIR:-/tmp}/phobos-eww-input-buffer.lock"
flock -n 9 || exit 0

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

for sink in powermenu lockscreen; do
  pipe="/tmp/phobos-eww-input-pipe-$sink"
  [[ -p "$pipe" ]] || { rm -f "$pipe"; mkfifo "$pipe"; }
  (
    while true; do
      while IFS=$'\t' read -r kind value; do
        "$DIR/scripts/helper/input-sink-$sink.sh" "$kind" "$value"
      done < "$pipe"
    done
  ) &
done

wait
