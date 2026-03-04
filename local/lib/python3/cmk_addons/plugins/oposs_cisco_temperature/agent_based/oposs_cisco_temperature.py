#!/usr/bin/env python3
# Copyright (C) 2025 OETIKER+PARTNER AG - License: GNU General Public License v2

"""
Enhanced Cisco temperature and DOM (Digital Optical Monitoring) check.
v2 rewrite of legacy cisco_temperature override.

Provides:
- Improved sensor descriptions (entPhysicalDescr + entPhysicalName)
- Temperature monitoring with device-provided thresholds
- DOM monitoring for optical transceiver power (dBm/watts)
"""

import math

from cmk.agent_based.v2 import (
    CheckPlugin,
    CheckResult,
    DiscoveryResult,
    OIDCached,
    OIDEnd,
    Result,
    SNMPSection,
    SNMPTree,
    Service,
    State,
    check_levels,
    all_of,
    any_of,
    exists,
    matches,
    render,
)

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


def _watt_to_dbm(watt):
    """Convert watts to dBm."""
    if watt <= 0:
        return float("nan")
    return 10.0 * math.log10(watt) + 30.0


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

    # 1. Build descriptions: sensor_id -> "desc_a - desc_b"
    descriptions = {}
    for row in description_info:
        descriptions[row[0]] = row[1] + " - " + row[2]

    # 2. Map admin states to sensor IDs
    admin_states_dict = {}
    for if_name, admin_state in admin_states:
        for sensor_id, descr in descriptions.items():
            if descr.startswith(if_name):
                admin_states_dict[sensor_id] = _ADMIN_STATE_MAP.get(admin_state)

    # 3. Build thresholds: sensor_id -> [level, ...]
    thresholds = {}
    for row in state_info:
        thresholds.setdefault(row[0], [])
    for row in levels_info:
        sensor_id, _subid = row[0].split(".")
        thresholds.setdefault(sensor_id, []).append(row[1])

    # 4. Parse entity sensors (CISCO-ENTITY-SENSOR-MIB)
    entity_parsed = {}
    for sensor_id, sensortype_id, scalecode, magnitude, value, sensorstate in state_info:
        sensortype = _SENSOR_TYPES.get(sensortype_id)
        if sensortype not in ("dBm", "celsius", "watts"):
            continue

        descr = descriptions.get(sensor_id, sensor_id)
        if not descr:
            continue

        entity_parsed.setdefault(sensortype_id, {})
        dev_state = _ENTITY_STATES.get(sensorstate, (State.UNKNOWN, "unknown[%s]" % sensorstate))

        sensor_attrs = {
            "descr": descr,
            "raw_dev_state": sensorstate,
            "dev_state": dev_state,
            "admin_state": admin_states_dict.get(sensor_id),
        }

        if sensorstate == "1":
            factor = 10.0 ** (float(_SCALE_EXPONENTS.get(scalecode, 0)) - float(magnitude))
            sensor_attrs["reading"] = float(value) * factor

            dev_levels = None
            sensor_thresholds = thresholds.get(sensor_id, [])
            if sensortype == "dBm" and len(sensor_thresholds) == 4:
                converted = sorted(float(t) * factor for t in sensor_thresholds)
                dev_levels = (converted[2], converted[3], converted[1], converted[0])
            elif sensortype == "celsius" and len(sensor_thresholds) == 4:
                raw_w, raw_c = float(sensor_thresholds[0]) * factor, float(sensor_thresholds[1]) * factor
                dev_levels = (min(raw_w, raw_c), max(raw_w, raw_c))

            sensor_attrs["dev_levels"] = dev_levels
            entity_parsed[sensortype_id].setdefault(sensor_id, sensor_attrs)

    # 5. Parse ENVMON temperatures
    found_temp_sensors = entity_parsed.get("8", {})
    parsed = {}
    temp_sensors = parsed.setdefault("8", {})

    for sensor_id, statustext, temp, max_temp, state in perfstuff:
        if sensor_id in descriptions and sensor_id in found_temp_sensors:
            item = descriptions[sensor_id]
            prev_description = _cisco_sensor_item(statustext, sensor_id)
            temp_sensors[prev_description] = {"obsolete": True}
        else:
            item = _cisco_sensor_item(statustext, sensor_id)

        sensor_attrs = {
            "raw_dev_state": state,
            "dev_state": _ENVMON_STATES.get(state, (State.UNKNOWN, "unknown[%s]" % state)),
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
        # 0: Entity descriptions
        SNMPTree(
            base=".1.3.6.1.2.1.47.1.1.1.1",
            oids=[OIDEnd(), OIDCached("2"), OIDCached("7")],
        ),
        # 1: Entity sensor data
        SNMPTree(
            base=".1.3.6.1.4.1.9.9.91.1.1.1.1",
            oids=[OIDEnd(), "1", "2", "3", "4", "5"],
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
        if not attrs.get("obsolete", False):
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
        yield Result(state=dev_state, summary="Status: %s" % state_readable)
        return

    # Device state
    yield Result(state=dev_state, notice="Device status: %s" % state_readable)

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
        render_func=lambda v: "%.1f \u00b0C" % v,
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

def _discover_dom(section) -> DiscoveryResult:
    for sensor_type in ("14", "6"):
        for item, attrs in section.get(sensor_type, {}).items():
            if attrs.get("raw_dev_state") == "1":
                admin = attrs.get("admin_state")
                if admin in ("up", None):
                    yield Service(item=item)


def _check_dom(item, params, section) -> CheckResult:
    # Look up in dBm sensors first, then watts
    data = section.get("14", {}).get(item)
    unit = "dBm"
    if data is None:
        data = section.get("6", {}).get(item, {})
        unit = "W"

    reading = data.get("reading")
    if reading is None:
        return

    dev_state, state_readable = data["dev_state"]
    yield Result(state=dev_state, notice="Device status: %s" % state_readable)

    # Convert watts < 1 to dBm
    if unit == "W" and reading < 1:
        reading = _watt_to_dbm(reading)
        unit = "dBm"

    # Determine metric name from description
    descr = data.get("descr", "")
    if "Transmit" in descr:
        dsname = "oposs_cisco_output_signal_power_dbm" if unit == "dBm" else "oposs_cisco_output_signal_power_w"
    elif "Receive" in descr:
        dsname = "oposs_cisco_input_signal_power_dbm" if unit == "dBm" else "oposs_cisco_input_signal_power_w"
    else:
        dsname = "oposs_cisco_signal_power_dbm"

    # User-configured levels override device thresholds
    levels_upper = params.get("levels_upper")
    levels_lower = params.get("levels_lower")

    if levels_upper is None:
        dev_levels = data.get("dev_levels") or (None, None, None, None)
        if dev_levels[0] is not None and dev_levels[1] is not None:
            levels_upper = ("fixed", (dev_levels[0], dev_levels[1]))
    if levels_lower is None:
        dev_levels = data.get("dev_levels") or (None, None, None, None)
        if len(dev_levels) >= 4 and dev_levels[2] is not None and dev_levels[3] is not None:
            levels_lower = ("fixed", (dev_levels[2], dev_levels[3]))

    yield from check_levels(
        reading,
        levels_upper=levels_upper,
        levels_lower=levels_lower,
        metric_name=dsname,
        label="Signal power" if unit == "dBm" else "Power",
        render_func=lambda v: "%.2f %s" % (v, unit),
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
