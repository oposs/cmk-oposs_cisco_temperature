"""Parse, discovery and check functions of the three check plugins.

The string tables have the shape the SNMP fetch of the section
`oposs_cisco_sensor` delivers: five lists of rows, one per SNMPTree, with the
columns in fetch order. Values use the MIB encodings the plugin reads
(entSensorScale codes, entSensorStatus, ciscoEnvMonState, ifAdminStatus). The
IOS-XR entity rows come from the ASR 9000 walk used in
test_oposs_cisco_temperature.py.
"""

import importlib.util
import json
import pathlib
import re
import sys

import pytest
from cmk.agent_based.v2 import Metric, Result, Service, State

ROOT = pathlib.Path(__file__).resolve().parent.parent
PLUGIN = (
    ROOT
    / "local/lib/python3/cmk_addons/plugins/oposs_cisco_temperature/agent_based/oposs_cisco_temperature.py"
)


@pytest.fixture(scope="module")
def p():
    name = "test_oposs_cisco_temperature_check"
    spec = importlib.util.spec_from_file_location(name, PLUGIN)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(name, None)


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

# 0: [entPhysicalIndex, entPhysicalDescr, entPhysicalName, entPhysicalContainedIn, entPhysicalClass]
ENTITIES = [
    ["1",       "ASR 9000 Chassis",      "Rack 0",                          "0",       "3"],
    ["33569",   "SFP+ bay 0",            "0/6-SFP+ bay 0",                  "1",       "5"],
    ["4554753", "10GBASE-SR SFP Module", "TenGigE0/6/0/0",                  "33569",   "9"],
    ["4555022", "Power Sensor",          "TenGigE0/6/0/0-Tx Lane 0 Power",  "4554753", "8"],
    ["4555034", "Power Sensor",          "TenGigE0/6/0/0-Rx Lane 0 Power",  "4554753", "8"],
    ["4559000", "10GBASE-SR SFP Module", "TenGigE0/6/0/9",                  "33569",   "9"],
    ["4559118", "Power Sensor",          "TenGigE0/6/0/9-Tx Lane 0 Power",  "4559000", "8"],
    ["2375681", "3kW AC Power Module",   "0/PT0-PM0",                       "1",       "6"],
    ["2375950", "Power Sensor",          "0/PT0-PM0-Input Power",           "2375681", "8"],
    ["2375951", "Power Sensor",          "0/PT0-PM0-Output Power",          "2375681", "8"],
    ["5000",    "Temp Sensor",           "0/RSP0-Inlet",                    "1",       "8"],
    ["5001",    "Temp Sensor",           "0/RSP0-Hotspot",                  "1",       "8"],
    ["6000",    "Transceiver",           "Ethernet1/9",                     "1",       "10"],
    ["6001",    "Ethernet1/9 Transmit Power Sensor", "Ethernet1/9 Lane 1",  "6000",    "8"],
    ["6002",    "Ethernet1/9 Receive Power Sensor",  "Ethernet1/9 Lane 1",  "6000",    "8"],
    ["7000",    "Voltage Sensor",        "0/RSP0-3.3V",                     "1",       "8"],
]

# 1: [index, entSensorType, entSensorScale, entSensorPrecision, entSensorValue,
#     entSensorStatus, entSensorMeasuredEntity]
SENSORS = [
    # optics on IOS-XR: watts, scale milli(8), precision 5
    ["4555022", "6", "8", "5", "58700",  "1", "4554753"],   # 0.587 mW
    ["4555034", "6", "8", "5", "58900",  "1", "4554753"],
    ["4559118", "6", "8", "5", "0",      "1", "4559000"],   # dark optic, admin down
    # power module: watts, scale units(9), precision 2
    ["2375950", "6", "9", "2", "127037", "1", "2375681"],   # 1270.37 W
    ["2375951", "6", "9", "2", "78826",  "1", "2375681"],   # 788.26 W
    # temperatures: celsius, units, precision 0
    ["5000",    "8", "9", "0", "31",     "1", "0"],
    ["5001",    "8", "9", "0", "64",     "1", "0"],
    # native dBm optics (NX-OS style), scale milli, precision 0 -> value/1000
    ["6001",    "14", "8", "0", "-2213", "1", "6000"],
    ["6002",    "14", "8", "0", "-5120", "1", "6000"],
    # a voltage sensor: no check owns it
    ["7000",    "4", "9", "2", "330",    "1", "0"],
]

# 2: [<sensor index>.<threshold index>, entSensorThresholdValue]
THRESHOLDS = [
    # temperatures: first two rows are warn/crit, the rest is ignored
    ["5000.1", "55"], ["5000.2", "65"], ["5000.3", "0"], ["5000.4", "-5"],
    ["5001.1", "60"], ["5001.2", "70"], ["5001.3", "0"], ["5001.4", "-5"],
    # dBm, milli: upper 1.0 / 2.0 dBm, lower -9.0 / -11.0 dBm
    ["6001.1", "1000"], ["6001.2", "2000"], ["6001.3", "-9000"], ["6001.4", "-11000"],
    ["6002.1", "1000"], ["6002.2", "2000"], ["6002.3", "-9000"], ["6002.4", "-11000"],
    # optic in watts (milli, precision 5): 1.0 / 1.5 mW upper, 0.1 / 0.05 mW lower
    ["4555022.1", "100000"], ["4555022.2", "150000"], ["4555022.3", "10000"], ["4555022.4", "5000"],
    # power module: 1500 / 2000 W upper, 100 / 50 W lower
    ["2375950.1", "150000"], ["2375950.2", "200000"], ["2375950.3", "10000"], ["2375950.4", "5000"],
]

# 3: [index, ciscoEnvMonTemperatureStatusDescr, ...StatusValue, ...Threshold, ...State]
ENVMON = [
    ["1", "Intake Left, GREEN",   "27", "56", "1"],
    ["2", "Exhaust Right, YELLOW", "48", "50", "2"],
    ["3", "CPU, RED",             "73", "70", "3"],
    ["4", "Sensor without data",  "",   "",   "1"],
    ["5", "Inlet no threshold",   "29", "0",  "1"],
    ["6", "",                     "30", "60", "1"],
]

# 4: [ifDescr, ifAdminStatus]
IFACES = [
    ["TenGigE0/6/0/0", "1"],
    ["TenGigE0/6/0/9", "2"],
    ["Ethernet1/9 Lane 1", "1"],
]

TX = "Power Sensor - TenGigE0/6/0/0-Tx Lane 0 Power"
RX = "Power Sensor - TenGigE0/6/0/0-Rx Lane 0 Power"
DARK = "Power Sensor - TenGigE0/6/0/9-Tx Lane 0 Power"
PSU_IN = "Power Sensor - 0/PT0-PM0-Input Power"
PSU_OUT = "Power Sensor - 0/PT0-PM0-Output Power"
INLET = "Temp Sensor - 0/RSP0-Inlet"
HOTSPOT = "Temp Sensor - 0/RSP0-Hotspot"
NX_TX = "Ethernet1/9 Transmit Power Sensor - Ethernet1/9 Lane 1"
NX_RX = "Ethernet1/9 Receive Power Sensor - Ethernet1/9 Lane 1"


@pytest.fixture(scope="module")
def section(p):
    return p._parse_cisco_sensor([ENTITIES, SENSORS, THRESHOLDS, ENVMON, IFACES])


def _items(services):
    return sorted(s.item for s in services)


def _results(out):
    return [r for r in out if isinstance(r, Result)]


def _metrics(out):
    return {m.name: m for m in out if isinstance(m, Metric)}


def _worst(out):
    return State.worst(*(r.state for r in _results(out)))


# ---------------------------------------------------------------------------
# SNMP section definition
# ---------------------------------------------------------------------------

def _detect(spec, walk):
    """Evaluate a detect specification the way Checkmk does.

    `walk` maps OIDs to values. An OID ending in ".*" matches when any OID
    below it exists.
    """
    def value(oid):
        if oid.endswith(".*"):
            prefix = oid[:-1]
            return next((v for k, v in walk.items() if k.startswith(prefix)), None)
        return walk.get(oid)

    def atom(oid, pattern, expected):
        v = value(oid)
        if v is None:
            return not expected
        return expected is bool(re.compile(pattern, re.IGNORECASE | re.DOTALL).fullmatch(v))

    return any(all(atom(*a) for a in conj) for conj in spec)


SYSDESCR = ".1.3.6.1.2.1.1.1.0"
XR_DESCR = "Cisco IOS XR Software (ASR9K), Version 7.5.2"


@pytest.mark.parametrize(
    "walk, expected",
    [
        ({SYSDESCR: XR_DESCR, ".1.3.6.1.4.1.9.9.91.1.1.1.1.1.5000": "8"}, True),
        ({SYSDESCR: "Cisco IOS Software, C3750", ".1.3.6.1.4.1.9.9.13.1.3.1.3.1": "27"}, True),
        ({SYSDESCR: XR_DESCR}, False),
        ({SYSDESCR: "Linux router 6.1", ".1.3.6.1.4.1.9.9.91.1.1.1.1.1.5000": "8"}, False),
    ],
)
def test_detect(p, walk, expected):
    assert _detect(p.snmp_section_oposs_cisco_sensor.detect, walk) is expected


def test_fetch_columns_match_what_parse_unpacks(p):
    # parse unpacks 5, 7, 2, 5 and 2 columns from the five tables
    fetch = p.snmp_section_oposs_cisco_sensor.fetch
    assert [len(tree.oids) for tree in fetch] == [5, 7, 2, 5, 2]
    assert fetch[1].base == ".1.3.6.1.4.1.9.9.91.1.1.1.1"
    assert fetch[2].base == ".1.3.6.1.4.1.9.9.91.1.2.1.1"
    assert fetch[3].base == ".1.3.6.1.4.1.9.9.13.1.3.1"


# ---------------------------------------------------------------------------
# Parse
# ---------------------------------------------------------------------------

def test_parse_empty_tables(p):
    section = p._parse_cisco_sensor([[], [], [], [], []])
    assert section == {"8": {}}
    assert list(p._discover_temperature(section)) == []
    assert list(p._discover_dom(section)) == []
    assert list(p._discover_power(section)) == []


def test_parse_keeps_only_temperature_dbm_and_watts(section):
    assert set(section) == {"6", "8", "14"}
    assert not any("3.3V" in item for sensors in section.values() for item in sensors)


def test_parse_scales_readings(section):
    assert section["6"][PSU_IN]["reading"] == pytest.approx(1270.37)
    assert section["6"][TX]["reading"] == pytest.approx(0.000587)
    assert section["14"][NX_TX]["reading"] == pytest.approx(-2.213)
    assert section["8"][INLET]["reading"] == 31.0


def test_parse_device_levels(section):
    assert section["8"][INLET]["dev_levels"] == (55.0, 65.0)
    assert section["14"][NX_TX]["dev_levels"] == pytest.approx((1.0, 2.0, -9.0, -11.0))
    assert section["6"][PSU_IN]["dev_levels"] == pytest.approx((1500.0, 2000.0, 100.0, 50.0))
    # no thresholds for this one
    assert section["6"][PSU_OUT]["dev_levels"] is None


def test_parse_envmon(section):
    temps = section["8"]
    assert temps["Intake Left"]["reading"] == 27
    assert temps["Intake Left"]["dev_levels"] == (56, 56)
    assert temps["Exhaust Right"]["dev_state"] == (State.WARN, "warning")
    assert temps["Inlet no threshold"]["dev_levels"] is None
    assert temps["Sensor without data"]["dev_state"] == (State.UNKNOWN, "sensor defect")
    # an empty description falls back to the index
    assert "6" in temps


def test_parse_unknown_scale_and_missing_entity(p):
    # A sensor without an entPhysicalTable row is named by its index; an
    # unknown scale code counts as units.
    section = p._parse_cisco_sensor([[], [["42", "8", "99", "0", "40", "1", ""]], [], [], []])
    assert section["8"]["42"]["reading"] == 40.0
    assert section["8"]["42"]["role"] is None


def test_parse_survives_a_containment_cycle(p):
    entities = [
        ["10", "Box A", "a", "11", "9"],
        ["11", "Box B", "b", "10", "9"],
        ["12", "Power Sensor", "x", "10", "8"],
    ]
    sensors = [["12", "6", "9", "0", "250", "1", "0"]]
    section = p._parse_cisco_sensor([entities, sensors, [], [], []])
    attrs = section["6"]["Power Sensor - x"]
    assert attrs["role"] is None
    # no structure, no optical name, 250 W: the fallback says power supply
    assert p._watts_sensor_role(attrs) == "psu"


def test_parse_skips_a_threshold_row_with_an_odd_index(p):
    # A threshold index without the "<sensor>.<threshold>" shape, or with
    # more parts, is skipped; the other sensors keep their levels.
    thresholds = THRESHOLDS + [["5000", "70"], ["5001.1.9", "80"]]
    section = p._parse_cisco_sensor([ENTITIES, SENSORS, thresholds, ENVMON, IFACES])
    assert section["6"][PSU_IN]["dev_levels"] == pytest.approx((1500.0, 2000.0, 100.0, 50.0))
    assert section["8"][INLET]["dev_levels"] == (55.0, 65.0)
    assert section["8"][HOTSPOT]["dev_levels"] == (60.0, 70.0)


@pytest.mark.parametrize("bad", ["n/a", "nan", "inf", "-inf"])
def test_parse_skips_a_non_numeric_threshold_value(p, bad):
    # The broken row is dropped; with only three thresholds left the sensor
    # gets no device levels, but it is still monitored.
    thresholds = [row for row in THRESHOLDS if row[0] != "2375950.4"]
    thresholds.append(["2375950.4", bad])
    section = p._parse_cisco_sensor([ENTITIES, SENSORS, thresholds, ENVMON, IFACES])
    assert section["6"][PSU_IN]["reading"] == pytest.approx(1270.37)
    assert section["6"][PSU_IN]["dev_levels"] is None
    assert section["8"][INLET]["dev_levels"] == (55.0, 65.0)


@pytest.mark.parametrize(
    "column, bad",
    [(3, ""), (4, ""), (4, "12.5.1"), (4, "n/a"), (4, "nan"), (4, "inf"), (4, "-Infinity"), (3, "nan"), (3, "-400")],
)
def test_parse_skips_a_sensor_row_with_a_non_numeric_value(p, column, bad):
    # One sensor with an unusable entSensorPrecision or entSensorValue must
    # not take the other sensors of the device down with it.
    sensors = [list(row) for row in SENSORS]
    broken = next(row for row in sensors if row[0] == "2375951")
    broken[column] = bad
    section = p._parse_cisco_sensor([ENTITIES, sensors, THRESHOLDS, ENVMON, IFACES])
    assert PSU_OUT not in section["6"]
    assert section["6"][PSU_IN]["reading"] == pytest.approx(1270.37)
    assert _items(p._discover_power(section)) == [PSU_IN]
    assert _items(p._discover_temperature(section)) == _items(
        p._discover_temperature(p._parse_cisco_sensor([ENTITIES, SENSORS, THRESHOLDS, ENVMON, IFACES]))
    )


# Older IOS platforms leave entPhysicalName empty on sensor rows.
UNNAMED_ENTITIES = [
    ["1",    "Chassis",      "",     "0", "3"],
    ["1006", "Temp Sensor",  "",     "1", "8"],
    ["1007", "Temp Sensor",  "",     "1", "8"],
    ["1008", "Inlet Sensor", "",     "1", "8"],
    ["1009", "",             "",     "1", "8"],
    ["1010", "Temp Sensor",  "CPU",  "1", "8"],
]
UNNAMED_SENSORS = [
    ["1006", "8", "9", "0", "41", "1", "0"],
    ["1007", "8", "9", "0", "43", "2", "0"],   # unavailable: still in the group
    ["1008", "8", "9", "0", "29", "1", "0"],
    ["1009", "8", "9", "0", "35", "1", "0"],
    ["1010", "8", "9", "0", "52", "1", "0"],
]


def test_sensor_without_name_is_named_by_its_description(p):
    section = p._parse_cisco_sensor([UNNAMED_ENTITIES, UNNAMED_SENSORS, [], [], []])
    temps = section["8"]
    assert temps["Inlet Sensor"]["reading"] == 29.0
    # without description and name the index names it, as for ENVMON
    assert temps["1009"]["reading"] == 35.0
    # a sensor with a name keeps exactly its item
    assert temps["Temp Sensor - CPU"]["reading"] == 52.0
    assert not any(item.endswith(" - ") or item == "Temp Sensor" for item in temps)


def test_unnamed_sensors_with_the_same_description_get_their_index(p):
    section = p._parse_cisco_sensor([UNNAMED_ENTITIES, UNNAMED_SENSORS, [], [], []])
    temps = section["8"]
    assert temps["Temp Sensor 1006"]["reading"] == 41.0
    assert temps["Temp Sensor 1007"]["dev_state"] == (State.UNKNOWN, "unavailable")
    assert _items(p._discover_temperature(section)) == [
        "1009", "Inlet Sensor", "Temp Sensor - CPU", "Temp Sensor 1006",
    ]
    # the names do not depend on the row order of the walk
    reverse = p._parse_cisco_sensor(
        [UNNAMED_ENTITIES[::-1], UNNAMED_SENSORS[::-1], [], [], []]
    )
    assert set(reverse["8"]) == set(temps)


def test_obsolete_envmon_item_when_entity_sensor_has_the_same_index(p):
    entities = [["5000", "Temp Sensor", "Inlet", "1", "8"]]
    sensors = [["5000", "8", "9", "0", "31", "1", "0"]]
    envmon = [["5000", "Inlet, GREEN", "31", "60", "1"]]
    section = p._parse_cisco_sensor([entities, sensors, [], envmon, []])
    assert _items(p._discover_temperature(section)) == ["Temp Sensor - Inlet"]
    assert list(p._check_temperature("Inlet", {}, section)) == [
        Result(state=State.UNKNOWN, summary="Sensor obsolete, please rediscover")
    ]


# ---------------------------------------------------------------------------
# Temperature
# ---------------------------------------------------------------------------

def test_discover_temperature(p, section):
    assert _items(p._discover_temperature(section)) == sorted(
        ["6", "CPU", "Exhaust Right", "Inlet no threshold", "Intake Left",
         "Sensor without data", HOTSPOT, INLET]
    )


def test_temperature_ok_with_device_levels(p, section):
    out = list(p._check_temperature(INLET, {}, section))
    assert _worst(out) is State.OK
    assert Result(state=State.OK, summary="Temperature: 31.0 °C") in out
    m = _metrics(out)["oposs_cisco_temperature"]
    assert m.value == 31.0 and m.levels == (55.0, 65.0)


def test_temperature_warn_from_device_levels(p, section):
    out = list(p._check_temperature(HOTSPOT, {}, section))
    assert _worst(out) is State.WARN
    assert "warn/crit at 60.0 °C/70.0 °C" in _results(out)[-1].summary


def test_temperature_crit_from_user_levels(p, section):
    out = list(p._check_temperature(INLET, {"levels": ("fixed", (25.0, 30.0))}, section))
    assert _worst(out) is State.CRIT
    assert _metrics(out)["oposs_cisco_temperature"].levels == (25.0, 30.0)


def test_temperature_no_levels_switches_device_levels_off(p, section):
    out = list(p._check_temperature(HOTSPOT, {"levels": ("no_levels", None)}, section))
    assert _worst(out) is State.OK
    assert _metrics(out)["oposs_cisco_temperature"].levels == (None, None)


def test_temperature_envmon_states(p, section):
    assert _worst(p._check_temperature("Intake Left", {}, section)) is State.OK
    exhaust = list(p._check_temperature("Exhaust Right", {}, section))
    assert Result(state=State.WARN, notice="Device status: warning") in exhaust
    cpu = list(p._check_temperature("CPU", {}, section))
    assert _worst(cpu) is State.CRIT
    assert _metrics(cpu)["oposs_cisco_temperature"].value == 73


def test_temperature_envmon_without_threshold(p, section):
    out = list(p._check_temperature("Inlet no threshold", {}, section))
    assert _worst(out) is State.OK
    assert _metrics(out)["oposs_cisco_temperature"].levels == (None, None)


def test_temperature_envmon_sensor_defect(p, section):
    assert list(p._check_temperature("Sensor without data", {}, section)) == [
        Result(state=State.UNKNOWN, summary="Status: sensor defect")
    ]


def test_temperature_vanished_item(p, section):
    assert list(p._check_temperature("does not exist", {}, section)) == []


def test_temperature_reports_a_non_operational_entity_sensor(p):
    entities = [["5000", "Temp Sensor", "0/RSP0-Inlet", "1", "8"]]
    sensors = [["5000", "8", "9", "0", "0", "3", "0"]]   # nonoperational(3)
    section = p._parse_cisco_sensor([entities, sensors, [], [], []])
    assert list(p._check_temperature(INLET, {}, section)) == [
        Result(state=State.UNKNOWN, summary="Status: non-operational")
    ]


def test_non_ok_entity_sensor_is_not_discovered(p):
    # It reports its status once discovered, but a rediscovery does not add it
    entities = [["5000", "Temp Sensor", "0/RSP0-Inlet", "1", "8"]]
    sensors = [["5000", "8", "9", "0", "0", "2", "0"]]   # unavailable(2)
    section = p._parse_cisco_sensor([entities, sensors, [], [], []])
    assert list(p._discover_temperature(section)) == []


def test_non_ok_entity_sensor_keeps_the_envmon_item(p):
    # An ENVMON row with the index of a broken entity sensor stays a normal
    # service, as before; only an ok entity sensor makes it obsolete.
    entities = [["5000", "Temp Sensor", "Inlet", "1", "8"]]
    sensors = [["5000", "8", "9", "0", "0", "3", "0"]]
    envmon = [["5000", "Inlet, GREEN", "31", "60", "1"]]
    section = p._parse_cisco_sensor([entities, sensors, [], envmon, []])
    assert _items(p._discover_temperature(section)) == ["Inlet"]
    assert _worst(p._check_temperature("Inlet", {}, section)) is State.OK


# ---------------------------------------------------------------------------
# DOM
# ---------------------------------------------------------------------------

def test_discover_dom(p, section):
    # the dark optic sits on an admin-down interface; power modules are not optics
    assert _items(p._discover_dom(section)) == sorted([NX_RX, NX_TX, RX, TX])


def test_discover_dom_without_interface_table(p):
    # with no ifTable rows the admin state is unknown and the optic is kept
    section = p._parse_cisco_sensor([ENTITIES, SENSORS, [], [], []])
    assert DARK in _items(p._discover_dom(section))


def test_dom_dbm_ok(p, section):
    out = list(p._check_dom(NX_TX, {}, section))
    assert _worst(out) is State.OK
    m = _metrics(out)["oposs_cisco_output_signal_power_dbm"]
    assert m.value == pytest.approx(-2.213)
    assert m.levels == pytest.approx((1.0, 2.0))
    assert "oposs_cisco_input_signal_power_dbm" in _metrics(p._check_dom(NX_RX, {}, section))


@pytest.mark.parametrize(
    "value, state",
    [
        ("500", State.OK),        # 0.5 dBm
        ("1500", State.WARN),     # 1.5 dBm, upper warn
        ("2500", State.CRIT),     # 2.5 dBm, upper crit
        ("-9500", State.WARN),    # lower warn
        ("-12000", State.CRIT),   # lower crit
    ],
)
def test_dom_dbm_device_levels(p, value, state):
    sensors = [["6001", "14", "8", "0", value, "1", "6000"]]
    section = p._parse_cisco_sensor([ENTITIES, sensors, THRESHOLDS, [], IFACES])
    assert _worst(p._check_dom(NX_TX, {}, section)) is state


def test_dom_user_lower_levels_win(p, section):
    out = list(p._check_dom(NX_RX, {"levels_lower": ("fixed", (-4.0, -6.0))}, section))
    assert _worst(out) is State.WARN


def test_dom_watt_optic_converted_to_dbm(p, section):
    out = list(p._check_dom(TX, {}, section))
    (m,) = _metrics(out).values()
    assert m.value == pytest.approx(-2.3136, abs=1e-3)
    # 1.0 / 1.5 mW upper levels are 0 / 1.76 dBm
    assert m.levels == pytest.approx((0.0, 1.7609), abs=1e-3)
    assert Result(state=State.OK, summary="Signal power: -2.31 dBm") in out


def test_dom_dark_optic(p, section):
    out = list(p._check_dom(DARK, {}, section))
    assert Result(state=State.UNKNOWN, summary="No optical power (0 W)") in out
    assert _metrics(out) == {}


@pytest.mark.parametrize("status, text", [("2", "unavailable"), ("3", "non-operational")])
def test_dom_reports_a_non_ok_optic(p, status, text):
    sensors = [["4555022", "6", "8", "5", "0", status, "4554753"]]
    section = p._parse_cisco_sensor([ENTITIES, sensors, [], [], IFACES])
    assert list(p._discover_dom(section)) == []
    assert list(p._check_dom(TX, {}, section)) == [
        Result(state=State.UNKNOWN, summary=f"Status: {text}")
    ]


def test_dom_ignores_power_supplies(p, section):
    assert list(p._check_dom(PSU_IN, {}, section)) == []


def test_dom_metric_direction_on_ios_xr(p, section):
    assert "oposs_cisco_output_signal_power_dbm" in _metrics(p._check_dom(TX, {}, section))
    assert "oposs_cisco_input_signal_power_dbm" in _metrics(p._check_dom(RX, {}, section))


@pytest.mark.parametrize(
    "descr, name, metric",
    [
        ("Ethernet1/9(Tx-dBm)", "Ethernet1/9", "oposs_cisco_output_signal_power_dbm"),
        ("Ethernet1/9(Rx-dBm)", "Ethernet1/9", "oposs_cisco_input_signal_power_dbm"),
        ("Transmitted Power", "Gi1/0/1", "oposs_cisco_output_signal_power_dbm"),
        ("Power Sensor", "Gi1/0/1 Lane 1", "oposs_cisco_signal_power_dbm"),
    ],
)
def test_dom_metric_direction_from_description(p, descr, name, metric):
    entities = [["10", descr, name, "0", "8"]]
    sensors = [["10", "14", "8", "0", "-3000", "1", "0"]]
    section = p._parse_cisco_sensor([entities, sensors, [], [], []])
    assert list(_metrics(p._check_dom(f"{descr} - {name}", {}, section))) == [metric]


# ---------------------------------------------------------------------------
# Power supplies
# ---------------------------------------------------------------------------

def test_discover_power(p, section):
    assert _items(p._discover_power(section)) == [PSU_IN, PSU_OUT]


def test_power_ok_renders_kilowatts(p, section):
    out = list(p._check_power(PSU_IN, {}, section))
    assert _worst(out) is State.OK
    assert Result(state=State.OK, summary="Power: 1.27 kW") in out
    m = _metrics(out)["oposs_cisco_power_w"]
    assert m.value == pytest.approx(1270.37)
    assert m.levels == pytest.approx((1500.0, 2000.0))


def test_power_without_device_levels(p, section):
    out = list(p._check_power(PSU_OUT, {}, section))
    assert Result(state=State.OK, summary="Power: 788.26 W") in out
    assert _metrics(out)["oposs_cisco_power_w"].levels == (None, None)


@pytest.mark.parametrize(
    "value, state",
    [
        ("170000", State.WARN),   # 1700 W
        ("210000", State.CRIT),   # 2100 W
        ("8000", State.WARN),     # 80 W, lower warn
        ("4000", State.CRIT),     # 40 W, lower crit
    ],
)
def test_power_device_levels(p, value, state):
    sensors = [["2375950", "6", "9", "2", value, "1", "2375681"]]
    section = p._parse_cisco_sensor([ENTITIES, sensors, THRESHOLDS, [], IFACES])
    assert _worst(p._check_power(PSU_IN, {}, section)) is state


def test_power_user_levels_win(p, section):
    params = {"levels_upper": ("fixed", (1000.0, 1200.0))}
    assert _worst(p._check_power(PSU_IN, params, section)) is State.CRIT


def test_power_reports_a_non_ok_power_module(p):
    sensors = [["2375950", "6", "9", "2", "0", "3", "2375681"]]
    section = p._parse_cisco_sensor([ENTITIES, sensors, [], [], IFACES])
    assert list(p._discover_power(section)) == []
    assert list(p._check_power(PSU_IN, {}, section)) == [
        Result(state=State.UNKNOWN, summary="Status: non-operational")
    ]


def test_power_ignores_optics(p, section):
    assert list(p._check_power(TX, {}, section)) == []
    assert list(p._check_power("does not exist", {}, section)) == []


def test_plugins_share_the_section(p):
    for plugin in (
        p.check_plugin_oposs_cisco_temperature,
        p.check_plugin_oposs_cisco_dom,
        p.check_plugin_oposs_cisco_power,
    ):
        assert plugin.sections == ["oposs_cisco_sensor"]
        assert plugin.check_default_parameters == {}
    assert isinstance(next(iter(p._discover_power(p._parse_cisco_sensor(
        [ENTITIES, SENSORS, [], [], []])))), Service)


# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------

def test_check_carries_the_released_version():
    # The publish check fails on main when a version file disagrees with
    # the newest released CHANGES.md heading.
    check = ROOT / "local/lib/python3/cmk_addons/plugins/oposs_cisco_temperature/agent_based/oposs_cisco_temperature.py"
    released = re.search(r"^## (\d+\.\d+\.\d+)", (ROOT / "CHANGES.md").read_text(),
                         flags=re.MULTILINE).group(1)
    assert re.search(rf'^__version__ = "{re.escape(released)}"$', check.read_text(), flags=re.MULTILINE)


def test_release_writes_version_into_check(tmp_path):
    """Apply the version_files entry of .github/repo-infra.json to the check
    module, as Create release PR does (a multiline regex, first match)"""
    config = json.loads((ROOT / ".github/repo-infra.json").read_text())
    (spec,) = [f for f in config["version_files"] if (ROOT / f["path"]) == PLUGIN]
    stamped = re.sub(spec["pattern"], spec["replacement"].replace("$VERSION", "9.8.7"),
                     PLUGIN.read_text(), count=1, flags=re.MULTILINE)
    assert re.search(spec["verify"].replace("$VERSION", re.escape("9.8.7")), stamped, flags=re.MULTILINE)
    copy = tmp_path / "stamped_check.py"
    copy.write_text(stamped)
    module_spec = importlib.util.spec_from_file_location("stamped_check", copy)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    assert module.__version__ == "9.8.7"


def test_readme_lists_every_service(p):
    readme = (ROOT / "README.md").read_text()
    for plugin in (
        p.check_plugin_oposs_cisco_temperature,
        p.check_plugin_oposs_cisco_dom,
        p.check_plugin_oposs_cisco_power,
    ):
        assert f"| {plugin.service_name} |" in readme, plugin.service_name


def test_readme_installation_tree_lists_every_plugin_file():
    readme = (ROOT / "README.md").read_text()
    tree = readme.split("### Manual Installation", 1)[1].split("## ", 1)[0]
    plugin_dir = ROOT / "local/lib/python3/cmk_addons/plugins/oposs_cisco_temperature"
    for path in sorted(plugin_dir.rglob("*.py")):
        assert path.parent.name + "/" in tree, path.parent.name
        assert path.name in tree, path.name
