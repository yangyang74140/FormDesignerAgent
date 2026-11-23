"""NumberPicker properties and paired numeric defaults."""
from __future__ import annotations

from typing import Any, Mapping

from ..common import PropertyRule, boolean, default_snapshot, enum, number, simulate_default, string, validate_default
from ..validation import reject, validate_schema

PROPERTIES = {
    "placeholder": string(reset="请输入数字", has_reset=True),
    "defaultValue": PropertyRule(unvalidated_operations=("clear", "reset")),
    "numericRange": PropertyRule(handler_required=True, reset={}, has_reset=True, unvalidated_operations=("clear", "reset")),
    "precision": number(0, 10, default=0, has_default=True, saved_lock=True),
    "numberType": enum(["numeric", "permille", "percent"], default="numeric", has_default=True, saved_lock=True),
    "showAmountInUppercase": boolean(),
    "amountInUppercase": enum(["inner", "outer"], default="outer", has_default=True, prerequisite="showAmountInUppercase"),
    "thousandsSeparator": boolean(),
    "step": number(0, default=1, has_default=True),
    "innerAfter": string(reset="", has_reset=True),
    "minEnable": boolean(),
    "min": number(prerequisite="minEnable"),
    "minMessage": string(prerequisite="minEnable"),
    "maxEnable": boolean(),
    "max": number(prerequisite="maxEnable"),
    "maxMessage": string(prerequisite="maxEnable"),
}


def snapshot(node: Mapping[str, Any], prop: str) -> dict[str, Any] | None:
    props = node.get("props", {})
    if prop == "defaultValue":
        return default_snapshot(props)
    if prop == "numericRange":
        keys = ("minEnable", "min", "minMessage", "maxEnable", "max", "maxMessage")
        value = {bound: {"value": props[bound], **({"message": props[bound + "Message"]} if bound + "Message" in props else {})}
                 for bound in ("min", "max") if props.get(bound + "Enable") is True and bound in props}
        return {"exists": True, "value": value} if any(key in props for key in keys) else {"exists": False}
    return None


def clear(node: Mapping[str, Any], prop: str) -> dict[str, Any] | None:
    if prop == "defaultValue":
        return {"exists": True, "value": {"mode": "undefined"}}
    return {"exists": True, "value": {}} if prop == "numericRange" else None


def validate(node: Mapping[str, Any], prop: str, value: Any) -> bool:
    if prop == "defaultValue":
        validate_default(value, "number")
    elif prop == "numericRange":
        bound = {"type": "object", "properties": {"value": {"type": "number"}, "message": {"type": "string", "maxLength": 200}}, "required": ["value"], "additionalProperties": False}
        validate_schema(value, {"type": "object", "properties": {"min": bound, "max": bound}, "additionalProperties": False})
        if "min" in value and "max" in value and value["min"]["value"] > value["max"]["value"]:
            reject("INVALID_RANGE", "最小值不能大于最大值。")
    else:
        return False
    return True


def simulate(node: dict[str, Any], prop: str, after: Mapping[str, Any]) -> list[str] | None:
    props, value = node["props"], after.get("value")
    if prop == "defaultValue":
        return simulate_default(props, value)
    if prop == "numericRange":
        for bound in ("min", "max"):
            props[bound + "Enable"] = bound in value
            if bound in value:
                props[bound] = value[bound]["value"]
                if "message" in value[bound]:
                    props[bound + "Message"] = value[bound]["message"]
                else:
                    props.pop(bound + "Message", None)
            else:
                props.pop(bound, None)
                props.pop(bound + "Message", None)
        return ["成组更新最小值、最大值及提示；未指定的边界关闭并清理"]
    return None


def validate_candidate(node: Mapping[str, Any], prop: str) -> None:
    props = node.get("props", {})
    for bound in ("min", "max"):
        if props.get(bound + "Enable"):
            validate_schema(props.get(bound), {"type": "number"})
    if prop in {"numericRange", "defaultValue", "min", "max", "minEnable", "maxEnable"}:
        default = props.get("defaultValue")
        if props.get("defaultValueConfig") == "custom" and type(default) in (int, float):
            if any(props.get(bound + "Enable") is True and type(props.get(bound)) in (int, float) and (default < props[bound] if bound == "min" else default > props[bound]) for bound in ("min", "max")):
                reject("INVALID_DEFAULT_RANGE", "默认数字超出配置范围。")
