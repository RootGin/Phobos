# Phobos — niri fork

A fork of **[Phobos](https://github.com/Failedex/Phobos)** by
[Failedex](https://github.com/Failedex) — an eww desktop shell built around diagonal
triangle corners, which is the whole visual signature of the upstream rice and is kept here.

This fork re-targets the config from **sway** to **[niri](https://github.com/YaLTeR/niri)**
(Wayland), moves the palette to **Nord**, and rebuilds the two panels that were the weakest
parts upstream (the network manager and the power menu). Original work and the pixel-art
inspiration are upstream's — see their README for that.

Public domain, same as upstream — see [LICENSE](LICENSE).

---

## Requirements

| | |
|---|---|
| Compositor | niri (Wayland) — this config is **niri-only**; the sway/i3 IPC is gone |
| Shell | [eww](https://github.com/elkowar/eww) 0.6.x |
| Font | **Fairfax HD** (the config asks for it by name and will not fall back gracefully) |
| Interpreter | python3 |

CLI tools the `scripts/` layer shells out to:

- `nmcli` — NetworkManager, for the network panel
- `wpctl` — PipeWire/PulseAudio volume
- `brightnessctl` — backlight
- `playerctl` — MPRIS now-playing
- `end-rs` — eww-native notification daemon (DND toggle, history, close)
- `bluetoothctl` — Bluetooth toggle
- `niri msg` — workspaces, window list, focus/quit actions (replaces `swaymsg`/`i3ipc`)

## Running it

```sh
eww -c ~/.config/eww/Phobos-dev open-many barslide topbar bottombar wsosd
```

Those four windows are the whole shell. Everything else — `systemint`, `tasklistint`,
`launcherint`, `mediaint`, `powermenu`, `network` — is opened on demand by
`scripts/hackslide.sh` or by a click in one of the four.

`wsosd` is opened at startup and then deliberately **left open but hidden**: eww 0.6 only runs a
`defpoll`/`deflisten` while an open window references its variable, so keeping that window alive
is what keeps the workspace watcher running.

Wallpaper, borders, keybinds and workspace switching belong to niri — there is no window-manager
binding in this repo.

## Layout

```
eww.yuck / eww.scss      entry points; scss is imported theme-first, then _scale
theme.scss               one line: re-theming is repointing this at another themes/<name>.scss
themes/nord.scss         the palette — $xbg/$xfg and the $x0–$x15 slots, single source of truth
scss/_scale.scss         $scale + dpi(), so every px value scales with the resolution
scss/_octagon.scss       the chamfer mixins: octagon (4 cut corners) and cut2 (2)
yuck/<name>.yuck         one window per file, included from eww.yuck
scss/<name>.scss         style partial mirroring the yuck/ name
yuck/util.yuck           shared chrome widgets (floatwin, subbox, subboxl)
scripts/                 the tools layer: every subprocess this config runs
scripts/helper/          helpers called only by an entry script (powermenu / lockscreen)
assets/icons/            SVG icons
wall/                    wallpapers
```

The split that matters: **yuck is structure, `scripts/` is work.** Widgets never compute
anything themselves; they display what a script told them.

## What this fork changes

- **sway → niri.** Every `swaymsg` / `i3ipc` call is now `niri msg`: `action focus-workspace`
  for the workspace keys, `action quit` for the log-out action, and `niri msg --json workspaces` /
  `windows` for the tasklist and workspace OSD. Nothing in this repo binds a window manager; niri
  owns that.
- **Palette → Nord**, extracted into `themes/nord.scss` so the whole shell can be re-themed by
  editing one file. Upstream's colours were a bespoke palette; this is Polar Night / Snow Storm /
  Frost / Aurora.
- **Resolution scaling.** `scss/_scale.scss` defines `$scale` and a `dpi()` function; every `px`
  in every partial goes through it, so a 1440p screen is a one-line change instead of a sweep.
- **Network Manager rewritten** (`yuck/network.yuck` + `scripts/wifi.py`): an available-networks
  list with a detail/connect panel, driven by `nmcli` through one script
  (`connect` / `disconnect` / `rescan` / `getpass`) instead of inline shell in the click handler.
- **Power menu + lockscreen** (`scripts/powermenu.sh`): six actions — poweroff, reboot, suspend,
  hibernate, log out, lock — plus a lockscreen that arms and then confirms. Every action is gated
  on what logind reports the machine can actually do
  (`scripts/helper/check-power-capabilities.sh` queries `org.freedesktop.login1`), so you never
  get a dead button. niri has no runtime binding modes and eww 0.6 has no raw key events, so while
  the menu is open `scripts/helper/powermenu-keys.py` reads the keyboard event devices directly
  for Esc / arrows / Enter — without grabbing them, so nothing outside the menu is affected.
- **The chamfer motif extended.** Upstream cuts corners with border triangles; this fork also
  cuts the corners of *filled* cards with quadrant gradients (`octagon` for four corners,
  `cut2` for the two-corner window silhouette), because GTK3 has no `clip-path`.

## Versioning

The `version` variable in `eww.yuck` is shown in the topbar and is incremented per change, the
same convention upstream uses. It is not a package version — there is nothing to install.
