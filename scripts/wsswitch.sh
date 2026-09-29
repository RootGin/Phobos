#!/usr/bin/env bash
# Switch to a niri workspace. The eww workspace OSD is revealed by
# scripts/tasklist.py whenever the focused workspace changes, so this is
# just the focus command (bind it in niri if you want it).
niri msg action focus-workspace "$1"
