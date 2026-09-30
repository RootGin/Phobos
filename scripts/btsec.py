#!/usr/bin/env python3
"""Bluetooth pairing/bond security manager, modelled on the Bluetooth Core Specification.

BlueZ deliberately does not expose a bond's security properties. Adapter1 and
Device1 carry no field for the association model, the key strength, the MITM flag
or the encryption key size, and /var/lib/bluetooth -- where BlueZ keeps the LTK,
the IRK and the key-distribution record -- is root-only. So the security property
of a bond cannot be read back from the system. This tool therefore:

  * reports what BlueZ does expose, without pretending the rest is knowable;
  * computes the association model the specification's tables select, from a
    declared IO capability and the peer's, so the consequence of a pairing is
    visible *before* it happens;
  * records the observed model in a host-side security database at pairing time,
    which is what [Vol 3] Part H Sec 2.3.1 asks of the initiating device;
  * never marks a device trusted on its own. [Vol 3] Part C Sec 16.5 makes trust
    marking a user decision.

Specifications are cited as [Vol 3] Part <letter>, section <n>.
"""

import json
import os
import re
import select
import subprocess
import sys
import time

try:
    import gi
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib
except ImportError:
    sys.exit("PyGObject (gi) is required: it ships with python3 on this system.")

BLUEZ = "org.bluez"
ADAPTER = "/org/bluez/hci0"
DB = os.path.join(os.environ.get("XDG_STATE_HOME",
                                 os.path.expanduser("~/.local/state")), "btsec/bonds.json")

# --- Specification tables -----------------------------------------------------

# [Vol 3] Part H Sec 2.3.2 Table 3.4
IO_CAPABILITY = {
    "DisplayOnly": 0x00,
    "DisplayYesNo": 0x01,
    "KeyboardOnly": 0x02,
    "NoInputNoOutput": 0x03,
    "KeyboardDisplay": 0x04,
}
CAPABILITY_OF = {v: k for k, v in IO_CAPABILITY.items()}

# [Vol 3] Part H Sec 2.3.2 Table 2.5. Rows are local input capacity, columns are
# local output capacity. Footnote 1: no pairing algorithm can use Yes/No input
# with no output, so that combination resolves to NoInputNoOutput.
IO_TABLE_2_5 = {
    ("no-input", "no-output"): "NoInputNoOutput",
    ("no-input", "numeric-output"): "DisplayOnly",
    ("yes-no", "no-output"): "NoInputNoOutput",
    ("yes-no", "numeric-output"): "DisplayYesNo",
    ("keyboard", "no-output"): "KeyboardOnly",
    ("keyboard", "numeric-output"): "KeyboardDisplay",
}

JUST_WORKS = "Just Works"
PASSKEY = "Passkey Entry"
NUMERIC = "Numeric Comparison"
OOB = "Out Of Band"
LEGACY_ONLY = "LE legacy pairing"
SC = "LE Secure Connections"
AUTHENTICATED = "Authenticated MITM protection"
UNAUTHENTICATED = "Unauthenticated, no MITM protection"

# [Vol 3] Part H Sec 2.3.5.1 Table 2.8: mapping of IO capabilities to key
# generation method. Rows are the initiator, columns the responder, both in the
# order DisplayOnly, DisplayYesNo, KeyboardOnly, NoInputNoOutput, KeyboardDisplay.
# Cells that list two outcomes are (legacy, secure-connections): a
# DisplayYesNo/KeyboardDisplay pair gets Passkey Entry and an unauthenticated key
# under legacy pairing, and Numeric Comparison and an authenticated key under LE
# Secure Connections. `who` records which side displays the passkey, because that
# is what tells an operator where to type the number.
def _c(legacy, sc_entry, who=None):
    return (legacy, sc_entry, who)


_UNAUTH_JW = (JUST_WORKS, UNAUTHENTICATED)
_PE_AUTH = (PASSKEY, AUTHENTICATED)
_PE_LEGACY_UNAUTH = (PASSKEY, UNAUTHENTICATED)
_NUMERIC_SC = (NUMERIC, AUTHENTICATED)
_PE_BOTH = (PASSKEY, AUTHENTICATED)

TABLE_2_8 = {
    ("DisplayOnly", "DisplayOnly"): _c(_UNAUTH_JW, _UNAUTH_JW),
    ("DisplayOnly", "DisplayYesNo"): _c(_UNAUTH_JW, _UNAUTH_JW),
    ("DisplayOnly", "KeyboardOnly"): _c(_PE_AUTH, _PE_AUTH, "responder"),
    ("DisplayOnly", "NoInputNoOutput"): _c(_UNAUTH_JW, _UNAUTH_JW),
    ("DisplayOnly", "KeyboardDisplay"): _c(_PE_AUTH, _PE_AUTH, "responder"),

    ("DisplayYesNo", "DisplayOnly"): _c(_UNAUTH_JW, _UNAUTH_JW),
    ("DisplayYesNo", "DisplayYesNo"): _c(_UNAUTH_JW, _UNAUTH_JW),
    ("DisplayYesNo", "KeyboardOnly"): _c(_PE_AUTH, _PE_AUTH, "responder"),
    ("DisplayYesNo", "NoInputNoOutput"): _c(_UNAUTH_JW, _UNAUTH_JW),
    ("DisplayYesNo", "KeyboardDisplay"): _c(_PE_LEGACY_UNAUTH, _NUMERIC_SC),

    ("KeyboardOnly", "DisplayOnly"): _c(_PE_AUTH, _PE_AUTH, "initiator"),
    ("KeyboardOnly", "DisplayYesNo"): _c(_PE_AUTH, _PE_AUTH, "initiator"),
    ("KeyboardOnly", "KeyboardOnly"): _c(_PE_BOTH, _PE_BOTH, "both"),
    ("KeyboardOnly", "NoInputNoOutput"): _c(_UNAUTH_JW, _UNAUTH_JW),
    ("KeyboardOnly", "KeyboardDisplay"): _c(_PE_AUTH, _PE_AUTH, "initiator"),

    ("NoInputNoOutput", "DisplayOnly"): _c(_UNAUTH_JW, _UNAUTH_JW),
    ("NoInputNoOutput", "DisplayYesNo"): _c(_UNAUTH_JW, _UNAUTH_JW),
    ("NoInputNoOutput", "KeyboardOnly"): _c(_UNAUTH_JW, _UNAUTH_JW),
    ("NoInputNoOutput", "NoInputNoOutput"): _c(_UNAUTH_JW, _UNAUTH_JW),
    ("NoInputNoOutput", "KeyboardDisplay"): _c(_UNAUTH_JW, _UNAUTH_JW),

    ("KeyboardDisplay", "DisplayOnly"): _c(_PE_AUTH, _PE_AUTH, "initiator"),
    ("KeyboardDisplay", "DisplayYesNo"): _c(_PE_LEGACY_UNAUTH, _NUMERIC_SC),
    ("KeyboardDisplay", "KeyboardOnly"): _c(_PE_AUTH, _PE_AUTH, "responder"),
    ("KeyboardDisplay", "NoInputNoOutput"): _c(_UNAUTH_JW, _UNAUTH_JW),
    ("KeyboardDisplay", "KeyboardDisplay"): _c(_PE_LEGACY_UNAUTH, _NUMERIC_SC),
}

# [Vol 3] Part H Sec 2.4.6 Table 2.9: action after encryption setup failure.
TABLE_2_9 = {
    (UNAUTHENTICATED, False): ("auto-repair-ok", "Automatically initiate pairing."),
    (UNAUTHENTICATED, True): ("notify", "Notify user of security failure."),
    (AUTHENTICATED, False): ("notify-then-repair", "Notify user and ask if pairing is ok."),
    (AUTHENTICATED, True): ("notify", "Notify user of security failure."),
}

# [Vol 3] Part C Sec 10.2.1: LE security mode 1 levels. Cumulative: a higher level
# satisfies every lower one.
LE_SECURITY_MODE_1 = {
    1: "No security (no authentication, no encryption)",
    2: "Unauthenticated pairing with encryption",
    3: "Authenticated pairing with encryption",
    4: "Authenticated LE Secure Connections pairing with encryption, 128-bit key",
}

# Properties BlueZ does not expose, so that a bond's security property is known
# only from what this tool recorded at pairing time.
UNOBSERVABLE = (
    "association model actually used", "authenticated vs unauthenticated key",
    "MITM flag", "LE Secure Connections flag", "encryption key size",
    "which keys were distributed", "LE security mode 1 level achieved",
)


def io_capability(input_kind, output_kind):
    """Table 2.5: local input/output capacity -> a single IO capability."""
    try:
        return IO_TABLE_2_5[(input_kind, output_kind)]
    except KeyError:
        raise ValueError("input must be no-input/yes-no/keyboard, "
                         "output must be no-output/numeric-output")


def select_model(init_io, resp_io, init_mitm=False, resp_mitm=False,
                 secure_connections=True, init_oob=False, resp_oob=False):
    """Choose the Phase 2 key generation method and its Security Properties.

    Order of resolution, per the specification:
      1. Out-of-band data overrides the capability table (Tables 2.6 / 2.7). For
         LE Secure Connections one side having OOB data is enough; for LE legacy
         both must.
      2. If neither side requested MITM, the IO capabilities are ignored and the
         method is Just Works (Sec 2.3.5.1).
      3. Otherwise Table 2.8 supplies the method, and the transport decides which
         of a cell's two outcomes applies.
    """
    if init_io not in IO_CAPABILITY or resp_io not in IO_CAPABILITY:
        raise ValueError("unknown IO capability")
    oob = (init_oob or resp_oob) if secure_connections else (init_oob and resp_oob)
    if oob:
        # Sec 2.3.5.1: an eavesdropping-resistant OOB channel yields an
        # authenticated key; otherwise the key is unauthenticated. Which one
        # cannot be determined from the flag alone, so the caller must say.
        return OOB, "oob-dependent", None
    if not init_mitm and not resp_mitm:
        return JUST_WORKS, UNAUTHENTICATED, None
    legacy, sc_entry, who = TABLE_2_8[(init_io, resp_io)]
    model, prop = sc_entry if secure_connections else legacy
    return model, prop, who


def security_level(secure_connections, prop, encrypted=True):
    """LE security mode 1 level (Sec 10.2.1) implied by a pairing outcome.

    Levels are cumulative, so each satisfies every lower one. Level 1 is the
    absence of encryption; an unauthenticated pairing that *is* encrypted is level
    2, which is the normal case for a bond. Just Works can never exceed 2 however
    it was negotiated. Level 3 needs authentication, and level 4 additionally
    requires LE Secure Connections with a full-length key.
    """
    if not encrypted:
        return 1
    if prop == UNAUTHENTICATED:
        return 2
    return 4 if secure_connections else 3


def failure_action(prop, bonded):
    """Table 2.9: what to do when enabling encryption fails."""
    return TABLE_2_9[(prop, bool(bonded))]


# --- BlueZ --------------------------------------------------------------------

class Bluez:
    def __init__(self):
        self.bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)

    def get(self, path, iface, prop):
        variant = self.bus.call_sync(
            BLUEZ, path, "org.freedesktop.DBus.Properties", "Get",
            GLib.Variant("(ss)", (iface, prop)), GLib.VariantType("(v)"),
            Gio.DBusCallFlags.NONE, -1, None)
        return variant.unpack()[0]

    def set(self, path, iface, prop, sig, value):
        self.bus.call_sync(
            BLUEZ, path, "org.freedesktop.DBus.Properties", "Set",
            GLib.Variant("(ssv)", (iface, prop, GLib.Variant(sig, value))),
            None, Gio.DBusCallFlags.NONE, -1, None)

    def call(self, path, iface, method, body=None, reply=None):
        return self.bus.call_sync(
            BLUEZ, path, iface, method, body, reply,
            Gio.DBusCallFlags.NONE, -1, None)

    def adapter_call(self, method, body=None, reply=None):
        return self.call(ADAPTER, "org.bluez.Adapter1", method, body, reply)

    def agent_call(self, method, body=None, reply=None):
        # AgentManager1 lives on /org/bluez, not on the adapter object.
        return self.call("/org/bluez", "org.bluez.AgentManager1", method, body, reply)

    def adapter(self):
        a = {"path": ADAPTER}
        for p in ("Address", "Name", "Alias", "AddressType", "PowerState"):
            a[p.lower()] = self.get(ADAPTER, "org.bluez.Adapter1", p)
        for p in ("Powered", "Connectable", "Discoverable", "Pairable", "Discovering"):
            a[p.lower()] = self.get(ADAPTER, "org.bluez.Adapter1", p)
        return a

    def devices(self):
        """Every device object BlueZ currently knows, with its exposed state."""
        managed = self.bus.call_sync(
            BLUEZ, "/", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects",
            None, GLib.VariantType("(a{oa{sa{sv}}})"), Gio.DBusCallFlags.NONE, -1, None)
        out = []
        for path, ifaces in managed.unpack()[0].items():
            if "org.bluez.Device1" not in ifaces:
                continue
            props = ifaces["org.bluez.Device1"]
            dev = {"path": path, "addr": path.split("dev_")[-1].replace("_", ":").upper()}
            for key, value in props.items():
                # GetManagedObjects replies a{oa{sa{sv}}}; GLib unwraps the nested
                # containers itself, but whether the leaf is still a Variant
                # depends on how deep the tree went, so accept either.
                dev[key] = value.unpack() if hasattr(value, "unpack") else value
            out.append(dev)
        out.sort(key=lambda d: d.get("Address", ""))
        return out


# --- Host-side security database ---------------------------------------------

def load_db():
    try:
        with open(DB) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_db(db):
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    tmp = DB + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(db, fh, indent=1, sort_keys=True)
    os.replace(tmp, DB)


def record_bond(addr, entry):
    db = load_db()
    db[addr.upper()] = entry
    save_db(db)


def forget_bond(addr):
    db = load_db()
    if db.pop(addr.upper(), None) is not None:
        save_db(db)
        return True
    return False


# --- Commands -----------------------------------------------------------------

def fmt_security(entry):
    """One line: the bond's security posture, and how much of it we can prove."""
    if not entry:
        return "unknown (not paired by this tool -- BlueZ exposes no key strength)"
    prop = entry.get("property", "?")
    who = entry.get("passkey_side")
    bits = [entry.get("model", "?"), "|", prop]
    if who:
        bits.append("| passkey %s" % who)
    if entry.get("level"):
        bits.append("| SM1 level %d" % entry["level"])
    if not entry.get("secure_connections"):
        bits.append("| LE legacy pairing")
    return " ".join(b for b in bits if b)


def cmd_modes(bz):
    """Adapter modes, against GAP Sec 4.1/4.2/4.3 (BR/EDR) and Sec 9.2/9.3 (LE)."""
    a = bz.adapter()
    print("adapter %s  (%s, %s)  power=%s" % (a["name"], a["address"], a["addresstype"], a["powerstate"]))
    for key, label, ref in (
            ("pairable", "Bondable", "GAP Sec 4.3 / 9.4.2 Non Bonding | 9.4.3 Bonding"),
            ("connectable", "Connectable", "GAP Sec 4.2 / 9.3.2 Non-connectable | 9.3.4 Undirected connectable"),
            ("discoverable", "Discoverable", "GAP Sec 4.1 / 9.2.2 Non-discoverable | 9.2.4 General discoverable"),
            ("powered", "Powered", "GAP Table 2.1 Link Layer: Standby | Connection")):
        print("  %-13s %-9s %s" % (label, str(a[key]), ref))


def cmd_bonds(bz):
    """Bonds and the security properties recorded for them."""
    db = load_db()
    devices = bz.devices()
    if not devices:
        print("no devices known to BlueZ")
        return
    bonded = [d for d in devices if d.get("Bonded") or d.get("Paired")]
    if not bonded:
        print("no bonds. %d device(s) known, none paired." % len(devices))
        return
    for d in bonded:
        addr = d.get("Address", "")
        flags = " ".join(
            "%s=%s" % (k, "yes" if d.get(k) else "no")
            for k in ("Paired", "Bonded", "Trusted", "Blocked", "LegacyPairing",
                      "ServicesResolved", "Connected"))
        print("%s  %s" % (addr, d.get("Alias") or d.get("Name") or "(no name)"))
        print("  bluez      %s" % flags)
        print("  security   %s" % fmt_security(db.get(addr)))
    print()
    print("BlueZ does not expose any of: %s." % ", ".join(UNOBSERVABLE))
    print("A blank 'security' line means the bond was created outside this tool,")
    print("so its association model cannot be recovered. See 'btsec policy'.")


def cmd_policy(args):
    """Table 2.9, the action to take when enabling encryption fails."""
    for a in args:
        if a not in (AUTHENTICATED, UNAUTHENTICATED):
            sys.exit("security property must be one of:\n  %s\n  %s"
                     % (AUTHENTICATED, UNAUTHENTICATED))
    rows = [(prop, bond) for prop in (UNAUTHENTICATED, AUTHENTICATED)
            for bond in (False, True)]
    print("Table 2.9 -- action after encryption setup failure\n")
    for prop, bond in rows:
        kind, text = failure_action(prop, bond)
        print("  %-36s bonded=%-3s  %s" % (prop, "yes" if bond else "no", text))
    print()
    print("The recommendation differs by row on purpose: an unauthenticated bond")
    print("that is not yet stored can be re-paired silently, but one that is")
    print("already stored may mean the peer lost its keys -- that is a security")
    print("event, not a retry. An authenticated bond always asks first.")


def cmd_plan(init_io, resp_io, mitm, secure, init_oob=False, resp_oob=False):
    """What pairing would select, before doing it."""
    model, prop, who = select_model(
        init_io, resp_io, init_mitm=mitm, resp_mitm=mitm,
        secure_connections=secure, init_oob=init_oob, resp_oob=resp_oob)
    print("initiator  %s" % init_io)
    print("responder  %s" % resp_io)
    print("MITM       %s" % ("requested by both" if mitm else "not requested"))
    print("transport  %s" % (SC if secure else LEGACY_ONLY))
    print()
    print("model      %s" % model)
    print("property   %s" % prop)
    if who:
        print("passkey    %s" % who)
    if model != OOB:
        print("SM1 level  %d  %s" % (security_level(secure, prop),
                                     LE_SECURITY_MODE_1[security_level(secure, prop)]))
    if prop == UNAUTHENTICATED:
        print()
        print("WARNING  an unauthenticated key has no MITM protection. Per Sec")
        print("2.4.3.1/2.4.3.2 every key distributed in Phase 3 inherits this, so")
        print("the whole bond is only as strong as the weakest moment of pairing.")
        if init_io == "NoInputNoOutput":
            print("         NoInputNoOutput is Just Works against every peer")
            print("         capability (Table 2.8) -- declare a real capability.")


def selftest():
    assert io_capability("no-input", "no-output") == "NoInputNoOutput"
    assert io_capability("no-input", "numeric-output") == "DisplayOnly"
    assert io_capability("yes-no", "no-output") == "NoInputNoOutput"
    assert io_capability("yes-no", "numeric-output") == "DisplayYesNo"
    assert io_capability("keyboard", "no-output") == "KeyboardOnly"
    assert io_capability("keyboard", "numeric-output") == "KeyboardDisplay"

    for peer in IO_CAPABILITY:
        model, prop, who = select_model("NoInputNoOutput", peer)
        assert model == JUST_WORKS and prop == UNAUTHENTICATED, peer

    m, p, _ = select_model("DisplayYesNo", "DisplayYesNo", init_mitm=True, resp_mitm=True)
    assert (m, p) == (JUST_WORKS, UNAUTHENTICATED), (m, p)

    m, p, _ = select_model("DisplayYesNo", "KeyboardDisplay",
                           init_mitm=True, resp_mitm=True, secure_connections=True)
    assert (m, p) == (NUMERIC, AUTHENTICATED), (m, p)

    m, p, _ = select_model("DisplayYesNo", "KeyboardDisplay",
                           init_mitm=True, resp_mitm=True, secure_connections=False)
    assert (m, p) == (PASSKEY, UNAUTHENTICATED), (m, p)

    m, p, who = select_model("DisplayOnly", "KeyboardOnly",
                             init_mitm=True, resp_mitm=True)
    assert (m, p, who) == (PASSKEY, AUTHENTICATED, "responder"), (m, p, who)

    m, p, who = select_model("KeyboardOnly", "DisplayOnly",
                             init_mitm=True, resp_mitm=True)
    assert (m, p, who) == (PASSKEY, AUTHENTICATED, "initiator"), (m, p, who)

    m, p, who = select_model("KeyboardOnly", "KeyboardOnly",
                             init_mitm=True, resp_mitm=True)
    assert who == "both", who

    # Sec 2.3.5.1: no MITM on either side short-circuits the capability table.
    for init in ("DisplayOnly", "KeyboardDisplay", "NoInputNoOutput"):
        for resp in ("DisplayOnly", "KeyboardDisplay", "NoInputNoOutput"):
            m, p, _ = select_model(init, resp, init_mitm=False, resp_mitm=False)
            assert (m, p) == (JUST_WORKS, UNAUTHENTICATED), (init, resp)

    # Out-of-band: one side suffices for SC, both are required for legacy.
    m, _, _ = select_model("NoInputNoOutput", "NoInputNoOutput",
                           init_oob=True, secure_connections=True)
    assert m == OOB
    m, _, _ = select_model("NoInputNoOutput", "NoInputNoOutput",
                           init_oob=True, secure_connections=False)
    assert m == JUST_WORKS
    m, _, _ = select_model("NoInputNoOutput", "NoInputNoOutput",
                           init_oob=True, resp_oob=True, secure_connections=False)
    assert m == OOB

    # Sec 10.2.1 levels are cumulative; level 1 is the absence of encryption.
    assert security_level(True, UNAUTHENTICATED, encrypted=False) == 1
    assert security_level(True, UNAUTHENTICATED) == 2
    assert security_level(True, AUTHENTICATED) == 4
    assert security_level(False, AUTHENTICATED) == 3
    assert security_level(False, AUTHENTICATED, encrypted=False) == 1
    for lvl in (1, 2, 3, 4):
        assert lvl in LE_SECURITY_MODE_1

    assert failure_action(UNAUTHENTICATED, False)[0] == "auto-repair-ok"
    assert failure_action(UNAUTHENTICATED, True)[0] == "notify"
    assert failure_action(AUTHENTICATED, False)[0] == "notify-then-repair"
    assert failure_action(AUTHENTICATED, True)[0] == "notify"

    assert classify({}) == "unknown"
    assert classify({"property": AUTHENTICATED}) == "auth"
    assert classify({"property": UNAUTHENTICATED}) == "unauth"
    assert classify({"property": "unverified (observed X, predicted Y)"}) == "unverified"

    assert len(TABLE_2_8) == 25
    assert IO_CAPABILITY["NoInputNoOutput"] == 0x03
    assert IO_CAPABILITY["KeyboardDisplay"] == 0x04

    # The security database is the only place a bond's property survives, since
    # BlueZ will not report it. Round-trip it through a scratch file.
    global DB
    real_db = DB
    import tempfile
    fd, DB = tempfile.mkstemp(prefix="btsec-test-")
    os.close(fd)
    try:
        assert load_db() == {}
        record_bond("aa:bb:cc:dd:ee:ff", {
            "model": NUMERIC, "property": AUTHENTICATED, "level": 4,
            "passkey_side": None, "secure_connections": True})
        got = load_db()
        assert "AA:BB:CC:DD:EE:FF" in got, got
        assert got["AA:BB:CC:DD:EE:FF"]["property"] == AUTHENTICATED
        assert "Authenticated" in fmt_security(got["AA:BB:CC:DD:EE:FF"])
        assert "LE legacy" in fmt_security({"model": PASSKEY, "property": UNAUTHENTICATED,
                                           "secure_connections": False})
        assert fmt_security(None).startswith("unknown")
        assert forget_bond("AA:BB:CC:DD:EE:FF") is True
        assert forget_bond("AA:BB:CC:DD:EE:FF") is False
        assert load_db() == {}
        with open(DB, "w") as fh:
            fh.write("{ not json")
        assert load_db() == {}
    finally:
        os.unlink(DB)
        DB = real_db
    print("btsec selftest: ok")


def cmd_set_trusted(bz, addr, value):
    """Trust marking is a user decision ([Vol 3] Part C Sec 16.5), so it is only
    ever done by an explicit command -- never as a side effect of pairing."""
    dev = find_device(bz, addr)
    bz.set(dev["path"], "org.bluez.Device1", "Trusted", "b", value)
    print("%s  Trusted=%s" % (addr, "yes" if value else "no"))


def cmd_forget(bz, addr):
    dev = find_device(bz, addr)
    # RemoveDevice is an Adapter1 method: called on the adapter, taking the
    # device's object path as its argument.
    bz.adapter_call("RemoveDevice", GLib.Variant("(o)", (dev["path"],)), None)
    if forget_bond(addr):
        print("removed %s and its recorded security properties" % addr)
    else:
        print("removed %s (no recorded security properties)" % addr)


def find_device(bz, addr):
    addr = addr.upper()
    for dev in bz.devices():
        if dev.get("Address", "").upper() == addr:
            return dev
    sys.exit("no such device: %s" % addr)


# --- Pairing, as the agent ----------------------------------------------------

class Agent:
    """A BlueZ Agent1 that records which association model the stack actually ran.

    This is the only way to learn a bond's security property. BlueZ does not
    report it, and the specification says the method is decided by the two IO
    capabilities -- of which the host only knows its own. So the tool predicts the
    model from the capability the user declared, observes which callback the stack
    actually invoked, and reports any disagreement rather than picking a winner.

    Callback -> model mapping:
      DisplayPasskey   -> Passkey Entry, this side displays
      RequestPasskey   -> Passkey Entry, this side inputs
      RequestPinCode   -> BR/EDR legacy PIN pairing (pre-SSP)
      Authorize        -> Just Works *or* Numeric Comparison; not distinguishable
                          from the callback, which is why the prediction matters
    """

    def __init__(self, declared_io, predicted, mitm, secure):
        self.declared_io = declared_io
        self.predicted = predicted
        self.observed = None
        self.agree = None

    def _record(self, observed, note=None):
        self.observed = observed
        self.agree = (observed == self.predicted) if self.predicted else None

    def _ask(self, prompt):
        try:
            return input(prompt).strip()
        except EOFError:
            return ""

    def authorize(self):
        # Numeric Comparison: both sides show a number the user compares. Our own
        # capability decides whether we are in that model at all.
        numeric = self.declared_io in ("DisplayYesNo", "KeyboardDisplay")
        self._record(NUMERIC if numeric else JUST_WORKS)
        print("\npairing request -- the peer wants to bond with this host")
        if numeric:
            print("this host declared %s, so a 6-digit comparison is expected."
                  % self.declared_io)
        ans = self._ask("authorize this device? [y/N] ")
        return ans.lower() in ("y", "yes")

    def display_passkey(self, passkey, entered):
        self._record(PASSKEY)
        if entered:
            print("\ntype this passkey on the other device: %06d" % passkey)
        else:
            print("\npasskey to type on the other device: %06d" % passkey)
        return 0

    def request_passkey(self):
        self._record(PASSKEY)
        val = self._ask("\nenter the passkey shown on the other device: ")
        if not val.isdigit() or len(val) > 6:
            print("passkey entry failed (Sec 3.4: Pairing Failed / Passkey Entry Failed)")
            return None
        return int(val)

    def request_pin_code(self):
        self._record("BR/EDR legacy PIN pairing")
        val = self._ask("\nenter the PIN shown on the other device: ")
        return val or None

    def report(self, addr, sc_flag):
        print()
        if self.observed is None:
            print("pairing finished but no agent callback was observed, so the")
            print("association model is unknown; nothing has been recorded.")
            return
        if self.agree is False:
            print("MISMATCH  predicted %s, the stack ran %s." % (self.predicted, self.observed))
            print("          the bond is real, but its security property is not")
            print("          what the declared capability would have produced.")
        prop = self.predicted[1] if self.agree else None
        entry = {
            "model": self.observed,
            "property": prop or "unverified (observed %s, predicted %s)" % (
                self.observed, self.predicted),
            "passkey_side": self.predicted[2],
            "secure_connections": sc_flag,
            "level": security_level(sc_flag, prop) if prop else None,
        }
        record_bond(addr, entry)
        print("recorded for %s:" % addr)
        print("  observed model   %s" % entry["model"])
        print("  property         %s" % entry["property"])
        if prop:
            print("  SM1 level        %d" % entry["level"])
        if not prop:
            print()
            print("  Treat this bond as unauthenticated until you know otherwise:")
            print("  an unverified property is not evidence of a strong key.")


def cmd_pair(bz, addr, declared_io, peer_io, mitm, secure):
    """Pair while acting as the agent, so the association model is observable."""
    addr = addr.upper()
    predicted = None
    if peer_io:
        predicted = select_model(declared_io, peer_io, init_mitm=mitm,
                                 resp_mitm=mitm, secure_connections=secure)[:2]
        print("predicted: %s -> %s" % predicted)
    else:
        print("no --peer-io given, so the model cannot be predicted from")
        print("Table 2.8; it will be recorded from the observed callback only.")
    if not mitm:
        print()
        print("NOTE  with MITM unrequested, Sec 2.3.5.1 ignores the IO")
        print("      capabilities entirely and selects Just Works, whatever you")
        print("      declare. The bond will be unauthenticated.")

    agent = Agent(declared_io, predicted, mitm, secure)
    path = "/org/bluez/btsec_agent"
    node = Gio.DBusNodeInfo.new_for_xml("""
    <node><interface name="org.bluez.Agent1">
      <method name="Release"/>
      <method name="RequestPinCode">
        <arg type="o" name="device" direction="in"/>
        <arg type="s" name="pincode" direction="out"/></method>
      <method name="DisplayPasskey">
        <arg type="o" name="device" direction="in"/>
        <arg type="u" name="passkey" direction="in"/>
        <arg type="q" name="entered" direction="in"/></method>
      <method name="RequestPasskey">
        <arg type="o" name="device" direction="in"/>
        <arg type="u" name="passkey" direction="out"/></method>
      <method name="RequestAuthorization">
        <arg type="o" name="device" direction="in"/></method>
      <method name="Authorize">
        <arg type="o" name="device" direction="in"/>
        <arg type="b" name="authorized" direction="out"/></method>
      <method name="RequestCancel"/>
    </interface></node>""")
    iface = node.interfaces[0]

    def handler(_conn, _sender, _path, _iface, method, params, invocation):
        args = params.unpack()
        if method == "Release":
            invocation.return_value(None)
        elif method == "Authorize":
            invocation.return_value(GLib.Variant("(b)", (agent.authorize(),)))
        elif method == "DisplayPasskey":
            agent.display_passkey(args[1], args[2])
            invocation.return_value(None)
        elif method == "RequestPasskey":
            value = agent.request_passkey()
            if value is None:
                invocation.return_dbus_error("org.bluez.Error.Rejected", "cancelled")
            else:
                invocation.return_value(GLib.Variant("(u)", (value,)))
        elif method == "RequestPinCode":
            value = agent.request_pin_code()
            if value is None:
                invocation.return_dbus_error("org.bluez.Error.Rejected", "cancelled")
            else:
                invocation.return_value(GLib.Variant("(s)", (value,)))
        elif method == "RequestAuthorization":
            invocation.return_dbus_error("org.bluez.Error.Rejected",
                                         "authorization is not used here")
        elif method == "RequestCancel":
            invocation.return_value(None)

    reg = bz.bus.register_object(path, iface, handler, None, None)
    bz.agent_call("RegisterAgent", GLib.Variant("(os)", (path, declared_io)), None)
    bz.agent_call("RequestDefaultAgent", GLib.Variant("(o)", (path,)), None)
    try:
        bz.adapter_call("PairDevice",
                        GLib.Variant("(oss)", (addr, "KeyboardDisplay")), None)
        print("pairing with %s ... (Ctrl-C to abort)" % addr)
        loop = GLib.MainLoop()
        GLib.timeout_add_seconds(60, lambda: (loop.quit(), False)[1])
        GLib.timeout_add_seconds(1, lambda: agent_watch(agent, addr, bz, loop))
        loop.run()
    finally:
        try:
            bz.agent_call("UnregisterAgent", GLib.Variant("(o)", (path,)), None)
        except GLib.Error:
            pass
        bz.bus.unregister_object(reg)
    agent.report(addr, secure)


def agent_watch(agent, addr, bz, loop):
    """Stop once the device reports itself bonded, or on cancel."""
    try:
        dev = find_device(bz, addr)
        if dev.get("Bonded") or dev.get("Paired"):
            loop.quit()
            return False
    except SystemExit:
        pass
    return True


def cmd_power(bz, on):
    if on:
        bz.set(ADAPTER, "org.bluez.Adapter1", "Powered", "b", True)
    else:
        bz.set(ADAPTER, "org.bluez.Adapter1", "Powered", "b", False)
    print("Bluetooth %s" % ("on" if on else "off"))


def cmd_scan(bz, seconds):
    """Find devices to pair with. Discovery is the prerequisite for everything
    else here, and the address is the only thing a later command accepts."""
    adapter = bz.adapter()
    if not adapter["powered"]:
        print("adapter is powered off; powering it on")
        bz.set(ADAPTER, "org.bluez.Adapter1", "Powered", "b", True)
        for _ in range(20):
            if bz.adapter()["powered"]:
                break
            time.sleep(0.5)
        else:
            sys.exit("could not power on the adapter (rfkill or missing capability?)")

    found = {}
    bz.adapter_call("StartDiscovery")
    try:
        print("scanning for %ds ..." % seconds)
        deadline = time.time() + seconds
        while time.time() < deadline:
            for dev in bz.devices():
                addr = dev.get("Address", "")
                if addr:
                    found[addr] = dev
            time.sleep(1)
    except KeyboardInterrupt:
        print()
    finally:
        bz.adapter_call("StopDiscovery")

    if not found:
        print("nothing found. If devices are in range, check that the adapter is "
              "not blocked (rfkill) and that they are advertising.")
        return

    print()
    # Strongest first; a device that never reported RSSI sorts last rather than
    # being treated as best, and a literal 0 is not a reading.
    ordered = sorted(found.items(),
                     key=lambda kv: -(kv[1].get("RSSI") if isinstance(kv[1].get("RSSI"), int) else -127))
    for addr, dev in ordered:
        bonded = dev.get("Bonded") or dev.get("Paired")
        name = dev.get("Alias") or dev.get("Name") or "(no name)"
        rssi = dev.get("RSSI")
        print("  %-17s  %-24s %-16s %s%s"
              % (addr, name[:24], dev.get("Icon", "?")[:16],
                 ("%d dBm" % rssi) if isinstance(rssi, int) else "no RSSI",
                 "  [bonded]" if bonded else ""))
    print()
    unbonded = [a for a, d in ordered if not (d.get("Bonded") or d.get("Paired"))]
    if unbonded:
        print("To see what pairing would cost before doing it:")
        print("  btsec plan NoInputNoOutput DisplayYesNo --mitm")
        print("To pair, declaring this host's capability and the peer's:")
        print("  btsec pair %s --io DisplayYesNo --peer-io KeyboardDisplay --mitm"
              % unbonded[0])
        print()
        print("With no --peer-io the association model cannot be predicted from")
        print("Table 2.8 and is recorded from the observed callback only.")


# --- Stream mode ---------------------------------------------------------------
#
# A `deflisten` source for the eww panel: one long-lived dbus-monitor child
# scoped to org.bluez, with a slow poll for whatever the signal does not carry.
# Emits only when the payload actually changes.

POLL = 10.0
DEBOUNCE = 0.3
SCALARS = ("boolean", "byte", "int16", "uint16", "int32", "uint32", "string", "object")
DEV_PATH = re.compile(r"/org/bluez/hci\d+/dev_([0-9A-Fa-f_]+)")
KEY = re.compile(r'^\s*string "(\w+)"\s*$')
VAR = re.compile(r"^\s*variant\s+(\S+)\s+(.*)$")

BUCKET = ((-55, "excellent"), (-67, "good"), (-80, "weak"))


def bucket(rssi):
    for threshold, name in BUCKET:
        if rssi >= threshold:
            return name
    return "very-weak"


def monitor():
    return subprocess.Popen(
        ["dbus-monitor", "--system", "type='signal',sender='org.bluez'"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)


def fold_block(block, cache):
    """Fold one dbus-monitor signal into the device cache.

    Read as `string "Prop"` followed by `variant <type> <value>`, which is the
    shape both InterfacesAdded dict entries and PropertiesChanged deltas take.
    The device path is not always in the header: PropertiesChanged carries it in
    `path=`, but InterfacesAdded comes from the ObjectManager root (`path=/`) and
    names the device in an `object path` line in the *body*, so the whole block is
    searched. Names are lowercased on the way in, because BlueZ capitalises them
    and every consumer here reads snake_case.
    """
    match = None
    for line in block:
        match = DEV_PATH.search(line)
        if match:
            break
    if not match:
        return False
    addr = match.group(1).replace("_", ":").upper()
    dev = cache.setdefault(addr, {"addr": addr, "seen": 0.0})
    dev["seen"] = time.time()
    key = None
    dirty = False
    for line in block[1:]:
        km = KEY.match(line)
        if km:
            key = km.group(1)
            continue
        vm = VAR.match(line)
        if not vm or not key:
            continue
        kind, val = vm.group(1), vm.group(2).strip()
        if kind not in SCALARS:
            key = None
            continue
        if kind in ("string", "object"):
            val = val.split('"')[-2] if '"' in val else val
        elif kind == "boolean":
            val = val == "true"
        else:
            try:
                val = int(val)
            except ValueError:
                key = None
                continue
        dev[key.lower()] = val
        dirty = True
        key = None
    return dirty


def drain(mon, cache):
    """Swallow a burst of signals into whole blocks; restart if the pipe closed."""
    block = []
    touched = False
    while select.select([mon.stdout], [], [], DEBOUNCE)[0]:
        line = mon.stdout.readline()
        if not line:
            if block:
                touched |= fold_block(block, cache)
            return monitor(), True
        if line.startswith("signal "):
            if block:
                touched |= fold_block(block, cache)
            block = [line]
        elif block:
            block.append(line)
    if block:
        touched |= fold_block(block, cache)
    return mon, touched


def read_device(addr):
    """One `bluetoothctl info` call, worth name, alias, icon and RSSI.

    Name/alias because a device already known to BlueZ arrives from a rescan with
    neither, and RSSI because BlueZ only re-reports it when it reads it. The RSSI
    line is "0xffa9 (-87)": the signed value is the bracketed one, and matching
    bare digits reads the leading 0 of the hex form as a 0 dBm reading.
    """
    out = {}
    try:
        text = subprocess.run(["bluetoothctl", "info", addr],
                              capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return out
    for line in text.splitlines():
        m = re.match(r"\s*(Name|Alias|RSSI|Icon):\s*(.*)$", line)
        if not m:
            continue
        key, val = m.group(1).lower(), m.group(2).strip()
        if key == "rssi":
            v = re.search(r"\((-?\d+)\)", val) or re.match(r"(?:rssi\s+)?(-?\d+)$", val)
            if v and int(v.group(1)) < 0:
                out["rssi"] = int(v.group(1))
        elif val and key not in out:
            out[key] = val
    return out


def classify(entry):
    """Normalise a recorded bond down to one word the UI can switch on.

    eww has no "contains" for strings, so matching the full Security Property
    text in yuck would also miss the unverified case that Agent.report() writes.
    Deriving the class here keeps that comparison in one place.
    """
    if not entry:
        return "unknown"
    prop = entry.get("property", "")
    if prop == AUTHENTICATED:
        return "auth"
    if prop == UNAUTHENTICATED:
        return "unauth"
    return "unverified"


def payload(cache, bz, now):
    """Merge the signal cache, the security database and live adapter state."""
    adapter = bz.adapter()
    recorded = load_db()

    conn = next((a for a, d in cache.items() if d.get("connected")), "")
    if conn:
        cache[conn].update(read_device(conn))

    devices = []
    for addr, dev in cache.items():
        entry = recorded.get(addr, {})
        rssi = dev.get("rssi", -100)
        name = (dev.get("alias") or dev.get("name") or "").strip() or addr
        devices.append({
            "addr": addr,
            "name": name,
            "paired": bool(dev.get("paired")),
            "bonded": bool(dev.get("bonded")),
            "trusted": bool(dev.get("trusted")),
            "connected": addr == conn,
            "blocked": bool(dev.get("blocked")),
            "legacy": bool(dev.get("legacypairing")),
            "rssi": rssi,
            "bucket": bucket(rssi),
            "icon": dev.get("icon", ""),
            "model": entry.get("model", ""),
            "property": entry.get("property", ""),
            "sec": classify(entry),
            "level": entry.get("level") or 0,
            "secure": bool(entry.get("secure_connections")),
        })
    devices.sort(key=lambda d: (not d["connected"], not d["bonded"], -d["rssi"]))

    return {
        "powered": adapter["powered"],
        "adapter": adapter["name"],
        "discovering": adapter["discovering"],
        "devices": devices,
    }


def stream():
    bz = Bluez()
    cache = {}
    mon = monitor()
    last = None
    while True:
        if select.select([mon.stdout], [], [], POLL)[0]:
            mon, _ = drain(mon, cache)
        # The signal never reports Pairable/Discoverable or a device's trust flag
        # changing, so the adapter is re-read every tick regardless.
        blob = json.dumps(payload(cache, bz, time.time()))
        if blob != last:
            print(blob, flush=True)
            last = blob


def cmd_connect(bz, addr):
    """Connect a bonded device. Pairing is deliberately a separate command: this
    one refuses anything not already bonded, so it can never be the thing that
    silently produces an unauthenticated key."""
    dev = find_device(bz, addr)
    if not (dev.get("Bonded") or dev.get("Paired")):
        sys.exit("%s is not bonded; run `btsec pair %s` first" % (addr, addr))
    try:
        bz.adapter_call("ConnectDevice",
                        GLib.Variant("(os)", (dev["path"], "KeyboardDisplay")), None)
        print("connecting to %s" % addr)
    except GLib.Error as exc:
        sys.exit("connect failed: %s" % exc.message)
    write_pending_if_any(addr, "connect")


def cmd_disconnect(bz, addr=None):
    path = find_device(bz, addr)["path"] if addr else None
    try:
        if path:
            bz.call(path, "org.bluez.Device1", "Disconnect", None, None)
            print("disconnected %s" % addr)
        else:
            bz.call(ADAPTER, "org.bluez.Adapter1", "DisconnectDevice", None, None)
            print("disconnected all devices")
    except GLib.Error as exc:
        sys.exit("disconnect failed: %s" % exc.message)


def write_pending_if_any(addr, op):
    db = load_db()
    entry = db.get(addr.upper())
    if not entry:
        return
    kind, _ = failure_action(entry.get("property", UNAUTHENTICATED), True)
    if kind == "auto-repair-ok":
        print("note: Table 2.9 allows re-pairing automatically for this bond, "
              "but that is a user decision here -- nothing was re-paired.")


USAGE = """usage: btsec <command> [args]

  stream                             deflisten source for the eww panel
  power on | off                     adapter power
  modes                              adapter modes, cited against GAP
  scan [--seconds N]                 discover devices to pair with
  bonds                              bonds + recorded security properties
  plan <init-io> <resp-io> [--mitm] [--legacy]
                                    what pairing would select, before doing it
  policy                             Table 2.9 failure handling
  pair <addr> --io <cap> [--peer-io <cap>] [--mitm] [--legacy]
                                    pair as the agent, recording the model used
  connect <addr>                     connect a bonded device
  disconnect [<addr>]                disconnect one device, or all
  trust <addr> | untrust <addr>      explicit trust marking
  forget <addr>                      remove the device and its record
  selftest                           self-check

  IO capabilities: %s
""" % ", ".join(IO_CAPABILITY)


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help", "help"):
        print(USAGE)
        return
    cmd, rest = args[0], args[1:]
    if cmd == "stream":
        return stream()
    if cmd == "selftest":
        return selftest()
    if cmd == "policy":
        return cmd_policy(rest)
    if cmd == "plan":
        if len(rest) < 2:
            sys.exit("plan needs <init-io> <resp-io>")
        init_io, resp_io = rest[0], rest[1]
        for cap in (init_io, resp_io):
            if cap not in IO_CAPABILITY:
                sys.exit("unknown IO capability %r; choose from %s"
                         % (cap, ", ".join(IO_CAPABILITY)))
        return cmd_plan(init_io, resp_io,
                        "--mitm" in rest, "--legacy" not in rest)
    bz = Bluez()
    if cmd == "modes":
        return cmd_modes(bz)
    if cmd == "power":
        if not rest or rest[0] not in ("on", "off"):
            sys.exit("power needs 'on' or 'off'")
        return cmd_power(bz, rest[0] == "on")
    if cmd == "scan":
        seconds = 12
        if "--seconds" in rest:
            try:
                seconds = max(1, min(120, int(rest[rest.index("--seconds") + 1])))
            except (IndexError, ValueError):
                sys.exit("--seconds needs a number")
        return cmd_scan(bz, seconds)
    if cmd == "bonds":
        return cmd_bonds(bz)
    if cmd in ("trust", "untrust"):
        if not rest:
            sys.exit("%s needs a device address" % cmd)
        return cmd_set_trusted(bz, rest[0], cmd == "trust")
    if cmd == "forget":
        if not rest:
            sys.exit("forget needs a device address")
        return cmd_forget(bz, rest[0])
    if cmd == "connect":
        if not rest:
            sys.exit("connect needs a device address")
        return cmd_connect(bz, rest[0])
    if cmd == "disconnect":
        return cmd_disconnect(bz, rest[0] if rest else None)
    if cmd == "pair":
        if not rest:
            sys.exit("pair needs a device address")
        declared = "DisplayYesNo"
        if "--io" in rest:
            declared = rest[rest.index("--io") + 1]
        if declared not in IO_CAPABILITY:
            sys.exit("--io must be one of: %s" % ", ".join(IO_CAPABILITY))
        peer = None
        if "--peer-io" in rest:
            peer = rest[rest.index("--peer-io") + 1]
            if peer not in IO_CAPABILITY:
                sys.exit("--peer-io must be one of: %s" % ", ".join(IO_CAPABILITY))
        return cmd_pair(bz, rest[0], declared, peer,
                        "--mitm" in rest, "--legacy" not in rest)
    sys.exit("unknown command %r\n\n%s" % (cmd, USAGE))


if __name__ == "__main__":
    main()
