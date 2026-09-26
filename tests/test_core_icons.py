"""Test the namespaced icon-key module (task 707994b7).

:func:`validate_icon` is the strict write-side check (create/edit);
:func:`normalize_icon_for_read` the lenient read-side normalizer that
lets legacy bare Lucide names render without a data migration.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.nestquest.core.icons import (
    EMOJI_MAX_CODE_POINTS,
    ICON_NAMESPACES,
    normalize_icon_for_read,
    validate_icon,
)


def test_namespace_and_cap_constants() -> None:
    assert ICON_NAMESPACES == {"lucide", "fa", "emoji"}
    assert EMOJI_MAX_CODE_POINTS == 8


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("lucide:dog", "lucide:dog"),
        ("fa:dog", "fa:dog"),
        ("fa:paw-print", "fa:paw-print"),
        ("lucide:toy-box-2", "lucide:toy-box-2"),
        ("emoji:🐕", "emoji:🐕"),
        # A ZWJ family sequence (7 code points) is within the cap.
        ("emoji:👨‍👩‍👧‍👦", "emoji:👨‍👩‍👧‍👦"),
        ("emoji:" + "⭐" * EMOJI_MAX_CODE_POINTS, "emoji:" + "⭐" * 8),
        # Legacy bare Lucide names normalize to the lucide namespace.
        ("dog", "lucide:dog"),
    ],
)
def test_validate_icon_accepts(value: str, expected: str) -> None:
    assert validate_icon(value) == expected


@pytest.mark.parametrize("value", [None, "", "   ", "\t\n"])
def test_validate_icon_clears(value: str | None) -> None:
    assert validate_icon(value) is None


@pytest.mark.parametrize(
    "value",
    [
        "foo:dog",  # unknown namespace
        "javascript:alert(1)",  # unknown namespace (and markup-ish)
        "mdi:dog",  # not one of the supported namespaces
        "lucide:",  # empty name
        "fa:",  # empty name
        "emoji:",  # empty payload
        "lucide:Dog",  # uppercase
        "lucide:has space",  # whitespace
        "lucide:-dog",  # leading hyphen
        "lucide:dog-",  # trailing hyphen
        "lucide:dog_bone",  # not kebab
        "fa:dög",  # non-ASCII
        "lucide:a:b",  # colon inside the name
        "Dog",  # bare legacy name must still be kebab
        "has space",
        "<script>",
        "emoji:" + "⭐" * (EMOJI_MAX_CODE_POINTS + 1),  # over the cap
        "emoji:a b",  # whitespace
        "emoji:<b>",  # markup
        "emoji:a&b",  # entity start
        "emoji:🐕\x00",  # control character
        "emoji:🐕\x07🐕",  # control character between emoji
        "emoji:\ufeff",  # U+FEFF BOM: JS \s matches it, so reject to agree
        "emoji:🐕\ufeff",  # trailing U+FEFF
        # Edge whitespace/controls are part of the value, never trimmed away.
        "emoji:🐕 ",  # trailing space
        "emoji:🐕\n",  # trailing newline
        "emoji:🐕\x1c",  # trailing control character (str.strip() eats it)
        " emoji:🐕",  # leading space
        "lucide:dog ",  # trailing space
        "  fa:dog  ",  # padded namespaced key
        "  toy-box  ",  # padded legacy bare name
    ],
)
def test_validate_icon_rejects_naming_the_field(value: str) -> None:
    with pytest.raises(ValueError, match=r"^icon\b"):
        validate_icon(value)


@pytest.mark.parametrize("value", [42, True, ["dog"], {"icon": "dog"}])
def test_validate_icon_rejects_non_strings(value: object) -> None:
    with pytest.raises(ValueError, match="icon must be a string"):
        validate_icon(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("lucide:dog", "lucide:dog"),
        ("fa:dog", "fa:dog"),
        ("emoji:🐕", "emoji:🐕"),
        # Legacy bare names (and anything else) fall through to lucide so
        # the frontend's fallback handles an unknown name, never an error.
        ("dog", "lucide:dog"),
        ("mdi:tooth", "lucide:mdi:tooth"),
        ("Not Kebab", "lucide:Not Kebab"),
    ],
)
def test_normalize_icon_for_read(value: str | None, expected: str | None) -> None:
    assert normalize_icon_for_read(value) == expected


# The emoji-payload rule is duplicated in the generated JS resolver
# (``isEmojiPayload`` in tools/icons/generate.mjs).  Both suites assert
# this one table — admin/src/icons/registry.test.ts runs it through
# resolveIcon — so a divergence between the runtimes fails a test.
_EMOJI_PARITY_CASES = json.loads(
    (
        Path(__file__).parent.parent / "tools" / "icons" / "emoji-payload-cases.json"
    ).read_text(encoding="utf-8")
)["cases"]


@pytest.mark.parametrize(
    "case", _EMOJI_PARITY_CASES, ids=[case["why"] for case in _EMOJI_PARITY_CASES]
)
def test_validate_icon_emoji_verdict_matches_shared_table(case: dict) -> None:
    value = "emoji:" + case["payload"]
    if case["valid"]:
        assert validate_icon(value) == value
    else:
        with pytest.raises(ValueError, match=r"^icon\b"):
            validate_icon(value)


def test_emoji_parity_table_covers_the_contract_edges() -> None:
    payloads = {case["payload"]: case["valid"] for case in _EMOJI_PARITY_CASES}
    assert payloads["\ufeff"] is False
    assert payloads["🐕 "] is False
    assert payloads["🐕\x00"] is False
    assert payloads["<b>"] is False and payloads["a>b"] is False
    assert payloads["a&b"] is False
    assert payloads["⭐" * EMOJI_MAX_CODE_POINTS] is True
    assert payloads["⭐" * (EMOJI_MAX_CODE_POINTS + 1)] is False
    family = "👨\u200d👩\u200d👧\u200d👦"
    assert payloads[family] is True
