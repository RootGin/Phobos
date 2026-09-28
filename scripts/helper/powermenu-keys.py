#!/usr/bin/env python3
"""Passive keyboard reader for the powermenu (niri + eww 0.6.0).

Neither niri (no runtime binding modes) nor eww 0.6.0 (no raw key events) can
give the menu Escape / arrow keys. So while the menu is open we read the
keyboard event devices directly and drive eww from here.

It does NOT grab the device (no EVIOCGRAB): the compositor still receives every
key, so nothing outside the menu is affected. It is started by
`powermenu.sh show`, killed on `powermenu.sh hide` and when the screen locks
(`do-powermenu-action.sh enter_lock`) — so it only ever sees keys meant for the
menu (the window holds exclusive keyboard focus while open).

Keys: Esc / Caps-as-Esc (your `caps:escape`) = cancel, Up/Down (or Tab/Shift+Tab)
= move selection, Enter = confirm.
"""
import glob
import os
import select
import struct
import subprocess
import sys

DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

EV_KEY = 0x01
RELEASE, PRESS = 0, 1

KEY_ESC = 1
KEY_TAB = 15
KEY_ENTER = 28
KEY_LEFTSHIFT = 42
KEY_RIGHTSHIFT = 54
KEY_CAPSLOCK = 58
KEY_KPENTER = 96
KEY_UP = 103
KEY_DOWN = 108

_EVENT = struct.Struct("<qqHHi")

def kbd_devices():
    """All readable input event devices. We filter to our key codes while
    reading, so mice/lid/power devices are harmless; enumerating every event
    node (not just `*-event-kbd` by-path links) also picks up virtual keyboards
    and avoids depending on udev's by-path naming."""
    return sorted(glob.glob("/dev/input/event*"))

def key_action(code, shift):
    """Map a pressed key code to an action, or None if it's not ours."""
    if code in (KEY_ESC, KEY_CAPSLOCK):
        return ("cancel", None)
    if code == KEY_UP:
        return ("nav", "up")
    if code == KEY_DOWN:
        return ("nav", "down")
    if code == KEY_TAB:
        return ("nav", "up" if shift else "down")
    if code in (KEY_ENTER, KEY_KPENTER):
        return ("confirm", None)
    return None

def act(*args):
    subprocess.run(
        [os.path.join(DIR, "scripts", "helper", "do-powermenu-action.sh"), *args],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

def cancel():
    subprocess.run(
        [os.path.join(DIR, "scripts", "powermenu.sh"), "hide"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

def main():
    fds = []
    for dev in kbd_devices():
        try:
            fds.append(os.open(dev, os.O_RDONLY | os.O_NONBLOCK))
        except OSError:
            pass
    if not fds:
        print("powermenu-keys: no readable keyboard devices", file=sys.stderr)
        return 1

    shift = False
    while True:
        try:
            ready, _, _ = select.select(fds, [], [])
        except (OSError, ValueError):
            break
        for fd in ready:
            try:
                data = os.read(fd, _EVENT.size * 64)
            except OSError:
                continue
            for off in range(0, len(data) - _EVENT.size + 1, _EVENT.size):
                _, _, etype, code, value = _EVENT.unpack_from(data, off)
                if etype != EV_KEY:
                    continue
                if code in (KEY_LEFTSHIFT, KEY_RIGHTSHIFT):
                    shift = value == PRESS
                    continue
                if value != PRESS:
                    continue
                action = key_action(code, shift)
                if action is None:
                    continue
                kind, arg = action
                if kind == "cancel":
                    cancel()
                    return 0
                if kind == "nav":
                    act("nav", arg)
                else:
                    act("confirm")
    return 0

def _selftest():
    assert _EVENT.size == 24, _EVENT.size
    assert key_action(KEY_ESC, False) == ("cancel", None)
    assert key_action(KEY_CAPSLOCK, False) == ("cancel", None)
    assert key_action(KEY_UP, False) == ("nav", "up")
    assert key_action(KEY_DOWN, False) == ("nav", "down")
    assert key_action(KEY_TAB, True) == ("nav", "up")
    assert key_action(KEY_TAB, False) == ("nav", "down")
    assert key_action(KEY_ENTER, False) == ("confirm", None)
    assert key_action(KEY_KPENTER, False) == ("confirm", None)
    assert key_action(KEY_LEFTSHIFT, False) is None
    buf = _EVENT.pack(0, 0, EV_KEY, KEY_ESC, PRESS)
    assert _EVENT.unpack(buf) == (0, 0, EV_KEY, KEY_ESC, PRESS)
    print("powermenu-keys selftest ok")

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
        sys.exit(0)
    sys.exit(main())
