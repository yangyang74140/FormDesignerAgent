"""DatePicker properties, selectable weekdays and format effects."""
from __future__ import annotations

from typing import Any, Mapping

from ..common import PropertyRule, enum, string
from ..validation import reject
from ._shared import temporal
from ._shared.temporal import simulate, snapshot, validate

PROPERTIES = {
    **temporal.PROPERTIES,
    "placeholder": string(reset="年-月-日", has_reset=True),
    "format": enum(["YYYY", "YYYY-MM", "YYYY-MM-DD", "YYYY-MM-DD HH", "YYYY-MM-DD HH:mm", "YYYY-MM-DD HH:mm:ss"], reset="YYYY-MM-DD", has_reset=True, saved_lock=True),
    "disabledDays": PropertyRule(handler_required=True),
}


def clear(node: Mapping[str, Any], prop: str) -> dict[str, Any] | None:
    if prop == "disabledDays":
        return {"exists": True, "value": None}
    return temporal.clear(node, prop)


def validate_compound(node: dict[str, Any], prop: str, value: Any, original: list[dict[str, Any]], candidate: list[dict[str, Any]]) -> None:
    if prop == "disabledDays" and value is not None:
        if not isinstance(value, dict) or set(value) != {"enabled", "days"} or type(value["enabled"]) is not bool or not isinstance(value["days"], list):
            reject("INVALID_WEEKDAYS", "可选星期必须有 enabled 和 days。")
        if any(day not in [str(i) for i in range(7)] for day in value["days"]) or len(set(value["days"])) != len(value["days"]):
            reject("INVALID_WEEKDAYS", "星期必须是唯一的 0–6 字符串。")
        if value["enabled"] and (not value["days"] or node.get("props", {}).get("format") in ("YYYY", "YYYY-MM")):
            reject("INVALID_WEEKDAYS", "年/月格式不支持可选星期；空数组不能表示禁止全部日期。")
    temporal.validate_compound(node, prop, value, original, candidate)


def effects(node: dict[str, Any], prop: str, value: Any, previous: Any) -> list[str] | None:
    if prop == "format" and previous != value:
        props = node["props"]
        props["placeholder"] = value.replace("YYYY", "年").replace("MM", "月").replace("DD", "日").replace("HH", "时").replace("mm", "分").replace("ss", "秒")
        if value in ("YYYY", "YYYY-MM"):
            props["disabledDays"] = None
        return ["仅真实日期格式变更触发占位提示更新；年/月格式清空可选星期"]
    if prop == "disabledDays":
        return ["days 表示允许选择的星期；null 关闭限制，不用空数组表示全部禁用"]
    return temporal.effects(node, prop, value, previous)


def dependencies(prop: str) -> tuple[str, ...]:
    return ("format",) if prop == "disabledDays" else temporal.dependencies(prop)
