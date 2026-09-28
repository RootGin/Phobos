#!/usr/bin/env python3

import json
import os
import re
import subprocess
import sys
import time

POLL = 2.0
NOTIFY = ["notify-send", "-a", "Network"]
DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EWW = ["eww", "-c", DIR]

_SPLIT = re.compile(r"(?<!\\):")

def run(args, timeout=15):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return p.stdout if p.returncode == 0 else ""
    except Exception:
        return ""

def unescape(field):
    return field.replace("\\:", ":").replace("\\\\", "\\")

def fields(line, n):
    """nmcli -t line -> list of n fields (escaped ':' kept intact)."""
    parts = _SPLIT.split(line)
    if len(parts) < n:
        parts += [""] * (n - len(parts))
    return [unescape(p) for p in parts]

def bucket(signal):
    if signal >= 75:
        return "excellent"
    if signal >= 50:
        return "good"
    if signal >= 25:
        return "weak"
    return "very-weak"

def wifi_device():
    for line in run(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device"]).splitlines():
        dev, typ, state, conn = fields(line, 4)
        if typ == "wifi":
            return dev, state, conn
    return None, None, None

def parse_nmcli_error(text):
    for line in (text or "").splitlines():
        line = line.strip()
        if line.lower().startswith("error:"):
            m = re.search(r"\((.*)\)", line)
            return m.group(1) if m else line[6:].strip()
    return "connection failed"

def snapshot():
    radio = run(["nmcli", "radio", "wifi"]).strip() or "enabled"
    dev, dev_state, conn = wifi_device()

    if dev is None:
        return {"iface": "", "radio": radio, "state": "no-interface",
                "ssid": "", "security": "", "signal": 0, "bucket": "very-weak",
                "connected": False, "networks": []}
    if radio != "enabled":
        return {"iface": dev, "radio": radio, "state": "airplane-mode",
                "ssid": "", "security": "", "signal": 0, "bucket": "very-weak",
                "connected": False, "networks": []}

    nets = []
    seen = {}
    for line in run(["nmcli", "-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY",
                     "device", "wifi", "list"]).splitlines():
        inuse, ssid, signal, security = fields(line, 4)
        if not ssid:
            continue
        try:
            sig = int(signal)
        except ValueError:
            sig = 0
        old = seen.get(ssid)
        if old and old["signal"] >= sig:
            old["connected"] = old["connected"] or inuse == "*"
            continue
        entry = {
            "ssid": ssid,
            "security": security,
            "signal": sig,
            "bucket": bucket(sig),
            "open": security.strip().lower() in ("", "--", "open"),
            "connected": inuse == "*",
        }
        seen[ssid] = entry
        nets.append(entry)

    nets.sort(key=lambda n: (not n["connected"], -n["signal"], n["ssid"].lower()))

    active = next((n for n in nets if n["connected"]), None)
    if active:
        state = "connected"
    elif dev_state in ("connecting", "activating"):
        state = "connecting"
    elif not nets:
        state = "disconnected"
    else:
        state = "disconnected"

    return {
        "iface": dev,
        "radio": radio,
        "state": state if active is None else "connected",
        "ssid": active["ssid"] if active else "",
        "security": active["security"] if active else "",
        "signal": active["signal"] if active else 0,
        "bucket": active["bucket"] if active else "very-weak",
        "connected": active is not None,
        "state_raw": dev_state or "",
        "connecting": state == "connecting",
        "networks": nets,
    }

def step(snap, confirmed, bad, notified):
    """Debounce + one-shot-notify decision. Returns
    (out, confirmed, bad, notified, notify).

    A momentary bad read (one poll) is held as the previous connected state so
    the UI doesn't flash; two consecutive bad reads declare disconnected, and the
    notification fires exactly once per disconnect event.
    """
    if snap["connected"]:
        return snap, snap, 0, False, False
    if confirmed is not None:
        bad += 1
        if bad < 2:
            return confirmed, confirmed, bad, notified, False
        return snap, None, 0, True, not notified
    return snap, None, 0, notified, False

def loop():
    last = None
    confirmed = None
    bad = 0
    notified = False
    while True:
        snap = snapshot()
        snap.pop("state_raw", None)

        out, confirmed, bad, notified, notify = step(snap, confirmed, bad, notified)
        if notify:
            run(NOTIFY + [f"Disconnected from {out['ssid']}"])

        payload = json.dumps(out)
        if payload != last:
            print(payload, flush=True)
            last = payload
        time.sleep(POLL)

def cmd_rescan():
    run(["nmcli", "device", "wifi", "rescan"], timeout=10)

def cmd_disconnect(ssid):
    run(["nmcli", "connection", "down", ssid], timeout=20)

def cmd_getpass(ssid):
    """Fill the eww password field with the saved PSK for <ssid> (empty if none).

    Called from the row `:onclick`, so the user doesn't retype a password they've
    already saved; a stale/incorrect saved PSK is still filled (the user can edit
    it). Updates `netpass` directly over eww IPC so the secret never has to
    survive shell/yuck quoting.
    """
    psk = run(["nmcli", "-s", "-g", "802-11-wireless-security.psk",
               "connection", "show", ssid]).strip()
    run(EWW + ["update", f"netpass={psk}"])

def cmd_connect(args):
    vals = (args + [""] * 12)[:12]
    ssid, security, password, ipmode, ip, subnet, gw, dns, proxymode, proxyval, mtu, autoconnect = vals
    autoconnect = autoconnect != "false"

    connect = ["nmcli", "--wait", "30", "device", "wifi", "connect", ssid]
    if password:
        connect += ["password", password]
    p = subprocess.run(connect, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        print(parse_nmcli_error(p.stderr or p.stdout))
        return 1

    mods = []
    if not autoconnect:
        mods += ["connection.autoconnect", "no"]
    if ipmode == "manual" and ip:
        addr = f"{ip}/{subnet}" if subnet else ip
        mods += ["ipv4.method", "manual", "ipv4.addresses", addr]
        if gw:
            mods += ["ipv4.gateway", gw]
        if dns:
            mods += ["ipv4.dns", dns]
    elif ipmode == "manual":
        mods += ["ipv4.method", "manual"]
    else:
        mods += ["ipv4.method", "auto"]

    if proxymode == "auto":
        mods += ["proxy.method", "auto"]
    elif proxymode == "manual":
        mods += ["proxy.method", "manual", "proxy.pac-url", proxyval]
    else:
        mods += ["proxy.method", "none"]

    if mtu and mtu.isdigit():
        mods += ["802-11-wireless.mtu", mtu]

    if mods:
        subprocess.run(["nmcli", "connection", "modify", ssid, *mods],
                       capture_output=True, text=True, timeout=30)
        p = subprocess.run(["nmcli", "connection", "up", ssid],
                           capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            print(parse_nmcli_error(p.stderr or p.stdout))
            return 1
    return 0

def selftest():
    assert bucket(90) == "excellent" and bucket(75) == "excellent"
    assert bucket(60) == "good" and bucket(50) == "good"
    assert bucket(30) == "weak" and bucket(25) == "weak"
    assert bucket(10) == "very-weak"

    on = {"connected": True, "ssid": "A"}
    off = {"connected": False, "ssid": ""}

    out, confirmed, bad, notified, notify = step(on, None, 0, False)
    assert out is on and confirmed is on and bad == 0 and not notify

    out, confirmed, bad, notified, notify = step(off, confirmed, bad, notified)
    assert out is on and confirmed is on and bad == 1 and not notify

    out, confirmed, bad, notified, notify = step(off, confirmed, bad, notified)
    assert out is off and confirmed is None and notify and notified

    out, confirmed, bad, notified, notify = step(off, confirmed, bad, notified)
    assert not notify

    out, confirmed, bad, notified, notify = step(on, confirmed, bad, notified)
    assert notified is False and not notify
    out, confirmed, bad, notified, notify = step(off, confirmed, bad, notified)
    out, confirmed, bad, notified, notify = step(off, confirmed, bad, notified)
    assert notify
    print("wifi.py selftest: ok")

def main():
    argv = sys.argv[1:]
    if not argv:
        loop()
    elif argv[0] == "rescan":
        cmd_rescan()
    elif argv[0] == "disconnect":
        cmd_disconnect(argv[1] if len(argv) > 1 else "")
    elif argv[0] == "getpass":
        cmd_getpass(argv[1] if len(argv) > 1 else "")
    elif argv[0] == "connect":
        sys.exit(cmd_connect(argv[1:]))
    elif argv[0] == "selftest":
        selftest()
    else:
        sys.exit(f"unknown subcommand: {argv[0]}")

if __name__ == "__main__":
    main()
