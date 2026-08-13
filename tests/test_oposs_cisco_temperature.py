#!/usr/bin/env python3
"""Standalone harness: stubs cmk.agent_based.v2 so the plugin can be exercised
without a Checkmk site. Data reconstructed from the reported services."""

import sys, types, math, enum, re, importlib.util

# ---- stub cmk.agent_based.v2 ----------------------------------------------
class State(enum.Enum):
    OK = 0; WARN = 1; CRIT = 2; UNKNOWN = 3

class Result:
    def __init__(self, state=None, summary=None, notice=None):
        self.state, self.summary, self.notice = state, summary, notice
    def __repr__(self):
        return f"Result({self.state.name}, {self.summary or self.notice!r})"

class Metric:
    def __init__(self, name, value, levels=None):
        self.name, self.value, self.levels = name, value, levels
    def __repr__(self):
        return f"Metric({self.name!r}, {self.value!r}, levels={self.levels})"

class Service:
    def __init__(self, item=None): self.item = item
    def __repr__(self): return f"Service({self.item!r})"

def check_levels(value, *, levels_upper=None, levels_lower=None,
                 metric_name=None, label=None, render_func=None, **kw):
    state = State.OK
    if levels_upper and levels_upper[0] == "fixed":
        w, c = levels_upper[1]
        if value >= c: state = State.CRIT
        elif value >= w: state = State.WARN
    if levels_lower and levels_lower[0] == "fixed" and state is State.OK:
        w, c = levels_lower[1]
        if value <= c: state = State.CRIT
        elif value <= w: state = State.WARN
    yield Result(state=state, summary=f"{label}: {render_func(value)}")
    if metric_name:
        yield Metric(metric_name, value,
                     levels=levels_upper[1] if levels_upper else None)

class _T:
    def __init__(self, *a, **k): pass
class SNMPTree(_T): pass
class SNMPSection(_T): pass
class CheckPlugin(_T): pass
def OIDEnd(): return "OIDEnd"
def OIDCached(x): return x
def all_of(*a): return a
def any_of(*a): return a
def exists(x): return x
def matches(*a): return a
render = types.SimpleNamespace()

stub = types.ModuleType("cmk.agent_based.v2")
for _n in ("State","Result","Metric","Service","check_levels","SNMPTree",
           "SNMPSection","CheckPlugin","OIDEnd","OIDCached","all_of","any_of",
           "exists","matches","render"):
    setattr(stub, _n, globals()[_n])
stub.CheckResult = stub.DiscoveryResult = object
for mod in ("cmk", "cmk.agent_based"):
    sys.modules.setdefault(mod, types.ModuleType(mod))
sys.modules["cmk.agent_based.v2"] = stub

PLUGIN = ("/home/oetiker/checkouts/cmk-oposs_cisco_temperature/local/lib/python3/"
          "cmk_addons/plugins/oposs_cisco_temperature/agent_based/"
          "oposs_cisco_temperature.py")
spec = importlib.util.spec_from_file_location("p", PLUGIN)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

# ---- test data -------------------------------------------------------------
# [index, entPhysicalDescr, entPhysicalName, entPhysicalContainedIn, entPhysicalClass]
entities = [
    ["1",    "Cisco NCS Chassis",    "Rack 0",                "0",    "3"],   # chassis
    ["500",  "3kW AC Power Module",  "0/PT0-PM0",             "1",    "6"],   # powerSupply
    ["501",  "3kW AC Power Module",  "0/PT1-PM0",             "1",    "6"],   # powerSupply
    ["1000", "Power Sensor",         "0/PT0-PM0-Input Power", "500",  "8"],
    ["1001", "Power Sensor",         "0/PT0-PM0-Output Power","500",  "8"],
    ["1002", "Power Sensor",         "0/PT1-PM0-Input Power", "501",  "8"],
    ["1500", "40GE QSFP+ port",      "TenGigE0/0/0/1",        "1",    "10"],  # port
    ["2000", "Transmit Power Sensor","TenGigE0/0/0/1",        "1500", "8"],
    ["2001", "Receive Power Sensor", "TenGigE0/0/0/1",        "1500", "8"],
    ["3000", "Ethernet1/9(Tx-dBm)",  "Ethernet1/9",           "1",    "8"],
]

# [id, entSensorType, entSensorScale, entSensorPrecision, value, status, measuredEntity]
sensors = [
    # PSU sensors, scale units(9) precision 2 -> value/100
    ["1000", "6", "9", "2", "78826",  "1", "500"],
    ["1001", "6", "9", "2", "72140",  "1", "500"],
    ["1002", "6", "9", "2", "157300", "1", "501"],
    # optical watts sensor, measuredEntity NOT populated -> must walk containedIn
    ["2000", "6", "8", "4", "7200",   "1", "0"],
    ["2001", "6", "8", "4", "3100",   "1", "0"],
    # native dBm sensor
    ["3000", "14", "8", "0", "-3487", "1", "0"],
]
thresholds = []
envmon = []
ifaces = []
string_table = [entities, sensors, thresholds, envmon, ifaces]

section = p._parse_cisco_sensor(string_table)

print("=== roles resolved from the entity tree ===")
for attrs in section.get("6", {}).values():
    print(f"  {attrs['descr']:<45} role={attrs['role']!r:<10} "
          f"reading={attrs['reading']:.6g} W  -> {p._watts_sensor_role(attrs)}")

print("\n=== discovery: Cisco DOM ===")
for s in p._discover_dom(section): print(" ", s)
print("=== discovery: Cisco Power ===")
for s in p._discover_power(section): print(" ", s)

print("\n=== check results ===")
for item in list(section.get("6", {})) + list(section.get("14", {})):
    for fn, name in ((p._check_dom, "DOM"), (p._check_power, "Power")):
        out = list(fn(item, {}, section))
        if out:
            print(f"  [{name}] {item}")
            for r in out: print(f"        {r}")

# ---- assertions ------------------------------------------------------------
psu = section["6"]["Power Sensor - 0/PT1-PM0-Input Power"]
assert psu["role"] == "psu", psu
assert abs(psu["reading"] - 1573.0) < 1e-6, psu["reading"]

opt = section["6"]["Transmit Power Sensor - TenGigE0/0/0/1"]
assert opt["role"] == "optical", opt          # via containedIn walk, measuredEntity was 0
assert abs(opt["reading"] - 0.00072) < 1e-12, opt["reading"]

dom_items = {s.item for s in p._discover_dom(section)}
pwr_items = {s.item for s in p._discover_power(section)}
assert not (dom_items & pwr_items), "a sensor landed in both checks"
assert all("PT" not in i for i in dom_items), f"PSU sensor leaked into DOM: {dom_items}"
assert len(pwr_items) == 3, pwr_items

# the reported bug: watt value must never reach a dBm metric
for item in dom_items:
    for r in p._check_dom(item, {}, section):
        if isinstance(r, Metric):
            assert r.name.endswith("_dbm"), r
            assert -40 < r.value < 30, f"{r.name}={r.value} is not a dBm value"
for item in pwr_items:
    for r in p._check_power(item, {}, section):
        if isinstance(r, Metric):
            assert r.name == "oposs_cisco_power_w", r


# ---- regression: temperature path + device thresholds ----------------------
print("\n=== regression: temperature + device thresholds ===")
entities2 = entities + [
    ["4000", "Temp Sensor", "0/RP0/CPU0 Inlet", "1", "8"],
]
sensors2 = sensors + [
    ["4000", "8",  "9", "0", "42", "1", "0"],   # 42 degC
]
# entSensorThresholdTable: "<sensorid>.<subid>" -> value
thresholds2 = [
    ["4000.1", "70"], ["4000.2", "80"], ["4000.3", "5"], ["4000.4", "0"],
    # dBm sensor thresholds, same scale/precision as sensor 3000 (milli, prec 0)
    ["3000.1", "2000"], ["3000.2", "3000"], ["3000.3", "-14000"], ["3000.4", "-16000"],
    # watts optical thresholds for sensor 2000 (scale milli, precision 4)
    ["2000.1", "12000"], ["2000.2", "15000"], ["2000.3", "1000"], ["2000.4", "500"],
]
envmon2 = [["9001", "Chassis Outlet, GREEN", "38", "75", "1"]]
section2 = p._parse_cisco_sensor([entities2, sensors2, thresholds2, envmon2, ifaces])

temps = {s.item for s in p._discover_temperature(section2)}
print("  temperature services:", sorted(temps))
for item in sorted(temps):
    for r in p._check_temperature(item, {}, section2):
        print(f"    {item}: {r}")

assert "Temp Sensor - 0/RP0/CPU0 Inlet" in temps, temps
assert "Chassis Outlet" in temps, temps

t = section2["8"]["Temp Sensor - 0/RP0/CPU0 Inlet"]
assert t["reading"] == 42.0 and t["dev_levels"] == (70.0, 80.0), t

print("\n  device thresholds converted into the check unit:")
for item in ("Ethernet1/9(Tx-dBm) - Ethernet1/9",
             "Transmit Power Sensor - TenGigE0/0/0/1"):
    for r in p._check_dom(item, {}, section2):
        if isinstance(r, Metric):
            print(f"    {item}\n      {r}")

# dBm sensor: thresholds pass through unconverted
dbm = section2["14"]["Ethernet1/9(Tx-dBm) - Ethernet1/9"]
assert dbm["dev_levels"] == (2.0, 3.0, -14.0, -16.0), dbm["dev_levels"]

# watts optical sensor: raw levels stay in watts...
optw = section2["6"]["Transmit Power Sensor - TenGigE0/0/0/1"]
assert all(math.isclose(a, b, rel_tol=1e-9) for a, b in
           zip(optw["dev_levels"], (0.0012, 0.0015, 0.0001, 0.00005))), optw["dev_levels"]
# ...and the check converts them to dBm alongside the reading
mets = [r for r in p._check_dom("Transmit Power Sensor - TenGigE0/0/0/1", {}, section2)
        if isinstance(r, Metric)]
assert mets and abs(mets[0].levels[0] - p._watt_to_dbm(0.0012)) < 1e-9, mets[0].levels

# user params must still win over device levels
mets = [r for r in p._check_dom("Ethernet1/9(Tx-dBm) - Ethernet1/9",
                                {"levels_upper": ("fixed", (1.0, 2.0))}, section2)
        if isinstance(r, Metric)]
assert mets[0].levels == (1.0, 2.0), mets[0].levels


# ---- IOS-XR / ASR 9000 entity shape ----------------------------------------
# Taken from a real ASR 9000 walk. The platform models a transceiver as
# module(9) inside an "SFP+ bay" container(5) and reserves port(10) for
# internal control-ethernet ports, so NO port(10) appears in an optic's
# containment chain. What identifies it is that the measured entity's
# entPhysicalName equals an ifDescr.
print("\n=== IOS-XR entity shape (transceiver is module(9), not port(10)) ===")
xr_entities = [
    ["1",       "ASR 9000 Chassis",       "Rack 0",                        "0",       "3"],
    ["18",      "Mgmt Ethernet Switch",   "0/RSP0-Mgmt Ethernet Switch",   "1",       "9"],
    ["101",     "Control Ethernet Port 10", "0/RSP0-CE Port 10",           "18",      "10"],  # port(10) decoy
    ["33569",   "SFP+ bay 0",             "0/6-SFP+ bay 0",                "1",       "5"],
    ["4554753", "10GBASE-SR SFP Module, Enterprise-Class", "TenGigE0/6/0/0", "33569", "9"],
    ["4555022", "Power Sensor",           "TenGigE0/6/0/0-Tx Lane 0 Power", "4554753", "8"],
    ["4555034", "Power Sensor",           "TenGigE0/6/0/0-Rx Lane 0 Power", "4554753", "8"],
    ["2375681", "3kW AC Power Module",    "0/PT0-PM0",                     "1",       "6"],
    ["2375950", "Power Sensor",           "0/PT0-PM0-Input Power",         "2375681", "8"],
    # a dark optic on an admin-down interface
    ["4559000", "10GBASE-SR SFP Module",  "TenGigE0/6/0/9",                "33569",   "9"],
    ["4559118", "Power Sensor",           "TenGigE0/6/0/9-Tx Lane 0 Power", "4559000", "8"],
]
xr_sensors = [
    ["4555022", "6", "8", "5", "58700",  "1", "4554753"],   # 0.587 mW -> -2.32 dBm
    ["4555034", "6", "8", "5", "58900",  "1", "4554753"],
    ["2375950", "6", "9", "2", "127037", "1", "2375681"],   # 1270.37 W
    ["4559118", "6", "8", "5", "0",      "1", "4559000"],   # dark optic: 0 W
]
xr_ifs = [
    ["TenGigE0/6/0/0", "1"],   # up
    ["TenGigE0/6/0/9", "2"],   # down
]
xr = p._parse_cisco_sensor([xr_entities, xr_sensors, [], [], xr_ifs])

for item, attrs in sorted(xr["6"].items()):
    print(f"  {item:<55} role={attrs['role']!r:<11} admin={attrs['admin_state']!r}")

# classification must be structural, NOT via the name regex or the magnitude
# test -- disable both and require an identical answer
saved_re, saved_max = p._OPTICAL_DESCR_RE, p._MAX_PLAUSIBLE_OPTICAL_WATTS
p._OPTICAL_DESCR_RE = re.compile(r"(?!x)x")
p._MAX_PLAUSIBLE_OPTICAL_WATTS = -1.0
try:
    xr_nofallback = p._parse_cisco_sensor([xr_entities, xr_sensors, [], [], xr_ifs])
    for item, attrs in xr["6"].items():
        assert xr_nofallback["6"][item]["role"] == attrs["role"], (
            f"{item}: classification depends on a heuristic fallback")
    dom_a = {s.item for s in p._discover_dom(xr)}
    dom_b = {s.item for s in p._discover_dom(xr_nofallback)}
    assert dom_a == dom_b, (dom_a ^ dom_b)
finally:
    p._OPTICAL_DESCR_RE, p._MAX_PLAUSIBLE_OPTICAL_WATTS = saved_re, saved_max
print("  -> classification unchanged with both heuristics disabled")

opt = xr["6"]["Power Sensor - TenGigE0/6/0/0-Tx Lane 0 Power"]
assert opt["role"] == "optical", opt          # module(9), no port(10) in chain
assert opt["admin_state"] == "up", opt        # joined to ifDescr

psu = xr["6"]["Power Sensor - 0/PT0-PM0-Input Power"]
assert psu["role"] == "psu" and psu["admin_state"] is None, psu

# admin-down interfaces must not be discovered as DOM services
dark = "Power Sensor - TenGigE0/6/0/9-Tx Lane 0 Power"
assert xr["6"][dark]["admin_state"] == "down", xr["6"][dark]
assert dark not in {s.item for s in p._discover_dom(xr)}, "admin-down optic discovered"

# a 0 W optic must not render as "nan dBm"
res = [r for r in p._check_dom(dark, {}, xr) if getattr(r, "summary", None)]
assert any("No optical power" in r.summary for r in res), res
print(f"  -> dark optic reports: {[r.summary for r in res if r.summary][-1]!r}")

print("\nALL ASSERTIONS PASSED")
