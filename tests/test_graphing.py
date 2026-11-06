"""Metric names: prefixed, declared, graphed and translated from the stock names."""

import importlib.util
import pathlib
import sys

import pytest
from cmk.agent_based.v2 import Metric
from cmk.graphing.v1 import graphs, metrics, perfometers, translations

ROOT = pathlib.Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "local/lib/python3/cmk_addons/plugins/oposs_cisco_temperature"

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import test_check as data


def _load(path):
    name = "test_graphing_" + path.stem + "_" + path.parent.name
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def check():
    return _load(PLUGIN / "agent_based/oposs_cisco_temperature.py")


@pytest.fixture(scope="module")
def graphing_objects():
    objects = []
    for path in sorted((PLUGIN / "graphing").glob("*.py")):
        objects.extend(vars(_load(path)).values())
    return objects


@pytest.fixture(scope="module")
def declared(graphing_objects):
    return {o.name for o in graphing_objects if isinstance(o, metrics.Metric)}


@pytest.fixture(scope="module")
def emitted(check):
    """Every metric the three checks yield for the test data."""
    section = check._parse_cisco_sensor(
        [data.ENTITIES, data.SENSORS, data.THRESHOLDS, data.ENVMON, data.IFACES]
    )
    sensors = [["6003", "14", "8", "0", "-3000", "1", "0"]]
    generic = check._parse_cisco_sensor([[["6003", "Lane", "Lane 1", "0", "8"]], sensors, [], [], []])
    names = set()
    for discover, run, sec in (
        (check._discover_temperature, check._check_temperature, section),
        (check._discover_dom, check._check_dom, section),
        (check._discover_dom, check._check_dom, generic),
        (check._discover_power, check._check_power, section),
    ):
        for service in discover(sec):
            names.update(m.name for m in run(service.item, {}, sec) if isinstance(m, Metric))
    return names


def test_every_emitted_metric_is_declared(emitted, declared):
    assert emitted
    assert sorted(emitted - declared) == []


def test_every_declared_metric_is_emitted(emitted, declared):
    assert sorted(declared - emitted) == []


def test_every_declared_name_is_prefixed(graphing_objects):
    kinds = (metrics.Metric, graphs.Graph, perfometers.Perfometer, translations.Translation)
    names = [o.name for o in graphing_objects if isinstance(o, kinds)]
    assert names
    assert [n for n in names if not n.startswith("oposs_cisco_")] == []


def test_graphs_use_declared_metrics(graphing_objects, declared):
    used = set()
    for o in graphing_objects:
        if isinstance(o, graphs.Graph):
            used.update(o.simple_lines)
    assert used and sorted(used - declared) == []


def test_stock_names_translate_to_declared_metrics(graphing_objects, declared):
    found = {o.name: o for o in graphing_objects if isinstance(o, translations.Translation)}
    assert set(found) == {"oposs_cisco_temperature", "oposs_cisco_dom"}
    for name, translation in found.items():
        # keyed on the check command the live service runs today
        assert translation.check_commands == [translations.PassiveCheck(name)]
        for rule in translation.translations.values():
            assert isinstance(rule, translations.RenameTo)
            assert rule.metric_name in declared
    assert found["oposs_cisco_temperature"].translations == {
        "temp": translations.RenameTo("oposs_cisco_temperature")
    }
