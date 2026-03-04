#!/usr/bin/env python3
# Copyright (C) 2025 OETIKER+PARTNER AG - License: GNU General Public License v2

"""Metric and graph definitions for the Cisco temperature and DOM check."""

from cmk.graphing.v1 import Title
from cmk.graphing.v1.metrics import (
    Color,
    DecimalNotation,
    Metric,
    Unit,
)
from cmk.graphing.v1.graphs import Graph, MinimalRange

# Units
unit_celsius = Unit(DecimalNotation("\u00b0C"))
unit_dbm = Unit(DecimalNotation("dBm"))
unit_watts = Unit(DecimalNotation("W"))

# Metrics
metric_oposs_cisco_temperature = Metric(
    name="oposs_cisco_temperature",
    title=Title("Temperature"),
    unit=unit_celsius,
    color=Color.ORANGE,
)

metric_oposs_cisco_output_signal_power_dbm = Metric(
    name="oposs_cisco_output_signal_power_dbm",
    title=Title("Output Signal Power"),
    unit=unit_dbm,
    color=Color.BLUE,
)

metric_oposs_cisco_input_signal_power_dbm = Metric(
    name="oposs_cisco_input_signal_power_dbm",
    title=Title("Input Signal Power"),
    unit=unit_dbm,
    color=Color.GREEN,
)

metric_oposs_cisco_signal_power_dbm = Metric(
    name="oposs_cisco_signal_power_dbm",
    title=Title("Signal Power"),
    unit=unit_dbm,
    color=Color.PURPLE,
)

metric_oposs_cisco_output_signal_power_w = Metric(
    name="oposs_cisco_output_signal_power_w",
    title=Title("Output Signal Power"),
    unit=unit_watts,
    color=Color.DARK_BLUE,
)

metric_oposs_cisco_input_signal_power_w = Metric(
    name="oposs_cisco_input_signal_power_w",
    title=Title("Input Signal Power"),
    unit=unit_watts,
    color=Color.DARK_GREEN,
)

# Graphs
graph_oposs_cisco_temperature = Graph(
    name="oposs_cisco_temperature",
    title=Title("Cisco Temperature"),
    simple_lines=["oposs_cisco_temperature"],
    minimal_range=MinimalRange(lower=0, upper=80),
)

graph_oposs_cisco_dom_signal_power = Graph(
    name="oposs_cisco_dom_signal_power",
    title=Title("Cisco DOM Signal Power"),
    simple_lines=[
        "oposs_cisco_output_signal_power_dbm",
        "oposs_cisco_input_signal_power_dbm",
    ],
)
