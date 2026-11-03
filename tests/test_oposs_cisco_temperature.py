"""Watt sensor classification, device thresholds and the IOS-XR entity shape.

The data was reconstructed from the services reported on real devices; the
IOS-XR block is taken from an ASR 9000 walk. The string tables have the shape
the SNMP fetch delivers: one list of rows per SNMPTree, in fetch order.
"""

import importlib.util
import math
import pathlib
import re
import sys

import pytest

from cmk.agent_based.v2 import Metric

ROOT = pathlib.Path(__file__).resolve().parent.parent
PLUGIN = (
    ROOT
    / "local/lib/python3/cmk_addons/plugins/oposs_cisco_temperature/agent_based/oposs_cisco_temperature.py"
)


@pytest.fixture(scope="module")
def p():
    name = "test_oposs_cisco_temperature_classification"
    spec = importlib.util.spec_from_file_location(name, PLUGIN)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(name, None)


# [index, entPhysicalDescr, entPhysicalName, entPhysicalContainedIn, entPhysicalClass]
ENTITIES = [
    ["1",    "Cisco NCS Chassis",    "Rack 0",                "0",    "3"],   # chassis
    ["500",  "3kW AC Power Module",  "0/PT0-PM0",             "1",    "6"],   # powerSupply
    ["501",  "3kW AC Power Module",  "0/PT1-PM0",             "1",    "6"],   # powerSupply
    ["1000", "Power Sensor",         "0/PT0-PM0-Input Power", "500",  "8"],
    ["1001", "Power Sensor",         "0/PT0-PM0-Output Power", "500", "8"],
    ["1002", "Power Sensor",         "0/PT1-PM0-Input Power", "501",  "8"],
    ["1500", "40GE QSFP+ port",      "TenGigE0/0/0/1",        "1",    "10"],  # port
    ["2000", "Transmit Power Sensor", "TenGigE0/0/0/1",       "1500", "8"],
    ["2001", "Receive Power Sensor", "TenGigE0/0/0/1",        "1500", "8"],
    ["3000", "Ethernet1/9(Tx-dBm)",  "Ethernet1/9",           "1",    "8"],
]

# [id, entSensorType, entSensorScale, entSensorPrecision, value, status, measuredEntity]
SENSORS = [
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

ENTITIES2 = ENTITIES + [
    ["4000", "Temp Sensor", "0/RP0/CPU0 Inlet", "1", "8"],
]
SENSORS2 = SENSORS + [
    ["4000", "8", "9", "0", "42", "1", "0"],   # 42 degC
]
# entSensorThresholdTable: "<sensorid>.<subid>" -> value
THRESHOLDS2 = [
    ["4000.1", "70"], ["4000.2", "80"], ["4000.3", "5"], ["4000.4", "0"],
    # dBm sensor thresholds, same scale/precision as sensor 3000 (milli, prec 0)
    ["3000.1", "2000"], ["3000.2", "3000"], ["3000.3", "-14000"], ["3000.4", "-16000"],
    # watts optical thresholds for sensor 2000 (scale milli, precision 4)
    ["2000.1", "12000"], ["2000.2", "15000"], ["2000.3", "1000"], ["2000.4", "500"],
]
ENVMON2 = [["9001", "Chassis Outlet, GREEN", "38", "75", "1"]]

# IOS-XR / ASR 9000 entity shape. The platform models a transceiver as
# module(9) inside an "SFP+ bay" container(5) and reserves port(10) for
# internal control-ethernet ports, so NO port(10) appears in an optic's
# containment chain. What identifies it is that the measured entity's
# entPhysicalName equals an ifDescr.
XR_ENTITIES = [
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
XR_SENSORS = [
    ["4555022", "6", "8", "5", "58700",  "1", "4554753"],   # 0.587 mW -> -2.32 dBm
    ["4555034", "6", "8", "5", "58900",  "1", "4554753"],
    ["2375950", "6", "9", "2", "127037", "1", "2375681"],   # 1270.37 W
    ["4559118", "6", "8", "5", "0",      "1", "4559000"],   # dark optic: 0 W
]
XR_IFS = [
    ["TenGigE0/6/0/0", "1"],   # up
    ["TenGigE0/6/0/9", "2"],   # down
]
DARK = "Power Sensor - TenGigE0/6/0/9-Tx Lane 0 Power"


@pytest.fixture(scope="module")
def section(p):
    return p._parse_cisco_sensor([ENTITIES, SENSORS, [], [], []])


@pytest.fixture(scope="module")
def section2(p):
    return p._parse_cisco_sensor([ENTITIES2, SENSORS2, THRESHOLDS2, ENVMON2, []])


@pytest.fixture(scope="module")
def xr(p):
    return p._parse_cisco_sensor([XR_ENTITIES, XR_SENSORS, [], [], XR_IFS])


def _metrics(results):
    return [r for r in results if isinstance(r, Metric)]


# ---- watt sensors: PSU or optic --------------------------------------------

def test_psu_sensor_resolves_to_psu(section):
    psu = section["6"]["Power Sensor - 0/PT1-PM0-Input Power"]
    assert psu["role"] == "psu", psu
    assert abs(psu["reading"] - 1573.0) < 1e-6, psu["reading"]


def test_optic_resolves_by_walking_contained_in(section):
    # measuredEntity is 0, so the role comes from the containedIn walk
    opt = section["6"]["Transmit Power Sensor - TenGigE0/0/0/1"]
    assert opt["role"] == "optical", opt
    assert abs(opt["reading"] - 0.00072) < 1e-12, opt["reading"]


def test_no_sensor_lands_in_both_checks(p, section):
    dom_items = {s.item for s in p._discover_dom(section)}
    pwr_items = {s.item for s in p._discover_power(section)}
    assert not (dom_items & pwr_items), "a sensor landed in both checks"
    assert all("PT" not in i for i in dom_items), f"PSU sensor leaked into DOM: {dom_items}"
    assert len(pwr_items) == 3, pwr_items


def test_watt_value_never_reaches_a_dbm_metric(p, section):
    for item in {s.item for s in p._discover_dom(section)}:
        for m in _metrics(p._check_dom(item, {}, section)):
            assert m.name.endswith("_dbm"), m
            assert -40 < m.value < 30, f"{m.name}={m.value} is not a dBm value"
    for item in {s.item for s in p._discover_power(section)}:
        for m in _metrics(p._check_power(item, {}, section)):
            assert m.name == "oposs_cisco_power_w", m


# ---- temperature path and device thresholds --------------------------------

def test_entity_and_envmon_temperatures_are_discovered(p, section2):
    temps = {s.item for s in p._discover_temperature(section2)}
    assert "Temp Sensor - 0/RP0/CPU0 Inlet" in temps, temps
    assert "Chassis Outlet" in temps, temps


def test_entity_temperature_reading_and_levels(section2):
    t = section2["8"]["Temp Sensor - 0/RP0/CPU0 Inlet"]
    assert t["reading"] == 42.0 and t["dev_levels"] == (70.0, 80.0), t


def test_dbm_thresholds_pass_through_unconverted(section2):
    dbm = section2["14"]["Ethernet1/9(Tx-dBm) - Ethernet1/9"]
    assert dbm["dev_levels"] == (2.0, 3.0, -14.0, -16.0), dbm["dev_levels"]


def test_optical_watt_thresholds_are_converted_to_dbm(p, section2):
    optw = section2["6"]["Transmit Power Sensor - TenGigE0/0/0/1"]
    # the parsed levels stay in watts ...
    assert all(
        math.isclose(a, b, rel_tol=1e-9)
        for a, b in zip(optw["dev_levels"], (0.0012, 0.0015, 0.0001, 0.00005))
    ), optw["dev_levels"]
    # ... and the check converts them to dBm alongside the reading
    mets = _metrics(p._check_dom("Transmit Power Sensor - TenGigE0/0/0/1", {}, section2))
    assert mets and abs(mets[0].levels[0] - p._watt_to_dbm(0.0012)) < 1e-9, mets[0].levels


def test_user_params_win_over_device_levels(p, section2):
    mets = _metrics(
        p._check_dom(
            "Ethernet1/9(Tx-dBm) - Ethernet1/9",
            {"levels_upper": ("fixed", (1.0, 2.0))},
            section2,
        )
    )
    assert mets[0].levels == (1.0, 2.0), mets[0].levels


# ---- IOS-XR entity shape (transceiver is module(9), not port(10)) ----------

def test_xr_classification_needs_no_heuristic(p, xr, monkeypatch):
    # Classification must be structural, not via the name regex or the
    # magnitude test: disable both and require an identical answer.
    monkeypatch.setattr(p, "_OPTICAL_DESCR_RE", re.compile(r"(?!x)x"))
    monkeypatch.setattr(p, "_MAX_PLAUSIBLE_OPTICAL_WATTS", -1.0)
    xr_nofallback = p._parse_cisco_sensor([XR_ENTITIES, XR_SENSORS, [], [], XR_IFS])
    for item, attrs in xr["6"].items():
        assert xr_nofallback["6"][item]["role"] == attrs["role"], (
            f"{item}: classification depends on a heuristic fallback"
        )
    dom_b = {s.item for s in p._discover_dom(xr_nofallback)}
    monkeypatch.undo()
    dom_a = {s.item for s in p._discover_dom(xr)}
    assert dom_a == dom_b, dom_a ^ dom_b


def test_xr_optic_joined_to_its_interface(xr):
    opt = xr["6"]["Power Sensor - TenGigE0/6/0/0-Tx Lane 0 Power"]
    assert opt["role"] == "optical", opt          # module(9), no port(10) in chain
    assert opt["admin_state"] == "up", opt        # joined to ifDescr


def test_xr_psu(xr):
    psu = xr["6"]["Power Sensor - 0/PT0-PM0-Input Power"]
    assert psu["role"] == "psu" and psu["admin_state"] is None, psu


def test_xr_admin_down_optic_is_not_discovered(p, xr):
    assert xr["6"][DARK]["admin_state"] == "down", xr["6"][DARK]
    assert DARK not in {s.item for s in p._discover_dom(xr)}, "admin-down optic discovered"


def test_xr_dark_optic_is_not_nan_dbm(p, xr):
    res = [r for r in p._check_dom(DARK, {}, xr) if getattr(r, "summary", None)]
    assert any("No optical power" in r.summary for r in res), res
