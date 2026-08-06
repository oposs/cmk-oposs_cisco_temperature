#!/usr/bin/env python3
# Copyright (C) 2025 OETIKER+PARTNER AG - License: GNU General Public License v2

"""Metric and graph definitions for the Cisco temperature and DOM check."""

from cmk.graphing.v1 import Title
from cmk.graphing.v1.metrics import (
    Color,
    DecimalNotation,
    Metric,
    SINotation,
    Unit,
)
from cmk.graphing.v1.graphs import Graph, MinimalRange

# Units. Power supplies reach several kW, so use SI scaling there rather than
# printing a five-digit watt figure.
unit_celsius = Unit(DecimalNotation("\u00b0C"))
unit_dbm = Unit(DecimalNotation("dBm"))
unit_watts = Unit(SINotation("W"))

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

# Power supply readings. Optical power is always normalised to dBm, so the
# only watt metric left is the one for power modules.
metric_oposs_cisco_power_w = Metric(
    name="oposs_cisco_power_w",
    title=Title("Power"),
    unit=unit_watts,
    color=Color.DARK_BLUE,
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

graph_oposs_cisco_power = Graph(
    name="oposs_cisco_power",
    title=Title("Cisco Power"),
    simple_lines=["oposs_cisco_power_w"],
)
