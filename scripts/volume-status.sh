#!/usr/bin/env bash
# $2 is the level and $3 is "[MUTED]" when muted, so taking $NF reads the flag
# instead of the level and every muted sink reports 0%. Anchor on $2.
raw="$(wpctl get-volume @DEFAULT_AUDIO_SINK@)"
pct="$(printf '%s' "$raw" | awk '{print int($2*100)}')"
if printf '%s' "$raw" | grep -q 'MUTED'; then muted=true; else muted=false; fi
printf '{"volume": %s, "volumemute": %s}\n' "$pct" "$muted"
