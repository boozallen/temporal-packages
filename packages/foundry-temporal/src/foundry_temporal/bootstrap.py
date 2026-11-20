# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Composition root: the single place where configuration becomes wired objects.

This is where dependencies are constructed and implementations are chosen, so
that everything else depends on the objects it's given rather than deciding for
itself what to be.

What belongs here: assembly — building dependencies and selecting implementations.
What doesn't: orchestration and the actual work, which live in the workflows and
activities a consuming worker assembles from its own `config/` directory.
"""

import importlib
import inspect
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .errors import ValidationError

logger = logging.getLogger(__name__)

# STIG V-222612: config has no legitimate reason to nest this deep; a limit well under
# Python's default recursion limit turns a pathologically nested workflows/activities.yaml
# into a clean ValidationError instead of a stack overflow.
_MAX_BUILD_DEPTH = 50


def _import(target: str) -> object:
    """Resolve a ``module.attr`` dotted path to the object.

    Returns ``object``: what a dotted path names is only known at runtime, so each caller
    states the shape it asked for rather than this returning ``Any`` and every call site
    silently losing its checks.
    """
    module_name, _, attr = target.rpartition(".")
    return getattr(importlib.import_module(module_name), attr)


def _resolve_service(spec: dict[str, Any], services: dict[str, Any]) -> object:
    """Read one value out of ``services.yaml`` for a ``_service`` node.

    Every failure here raises rather than resolving to something empty: a wrong endpoint at
    startup is cheap to diagnose, and the same one missing at publish time is a run lost
    hours in.
    """
    service = spec["_service"]
    key = spec.get("key")
    if not key:
        raise ValidationError(f"Reference to service {service!r} needs a `key`")
    try:
        config = services[service]
    except KeyError as exc:
        raise ValidationError(f"Service {service!r} not found. Available: {list(services)}") from exc
    if not isinstance(config, dict):
        raise ValidationError(f"Service {service!r} must hold a mapping of keys, not {type(config).__name__}")
    try:
        return config[key]
    except KeyError as exc:
        raise ValidationError(f"Service {service!r} has no {key!r}. Available: {list(config)}") from exc


def _build(
    spec: object,
    cache: dict[int, object] | None = None,
    services: dict[str, Any] | None = None,
    depth: int = 0,
) -> object:
    """Recursively build a value from config.

    A mapping with a ``_target_`` key is constructed by importing that callable and
    calling it with the remaining keys as keyword arguments (each built recursively). A
    mapping with a ``_service`` key resolves to a value read from ``services`` instead —
    see ``_resolve_service``. Plain mappings and lists are walked so objects nested inside
    them are built too — that's what lets an argument be a collection of objects, such as
    one implementation per name. Anything else is returned as-is.

    ``cache`` is keyed by the id of the YAML node being built, not by its value: a YAML
    anchor (``&name`` / ``*name``) parses to the identical dict object at every alias
    site, so two args that reference one anchor build one instance and share it — which is
    what makes an anchor mean "one instance across activities" rather than "one instance
    per activity, built from equal config." Without this, an anchored manifest or object
    store would silently give each activity its own instance, and no stage would see
    another's result.

    ``depth`` counts recursion into nested mappings/lists and is checked against
    ``_MAX_BUILD_DEPTH`` (STIG V-222612): config for DI wiring has no legitimate reason to
    nest past that, so a pathologically nested file raises a clean ``ValidationError``
    instead of exhausting the call stack.
    """
    if depth > _MAX_BUILD_DEPTH:
        raise ValidationError(f"Config nesting exceeds max depth of {_MAX_BUILD_DEPTH}")
    if cache is None:
        cache = {}
    if services is None:
        services = {}
    if isinstance(spec, dict) and "_service" in spec:
        return _resolve_service(spec, services)
    if isinstance(spec, dict) and "_target_" in spec:
        key = id(spec)
        if key in cache:
            return cache[key]
        factory = _import(spec["_target_"])
        kwargs = {k: _build(v, cache, services, depth + 1) for k, v in spec.items() if k != "_target_"}
        built = factory(**kwargs)  # type: ignore[operator]
        cache[key] = built
        return built
    if isinstance(spec, dict):
        return {k: _build(v, cache, services, depth + 1) for k, v in spec.items()}
    if isinstance(spec, list):
        return [_build(v, cache, services, depth + 1) for v in spec]
    return spec


@dataclass
class Registrations:
    """What the worker needs to register: workflow classes and activity callables."""

    workflows: list[type]
    activities: list[Callable[..., Any]]


def _read_config(config_path: Path) -> dict[str, Any]:
    """Parse a YAML config file, logging which file failed before re-raising.

    The top-level mapping check is what makes the return annotation true rather than
    asserted: ``yaml.safe_load`` is typed ``Any``, so a file holding a list — or a bare
    string — would otherwise satisfy every caller's ``dict`` until one of them indexed it.
    """
    try:
        with config_path.open() as f:
            config = yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.error(f"Configuration file not found: {config_path}")
        raise
    except yaml.YAMLError:
        logger.error(f"Malformed configuration file: {config_path}")
        raise
    if not isinstance(config, dict):
        raise ValidationError(f"{config_path} must hold a mapping at the top level, not {type(config).__name__}")
    return config


def _import_workflows(config: dict[str, Any]) -> list[type]:
    """The workflow classes a parsed ``workflows.yaml`` declares.

    Imported and left alone, never constructed: Temporal instantiates workflows itself and
    replays them, so there is no injection point here and nothing to wire.
    """
    workflows: list[type] = []
    for item in config.get("workflows", []):
        module = importlib.import_module(item["module"])
        for class_name in item["classes"]:
            workflow = getattr(module, class_name)
            if not isinstance(workflow, type):
                raise ValidationError(f"{item['module']}.{class_name} is not a class, so it cannot be a workflow")
            workflows.append(workflow)
            logger.info(f"Imported workflow: {class_name} from {item['module']}")
    return workflows


def _construct_activities(config: dict[str, Any], services: dict[str, Any]) -> list[Callable[..., Any]]:
    """Activity methods bound to the instances a parsed ``activities.yaml`` wires up.

    One build cache spans every activity here, not just one activity's own args: a YAML
    anchor shared between two activities' `args:` blocks (the object store, the manifest)
    must resolve to the same built instance in both, and `_build` only dedupes within the
    cache it is handed.
    """
    cache: dict[int, object] = {}

    activities: list[Callable[..., Any]] = []
    for item in config.get("activities", []):
        module = importlib.import_module(item["module"])
        for entry in item.get("functions", []):
            class_name, _, method_name = entry["name"].rpartition(".")
            kwargs = {k: _build(v, cache, services) for k, v in entry.get("args", {}).items()}
            instance = getattr(module, class_name)(**kwargs)
            activity = getattr(instance, method_name)
            if not callable(activity):
                raise ValidationError(f"{entry['name']} names an attribute, not a method")
            activities.append(activity)
            logger.info(f"Constructed activity: {entry['name']} from {item['module']}")
    return activities


def _bootstrap(config_dir: Path) -> Registrations:
    """Do the actual assembly, unvalidated.

    Split out from ``bootstrap()`` so tests can drive arbitrary ``config_dir`` values
    without tripping the caller-convention enforcement in the public entry point.
    """
    workflow_config = _read_config(config_dir / "workflows.yaml")
    activity_config = _read_config(config_dir / "activities.yaml")
    services = _read_config(config_dir / "services.yaml")

    return Registrations(
        workflows=_import_workflows(workflow_config),
        activities=_construct_activities(activity_config, services),
    )


def bootstrap(config_dir: Path) -> Registrations:
    """Assemble workflows and activities for the worker to register.

    ``config_dir`` is the consuming repo's own ``config/`` directory — this module is
    installed into site-packages, so it cannot locate that directory from its own
    ``__file__`` the way a repo-local bootstrap module could. Callers pass
    ``Path(__file__).parent.parent / "config"`` from their own ``worker.py``.

    That convention is enforced here, not just documented (STIG V-222604): the immediate
    caller's own file is used to recompute the expected path, and a mismatch raises rather
    than silently importing and executing whatever config a caller — or a future caller
    that doesn't follow the convention — happens to hand in.
    """
    caller_file = Path(inspect.stack()[1].filename)
    expected = (caller_file.parent.parent / "config").resolve()
    resolved = config_dir.resolve()
    if resolved != expected:
        raise ValidationError(f"config_dir must be the caller's own config/ directory ({expected}), got {resolved}")
    return _bootstrap(config_dir)
