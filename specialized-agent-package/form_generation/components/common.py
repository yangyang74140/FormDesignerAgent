"""Shared property definitions and paired scalar-default behavior."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping

from .validation import reject, validate_schema

ACCESS = {"required": "required", "edit": "editable", "display": "visible", "disableManualEdit": "forbidManualInput"}
ACCESS_DEFAULTS = {"required": False, "editable": True, "visible": True, "forbidManualInput": False}
ALIASES = {
    "extra": "description", "描述": "description", "描述信息": "description",
    "extraType": "descriptionDisplay", "hideTitle": "titleHidden", "textAlign": "titleAlign",
    "labelPosition": "titlePosition", "标题": "label", "字段标题": "label",
    "必填": "required", "必添": "required", "requried": "required", "requied": "required",
    "占位提示": "placeholder", "占位符": "placeholder", "默认值": "defaultValue",
    "隐藏标题": "titleHidden", "标题对齐": "titleAlign", "标题位置": "titlePosition", "尺寸": "size",
    "可编辑": "edit", "显示": "display", "禁止手工编辑": "disableManualEdit",
}
STORAGE = {"description": "extra", "descriptionDisplay": "extraType", "titleHidden": "hideTitle", "titleAlign": "textAlign", "titlePosition": "labelPosition"}


@dataclass(frozen=True)
class PropertyRule:
    schema: Mapping[str, Any] | None = None
    default: Any = None
    has_default: bool = False
    reset: Any = None
    has_reset: bool = False
    prerequisite: str | None = None
    saved_lock: bool = False
    handler_required: bool = False
    unvalidated_operations: tuple[str, ...] = ()


def boolean(**kwargs: Any) -> PropertyRule:
    return PropertyRule({"type": "boolean"}, **kwargs)


def number(minimum: Any = None, maximum: Any = None, **kwargs: Any) -> PropertyRule:
    return PropertyRule({"type": "number", **({"minimum": minimum} if minimum is not None else {}), **({"maximum": maximum} if maximum is not None else {})}, **kwargs)


def string(**kwargs: Any) -> PropertyRule:
    return PropertyRule({"type": "string"}, **kwargs)


def enum(values: list[str], **kwargs: Any) -> PropertyRule:
    return PropertyRule({"type": "string", "enum": values}, **kwargs)


COMMON_PROPERTIES = {
    "label": PropertyRule({"type": "string", "maxLength": 50, "minLength": 1}),
    "enableCustomTitle": boolean(),
    "customTitle": PropertyRule({"type": "string", "maxLength": 50, "minLength": 0}, prerequisite="enableCustomTitle", reset="", has_reset=True),
    "description": PropertyRule({"type": "string", "maxLength": 200}, reset="", has_reset=True),
    "descriptionDisplay": enum(["text", "icon"], default="icon", has_default=True),
    "required": boolean(),
    "requiredMessage": string(prerequisite="required"),
    "edit": boolean(),
    "display": boolean(),
    "disableManualEdit": boolean(),
    "titleHidden": boolean(),
    "readOnlyDisplay": boolean(),
    "titleAlign": enum(["left", "right"]),
    "titlePosition": enum(["top", "left"]),
    "size": enum(["small", "medium", "large"], default="medium", has_default=True),
    "relatedField": PropertyRule(handler_required=True),
}


def default_snapshot(props: Mapping[str, Any]) -> dict[str, Any]:
    if "defaultValueConfig" not in props and "defaultValue" not in props:
        return {"exists": False}
    mode = props.get("defaultValueConfig", "custom" if "defaultValue" in props else "undefined")
    value = {"mode": mode}
    if mode in ("custom", "formula") and "defaultValue" in props:
        value["value"] = deepcopy(props["defaultValue"])
    return {"exists": True, "value": value}


def validate_default(value: Any, value_type: str, system_mode: str | None = None) -> None:
    if not isinstance(value, dict) or set(value) - {"mode", "value"}:
        reject("INVALID_DEFAULT", "默认值必须包含受控 mode/value。")
    mode = value.get("mode")
    modes = {"undefined", "custom"} | ({system_mode} if system_mode else set())
    if mode not in modes or (mode == "custom") != ("value" in value):
        reject("UNSUPPORTED_DEFAULT_MODE", "默认值模式无效；公式执行未注册。")
    if mode == "custom":
        validate_schema(value["value"], {"type": value_type})


def simulate_default(props: dict[str, Any], value: Any) -> list[str]:
    props["defaultValueConfig"] = value["mode"]
    if value["mode"] == "custom":
        props["defaultValue"] = deepcopy(value["value"])
    else:
        props.pop("defaultValue", None)
    return ["成对更新默认值模式和内容；非静态模式删除静态值"]
