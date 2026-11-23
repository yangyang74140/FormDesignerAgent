"""SelectMulti properties and multiple-option clearing."""
from __future__ import annotations

from typing import Any, Mapping

from ..common import PropertyRule, boolean, number, string
from ._shared import choice
from ..validation import reject, validate_schema
from ._shared.choice import dependencies, effects, validate_compound

PROPERTIES = {
    **choice.PROPERTIES,
    "defaultValue": PropertyRule(unvalidated_operations=("clear", "reset")),
    "selectionLimit": PropertyRule(handler_required=True, reset=None, has_reset=True, unvalidated_operations=("clear", "reset")),
    "selectAll": boolean(),
    "supportReverseSelect": boolean(reset=True, has_reset=True),
    "maxCountEnable": boolean(),
    "maxTagCount": number(1, prerequisite="maxCountEnable"),
    "maxCountMessage": string(prerequisite="maxCountEnable"),
}


def snapshot(node: Mapping[str, Any], prop: str) -> dict[str, Any] | None:
    if prop != "selectionLimit":
        return None
    props = node.get("props", {})
    value = {"count": props["maxTagCount"], **({"message": props["maxCountMessage"]} if "maxCountMessage" in props else {})} if props.get("maxCountEnable") is True and "maxTagCount" in props else None
    return {"exists": True, "value": value} if any(key in props for key in ("maxCountEnable", "maxTagCount", "maxCountMessage")) else {"exists": False}


def clear(node: Mapping[str, Any], prop: str) -> dict[str, Any] | None:
    if prop == "defaultValue":
        return {"exists": True, "value": []}
    return {"exists": True, "value": None} if prop == "selectionLimit" else None


def validate(node: Mapping[str, Any], prop: str, value: Any) -> bool:
    if prop != "selectionLimit":
        return choice.validate(node, prop, value)
    validate_schema(value, {"type": "object", "properties": {"count": {"type": "integer", "minimum": 1, "maximum": 1000}, "message": {"type": "string", "maxLength": 200}}, "required": ["count"], "additionalProperties": False})
    return True


def simulate(node: dict[str, Any], prop: str, after: Mapping[str, Any]) -> list[str] | None:
    if prop != "selectionLimit":
        return choice.simulate(node, prop, after)
    props, value = node["props"], after.get("value")
    props["maxCountEnable"] = value is not None
    if value is None:
        props.pop("maxTagCount", None)
        props.pop("maxCountMessage", None)
    else:
        props["maxTagCount"] = value["count"]
        if "message" in value:
            props["maxCountMessage"] = value["message"]
        else:
            props.pop("maxCountMessage", None)
    return ["成组更新最多选择数和提示，不改变选项身份"]


def validate_candidate(node: Mapping[str, Any], prop: str) -> None:
    props = node.get("props", {})
    if prop in {"selectionLimit", "defaultValue"} and props.get("maxCountEnable") is True:
        default, limit = props.get("defaultValue"), props.get("maxTagCount")
        if isinstance(default, list) and type(limit) in (int, float) and len(default) > limit:
            reject("INVALID_DEFAULT_RANGE", "默认选项超过最多选择数量。")
