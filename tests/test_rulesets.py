"""The rule forms build and fit the parameters the check functions read."""

import importlib.util
import pathlib
import sys

import pytest

from cmk.rulesets.v1.form_specs import LevelDirection, SimpleLevels
from cmk.rulesets.v1.rule_specs import CheckParameters, HostAndItemCondition

ROOT = pathlib.Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "local/lib/python3/cmk_addons/plugins/oposs_cisco_temperature"


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def rulesets():
    return _load(PLUGIN / "rulesets/cisco_temperature.py", "test_oposs_cisco_temperature_rulesets")


@pytest.fixture(scope="module")
def check():
    return _load(PLUGIN / "agent_based/oposs_cisco_temperature.py", "test_oposs_cisco_temperature_check_rs")


# check plugin -> (rule spec, {parameter: level direction})
EXPECTED = {
    "check_plugin_oposs_cisco_temperature": (
        "rule_spec_oposs_cisco_temperature_params",
        {"levels": LevelDirection.UPPER},
    ),
    "check_plugin_oposs_cisco_dom": (
        "rule_spec_oposs_cisco_dom_params",
        {"levels_upper": LevelDirection.UPPER, "levels_lower": LevelDirection.LOWER},
    ),
    "check_plugin_oposs_cisco_power": (
        "rule_spec_oposs_cisco_power_params",
        {"levels_upper": LevelDirection.UPPER, "levels_lower": LevelDirection.LOWER},
    ),
}


@pytest.mark.parametrize("plugin_name", sorted(EXPECTED))
def test_rule_matches_check_plugin(rulesets, check, plugin_name):
    rule_name, elements = EXPECTED[plugin_name]
    plugin = getattr(check, plugin_name)
    rule = getattr(rulesets, rule_name)
    assert isinstance(rule, CheckParameters)
    assert plugin.check_ruleset_name == rule.name
    # the services have items, so the rule needs an item condition
    assert isinstance(rule.condition, HostAndItemCondition)
    form = rule.parameter_form()
    assert set(form.elements) == set(elements)
    assert set(plugin.check_default_parameters) <= set(form.elements)
    for key, direction in elements.items():
        element = form.elements[key]
        # optional: an unset field means "use the device thresholds"
        assert element.required is False
        assert isinstance(element.parameter_form, SimpleLevels)
        assert element.parameter_form.level_direction is direction


@pytest.mark.parametrize("plugin_name", sorted(EXPECTED))
def test_prefills_are_ordered_for_their_direction(rulesets, plugin_name):
    rule_name, elements = EXPECTED[plugin_name]
    form = getattr(rulesets, rule_name).parameter_form()
    for key, direction in elements.items():
        warn, crit = form.elements[key].parameter_form.prefill_fixed_levels.value
        if direction is LevelDirection.UPPER:
            assert warn < crit, key
        else:
            assert warn > crit, key
