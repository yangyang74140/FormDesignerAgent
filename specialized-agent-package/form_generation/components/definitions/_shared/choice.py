"""Choice-family defaults, option identity preservation and derived state."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from ...common import PropertyRule, boolean, string
from ...validation import reject, validate_schema

PROPERTIES = {
    "placeholder": string(reset="请选择", has_reset=True),
    "defaultValue": PropertyRule(),
    "popupMatchSelectWidth": boolean(),
    "showSearch": boolean(),
    "options": PropertyRule(saved_lock=True, handler_required=True),
}
def validate(node: Mapping[str, Any], prop: str, value: Any) -> bool:
    if prop != "defaultValue":
        return False
    component = node["componentName"]
    validate_schema(value, {"type": "string"} if component == "SelectSingle" else {"type": "array", "items": {"type": "string"}, "uniqueItems": True})
    options = node.get("props", {}).get("options", {}).get("dataSource")
    if not isinstance(options, list) or not all(isinstance(o, dict) and isinstance(o.get("value"), str) for o in options) or len({o["value"] for o in options}) != len(options):
        reject("MISSING_OPTIONS", "复制或设置默认项需要真实且唯一的选项 value。")
    wanted = [value] if component == "SelectSingle" else value
    if any(not any(o["value"] == v and o.get("disabled") is False for o in options) for v in wanted):
        reject("INVALID_DEFAULT_OPTION", "默认项必须存在且明确启用。")
    return True


def simulate(node: dict[str, Any], prop: str, after: Mapping[str, Any]) -> list[str] | None:
    if prop != "defaultValue":
        return None
    props, value = node["props"], after.get("value")
    if not isinstance(props.get("options"), dict) or not isinstance(props["options"].get("dataSource"), list):
        reject("MISSING_OPTIONS", "设置或清空默认项需要真实选项快照。")
    wanted = value if isinstance(value, list) else [value] if after["exists"] else []
    for option in props.get("options", {}).get("dataSource", []):
        option["activeKey"] = option.get("value") in wanted
    if after["exists"]:
        props["defaultValue"] = deepcopy(value)
    else:
        props.pop("defaultValue", None)
    return ["同步选项 activeKey 与默认值，保留选项身份和业务 value"]


def effects(node: dict[str, Any], prop: str, value: Any, previous: Any) -> list[str] | None:
    if prop != "options" or not isinstance(value, dict):
        return None
    props = node["props"]
    active = [o.get("value") for o in value.get("dataSource", []) if isinstance(o, dict) and o.get("activeKey")]
    if node["componentName"] == "SelectMulti":
        props["defaultValue"] = active
    elif active:
        props["defaultValue"] = active[0]
    else:
        props.pop("defaultValue", None)
    if "isColor" in value:
        props["enableColor"] = value["isColor"]
    return ["同步选项默认项、defaultValue 和颜色开关；保留身份与关联数据，删除须先检查引用"]


def dependencies(prop: str) -> tuple[str, ...]:
    return ("options",) if prop == "defaultValue" else ()


def validate_compound(node: dict[str, Any], prop: str, value: Any, original: list[dict[str, Any]], candidate: list[dict[str, Any]]) -> None:
    component = node["componentName"]
    if prop == "options":
        options = value.get("dataSource") if isinstance(value, dict) else None
        if not isinstance(options, list) or not all(isinstance(o, dict) and isinstance(o.get("primaryKey"), str) and isinstance(o.get("value"), str) and type(o.get("disabled")) is bool and type(o.get("activeKey")) is bool for o in options):
            reject("INVALID_OPTIONS", "选项必须保留真实身份、业务 value 及状态。")
        if len({o["primaryKey"] for o in options}) != len(options) or len({o["value"] for o in options}) != len(options):
            reject("INVALID_OPTIONS", "选项身份和业务 value 必须唯一。")
        active = [o for o in options if o["activeKey"]]
        if any(o["disabled"] for o in active) or component == "SelectSingle" and len(active) > 1:
            reject("INVALID_DEFAULT_OPTION", "默认项必须启用，单选至多一个。")
        old = next(n for n in original if n["id"] == node["id"])["props"].get("options", {})
        old_options = old.get("dataSource", []) if isinstance(old, dict) else []
        for previous in old_options:
            match = next((o for o in options if o["primaryKey"] == previous.get("primaryKey")), None)
            if match is None:
                reject("OPTION_REFERENCE_CHECK_REQUIRED", "删除选项需要专用引用检查，当前编译器不开放。")
            if match["value"] != previous.get("value"):
                reject("OPTION_IDENTITY_CHANGED", "不得改变已有选项的业务 value。")
            for key in ("associateDirectory", "relatedParentField"):
                if key in previous and match.get(key) != previous[key]:
                    reject("OPTION_RELATION_CHANGED", "选项目录和父子关系必须保留。")
        for key in ("associateDirectory", "relatedParentField"):
            if key in old and value.get(key) != old[key]:
                reject("OPTION_RELATION_CHANGED", "选项配置关联关系必须保留。")
