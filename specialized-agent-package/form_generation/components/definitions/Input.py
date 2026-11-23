"""Input properties and single-line format validation."""
from __future__ import annotations

from typing import Any, Mapping

from ..common import PropertyRule, boolean, enum, string
from ..validation import reject, validate_schema
from ._shared import text
from ._shared.text import matches, normalize_copy

INPUT_FORMATS = ["none", "chinese", "number", "letter", "letter_num", "phone", "tel", "postcode", "idcard", "email"]
PROPERTIES = {
    **text.PROPERTIES,
    "allowClear": boolean(reset=False, has_reset=True),
    "isUnique": boolean(handler_required=True),
    "uniqueMessage": string(prerequisite="isUnique"),
    "format": enum(INPUT_FORMATS, reset="none", has_reset=True),
    "formatMessage": string(),
    "formatValidation": PropertyRule(),
}


def snapshot(node: Mapping[str, Any], prop: str) -> dict[str, Any] | None:
    if prop == "formatValidation":
        props = node.get("props", {})
        return {"exists": True, "value": {"format": props.get("format", "none"), **({"message": props["formatMessage"]} if "formatMessage" in props else {})}} if "format" in props or "formatMessage" in props else {"exists": False}
    return text.snapshot(node, prop)


def normalize_set(node: Mapping[str, Any], prop: str, value: Any) -> Any:
    if prop == "formatValidation" and isinstance(value, dict) and "message" not in value and "formatMessage" in node.get("props", {}):
        value["message"] = node["props"]["formatMessage"]
    return value


def clear(node: Mapping[str, Any], prop: str) -> dict[str, Any] | None:
    if prop == "formatValidation":
        props = node.get("props", {})
        return {"exists": True, "value": {"format": "none", **({"message": props["formatMessage"]} if "formatMessage" in props else {})}}
    if prop == "format":
        return {"exists": True, "value": "none"}
    return text.clear(node, prop)


def validate(node: Mapping[str, Any], prop: str, value: Any) -> bool:
    if prop == "formatValidation":
        validate_schema(value, {"type": "object", "properties": {"format": {"type": "string", "enum": INPUT_FORMATS}, "message": {"type": "string"}}, "required": ["format"], "additionalProperties": False})
        return True
    return text.validate(node, prop, value)


def simulate(node: dict[str, Any], prop: str, after: Mapping[str, Any]) -> list[str] | None:
    if prop == "formatValidation":
        props, value = node["props"], after.get("value")
        props["format"] = value["format"]
        if "message" in value:
            props["formatMessage"] = value["message"]
        return ["同步内置格式校验及提示，不创建任意 rules 数组"]
    return text.simulate(node, prop, after)


def validate_candidate(node: Mapping[str, Any], prop: str) -> None:
    text.validate_candidate(node, prop)
    if prop == "formatMessage" and node.get("props", {}).get("format", "none") == "none":
        reject("PROPERTY_CONDITION_UNMET", "格式提示需要启用格式校验。", True)


def dependencies(prop: str) -> tuple[str, ...]:
    return ("format",) if prop == "formatMessage" else ()
