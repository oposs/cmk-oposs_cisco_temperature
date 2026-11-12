# Copyright (C) 2025 OETIKER+PARTNER AG - License: GNU General Public License v2

"""
Enhanced Cisco temperature, DOM and power check.
v2 rewrite of legacy cisco_temperature override.

Provides:
- Improved sensor descriptions (entPhysicalDescr + entPhysicalName)
- Temperature monitoring with device-provided thresholds
- DOM monitoring for optical transceiver power (dBm)
- Power supply monitoring for power modules (watts)

Watts sensors (entSensorType 6) are ambiguous: an optical transceiver and a
power supply both report watts. They are told apart structurally rather than
by name -- see _resolve_sensor_role().
"""

import math
import re
from collections import Counter

from cmk.agent_based.v2 import (
    CheckPlugin,
    CheckResult,
    DiscoveryResult,
    OIDCached,
    OIDEnd,
    Result,
    Service,
    SNMPSection,
    SNMPTree,
    State,
    all_of,
    any_of,
    check_levels,
    exists,
    matches,
)

# Create release PR writes the released version here (version_files in
# .github/repo-infra.json)
__version__ = "0.5.0"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# CISCO-ENTITY-SENSOR-MIB entSensorType
_SENSOR_TYPES = {
    "1": "other", "2": "unknown", "3": "voltsAC", "4": "voltsDC",
    "5": "amperes", "6": "watts", "7": "hertz", "8": "celsius",
    "9": "parentRH", "10": "rpm", "11": "cmm", "12": "truthvalue",
    "13": "specialEnum", "14": "dBm",
}

# CISCO-ENTITY-SENSOR-MIB::entSensorScale exponents
_SCALE_EXPONENTS = {
    "1": -24, "2": -21, "3": -18, "4": -15, "5": -12, "6": -9,
    "7": -6, "8": -3, "9": 0, "10": 3, "11": 6, "12": 9,
    "13": 12, "14": 18, "15": 15, "16": 21, "17": 24,
}

# CISCO-ENTITY-SENSOR-MIB::entSensorStatus
_ENTITY_STATES = {
    "1": (State.OK, "OK"),
    "2": (State.UNKNOWN, "unavailable"),
    "3": (State.UNKNOWN, "non-operational"),
}

# CISCO-ENVMON-MIB states
_ENVMON_STATES = {
    "1": (State.OK, "normal"),
    "2": (State.WARN, "warning"),
    "3": (State.CRIT, "critical"),
    "4": (State.CRIT, "shutdown"),
    "5": (State.UNKNOWN, "not present"),
    "6": (State.CRIT, "not functioning"),
}

_ADMIN_STATE_MAP = {"1": "up", "2": "down", "3": "testing"}

# ENTITY-MIB entPhysicalClass. A sensor row is always class sensor(8); the
# class that matters is the one of the entity the sensor measures.
_CLASS_POWER_SUPPLY = "6"
_CLASS_PORT = "10"

# Depth limit for the entPhysicalContainedIn walk. The MIB guarantees a strict
# hierarchy, but a broken agent could still hand us a cycle.
_MAX_CONTAINMENT_DEPTH = 16

# Last-resort naming patterns for optical power, used only when the device
# exposes no usable entity class. Deliberately narrow: a power supply's
# "Input Power" / "Output Power" must not match.
_OPTICAL_DESCR_RE = re.compile(
    r"(?i)(?:\b(?:transmit|receive)\b|\b(?:tx|rx)\b|\((?:tx|rx)-)"
)

# Direction of an optical sensor, for the metric name.
_TRANSMIT_DESCR_RE = re.compile(r"Transmit|(?i:\btx\b)")
_RECEIVE_DESCR_RE = re.compile(r"Receive|(?i:\brx\b)")

# Optical power above this many watts is implausible for a transceiver, so a
# watts sensor exceeding it is treated as a power supply when nothing else
# identifies it. Only reached when both the entity class and the name are
# uninformative.
_MAX_PLAUSIBLE_OPTICAL_WATTS = 1.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cisco_sensor_item(description, sensor_id):
    """Create item name from ENVMON status description."""
    for color in ("GREEN", "YELLOW", "RED"):
        suffix = ", " + color
        if description.endswith(suffix):
            description = description[:-len(suffix)]
            break
    return description.strip() or str(sensor_id)


def _finite_float(text):
    """float() that also rejects "nan" and "inf", which no sensor reports."""
    number = float(text)
    if not math.isfinite(number):
        raise ValueError(f"not a finite number: {text!r}")
    return number


def _watt_to_dbm(watt):
    """Convert watts to dBm."""
    if watt <= 0:
        return float("nan")
    return 10.0 * math.log10(watt) + 30.0


def _resolve_sensor_role(sensor_id, measured_entity, entities, if_admin_states):
    """Determine what a sensor measures from the ENTITY-MIB containment tree.

    entSensorMeasuredEntity points at the entPhysicalIndex of the measured
    entity -- for a power supply sensor, the power supply itself. The MIB
    allows a value of 0 when no such row exists, and not every Cisco platform
    populates it, so fall back to walking entPhysicalContainedIn upwards from
    the sensor's own row.

    entPhysicalClass alone is not enough to recognise an optic. IOS-XR models
    a transceiver as module(9) inside an "SFP+ bay" container(5) and reserves
    port(10) for internal control-ethernet ports, so an ASR 9000 transceiver
    has no port(10) anywhere in its containment chain. What does identify it
    is that the measured entity's entPhysicalName is an interface: on that
    platform the transceiver entity is named e.g. "TenGigE0/6/0/0", matching
    ifDescr exactly. That join also yields the interface's admin state.

    Returns a (role, interface_name) pair; role is "psu", "optical" or None
    when the tree is uninformative, and interface_name is None unless the
    sensor was matched to an interface.
    """
    index = measured_entity if measured_entity not in (None, "", "0") else sensor_id

    seen = set()
    for _ in range(_MAX_CONTAINMENT_DEPTH):
        if index in (None, "", "0") or index in seen:
            break
        seen.add(index)
        entity = entities.get(index)
        if entity is None:
            break
        if entity["class"] == _CLASS_POWER_SUPPLY:
            return "psu", None
        if entity["name"] and entity["name"] in if_admin_states:
            return "optical", entity["name"]
        if entity["class"] == _CLASS_PORT:
            return "optical", None
        index = entity["parent"]

    return None, None


def _watts_sensor_role(attrs):
    """Classify a watts sensor as optical transceiver power or supply power.

    Structure first (authoritative), then naming, then magnitude. The last two
    only apply to devices that expose no usable entPhysicalClass.
    """
    if attrs.get("role"):
        return attrs["role"]

    if _OPTICAL_DESCR_RE.search(attrs.get("descr", "")):
        return "optical"

    reading = attrs.get("reading")
    if reading is not None and 0 < reading < _MAX_PLAUSIBLE_OPTICAL_WATTS:
        return "optical"

    return "psu"


def _sensor_service(sensortype, attrs):
    """Name the service a sensor ends up in: "temp", "dom" or "power"."""
    if sensortype == "celsius":
        return "temp"
    if sensortype == "dBm" or _watts_sensor_role(attrs) == "optical":
        return "dom"
    return "power"


# ---------------------------------------------------------------------------
# Parse function
# ---------------------------------------------------------------------------

def _parse_cisco_sensor(string_table):
    """Parse 5 SNMP tables into structured sensor data.

    Returns: {sensor_type_id: {item_name: {attrs}}}
    """
    description_info = string_table[0]
    state_info = string_table[1]
    levels_info = string_table[2]
    perfstuff = string_table[3]
    admin_states = string_table[4]

    # 1. Build descriptions and the entity tree used to classify sensors
    #    Older IOS platforms leave entPhysicalName empty on sensor rows; such
    #    a sensor is named by its description, or by its index when that is
    #    empty too, as for ENVMON.
    descriptions = {}
    entities = {}
    for index, descr, name, parent, phys_class in description_info:
        if name:
            descriptions[index] = descr + " - " + name
        else:
            descriptions[index] = descr or index
        entities[index] = {"name": name, "parent": parent, "class": phys_class}

    # 2. Interface admin states, keyed by ifDescr so a sensor can be joined to
    #    its interface through the measured entity's entPhysicalName. Matching
    #    on the item description instead would never fire: that string starts
    #    with entPhysicalDescr ("Power Sensor - ..."), not with the interface.
    if_admin_states = {
        if_name: _ADMIN_STATE_MAP.get(admin_state)
        for if_name, admin_state in admin_states
        if if_name
    }

    # 3. Build thresholds: sensor_id -> [level, ...]
    thresholds = {}
    for row in state_info:
        thresholds.setdefault(row[0], [])
    for row in levels_info:
        # One malformed row must not cost the device all its other sensors.
        try:
            sensor_id, _subid = row[0].split(".")
            _finite_float(row[1])
        except ValueError:
            continue
        thresholds.setdefault(sensor_id, []).append(row[1])

    # 4. Parse entity sensors (CISCO-ENTITY-SENSOR-MIB)
    #    Sensors that share a description (and name, if any) and end up in
    #    the same service would share an item, so every member of such a
    #    group gets its index appended; a sensor whose item is unique keeps
    #    it. The group is counted over all rows, whatever their status, so
    #    that a name does not change when a sibling sensor fails. It is
    #    counted per service, as "Cisco DOM" holds both dBm and optical watts
    #    sensors, and per type, as the section keeps optical and power supply
    #    watts sensors in one table.
    item_counts = Counter()
    entity_parsed = {}
    for (
        sensor_id,
        sensortype_id,
        scalecode,
        magnitude,
        value,
        sensorstate,
        measured_entity,
    ) in state_info:
        sensortype = _SENSOR_TYPES.get(sensortype_id)
        if sensortype not in ("dBm", "celsius", "watts"):
            continue

        descr = descriptions.get(sensor_id, sensor_id)
        if not descr:
            continue

        role, interface = _resolve_sensor_role(
            sensor_id, measured_entity, entities, if_admin_states
        )

        reading = None
        if sensorstate == "1":
            try:
                factor = 10.0 ** (_SCALE_EXPONENTS.get(scalecode, 0) - _finite_float(magnitude))
                reading = _finite_float(value) * factor
                if not math.isfinite(reading):
                    raise ValueError(reading)
            except (ValueError, OverflowError):
                reading = None
        service = _sensor_service(sensortype, {"role": role, "descr": descr, "reading": reading})
        item_counts[(service, descr)] += 1
        item_counts[(sensortype_id, descr)] += 1
        if sensorstate == "1" and reading is None:
            # Skip this sensor rather than fail the whole section.
            continue

        entity_parsed.setdefault(sensortype_id, {})
        dev_state = _ENTITY_STATES.get(sensorstate, (State.UNKNOWN, f"unknown[{sensorstate}]"))

        sensor_attrs = {
            "descr": descr,
            "raw_dev_state": sensorstate,
            "dev_state": dev_state,
            "admin_state": if_admin_states.get(interface) if interface else None,
            "role": role,
        }

        if sensorstate == "1":
            sensor_attrs["reading"] = reading

            dev_levels = None
            sensor_thresholds = thresholds.get(sensor_id, [])
            if sensortype in ("dBm", "watts") and len(sensor_thresholds) == 4:
                # Two lower and two upper bounds, in the sensor's own unit.
                converted = sorted(float(t) * factor for t in sensor_thresholds)
                dev_levels = (converted[2], converted[3], converted[1], converted[0])
            elif sensortype == "celsius" and len(sensor_thresholds) == 4:
                raw_w, raw_c = float(sensor_thresholds[0]) * factor, float(sensor_thresholds[1]) * factor
                dev_levels = (min(raw_w, raw_c), max(raw_w, raw_c))

            sensor_attrs["dev_levels"] = dev_levels

        # Keep a sensor that is not ok(1) too: its service reports the device
        # status instead of vanishing.
        entity_parsed[sensortype_id].setdefault(sensor_id, sensor_attrs)

    # 5. ENVMON temperatures (CISCO-ENVMON-MIB). A row with the index of an
    #    ok entity temperature sensor is that sensor: it takes the entity
    #    item, and the item of its own description stays behind as obsolete.
    #    Any other row is named by its description and counts towards the
    #    entity temperature groups above; a colliding row gets " ENVMON
    #    <index>" appended, as the ENVMON and entity indexes may coincide.
    found_temp_sensors = {
        sensor_id: attrs
        for sensor_id, attrs in entity_parsed.get("8", {}).items()
        if attrs["raw_dev_state"] == "1"
    }
    envmon_rows = []
    for sensor_id, statustext, temp, max_temp, state in perfstuff:
        own_item = _cisco_sensor_item(statustext, sensor_id)
        matched = sensor_id in descriptions and sensor_id in found_temp_sensors
        if not matched:
            item_counts[("temp", own_item)] += 1
        envmon_rows.append((sensor_id, own_item, matched, temp, max_temp, state))

    for sensortype_id, sensors in entity_parsed.items():
        for sensor_id, sensor_attrs in sensors.items():
            descr = sensor_attrs["descr"]
            service = _sensor_service(_SENSOR_TYPES[sensortype_id], sensor_attrs)
            if item_counts[(service, descr)] > 1 or item_counts[(sensortype_id, descr)] > 1:
                sensor_attrs["descr"] = f"{descr} {sensor_id}"

    parsed = {}
    temp_sensors = parsed.setdefault("8", {})
    obsolete_items = []

    for sensor_id, own_item, matched, temp, max_temp, state in envmon_rows:
        if matched:
            item = found_temp_sensors[sensor_id]["descr"]
            obsolete_items.append(own_item)
        elif item_counts[("temp", own_item)] > 1:
            item = f"{own_item} ENVMON {sensor_id}"
        else:
            item = own_item

        sensor_attrs = {
            "raw_dev_state": state,
            "dev_state": _ENVMON_STATES.get(state, (State.UNKNOWN, f"unknown[{state}]")),
        }
        try:
            sensor_attrs["reading"] = int(temp)
            if max_temp and int(max_temp):
                sensor_attrs["dev_levels"] = (int(max_temp), int(max_temp))
            else:
                sensor_attrs["dev_levels"] = None
        except (ValueError, TypeError):
            sensor_attrs["dev_state"] = (State.UNKNOWN, "sensor defect")

        temp_sensors.setdefault(item, sensor_attrs)

    # 6. Merge entity sensors into parsed
    for sensor_type, sensors in entity_parsed.items():
        for sensor_attrs in sensors.values():
            parsed.setdefault(sensor_type, {}).setdefault(sensor_attrs["descr"], sensor_attrs)

    # 7. An obsolete item yields to a sensor that is named the same.
    for item in obsolete_items:
        temp_sensors.setdefault(item, {"obsolete": True})

    return parsed


# ---------------------------------------------------------------------------
# SNMP Section
# ---------------------------------------------------------------------------

snmp_section_oposs_cisco_sensor = SNMPSection(
    name="oposs_cisco_sensor",
    detect=all_of(
        matches(".1.3.6.1.2.1.1.1.0", "(?i).*cisco.*"),
        any_of(
            exists(".1.3.6.1.4.1.9.9.91.1.1.1.1.*"),
            exists(".1.3.6.1.4.1.9.9.13.1.3.1.3.*"),
        ),
    ),
    parse_function=_parse_cisco_sensor,
    fetch=[
        # 0: Entity descriptions and containment tree
        #    2 = entPhysicalDescr, 7 = entPhysicalName,
        #    4 = entPhysicalContainedIn, 5 = entPhysicalClass
        SNMPTree(
            base=".1.3.6.1.2.1.47.1.1.1.1",
            oids=[
                OIDEnd(),
                OIDCached("2"),
                OIDCached("7"),
                OIDCached("4"),
                OIDCached("5"),
            ],
        ),
        # 1: Entity sensor data (8 = entSensorMeasuredEntity)
        SNMPTree(
            base=".1.3.6.1.4.1.9.9.91.1.1.1.1",
            oids=[OIDEnd(), "1", "2", "3", "4", "5", "8"],
        ),
        # 2: Sensor thresholds
        SNMPTree(
            base=".1.3.6.1.4.1.9.9.91.1.2.1.1",
            oids=[OIDEnd(), "4"],
        ),
        # 3: ENVMON temperature data
        SNMPTree(
            base=".1.3.6.1.4.1.9.9.13.1.3.1",
            oids=[OIDEnd(), "2", "3", "4", "6"],
        ),
        # 4: IF admin states (no OIDEnd - columns only)
        SNMPTree(
            base=".1.3.6.1.2.1.2.2.1",
            oids=[OIDCached("2"), OIDCached("7")],
        ),
    ],
)


# ---------------------------------------------------------------------------
# Temperature check
# ---------------------------------------------------------------------------

def _discover_temperature(section) -> DiscoveryResult:
    for item, attrs in section.get("8", {}).items():
        if attrs.get("obsolete", False):
            continue
        # An entity sensor (it has a "descr") is discovered only while ok(1);
        # ENVMON sensors are discovered in any state.
        if "descr" in attrs and attrs["raw_dev_state"] != "1":
            continue
        yield Service(item=item)


def _check_temperature(item, params, section) -> CheckResult:
    temp_parsed = section.get("8", {})
    if item not in temp_parsed:
        return

    data = temp_parsed[item]
    if data.get("obsolete", False):
        yield Result(state=State.UNKNOWN, summary="Sensor obsolete, please rediscover")
        return

    dev_state, state_readable = data["dev_state"]
    reading = data.get("reading")
    if reading is None:
        yield Result(state=dev_state, summary=f"Status: {state_readable}")
        return

    # Device state
    yield Result(state=dev_state, notice=f"Device status: {state_readable}")

    # User-configured levels override device thresholds
    levels_upper = params.get("levels")
    if levels_upper is None:
        dev_levels = data.get("dev_levels")
        levels_upper = ("fixed", (dev_levels[0], dev_levels[1])) if dev_levels else None

    yield from check_levels(
        reading,
        levels_upper=levels_upper,
        metric_name="oposs_cisco_temperature",
        label="Temperature",
        render_func=lambda v: f"{v:.1f} \u00b0C",
    )


check_plugin_oposs_cisco_temperature = CheckPlugin(
    name="oposs_cisco_temperature",
    sections=["oposs_cisco_sensor"],
    service_name="Cisco Temp %s",
    discovery_function=_discover_temperature,
    check_function=_check_temperature,
    check_ruleset_name="oposs_cisco_temperature_params",
    check_default_parameters={},
)


# ---------------------------------------------------------------------------
# DOM check
# ---------------------------------------------------------------------------

def _dom_sensors(section):
    """Yield (item, attrs) for every optical sensor.

    dBm sensors (type 14) are optical by definition. Watts sensors (type 6)
    only qualify once the entity tree says they belong to a port.
    """
    for item, attrs in section.get("14", {}).items():
        yield item, attrs, "dBm"
    for item, attrs in section.get("6", {}).items():
        if _watts_sensor_role(attrs) == "optical":
            yield item, attrs, "W"


def _discover_dom(section) -> DiscoveryResult:
    for item, attrs, _unit in _dom_sensors(section):
        if attrs.get("raw_dev_state") == "1":
            admin = attrs.get("admin_state")
            if admin in ("up", None):
                yield Service(item=item)


def _levels_from_params_or_device(params, dev_levels):
    """Resolve upper/lower levels, user configuration winning over the device."""
    dev_levels = dev_levels or (None, None, None, None)

    levels_upper = params.get("levels_upper")
    if levels_upper is None and dev_levels[0] is not None and dev_levels[1] is not None:
        levels_upper = ("fixed", (dev_levels[0], dev_levels[1]))

    levels_lower = params.get("levels_lower")
    if levels_lower is None and dev_levels[2] is not None and dev_levels[3] is not None:
        levels_lower = ("fixed", (dev_levels[2], dev_levels[3]))

    return levels_upper, levels_lower


def _check_dom(item, params, section) -> CheckResult:
    for candidate, attrs, unit in _dom_sensors(section):
        if candidate == item:
            data, native_unit = attrs, unit
            break
    else:
        return

    dev_state, state_readable = data["dev_state"]
    reading = data.get("reading")
    if reading is None:
        yield Result(state=dev_state, summary=f"Status: {state_readable}")
        return

    yield Result(state=dev_state, notice=f"Device status: {state_readable}")

    dev_levels = data.get("dev_levels")

    # Optical power is always reported in dBm, whatever unit the sensor used.
    if native_unit == "W":
        reading = _watt_to_dbm(reading)
        if dev_levels:
            dev_levels = tuple(
                _watt_to_dbm(level) if level is not None else None for level in dev_levels
            )

    if not math.isfinite(reading):
        # A transceiver reporting exactly 0 W has no light on that lane; dBm
        # is undefined for it. Say so rather than printing "nan dBm".
        yield Result(state=State.UNKNOWN, summary="No optical power (0 W)")
        return

    # Direction has no representation in the entity tree -- the name is the
    # only source for it, and it affects the metric name alone.
    # IOS-XR names its lanes "...-Tx Lane 0 Power" / "...-Rx Lane 0 Power".
    descr = data.get("descr", "")
    if _TRANSMIT_DESCR_RE.search(descr):
        dsname = "oposs_cisco_output_signal_power_dbm"
    elif _RECEIVE_DESCR_RE.search(descr):
        dsname = "oposs_cisco_input_signal_power_dbm"
    else:
        dsname = "oposs_cisco_signal_power_dbm"

    levels_upper, levels_lower = _levels_from_params_or_device(params, dev_levels)

    yield from check_levels(
        reading,
        levels_upper=levels_upper,
        levels_lower=levels_lower,
        metric_name=dsname,
        label="Signal power",
        render_func=lambda v: f"{v:.2f} dBm",
    )


check_plugin_oposs_cisco_dom = CheckPlugin(
    name="oposs_cisco_dom",
    sections=["oposs_cisco_sensor"],
    service_name="Cisco DOM %s",
    discovery_function=_discover_dom,
    check_function=_check_dom,
    check_ruleset_name="oposs_cisco_dom_params",
    check_default_parameters={},
)


# ---------------------------------------------------------------------------
# Power supply check
# ---------------------------------------------------------------------------

def _discover_power(section) -> DiscoveryResult:
    for item, attrs in section.get("6", {}).items():
        if attrs.get("raw_dev_state") == "1" and _watts_sensor_role(attrs) == "psu":
            yield Service(item=item)


def _check_power(item, params, section) -> CheckResult:
    data = section.get("6", {}).get(item)
    if data is None or _watts_sensor_role(data) != "psu":
        return

    dev_state, state_readable = data["dev_state"]
    reading = data.get("reading")
    if reading is None:
        yield Result(state=dev_state, summary=f"Status: {state_readable}")
        return

    yield Result(state=dev_state, notice=f"Device status: {state_readable}")

    levels_upper, levels_lower = _levels_from_params_or_device(params, data.get("dev_levels"))

    yield from check_levels(
        reading,
        levels_upper=levels_upper,
        levels_lower=levels_lower,
        metric_name="oposs_cisco_power_w",
        label="Power",
        render_func=lambda v: f"{v:.2f} W" if v < 1000 else f"{v / 1000.0:.2f} kW",
    )


check_plugin_oposs_cisco_power = CheckPlugin(
    name="oposs_cisco_power",
    sections=["oposs_cisco_sensor"],
    service_name="Cisco Power %s",
    discovery_function=_discover_power,
    check_function=_check_power,
    check_ruleset_name="oposs_cisco_power_params",
    check_default_parameters={},
)
