"""Tests for the Agent harness schema-locking helper.

The schema goes into OpenRouter with `strict: true`, which requires
`additionalProperties: false` on every nested object — not just the
root. Pydantic's `model_json_schema()` doesn't add it by default, so
the harness walks the tree and locks each object node.
"""

from serenity.agents.base import _lock_down


def test_lock_down_sets_root_object() -> None:
    schema = {"type": "object", "properties": {"x": {"type": "string"}}}
    _lock_down(schema)
    assert schema["additionalProperties"] is False


def test_lock_down_recurses_into_nested_object_property() -> None:
    schema = {
        "type": "object",
        "properties": {
            "inner": {"type": "object", "properties": {"y": {"type": "integer"}}},
        },
    }
    _lock_down(schema)
    assert schema["additionalProperties"] is False
    assert schema["properties"]["inner"]["additionalProperties"] is False


def test_lock_down_handles_list_of_object_schemas() -> None:
    schema = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {"type": "object", "properties": {"z": {"type": "boolean"}}},
            },
        },
    }
    _lock_down(schema)
    assert schema["properties"]["items"]["items"]["additionalProperties"] is False


def test_lock_down_descends_into_defs() -> None:
    schema = {
        "$defs": {
            "Inner": {"type": "object", "properties": {"w": {"type": "string"}}},
        },
        "type": "object",
        "properties": {"x": {"$ref": "#/$defs/Inner"}},
    }
    _lock_down(schema)
    assert schema["$defs"]["Inner"]["additionalProperties"] is False
    assert schema["additionalProperties"] is False


def test_lock_down_does_not_overwrite_explicit_value() -> None:
    schema = {"type": "object", "additionalProperties": True, "properties": {}}
    _lock_down(schema)
    # setdefault — leaves an existing value alone, only fills when absent.
    assert schema["additionalProperties"] is True
