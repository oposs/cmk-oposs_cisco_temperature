#!/usr/bin/env python3
# Copyright (C) 2025 OETIKER+PARTNER AG - License: GNU General Public License v2

"""Metric translations for the Cisco temperature/DOM plugin rename."""

from cmk.graphing.v1 import translations

translation_cisco_temperature = translations.Translation(
    name="cisco_temperature",
    check_commands=[translations.PassiveCheck("cisco_temperature")],
    translations={
        "temp": translations.RenameTo("oposs_cisco_temperature"),
    },
)

translation_cisco_temperature_dom = translations.Translation(
    name="cisco_temperature_dom",
    check_commands=[translations.PassiveCheck("cisco_temperature.dom")],
    translations={
        "output_signal_power_dbm": translations.RenameTo("oposs_cisco_output_signal_power_dbm"),
        "input_signal_power_dbm": translations.RenameTo("oposs_cisco_input_signal_power_dbm"),
        "signal_power_dbm": translations.RenameTo("oposs_cisco_signal_power_dbm"),
        "output_signal_power_w": translations.RenameTo("oposs_cisco_output_signal_power_w"),
        "input_signal_power_w": translations.RenameTo("oposs_cisco_input_signal_power_w"),
    },
)
