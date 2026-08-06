# cmk-oposs_cisco_temperature

Enhanced Cisco temperature and DOM SNMP monitoring.
Full v2 rewrite of legacy cisco_temperature override from oegig-plugins.

## Components

- `local/lib/python3/cmk_addons/plugins/oposs_cisco_temperature/agent_based/oposs_cisco_temperature.py` -- SNMP section + two check plugins (temperature + DOM)
- `.mkp-builder.ini` -- MKP packaging config
- `.github/workflows/release.yml` -- automated release workflow

## Architecture

- One SNMP section (`oposs_cisco_sensor`) fetches 5 tables:
  1. Entity table (entPhysicalDescr, entPhysicalName, entPhysicalContainedIn,
     entPhysicalClass)
  2. Entity sensor data (type, scale, precision, value, status,
     entSensorMeasuredEntity)
  3. Sensor thresholds
  4. ENVMON temperature data
  5. IF admin states (for DOM discovery filtering)
- Three check plugins sharing the same section:
  - `oposs_cisco_temperature`: celsius sensors (type 8)
  - `oposs_cisco_dom`: dBm sensors (type 14) + optical watts sensors
  - `oposs_cisco_power`: power supply watts sensors
- Parse output: `{sensor_type_id: {item_name: {attrs...}}}`
- Device-provided thresholds passed to `check_levels()` as `("fixed", (w, c))`

### Classifying watts sensors

`entSensorType` 6 (watts) is used both by optical transceivers and by power
supplies, so the type alone cannot decide which check owns a sensor.
`_resolve_sensor_role()` resolves it structurally: follow
`entSensorMeasuredEntity` (or, when the device leaves it at 0, walk
`entPhysicalContainedIn` upwards) and read `entPhysicalClass` — `powerSupply(6)`
means a PSU sensor, `port(10)` means an optic. Description patterns and a
"below 1 W" magnitude test are fallbacks only, for agents that populate
neither column.

Tx/Rx direction genuinely has no structural representation in ENTITY-MIB; it
is read from the description, and only selects the metric name.

DOM always reports dBm — watt-reporting optics get reading and thresholds
converted via `_watt_to_dbm()`.

## Testing

`tests/test_oposs_cisco_temperature.py` stubs `cmk.agent_based.v2` so the
plugin can be exercised with synthetic SNMP tables without a Checkmk site.
Run it with plain `python3`.

## Duplication Note

This plugin coexists with the built-in cisco_temperature check.
Users should disable the built-in for affected hosts to avoid duplicate services.
