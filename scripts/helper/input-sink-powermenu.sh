#!/usr/bin/env bash

kind="${1:-}"
value="${2:-}"

case "$kind" in
  change) printf '%s' "$value" > /tmp/phobos-eww-menu-prev ;;
esac
