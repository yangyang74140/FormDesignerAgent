"""Compose common and named component property rules."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Mapping

from .common import ACCESS, ACCESS_DEFAULTS, COMMON_PROPERTIES, STORAGE, PropertyRule
from .definitions import DatePicker, Input, InputTextArea, NumberPicker, SelectMulti, SelectSingle, TimePicker
from .validation import reject, validate_schema


@dataclass(frozen=True)
class ComponentRules:
    """Intrinsic rules only; host catalog authorization stays in the compiler.

    Snapshots and metadata returned by this module are detached. Simulation
    mutates only the caller's private candidate node, never a host snapshot.
    """

    _properties: Mapping[str, PropertyRule]
    _definition: ModuleType

    @property
    def properties(self) -> dict[str, PropertyRule]:
        return deepcopy(dict(self._properties))

    def intrinsic_schema(self, prop: str) -> dict[str, Any] | None:
        rule = self._properties.get(prop)
        return deepcopy(rule.schema) if rule else None

    def snapshot(self, node: Mapping[str, Any], prop: str) -> dict[str, Any]:
        props = node.get("props", {})
        if prop in ACCESS:
            access = props.get("access", {})
            if not isinstance(access, dict):
                reject("INVALID_SNAPSHOT", "access 快照无效。")
            key = ACCESS[prop]
            return {"exists": key in access, **({"value": deepcopy(access[key])} if key in access else {})}
        snapshot = getattr(self._definition, "snapshot", None)
        specialized = snapshot(node, prop) if snapshot else None
        if specialized is not None:
            return specialized
        key = STORAGE.get(prop, prop)
        return {"exists": key in props, **({"value": deepcopy(props[key])} if key in props else {})}

    def default(self, prop: str) -> tuple[bool, Any]:
        rule = self._properties.get(prop)
        return (True, deepcopy(rule.default)) if rule and rule.has_default else (False, None)

    def after(self, node: dict[str, Any], prop: str, op: str, slots: Mapping[str, Any], definition: Mapping[str, Any]) -> dict[str, Any]:
        rule = self._properties.get(prop)
        if op == "set":
            if "value" not in slots:
                reject("VALUE_REQUIRED", "set 必须有 value。", True)
            value = deepcopy(slots["value"])
            normalize = getattr(self._definition, "normalize_set", None)
            return {"exists": True, "value": normalize(node, prop, value) if normalize else value}
        if "value" in slots:
            reject("UNEXPECTED_VALUE", "clear/unset/reset 不携带 value。")
        if op == "unset":
            if prop in ACCESS or prop in ("defaultValue", "textLengthLimit", "formatValidation", "numericRange", "selectionLimit", "label"):
                reject("UNSET_UNSUPPORTED", "此语义属性不能用通用删除代替专用清空。")
            if prop not in ("titleAlign", "titlePosition") and not definition.get("allowUnset"):
                reject("UNSET_UNSUPPORTED", "该属性不支持删除局部覆盖。")
            return {"exists": False}
        if op == "reset":
            reset = definition.get("reset")
            if prop in ("titleAlign", "titlePosition") or isinstance(reset, dict) and reset.get("source") == "inherited":
                return {"exists": False}
            if "default" in definition:
                value = deepcopy(definition["default"])
            elif rule and rule.has_default:
                value = deepcopy(rule.default)
            elif rule and rule.has_reset:
                value = deepcopy(rule.reset)
            elif prop in ("defaultValue", "formatValidation"):
                return self.after(node, prop, "clear", {}, definition)
            elif prop in ACCESS:
                value = ACCESS_DEFAULTS[ACCESS[prop]]
            elif rule and rule.schema and rule.schema.get("type") == "boolean":
                value = False
            else:
                reject("MISSING_RESET_DEFAULT", "宿主未声明重置值。")
            return {"exists": True, "value": value}
        if op == "clear":
            if prop == "label":
                reject("TITLE_REQUIRED", "标题不能清空。")
            clear = self._definition.clear
            if prop in ("defaultValue", "textLengthLimit", "formatValidation"):
                specialized = clear(node, prop)
                if specialized is not None:
                    return specialized
            if "clearValue" in definition:
                return {"exists": True, "value": deepcopy(definition["clearValue"])}
            specialized = clear(node, prop)
            if specialized is not None:
                return specialized
            intrinsic = self.intrinsic_schema(prop)
            if intrinsic and intrinsic.get("type") == "boolean":
                return {"exists": True, "value": False}
            if intrinsic and intrinsic.get("type") == "string" and "enum" not in intrinsic:
                return {"exists": True, "value": ""}
            reject("CLEAR_UNSUPPORTED", "该属性没有已注册的清空语义。")
        reject("UNSUPPORTED_OPERATION", "不支持此操作。")

    def validate(self, node: dict[str, Any], prop: str, value: Any, definition: Mapping[str, Any]) -> None:
        rule = self._properties.get(prop)
        intrinsic = self.intrinsic_schema(prop)
        schema = definition.get("valueSchema", definition.get("schema"))
        if schema is None and "type" in definition:
            schema = {k: v for k, v in definition.items() if k in ("type", "enum", "minimum", "maximum", "minLength", "maxLength", "pattern", "items", "properties", "required", "additionalProperties")}
        if schema:
            validate_schema(value, schema)
        specialized = self._definition.validate(node, prop, value)
        if not specialized:
            if intrinsic:
                validate_schema(value, intrinsic)
            elif not schema or not definition.get("handlerId"):
                reject("MISSING_COMPOUND_HANDLER", "未知或复合属性必须有结构化 schema 和专用宿主处理器。")
        if isinstance(value, (dict, list)) and not specialized and (not schema or not definition.get("handlerId")):
            reject("MISSING_COMPOUND_HANDLER", "复合属性必须声明结构化 schema 和处理器。")
        if rule and rule.handler_required:
            if not definition.get("handlerId") or not schema:
                reject("MISSING_COMPOUND_HANDLER", "此属性依赖专用宿主校验与处理器。")
            if prop == "relatedField" and not definition.get("remoteMetadataAvailable"):
                reject("MISSING_REMOTE_METADATA", "缺少关联字段远程元数据。")
            if prop == "isUnique" and value and not definition.get("serviceAvailable"):
                reject("MISSING_UNIQUENESS_SERVICE", "未接入真实唯一性检查服务。")

    def validate_compound(self, node: dict[str, Any], prop: str, value: Any, definition: Mapping[str, Any], original: list[dict[str, Any]], candidate: list[dict[str, Any]]) -> None:
        validate = getattr(self._definition, "validate_compound", None)
        if validate:
            validate(node, prop, value, original, candidate)
        if prop == "relatedField" and value is not None and not definition.get("remoteMetadataAvailable"):
            reject("MISSING_REMOTE_METADATA", "关联字段缺少远程目录。")

    def simulate(self, node: dict[str, Any], prop: str, after: Mapping[str, Any]) -> list[str]:
        props = node.setdefault("props", {})
        value = after.get("value")
        if prop in ACCESS:
            access = props.setdefault("access", {})
            for key, default in ACCESS_DEFAULTS.items():
                access.setdefault(key, default)
            access[ACCESS[prop]] = value
            if prop == "display" and not value:
                access.update(editable=False, required=False, forbidManualInput=False)
            elif prop == "edit" and not value:
                access.update(required=False, forbidManualInput=False)
            elif prop in ("required", "disableManualEdit") and value:
                access.update(visible=True, editable=True)
            props["required"] = access["required"]
            return ["通过 access helper 同步权限及兼容 required；开启必填/禁止手工编辑会开启显示和编辑；关闭显示/编辑会关闭依赖权限"]
        specialized = self._definition.simulate(node, prop, after)
        if specialized is not None:
            return specialized
        key = STORAGE.get(prop, prop)
        previous = props.get(key)
        if after["exists"]:
            props[key] = deepcopy(value)
        else:
            props.pop(key, None)
        effects = getattr(self._definition, "effects", None)
        specialized = effects(node, prop, value, previous) if effects else None
        if specialized is not None:
            return specialized
        if prop in ("titleAlign", "titlePosition") and not after["exists"]:
            return ["删除局部覆盖，有效值由表单布局继承决定"]
        if prop == "relatedField":
            return ["请求宿主专用处理器同步节点绑定及表单 relatedFields，并复核远程字段元数据"]
        if prop == "isUnique" and value:
            return ["请求已注册的唯一性检查服务；真实执行结果以宿主回执为准"]
        return []

    def validate_candidate(self, node: Mapping[str, Any], prop: str) -> None:
        validate = getattr(self._definition, "validate_candidate", None)
        if validate:
            validate(node, prop)
        props = node.get("props", {})
        if props.get("minEnable") and props.get("maxEnable") and (type(props.get("min")) not in (int, float) or type(props.get("max")) not in (int, float) or props["min"] > props["max"]):
            reject("INVALID_RANGE", "最小值与最大值配置矛盾。")

    def dependencies(self, prop: str) -> tuple[str, ...]:
        dependencies = getattr(self._definition, "dependencies", None)
        return dependencies(prop) if dependencies else ()

    def normalize_copy(self, prop: str, value: Any) -> Any:
        normalize = getattr(self._definition, "normalize_copy", None)
        return normalize(prop, value) if normalize else value

    def matches(self, prop: str, actual: Mapping[str, Any], after: Mapping[str, Any]) -> bool:
        matches = getattr(self._definition, "matches", None)
        return matches(prop, actual, after) if matches else actual == after


def _compose(definition: ModuleType) -> ComponentRules:
    return ComponentRules(deepcopy({**COMMON_PROPERTIES, **definition.PROPERTIES}), definition)


_RULES = {
    "Input": _compose(Input),
    "Input.TextArea": _compose(InputTextArea),
    "NumberPicker": _compose(NumberPicker),
    "DatePicker": _compose(DatePicker),
    "TimePicker": _compose(TimePicker),
    "SelectSingle": _compose(SelectSingle),
    "SelectMulti": _compose(SelectMulti),
}
PROPERTY_COMPONENTS = frozenset(_RULES)


def get_component_rules(component: str) -> ComponentRules:
    """Return intrinsic rules with detached metadata; unsupported names raise KeyError."""
    return _RULES[component]


def property_names(component: str) -> frozenset[str]:
    return frozenset(_RULES[component]._properties)
