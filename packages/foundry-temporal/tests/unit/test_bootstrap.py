# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for foundry_temporal.bootstrap — the config-driven composition root."""

import inspect
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml
from foundry_temporal.bootstrap import (
    Registrations,
    _bootstrap,
    _build,
    _construct_activities,
    _import_workflows,
    _read_config,
    _resolve_service,
    bootstrap,
)
from foundry_temporal.errors import ValidationError

FIXTURE_MODULE_SOURCE = """
class DummyWorkflow:
    pass


NOT_A_CLASS = "just a constant"


class DummyActivities:
    def __init__(self, greeting="hello"):
        self.greeting = greeting

    def greet(self, name):
        return f"{self.greeting}, {name}"

    not_callable = "oops"
"""

# A YAML anchor (`&shared`) and an alias (`*shared`) to it parse to the identical dict
# object at every alias site — this is what makes an anchor mean "one instance shared
# across activities" rather than "one instance per site that looks equal."
ANCHORED_TWICE = """
first: &shared
  _target_: "bootstrap_fixtures.DummyActivities"
  greeting: "hi"
second: *shared
"""

TWO_SEPARATE_BLOCKS = """
first:
  _target_: "bootstrap_fixtures.DummyActivities"
  greeting: "hi"
second:
  _target_: "bootstrap_fixtures.DummyActivities"
  greeting: "hi"
"""

SERVICES = {"nemo_data_store": {"url": "http://data-store:3000"}}


@pytest.fixture
def fixture_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A tiny importable module (`bootstrap_fixtures`) standing in for a consuming
    repo's own workflow/activity code, so `bootstrap()` can be driven through a real
    import rather than mocked."""
    module_dir = tmp_path / "src_pkg"
    module_dir.mkdir()
    (module_dir / "bootstrap_fixtures.py").write_text(FIXTURE_MODULE_SOURCE)
    monkeypatch.syspath_prepend(str(module_dir))
    return module_dir


# -- _build / _resolve_service (plain values, _target_, _service) ------------


def test_build_passes_through_plain_values() -> None:
    assert _build("plain") == "plain"
    assert _build({"a": 1}) == {"a": 1}
    assert _build([1, 2, 3]) == [1, 2, 3]


def test_build_constructs_target_with_kwargs(fixture_module: Path) -> None:
    obj = _build({"_target_": "bootstrap_fixtures.DummyActivities", "greeting": "yo"})

    assert obj.greeting == "yo"


def test_build_raises_on_excessive_nesting_depth() -> None:
    """STIG V-222612: a pathologically nested config raises a clean ValidationError
    instead of exhausting the call stack."""
    spec: Any = "leaf"
    for _ in range(60):
        spec = {"nested": spec}

    with pytest.raises(ValidationError, match="max depth"):
        _build(spec)


class TestBuildResolvesServiceReferences:
    def test_resolves_to_the_service_value(self) -> None:
        spec = {"_service": "nemo_data_store", "key": "url"}

        assert _build(spec, services=SERVICES) == "http://data-store:3000"

    def test_unknown_service_raises(self) -> None:
        spec = {"_service": "nemo_entity_store", "key": "url"}

        with pytest.raises(ValidationError, match="nemo_entity_store"):
            _resolve_service(spec, SERVICES)

    def test_reference_without_a_key_raises(self) -> None:
        spec = {"_service": "nemo_data_store"}

        with pytest.raises(ValidationError, match="needs a `key`"):
            _resolve_service(spec, SERVICES)

    def test_absent_key_raises(self) -> None:
        spec = {"_service": "nemo_data_store", "key": "bucket"}

        with pytest.raises(ValidationError, match="bucket"):
            _resolve_service(spec, SERVICES)

    def test_service_holding_a_bare_value_raises(self) -> None:
        spec = {"_service": "nemo_data_store", "key": "url"}

        with pytest.raises(ValidationError, match="must hold a mapping"):
            _resolve_service(spec, {"nemo_data_store": "http://data-store:3000"})


class TestBuildSharesByAnchorIdentity:
    """Regression coverage: `_build` must dedupe by YAML-node identity (`id(spec)`), not
    by equality — an anchor's two alias sites are the same dict object, and two
    separately-written identical blocks are not."""

    def test_two_aliases_of_one_anchor_build_the_same_instance(self, fixture_module: Path) -> None:
        spec = yaml.safe_load(ANCHORED_TWICE)
        cache: dict[int, object] = {}

        first = _build(spec["first"], cache)
        second = _build(spec["second"], cache)

        assert first is second

    def test_two_separately_written_identical_blocks_build_distinct_instances(self, fixture_module: Path) -> None:
        spec = yaml.safe_load(TWO_SEPARATE_BLOCKS)
        cache: dict[int, object] = {}

        first = _build(spec["first"], cache)
        second = _build(spec["second"], cache)

        assert first is not second


# -- _read_config --------------------------------------------------------------


def test_read_config_logs_path_when_missing(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    missing = tmp_path / "absent.yaml"
    with pytest.raises(FileNotFoundError):
        _read_config(missing)
    assert str(missing) in caplog.text


def test_read_config_rejects_a_file_that_is_not_a_mapping(tmp_path: Path) -> None:
    a_list = tmp_path / "workflows.yaml"
    a_list.write_text("- one\n- two\n")

    with pytest.raises(ValidationError, match="must hold a mapping"):
        _read_config(a_list)


def test_read_config_returns_empty_dict_for_an_empty_file(tmp_path: Path) -> None:
    empty = tmp_path / "empty.yaml"
    empty.write_text("")

    assert _read_config(empty) == {}


# -- _import_workflows / _construct_activities --------------------------------


def test_import_workflows_returns_the_declared_classes(fixture_module: Path) -> None:
    config: dict[str, Any] = {"workflows": [{"module": "bootstrap_fixtures", "classes": ["DummyWorkflow"]}]}

    from bootstrap_fixtures import DummyWorkflow  # type: ignore[import-not-found]

    assert _import_workflows(config) == [DummyWorkflow]


def test_import_workflows_rejects_a_name_that_is_not_a_class(fixture_module: Path) -> None:
    config: dict[str, Any] = {"workflows": [{"module": "bootstrap_fixtures", "classes": ["NOT_A_CLASS"]}]}

    with pytest.raises(ValidationError, match="is not a class"):
        _import_workflows(config)


def test_construct_activities_binds_methods_to_a_constructed_instance(fixture_module: Path) -> None:
    config: dict[str, Any] = {
        "activities": [
            {
                "module": "bootstrap_fixtures",
                "functions": [{"name": "DummyActivities.greet", "args": {"greeting": "hi"}}],
            }
        ]
    }

    activities = _construct_activities(config, {})

    assert len(activities) == 1
    assert activities[0]("world") == "hi, world"


def test_construct_activities_rejects_an_entry_naming_an_attribute(fixture_module: Path) -> None:
    config: dict[str, Any] = {
        "activities": [
            {
                "module": "bootstrap_fixtures",
                "functions": [{"name": "DummyActivities.not_callable", "args": {}}],
            }
        ]
    }

    with pytest.raises(ValidationError, match="not a method"):
        _construct_activities(config, {})


def test_construct_activities_resolves_a_service_reference_into_a_built_instance(
    fixture_module: Path,
) -> None:
    config: dict[str, Any] = {
        "activities": [
            {
                "module": "bootstrap_fixtures",
                "functions": [
                    {
                        "name": "DummyActivities.greet",
                        "args": {"greeting": {"_service": "nemo_data_store", "key": "url"}},
                    }
                ],
            }
        ]
    }

    activities = _construct_activities(config, SERVICES)

    assert activities[0]("world") == "http://data-store:3000, world"


# -- bootstrap() end-to-end -----------------------------------------------------


@pytest.fixture
def config_dir(tmp_path: Path, fixture_module: Path) -> Path:
    config = tmp_path / "config"
    config.mkdir()
    (config / "workflows.yaml").write_text("workflows:\n  - module: bootstrap_fixtures\n    classes: [DummyWorkflow]\n")
    (config / "activities.yaml").write_text(
        "activities:\n"
        "  - module: bootstrap_fixtures\n"
        "    functions:\n"
        "      - name: DummyActivities.greet\n"
        "        args:\n"
        "          greeting: {_service: nemo_data_store, key: url}\n"
    )
    (config / "services.yaml").write_text("nemo_data_store:\n  url: http://data-store:3000\n")
    return config


def test_bootstrap_returns_registrations(config_dir: Path) -> None:
    regs = _bootstrap(config_dir)

    assert isinstance(regs, Registrations)
    assert len(regs.workflows) == 1
    assert regs.workflows[0].__name__ == "DummyWorkflow"
    assert len(regs.activities) == 1
    assert regs.activities[0]("world") == "http://data-store:3000, world"


def test_bootstrap_cache_does_not_leak_across_calls(config_dir: Path) -> None:
    """Each `_bootstrap()` call gets its own fresh wiring — instances built for one call
    must not be handed back to another."""
    first = _bootstrap(config_dir)
    second = _bootstrap(config_dir)

    assert first.activities[0].__self__ is not second.activities[0].__self__


# -- bootstrap() enforces config_dir matches the caller's own convention -------


def test_bootstrap_rejects_config_dir_that_does_not_match_caller_convention(config_dir: Path) -> None:
    """Called directly from this test file, the expected path is this file's own
    `../config`, which a tmp_path-based `config_dir` can never match — this is exactly
    the STIG V-222604 guardrail: the convention is enforced, not just documented."""
    with pytest.raises(ValidationError, match="config_dir must be the caller's own config"):
        bootstrap(config_dir)


def test_bootstrap_accepts_config_dir_matching_caller_convention(
    monkeypatch: pytest.MonkeyPatch, config_dir: Path
) -> None:
    """A caller whose own file resolves `parent.parent / "config"` to `config_dir` is
    accepted, and the call is delegated through to the real assembly."""
    fake_caller_file = config_dir.parent / "src" / "worker.py"
    monkeypatch.setattr(inspect, "stack", lambda: [None, SimpleNamespace(filename=str(fake_caller_file))])

    regs = bootstrap(config_dir)

    assert isinstance(regs, Registrations)
    assert len(regs.workflows) == 1
