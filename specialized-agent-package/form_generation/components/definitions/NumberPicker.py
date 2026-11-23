"""NumberPicker properties and paired numeric defaults."""
from __future__ import annotations

from typing import Any, Mapping

from ..common import PropertyRule, boolean, default_snapshot, enum, number, simulate_default, string, validate_default
from ..validation import validate_schema

PROPERTIES = {
    "placeholder": string(reset="请输入数字", has_reset=True),
    "defaultValue": PropertyRule(),
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
    return default_snapshot(node.get("props", {})) if prop == "defaultValue" else None


def clear(node: Mapping[str, Any], prop: str) -> dict[str, Any] | None:
    return {"exists": True, "value": {"mode": "undefined"}} if prop == "defaultValue" else None


def validate(node: Mapping[str, Any], prop: str, value: Any) -> bool:
    if prop != "defaultValue":
        return False
    validate_default(value, "number")
    return True


def simulate(node: dict[str, Any], prop: str, after: Mapping[str, Any]) -> list[str] | None:
    return simulate_default(node["props"], after.get("value")) if prop == "defaultValue" else None


def validate_candidate(node: Mapping[str, Any], prop: str) -> None:
    props = node.get("props", {})
    for bound in ("min", "max"):
        if props.get(bound + "Enable"):
            validate_schema(props.get(bound), {"type": "number"})
