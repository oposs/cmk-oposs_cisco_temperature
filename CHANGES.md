# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### New

### Changed

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


