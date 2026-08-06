# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### New
- New `oposs_cisco_power` check ("Cisco Power %s") for power supply /
  power module watt sensors, with an SI-scaled `oposs_cisco_power_w`
  metric (a 1573 W reading now renders as 1.57 kW) and a matching
  "Cisco Power Supply Monitoring" ruleset.
- The section now fetches `entSensorMeasuredEntity`
  (`.1.3.6.1.4.1.9.9.91.1.1.1.1.8`) plus `entPhysicalContainedIn` and
  `entPhysicalClass` (`.1.3.6.1.2.1.47.1.1.1.1.4` / `.5`), so a sensor's
  purpose is resolved from the ENTITY-MIB containment tree rather than
  guessed from its name.

### Changed
- **Requires a service rediscovery on affected hosts.** Power supply
  sensors move out of "Cisco DOM %s" into the new "Cisco Power %s"
  services; the old DOM services go stale until rediscovered.
- Watts sensors (`entSensorType` 6) are now assigned to a check
  structurally: an ancestor of class `powerSupply(6)` makes it a power
  supply sensor, `port(10)` makes it optical. Naming patterns and the old
  "below 1 W" magnitude test remain only as fallbacks for devices that
  expose no usable entity class.
- DOM readings are always reported in dBm. Optical sensors that report
  watts get both their reading *and* their device thresholds converted,
  instead of only readings under 1 W.
- Removed the `oposs_cisco_output_signal_power_w` /
  `oposs_cisco_input_signal_power_w` metrics and their translations; DOM
  no longer emits watt metrics. Existing RRDs for these hold mislabelled
  data and are not worth migrating.

### Fixed
- Power supply sensors are no longer discovered as DOM services. Watt
  sensors on power modules (e.g. `0/PT0-PM0-Input Power`) were swept into
  the DOM check by `entSensorType` alone, producing services like
  "Cisco DOM Power Sensor - 0/PT0-PM0-Input Power".
- A watt reading can no longer be written into a dBm metric. The metric
  name was chosen from the sensor description alone: a description
  containing neither "Transmit" nor "Receive" fell through to
  `oposs_cisco_signal_power_dbm` regardless of the actual unit, so a
  788 W power supply reading was graphed as "788 dBm" while the service
  summary correctly said "788.26 W".

## 0.1.2 - 2026-04-27
### Fixed
- Metric translations for legacy stock-Checkmk `cisco_temperature` and
  `cisco_temperature.dom` history are now keyed on the new
  `oposs_cisco_temperature` and `oposs_cisco_dom` check commands so they
  actually fire. Previously they were keyed on the stock commands and
  Checkmk's translation lookup (an exact match on the live service's
  current check command) silently missed them — leaving the legacy
  `temp.rrd` / `*_signal_power_*.rrd` files orphaned in the per-service
  directories. Note: continuous-line merge only happens if the service
  name is unchanged across the rename; if you renamed the service when
  switching off the stock plugin, the legacy RRD lives in a different
  per-service directory and the translation cannot bridge it.

## 0.1.1 - 2026-03-24
### Fixed
- Fix ruleset topic: use `Topic.ENVIRONMENTAL` instead of incorrect `Topic.ENVIRONMENT`

## 0.1.0 - 2026-03-04
### New
- Initial v2 rewrite of legacy cisco_temperature override
- Enhanced sensor descriptions (entPhysicalDescr + entPhysicalName)
- Temperature check with CISCO-ENTITY-SENSOR-MIB and CISCO-ENVMON-MIB support
- DOM check for optical transceiver power monitoring (dBm/watts)
- Device-provided threshold support for both checks
- MKP packaging via oposs/mkp-builder GitHub Action


