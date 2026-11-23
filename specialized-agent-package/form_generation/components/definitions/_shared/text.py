"""Shared text defaults, length limits and preview behavior."""
from __future__ import annotations

from typing import Any, Mapping

from ...common import PropertyRule, boolean, default_snapshot, number, simulate_default, string, validate_default
from ...validation import reject, validate_schema

_LENGTH_SCHEMA = {"type": "number", "minimum": 1}
PROPERTIES = {
    "placeholder": string(reset="", has_reset=True),
    "defaultValue": PropertyRule(unvalidated_operations=("clear", "reset")),
    "textLengthLimit": number(1, reset={"enabled": False, "maxLength": 200}, has_reset=True, unvalidated_operations=("clear", "reset")),
    "showLimitHint": boolean(),
    "textMaxLength": number(1, default=200, has_default=True, prerequisite="showLimitHint"),
    "enableQuickCopy": boolean(),
    "enableLinkParser": boolean(),
}


def snapshot(node: Mapping[str, Any], prop: str) -> dict[str, Any] | None:
    props = node.get("props", {})
    if prop == "defaultValue":
        return default_snapshot(props)
    if prop == "textLengthLimit":
        return {"exists": True, "value": {"enabled": props.get("showLimitHint", False), "maxLength": props.get("textMaxLength", 200)}} if "showLimitHint" in props or "textMaxLength" in props else {"exists": False}
    return None


def clear(node: Mapping[str, Any], prop: str) -> dict[str, Any] | None:
    props = node.get("props", {})
    if prop == "defaultValue":
        return {"exists": True, "value": {"mode": "undefined"}}
    if prop == "textLengthLimit":
        return {"exists": True, "value": {"enabled": False, "maxLength": props.get("textMaxLength", 200)}}
    return None


def validate(node: Mapping[str, Any], prop: str, value: Any) -> bool:
    if prop == "defaultValue":
        validate_default(value, "string")
    elif prop == "textLengthLimit":
        if isinstance(value, dict):
            validate_schema(value, {"type": "object", "properties": {"enabled": {"const": False}, "maxLength": _LENGTH_SCHEMA}, "required": ["enabled"], "additionalProperties": False})
        else:
            validate_schema(value, _LENGTH_SCHEMA)
    else:
        return False
    return True


def simulate(node: dict[str, Any], prop: str, after: Mapping[str, Any]) -> list[str] | None:
    props, value = node["props"], after.get("value")
    if prop == "defaultValue":
        return simulate_default(props, value)
    if prop == "textLengthLimit":
        enabled = not isinstance(value, dict)
        props["showLimitHint"] = enabled
        if enabled:
            props["textMaxLength"] = value
        elif "maxLength" in value:
            props["textMaxLength"] = value["maxLength"]
        return ["成组更新计数器与输入长度限制；关闭时保留历史阈值"]
    return None


def normalize_copy(prop: str, value: Any) -> Any:
    if prop == "textLengthLimit" and isinstance(value, dict) and value.get("enabled") is True:
        return value.get("maxLength")
    return value


def matches(prop: str, actual: Mapping[str, Any], after: Mapping[str, Any]) -> bool:
    if prop == "textLengthLimit":
        expected = after["value"]
        return actual == after if isinstance(expected, dict) else actual.get("value", {}).get("enabled") is True and actual["value"].get("maxLength") == expected
    return actual == after


def validate_candidate(node: Mapping[str, Any], prop: str) -> None:
    props = node.get("props", {})
    if prop in {"textLengthLimit", "defaultValue"} and props.get("defaultValueConfig") == "custom" and props.get("showLimitHint") is True:
        default, maximum = props.get("defaultValue"), props.get("textMaxLength", 200)
        if isinstance(default, str) and type(maximum) in (int, float) and len(default) > maximum:
            reject("INVALID_DEFAULT_RANGE", "默认文本超过输入长度限制。")
