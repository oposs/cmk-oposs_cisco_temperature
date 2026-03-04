#!/usr/bin/env python3
# Copyright (C) 2025 OETIKER+PARTNER AG - License: GNU General Public License v2

"""Rulesets for the Cisco temperature and DOM check plugins."""

from cmk.rulesets.v1 import Title, Help
from cmk.rulesets.v1.form_specs import (
    Dictionary,
    DictElement,
    Float,
    SimpleLevels,
    LevelDirection,
    DefaultValue,
)
from cmk.rulesets.v1.rule_specs import (
    CheckParameters,
    Topic,
    HostAndItemCondition,
)


def _form_spec_cisco_temperature():
    return Dictionary(
        title=Title("Cisco Temperature Levels"),
        elements={
            "levels": DictElement(
                parameter_form=SimpleLevels(
                    title=Title("Temperature upper levels"),
                    help_text=Help(
                        "Override device-reported temperature thresholds. "
                        "Leave unconfigured to use device defaults."
                    ),
                    level_direction=LevelDirection.UPPER,
                    form_spec_template=Float(unit_symbol="\u00b0C"),
                    prefill_fixed_levels=DefaultValue((50.0, 60.0)),
                ),
                required=False,
            ),
        },
    )


rule_spec_oposs_cisco_temperature_params = CheckParameters(
    title=Title("Cisco Temperature Monitoring"),
    topic=Topic.ENVIRONMENT,
    name="oposs_cisco_temperature_params",
    parameter_form=_form_spec_cisco_temperature,
    condition=HostAndItemCondition(item_title=Title("Sensor name")),
)


def _form_spec_cisco_dom():
    return Dictionary(
        title=Title("Cisco DOM Power Levels"),
        elements={
            "levels_upper": DictElement(
                parameter_form=SimpleLevels(
                    title=Title("Signal power upper levels"),
                    help_text=Help(
                        "Override device-reported upper power thresholds (dBm). "
                        "Leave unconfigured to use device defaults."
                    ),
                    level_direction=LevelDirection.UPPER,
                    form_spec_template=Float(unit_symbol="dBm"),
                    prefill_fixed_levels=DefaultValue((3.0, 7.0)),
                ),
                required=False,
            ),
            "levels_lower": DictElement(
                parameter_form=SimpleLevels(
                    title=Title("Signal power lower levels"),
                    help_text=Help(
                        "Override device-reported lower power thresholds (dBm). "
                        "Leave unconfigured to use device defaults."
                    ),
                    level_direction=LevelDirection.LOWER,
                    form_spec_template=Float(unit_symbol="dBm"),
                    prefill_fixed_levels=DefaultValue((-14.0, -16.0)),
                ),
                required=False,
            ),
        },
    )


rule_spec_oposs_cisco_dom_params = CheckParameters(
    title=Title("Cisco DOM Power Monitoring"),
    topic=Topic.NETWORKING,
    name="oposs_cisco_dom_params",
    parameter_form=_form_spec_cisco_dom,
    condition=HostAndItemCondition(item_title=Title("Sensor name")),
)
