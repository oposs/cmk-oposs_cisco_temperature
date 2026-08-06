#!/usr/bin/env python3
# Copyright (C) 2025 OETIKER+PARTNER AG - License: GNU General Public License v2

"""Metric translations for the Cisco temperature/DOM plugin rename.

The legacy stock Checkmk checks were ``cisco_temperature`` (and the DOM
subcheck ``cisco_temperature.dom``). This plugin re-implements them as
two independent check plugins ``oposs_cisco_temperature`` and
``oposs_cisco_dom``, with prefixed metrics.

IMPORTANT: ``check_commands`` references the *new* check command (the one
the live service has today). Checkmk's translation lookup is an exact
dict-key match against that command — keying on the legacy stock-plugin
name would silently miss for every service. Whether the legacy RRD data
actually merges also depends on the service name being unchanged across
the rename; if it was renamed, the legacy RRD lives in a different
per-service directory and the translation cannot bridge it.
"""

from cmk.graphing.v1 import translations

translation_oposs_cisco_temperature = translations.Translation(
    name="oposs_cisco_temperature",
    check_commands=[translations.PassiveCheck("oposs_cisco_temperature")],
    translations={
        "temp": translations.RenameTo("oposs_cisco_temperature"),
    },
)

translation_oposs_cisco_dom = translations.Translation(
    name="oposs_cisco_dom",
    check_commands=[translations.PassiveCheck("oposs_cisco_dom")],
    translations={
        "output_signal_power_dbm": translations.RenameTo("oposs_cisco_output_signal_power_dbm"),
        "input_signal_power_dbm": translations.RenameTo("oposs_cisco_input_signal_power_dbm"),
        "signal_power_dbm": translations.RenameTo("oposs_cisco_signal_power_dbm"),
    },
)
