#!/usr/bin/env bash
# One wpctl call for both volume fields, replacing two separate 2s defpoll's
# that each shelled out to `wpctl get-volume`.
raw="$(wpctl get-volume @DEFAULT_AUDIO_SINK@)"
pct="$(printf '%s' "$raw" | awk '{print int($NF*100)}')"
if printf '%s' "$raw" | grep -q 'MUTED'; then muted=true; else muted=false; fi
printf '{"volume": %s, "volumemute": %s}\n' "$pct" "$muted"
