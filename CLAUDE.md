# cmk-oposs_cisco_temperature

Enhanced Cisco temperature and DOM SNMP monitoring.
Full v2 rewrite of legacy cisco_temperature override from oegig-plugins.

## Components

- `local/lib/python3/cmk_addons/plugins/oposs_cisco_temperature/agent_based/oposs_cisco_temperature.py` -- SNMP section + two check plugins (temperature + DOM)
- `.mkp-builder.ini` -- MKP packaging config
- `.github/workflows/release.yml` -- automated release workflow

## Architecture

- One SNMP section (`oposs_cisco_sensor`) fetches 5 tables:
  1. Entity descriptions (entPhysicalDescr + entPhysicalName)
  2. Entity sensor data (type, scale, precision, value, status)
  3. Sensor thresholds
  4. ENVMON temperature data
  5. IF admin states (for DOM discovery filtering)
- Two check plugins sharing the same section:
  - `oposs_cisco_temperature`: celsius sensors (type 8)
  - `oposs_cisco_dom`: dBm (type 14) and watts (type 6) sensors
- Parse output: `{sensor_type_id: {item_name: {attrs...}}}`
- Device-provided thresholds passed to `check_levels()` as `("fixed", (w, c))`
- Watts readings < 1W auto-converted to dBm

## Duplication Note

This plugin coexists with the built-in cisco_temperature check.
Users should disable the built-in for affected hosts to avoid duplicate services.
