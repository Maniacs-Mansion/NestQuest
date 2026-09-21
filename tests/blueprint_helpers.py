"""Shared harness for the NestQuest automation-blueprint tests.

The blueprints are YAML data consumed by Home Assistant's blueprint
engine; the integration itself never imports yaml or jinja2.  The
blueprint tests therefore exercise them exactly the way HA would:
parse the YAML (with a loader that understands ``!input`` tags), then
render the message/condition templates with a plain jinja2 environment
over a fixture state set shaped like HA's template state objects.

The harness is mock-only (see conftest.py), so the fixtures model just
the surface the templates touch: ``states.binary_sensor`` /
``states.sensor`` lists of objects carrying ``entity_id``, ``state``
and ``attributes`` — plus, for the celebration blueprint, a callable
``states(entity_id)`` lookup over ``input_datetime`` helpers.  Jinja's
``search``/``match`` selectattr tests are Home Assistant additions,
registered here explicitly.

This module is plain helper code (deliberately not named ``test_*`` so
pytest never collects it); every blueprint test file imports from it.
"""
from __future__ import annotations

import re
from pathlib import Path

import jinja2
import yaml

REPO_ROOT = Path(__file__).parent.parent
BLUEPRINT_DIR = (
    REPO_ROOT / "custom_components" / "nestquest" / "blueprints" / "automation"
)


class BlueprintInput(str):
    """Marker for a parsed blueprint ``!input <name>`` reference."""


def _input_constructor(loader: yaml.SafeLoader, node: yaml.Node) -> BlueprintInput:
    return BlueprintInput(loader.construct_scalar(node))


class _BlueprintLoader(yaml.SafeLoader):
    """SafeLoader extended with Home Assistant's ``!input`` blueprint tag."""


_BlueprintLoader.add_constructor("!input", _input_constructor)


def load_blueprints() -> dict[str, dict]:
    """Parse every automation blueprint, asserting the directory exists."""
    assert BLUEPRINT_DIR.is_dir(), f"missing blueprint directory {BLUEPRINT_DIR}"
    paths = sorted(BLUEPRINT_DIR.glob("*.yaml"))
    assert paths, f"no blueprints under {BLUEPRINT_DIR}"
    return {
        path.stem: yaml.load(path.read_text(encoding="utf-8"), Loader=_BlueprintLoader)
        for path in paths
    }


def blueprint(name: str) -> dict:
    """Return one parsed blueprint by its file stem."""
    blueprints = load_blueprints()
    assert name in blueprints, f"{name}.yaml is missing"
    return blueprints[name]


def morning_summary() -> dict:
    """Return the parsed morning-summary blueprint."""
    return blueprint("morning_summary")


def single_action(bp: dict) -> dict:
    """Return the single action of a one-action blueprint."""
    actions = bp["actions"]
    assert isinstance(actions, list) and len(actions) == 1
    return actions[0]


def morning_action(bp: dict) -> dict:
    """Return the single notify action of the morning summary."""
    return single_action(bp)


def notify_data(bp: dict, index: int = 0) -> dict:
    """Return a notify action's service ``data`` (title/message live
    there in the modern HA action schema, not at the action's top level)."""
    action = bp["actions"][index]
    assert isinstance(action.get("data"), dict), (
        "notify payload fields must nest under data:"
    )
    return action["data"]


def iter_strings(node: object):
    """Yield every string value in a parsed YAML structure, recursively."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from iter_strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from iter_strings(value)


class TemplateState:
    """Stand-in for an HA template state object: entity_id/state/attributes."""

    def __init__(self, entity_id: str, state: str, attributes: dict | None = None):
        self.entity_id = entity_id
        self.state = state
        self.attributes = dict(attributes or {})


class StatesFixture:
    """HA's template ``states`` object over a fixture entity set.

    Like HA's ``AllStates``, it exposes per-domain lists (``.sensor``,
    ``.binary_sensor``, ``.input_datetime``, ``.input_text``) AND is
    callable as ``states(entity_id)`` returning the entity's state
    string — or ``None`` when the fixture holds no such entity, the
    way HA returns ``None`` for a nonexistent entity id.
    """

    def __init__(
        self, binary_sensors=(), sensors=(), input_datetimes=(), input_texts=()
    ):
        self.binary_sensor = list(binary_sensors)
        self.sensor = list(sensors)
        self.input_datetime = list(input_datetimes)
        self.input_text = list(input_texts)
        self._all = (
            self.binary_sensor
            + self.sensor
            + self.input_datetime
            + self.input_text
        )

    def __call__(self, entity_id: str):
        """Return the entity's state string, or None when absent."""
        for entity in self._all:
            if entity.entity_id == entity_id:
                return entity.state
        return None


def make_states(
    binary_sensors=(), sensors=(), input_datetimes=(), input_texts=()
) -> StatesFixture:
    """Build the ``states`` fixture: per-domain lists of TemplateState."""
    return StatesFixture(
        binary_sensors, sensors, input_datetimes, input_texts
    )


def make_template_environment() -> jinja2.Environment:
    """A plain jinja2 environment with HA's regex tests and bool filter."""
    env = jinja2.Environment()
    env.tests["match"] = lambda value, pattern: re.match(pattern, value) is not None
    env.tests["search"] = lambda value, pattern: re.search(pattern, value) is not None

    def _bool(value, default=False):
        if isinstance(value, str):
            return value.strip().lower() in ("true", "on", "open", "yes", "1")
        return bool(value) or default

    env.filters["bool"] = _bool
    return env


def render(template: str, **variables) -> str:
    """Render a template the way HA would substitute its variables."""
    return make_template_environment().from_string(template).render(**variables)


# ---------------------------------------------------------------------------
# Entity-reference discipline (Feature 10 shapes only).  The scanners
# are shared so every blueprint test file can assert the same rules;
# the directory-wide tests in test_blueprints.py apply them to every
# blueprint file automatically.
# ---------------------------------------------------------------------------
#: Entity shapes Feature 10 actually creates (sensor.py, binary_sensor.py).
ALLOWED_ENTITY_SHAPES: tuple[re.Pattern, ...] = tuple(
    re.compile(pattern)
    for pattern in (
        r"sensor\.nestquest_[a-z0-9_]+_quests_due_today",
        r"sensor\.nestquest_[a-z0-9_]+_quests_remaining_today",
        r"sensor\.nestquest_[a-z0-9_]+_quests_completed_today",
        r"sensor\.nestquest_[a-z0-9_]+_completion_pct_today",
        r"sensor\.nestquest_[a-z0-9_]+_next_quest",
        r"binary_sensor\.nestquest_[a-z0-9_]+_all_done",
        r"binary_sensor\.nestquest_[a-z0-9_]+_present_today",
        r"sensor\.nestquest_household_quests_due_today",
        r"sensor\.nestquest_household_quests_completed_today",
        r"sensor\.nestquest_cycle_day",
    )
)

#: An unescaped, id-like entity reference: any found must be a full
#: match for one of the Feature 10 shapes above.
_ENTITY_LITERAL_RE = re.compile(r"(?<![\\\w])(?:sensor|binary_sensor)\.[A-Za-z0-9_]+")

#: A domain-dot mention, ignoring the template's escaped-dot regexes
#: (one backslash is stripped so ``binary_sensor\\.`` counts too).
_MENTION_RE = re.compile(r"(?:sensor|binary_sensor)\.([A-Za-z0-9_]+)")