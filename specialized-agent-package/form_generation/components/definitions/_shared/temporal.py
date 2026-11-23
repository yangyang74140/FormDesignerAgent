"""Shared date/time defaults, format validation and range behavior."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from ...common import PropertyRule, boolean, default_snapshot, simulate_default, validate_default
from ...validation import reject, validate_schema

PROPERTIES = {
    "defaultValue": PropertyRule(),
    "allowClear": boolean(reset=True, has_reset=True),
    "minTimeCondition": PropertyRule(handler_required=True),
    "maxTimeCondition": PropertyRule(handler_required=True),
}


def validate_date(value: Any, fmt: str) -> None:
    formats = {"YYYY": "%Y", "YYYY-MM": "%Y-%m", "YYYY-MM-DD": "%Y-%m-%d", "YYYY-MM-DD HH": "%Y-%m-%d %H", "YYYY-MM-DD HH:mm": "%Y-%m-%d %H:%M", "YYYY-MM-DD HH:mm:ss": "%Y-%m-%d %H:%M:%S", "HH:mm": "%H:%M", "HH:mm:ss": "%H:%M:%S"}
    if fmt not in formats or not isinstance(value, str):
        reject("INVALID_DATE", "缺少有效日期/时间格式。")
    try:
        parsed = datetime.strptime(value, formats[fmt])
        if parsed.strftime(formats[fmt]) != value:
            reject("INVALID_DATE", "日期/时间格式不匹配。")
    except ValueError:
        reject("INVALID_DATE", "日期/时间值无效。")


def validate_compound(node: dict[str, Any], prop: str, value: Any, original: list[dict[str, Any]], candidate: list[dict[str, Any]]) -> None:
    component = node["componentName"]
    props = node.get("props", {})
    if prop in ("minTimeCondition", "maxTimeCondition") and value is not None:
        if not isinstance(value, dict) or value.get("enabled") is not True:
            reject("INVALID_TIME_CONDITION", "时间范围必须启用或显式置 null。")
        source = value.get("source")
        common = {"enabled", "source"}
        if source == "fixed":
            if set(value) != common | {"fixedValue"}:
                reject("INVALID_TIME_CONDITION", "固定时间范围不能残留其他 source 分支。")
            validate_date(value["fixedValue"], props.get("format"))
        elif source == "field":
            if set(value) != common | {"fieldName"}:
                reject("INVALID_TIME_CONDITION", "字段时间范围不能残留其他分支。")
            matches = [n for n in candidate if n.get("props", {}).get("name") == value["fieldName"]]
            if len(matches) != 1 or matches[0]["id"] == node["id"] or matches[0]["componentName"] != component:
                reject("INVALID_REFERENCE", "时间范围必须引用其他真实同类字段。")
        elif source == "dynamic":
            mode = value.get("dynamicMode")
            if mode == "current":
                allowed = common | {"dynamicMode"} | ({"dynamicAnchor"} if component == "DatePicker" else set())
                anchors = {"today", "currentWeek", "currentMonth", "nextMonth", "currentQuarter", "currentYear"}
                if set(value) - allowed or component == "DatePicker" and value.get("dynamicAnchor") not in anchors:
                    reject("INVALID_TIME_CONDITION", "动态当前时间分支参数无效。")
            elif component == "DatePicker" and mode in ("before", "after"):
                if set(value) != common | {"dynamicMode", "dynamicUnit", "offsetValue"} or value["dynamicUnit"] not in ("day", "week", "month", "quarter", "year"):
                    reject("INVALID_TIME_CONDITION", "动态日期偏移分支无效。")
                validate_schema(value["offsetValue"], {"type": "number", "minimum": 0})
            else:
                reject("INVALID_TIME_CONDITION", "时间仅支持 current；日期偏移需要完整参数。")
        else:
            reject("INVALID_TIME_CONDITION", "时间范围 source 未注册。")
        low, high = props.get("minTimeCondition"), props.get("maxTimeCondition")
        if isinstance(low, dict) and isinstance(high, dict) and low.get("source") == high.get("source") == "fixed" and low.get("enabled") and high.get("enabled") and low.get("fixedValue", "") > high.get("fixedValue", ""):
            reject("INVALID_RANGE", "最早时间不能晚于最晚时间。")


def snapshot(node: Mapping[str, Any], prop: str) -> dict[str, Any] | None:
    return default_snapshot(node.get("props", {})) if prop == "defaultValue" else None


def clear(node: Mapping[str, Any], prop: str) -> dict[str, Any] | None:
    if prop == "defaultValue":
        return {"exists": True, "value": {"mode": "undefined"}}
    if prop in ("minTimeCondition", "maxTimeCondition"):
        return {"exists": True, "value": None}
    return None


def validate(node: Mapping[str, Any], prop: str, value: Any) -> bool:
    if prop != "defaultValue":
        return False
    validate_default(value, "string", "systemDate" if node["componentName"] == "DatePicker" else "systemTime")
    if value["mode"] == "custom":
        validate_date(value["value"], node.get("props", {}).get("format"))
    return True


def simulate(node: dict[str, Any], prop: str, after: Mapping[str, Any]) -> list[str] | None:
    return simulate_default(node["props"], after.get("value")) if prop == "defaultValue" else None


def effects(node: dict[str, Any], prop: str, value: Any, previous: Any) -> list[str] | None:
    if prop in ("minTimeCondition", "maxTimeCondition"):
        result = ["按 source 替换范围分支并验证同类字段引用及上下界"]
        if isinstance(value, dict) and value.get("dynamicMode") in ("before", "after"):
            result.append("日期 day/week/month/quarter/year 使用 1/7/30/90/365 天近似偏移")
        return result
    return None


def dependencies(prop: str) -> tuple[str, ...]:
    return ("format",) if prop in ("defaultValue", "minTimeCondition", "maxTimeCondition") else ()
