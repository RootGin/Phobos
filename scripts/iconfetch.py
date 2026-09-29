#!/usr/bin/env python3
import os
import sys
from functools import lru_cache

ICON_DIRS = []
for env in ("XDG_DATA_HOME", "XDG_DATA_DIRS"):
    for d in os.environ.get(env, "").split(":"):
        if d:
            ICON_DIRS.append(os.path.join(d, "icons"))
ICON_DIRS.insert(0, "/run/current-system/sw/share/icons")  # system icons win
ICON_DIRS += [os.path.expanduser("~/.local/share/icons"), os.path.expanduser("~/.icons"), "/usr/share/icons"]

SIZES = ("scalable", "48x48", "128x128", "256x256", "32x32")
EXTS = ("svg", "png")


@lru_cache(maxsize=256)
def fetch(icon_name):
    if not icon_name:
        return None
    name = icon_name.replace("-symbolic", "").lower()

    for base in ICON_DIRS:
        if not os.path.isdir(base):
            continue
        for theme in os.listdir(base):
            for size in SIZES:
                for ext in EXTS:
                    p = os.path.join(base, theme, size, "apps", f"{name}.{ext}")
                    if os.path.isfile(p):
                        return p
    return None


if __name__ == "__main__":
    print(fetch(sys.argv[1]))