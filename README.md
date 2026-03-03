# Cisco Temperature & DOM Checkmk Plugin

Enhanced Checkmk SNMP plugin for Cisco temperature and DOM (Digital Optical Monitoring).

## Features

| Check | Service Name | Description |
|-------|-------------|-------------|
| Temperature | Cisco Temp %s | Temperature sensors with device thresholds |
| DOM | Cisco DOM %s | Optical transceiver power (dBm/watts) |

### Improvements over built-in

- **Better descriptions:** Combines `entPhysicalDescr` and `entPhysicalName` for clearer sensor identification
- **DOM monitoring:** Optical transceiver Tx/Rx power levels with device-provided thresholds
- **Watt-to-dBm conversion:** Automatically converts watt readings to dBm

## SNMP Detection

Detects Cisco devices where:
- sysDescr contains "cisco" (case-insensitive)
- AND either CISCO-ENTITY-SENSOR-MIB or CISCO-ENVMON-MIB temperature table exists

## Important Note

This plugin creates services alongside the built-in `cisco_temperature` check.
To avoid duplicate temperature services, disable the built-in check via
**Setup > Services > Disabled services** for hosts using this plugin.

## Installation

### MKP Package (recommended)

Download the latest `.mkp` file from the
[Releases](https://github.com/oposs/cmk-oposs_cisco_temperature/releases) page:

```bash
mkp install oposs_cisco_temperature-<version>.mkp
```

### Manual Installation

```
local/lib/python3/cmk_addons/plugins/oposs_cisco_temperature/
└── agent_based/
    └── oposs_cisco_temperature.py
```

## License

MIT - OETIKER+PARTNER AG
