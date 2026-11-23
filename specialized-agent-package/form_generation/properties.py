"""Deterministic property IR compiler; host execution is deliberately external.

Host metadata: capabilities.catalogVersion and components[name].properties map
semantic names to definitions (operations, valueSchema, handlerId, default,
clearValue, reset={"source": "inherited"}). capabilities.nodePolicies[id] declares
canRead/canModify/allowedProperties; legacy top-level nodePolicies with explicit
writable/saved/disabledName/system is also accepted. Saved-lock properties always
need saved/disabledName information. Structured values require a handlerId and a
bounded JSON schema. supportedActionVersions maps action names to exact versions.
resolvedProperties[id][property] supplies source/resolvedValue for query and copy.

Registered ruleCatalog/linkageCatalog entries contain handlerId, valueSchema,
operations and compatible components. Linkages additionally declare astOperators.
The rules/linkages context maps node IDs to current [{id, type, value}] snapshots.
Extension actions use form.apply_property_rule/form.apply_property_linkage, with
the same exact action contract version. Queries have a read-only presentation,
status ready, contract form_property_query.v1 and no executable result.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import json
import math
import re
from typing import Any, Mapping

PROPERTY_RESULT_KINDS = frozenset({"property_changes", "property_query", "property_undo"})
PROPERTY_ACTION_VERSION = "form_property_actions.v1"
COMPONENTS = frozenset({"Input", "Input.TextArea", "NumberPicker", "DatePicker", "TimePicker", "SelectSingle", "SelectMulti"})
_FORBIDDEN = frozenset({"name", "identifiers", "id", "__proto__", "prototype", "constructor"})
_ACCESS = {"required": "required", "edit": "editable", "display": "visible", "disableManualEdit": "forbidManualInput"}
_ACCESS_DEFAULTS = {"required": False, "editable": True, "visible": True, "forbidManualInput": False}
_ALIASES = {
    "extra": "description", "描述": "description", "描述信息": "description",
    "extraType": "descriptionDisplay", "hideTitle": "titleHidden", "textAlign": "titleAlign",
    "labelPosition": "titlePosition", "标题": "label", "字段标题": "label",
    "必填": "required", "必添": "required", "requried": "required", "requied": "required",
    "占位提示": "placeholder", "占位符": "placeholder", "默认值": "defaultValue",
    "隐藏标题": "titleHidden", "标题对齐": "titleAlign", "标题位置": "titlePosition", "尺寸": "size",
    "可编辑": "edit", "显示": "display", "禁止手工编辑": "disableManualEdit",
}
_STORAGE = {"description": "extra", "descriptionDisplay": "extraType", "titleHidden": "hideTitle", "titleAlign": "textAlign", "titlePosition": "labelPosition"}
_COMMON = {"label", "enableCustomTitle", "customTitle", "description", "descriptionDisplay", "required", "requiredMessage", "edit", "display", "disableManualEdit", "titleHidden", "readOnlyDisplay", "titleAlign", "titlePosition", "size", "placeholder", "defaultValue"}
_SPECIFIC = {
    "Input": {"allowClear", "textLengthLimit", "showLimitHint", "textMaxLength", "enableQuickCopy", "enableLinkParser", "relatedField", "isUnique", "uniqueMessage", "format", "formatMessage", "formatValidation"},
    "Input.TextArea": {"rows", "disableAutoHeight", "showEmptyLines", "textLengthLimit", "showLimitHint", "textMaxLength", "enableQuickCopy", "enableLinkParser", "relatedField"},
    "NumberPicker": {"numericRange", "precision", "numberType", "showAmountInUppercase", "amountInUppercase", "thousandsSeparator", "step", "innerAfter", "relatedField", "minEnable", "min", "minMessage", "maxEnable", "max", "maxMessage"},
    "DatePicker": {"format", "allowClear", "relatedField", "disabledDays", "minTimeCondition", "maxTimeCondition"},
    "TimePicker": {"format", "allowClear", "minuteStep", "secondStep", "relatedField", "minTimeCondition", "maxTimeCondition"},
    "SelectSingle": {"allowClear", "popupMatchSelectWidth", "showSearch", "options", "relatedField"},
    "SelectMulti": {"selectionLimit", "popupMatchSelectWidth", "selectAll", "showSearch", "supportReverseSelect", "options", "relatedField", "maxCountEnable", "maxTagCount", "maxCountMessage"},
}
_BOOLS = {"enableCustomTitle", "required", "edit", "display", "disableManualEdit", "titleHidden", "readOnlyDisplay", "allowClear", "showLimitHint", "enableQuickCopy", "enableLinkParser", "isUnique", "disableAutoHeight", "showEmptyLines", "showAmountInUppercase", "thousandsSeparator", "minEnable", "maxEnable", "popupMatchSelectWidth", "showSearch", "selectAll", "supportReverseSelect", "maxCountEnable"}
_NUMBERS = {"rows": (3, 10), "precision": (0, 10), "step": (0, None), "minuteStep": (1, 59), "secondStep": (1, 59), "min": (None, None), "max": (None, None), "textMaxLength": (1, None), "textLengthLimit": (1, None), "maxTagCount": (1, None)}
_ENUMS = {"descriptionDisplay": ["text", "icon"], "titleAlign": ["left", "right"], "titlePosition": ["top", "left"], "size": ["small", "medium", "large"], "numberType": ["numeric", "permille", "percent"], "amountInUppercase": ["inner", "outer"]}
_FORMATS = {"Input": ["none", "chinese", "number", "letter", "letter_num", "phone", "tel", "postcode", "idcard", "email"], "DatePicker": ["YYYY", "YYYY-MM", "YYYY-MM-DD", "YYYY-MM-DD HH", "YYYY-MM-DD HH:mm", "YYYY-MM-DD HH:mm:ss"], "TimePicker": ["HH:mm:ss", "HH:mm"]}
_DEFAULTS = {"size": "medium", "descriptionDisplay": "icon", "rows": 3, "precision": 0, "step": 1, "minuteStep": 1, "secondStep": 1, "textMaxLength": 200, "numberType": "numeric", "amountInUppercase": "outer"}
_CONDITIONS = {"customTitle": "enableCustomTitle", "requiredMessage": "required", "textMaxLength": "showLimitHint", "amountInUppercase": "showAmountInUppercase", "min": "minEnable", "minMessage": "minEnable", "max": "maxEnable", "maxMessage": "maxEnable", "maxTagCount": "maxCountEnable", "maxCountMessage": "maxCountEnable", "uniqueMessage": "isUnique"}


class _Rejected(Exception):
    def __init__(self, code: str, message: str, clarify: bool = False):
        self.code, self.message, self.clarify = code, message, clarify


def _reject(code: str, message: str, clarify: bool = False) -> None:
    raise _Rejected(code, message, clarify)


def property_capabilities() -> list[dict[str, Any]]:
    """Native Capability IR; definitions do not imply host execution support."""
    target = {"node_id": {"type": "string"}, "use_selection": {"type": "boolean"}, "node_label": {"type": "string"}, "node_name": {"type": "string"}}
    definitions = [
        ("form.property.change", ["property", "operation"], {**target, "property": {"type": "string"}, "operation": {"enum": ["set", "clear", "unset", "reset", "copy"]}, "value": {}, "selected": {"type": "boolean", "default": True}, "source_node_id": {"type": "string"}, "source_property": {"type": "string"}}, "单项语义属性操作。仅宿主注册能力可执行；复制读取真实来源；不写 JS、身份或任意路径。"),
        ("form.property.query", ["property"], {**target, "property": {"type": "string"}}, "只读查询存储状态、有效值及来源，不生成修改动作。"),
        ("form.property.undo", ["transaction_id"], {"transaction_id": {"type": "string"}}, "仅撤销宿主历史明确声明可撤销的当前事务，禁止自行构造逆补丁。"),
        ("form.property.rule", ["operation", "rule_type", "rule_id"], {**target, "operation": {"enum": ["add", "replace", "remove"]}, "rule_type": {"type": "string"}, "rule_id": {"type": "string"}, "value": {}, "selected": {"type": "boolean", "default": True}}, "受控规则目录操作，需要宿主 ruleCatalog、JSON schema 和处理器；rule_id 是真实规则或本提案稳定客户端引用。"),
        ("form.property.linkage", ["operation", "linkage_type", "linkage_id"], {**target, "operation": {"enum": ["add", "replace", "remove"]}, "linkage_type": {"type": "string"}, "linkage_id": {"type": "string"}, "value": {}, "selected": {"type": "boolean", "default": True}}, "宿主 linkageCatalog 注册的有界 AST；条件引用真实节点，禁止表达式字符串。"),
    ]
    return [{"capability": name, "semantics": text, "slots_schema": {"type": "object", "required": required, "additionalProperties": False, "properties": props}} for name, required, props, text in definitions]


def _json_safe(value: Any, depth: int = 0) -> bool:
    if depth > 30:
        return False
    if value is None or type(value) in (str, bool, int):
        return True
    if type(value) is float:
        return math.isfinite(value)
    if isinstance(value, list):
        return len(value) <= 1000 and all(_json_safe(v, depth + 1) for v in value)
    if isinstance(value, dict):
        return len(value) <= 1000 and all(isinstance(k, str) and k not in {"__proto__", "prototype", "constructor"} and _json_safe(v, depth + 1) for k, v in value.items())
    return False


def _schema(value: Any, schema: Any) -> None:
    """Validate the deliberately finite supported JSON-schema subset, fail closed."""
    if not isinstance(schema, Mapping) or not schema:
        _reject("MISSING_VALUE_SCHEMA", "宿主未声明可验证的值类型。")
    allowed = {"type", "enum", "const", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minLength", "maxLength", "pattern", "items", "minItems", "maxItems", "uniqueItems", "properties", "required", "additionalProperties", "oneOf", "anyOf", "description", "title", "default"}
    if set(schema) - allowed:
        _reject("UNSUPPORTED_VALUE_SCHEMA", "值 schema 含未支持的验证约束。")
    for union in ("oneOf", "anyOf"):
        if union in schema:
            if not isinstance(schema[union], list) or not schema[union]:
                _reject("INVALID_VALUE_SCHEMA", "联合类型声明无效。")
            matches = 0
            for branch in schema[union]:
                try:
                    _schema(value, branch)
                    matches += 1
                except _Rejected:
                    pass
            if matches == 0 or (union == "oneOf" and matches != 1):
                _reject("INVALID_VALUE", "值未匹配注册的联合类型。")
    kinds = schema.get("type")
    kinds = kinds if isinstance(kinds, list) else [kinds] if kinds else []
    types = {"string": type(value) is str, "boolean": type(value) is bool, "number": type(value) in (int, float) and math.isfinite(value), "integer": type(value) in (int, float) and math.isfinite(value) and value == int(value), "object": isinstance(value, dict), "array": isinstance(value, list), "null": value is None}
    if kinds and (any(kind not in types for kind in kinds) or not any(types[kind] for kind in kinds)):
        _reject("INVALID_VALUE", "属性值类型不匹配。")
    if not kinds and not any(key in schema for key in ("enum", "const", "oneOf", "anyOf")):
        _reject("MISSING_VALUE_SCHEMA", "值 schema 缺少类型。")
    if "enum" in schema and not any(type(value) is type(option) and value == option for option in schema["enum"]):
        _reject("INVALID_VALUE", "值不属于注册枚举。")
    if "const" in schema and (type(value) is not type(schema["const"]) or value != schema["const"]):
        _reject("INVALID_VALUE", "值不匹配常量。")
    if type(value) in (int, float):
        for key, valid in (("minimum", lambda x: value >= x), ("maximum", lambda x: value <= x), ("exclusiveMinimum", lambda x: value > x), ("exclusiveMaximum", lambda x: value < x)):
            if key in schema and not valid(schema[key]):
                _reject("INVALID_VALUE", "数值超出注册范围。")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", 100000):
            _reject("INVALID_VALUE", "字符串长度超出范围。")
        if "pattern" in schema and not re.fullmatch(schema["pattern"], value):
            _reject("INVALID_VALUE", "字符串格式不匹配。")
    if isinstance(value, (dict, list)) and "type" not in schema and "properties" not in schema and "items" not in schema and any(key in schema for key in ("oneOf", "anyOf", "enum", "const")):
        return
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", 1000):
            _reject("INVALID_VALUE", "数组长度超出范围。")
        if schema.get("uniqueItems") and len({json.dumps(v, sort_keys=True) for v in value}) != len(value):
            _reject("INVALID_VALUE", "数组不能包含重复值。")
        if "items" not in schema:
            _reject("MISSING_VALUE_SCHEMA", "数组缺少元素 schema。")
        for item in value:
            _schema(item, schema["items"])
    if isinstance(value, dict):
        props = schema.get("properties")
        if not isinstance(props, Mapping) or schema.get("additionalProperties") is not False:
            _reject("UNBOUNDED_OBJECT", "复合值必须声明完整字段并禁止额外属性。")
        if set(value) - set(props) or set(schema.get("required", [])) - set(value):
            _reject("INVALID_VALUE", "复合值字段缺失或不受支持。")
        for key, child in value.items():
            _schema(child, props[key])


def _id(prefix: str, value: Any) -> str:
    return prefix + hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()[:20]


def _nodes(schema: Mapping[str, Any]) -> list[dict[str, Any]]:
    out = []
    def walk(items: Any) -> None:
        if not isinstance(items, list):
            _reject("INVALID_SNAPSHOT", "节点列表无效。")
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not isinstance(item.get("props", {}), dict):
                _reject("INVALID_SNAPSHOT", "节点快照无效。")
            out.append(item)
            if "children" in item:
                walk(item["children"])
    walk(schema.get("fields", []))
    if len({n["id"] for n in out}) != len(out):
        _reject("INVALID_SNAPSHOT", "节点 ID 不唯一。")
    return out


def _target(slots: Mapping[str, Any], nodes: list[dict[str, Any]], context: Mapping[str, Any]) -> dict[str, Any]:
    if "use_selection" in slots and type(slots["use_selection"]) is not bool:
        _reject("INVALID_TARGET", "use_selection 必须为 boolean。")
    selectors = []
    for slot, key in (("node_id", "id"), ("node_label", "label"), ("node_name", "name")):
        if slot in slots:
            if not isinstance(slots[slot], str) or not slots[slot]:
                _reject("TARGET_REQUIRED", "目标不明确，请选择组件。", True)
            selectors.append({n["id"] for n in nodes if (n.get(key) if key == "id" else n.get("props", {}).get(key)) == slots[slot]})
    if slots.get("use_selection"):
        selected = context.get("selection", {}).get("nodeId")
        selectors.append({n["id"] for n in nodes if n["id"] == selected})
    if not selectors or any(len(s) != 1 for s in selectors) or len(set.union(*selectors)) != 1:
        _reject("TARGET_REQUIRED", "目标不存在、重复或选择为空，请明确一个组件。", True)
    node_id = next(iter(selectors[0]))
    return next(n for n in nodes if n["id"] == node_id)


def _canonical(prop: Any) -> str:
    if not isinstance(prop, str) or not prop or prop in _FORBIDDEN or "." in prop or "[" in prop:
        _reject("FORBIDDEN_PROPERTY", "禁止修改身份、路径或未知属性。")
    return _ALIASES.get(prop, prop)


def _definition(node: dict[str, Any], prop: str, caps: Mapping[str, Any]) -> dict[str, Any]:
    component = node.get("componentName")
    if component not in COMPONENTS:
        _reject("UNSUPPORTED_COMPONENT", "不支持系统组件或容器属性。")
    if prop not in _COMMON | _SPECIFIC[component]:
        _reject("UNSUPPORTED_PROPERTY", f"组件 {component} 没有注册的内置语义 {prop}。")
    definitions = caps.get("components", {}).get(component, {}).get("properties")
    if not isinstance(definitions, dict):
        _reject("MISSING_PROPERTY_CATALOG", "宿主未提供组件属性目录。")
    matches = [v for k, v in definitions.items() if _ALIASES.get(k, k) == prop or isinstance(v, dict) and prop in v.get("aliases", [])]
    if len(matches) != 1 or not isinstance(matches[0], dict):
        _reject("UNSUPPORTED_PROPERTY", f"宿主未唯一注册语义属性 {prop}。")
    if matches[0].get("supported") is False:
        _reject("UNSUPPORTED_PROPERTY", f"宿主不支持属性 {prop}。")
    return matches[0]


def _version(context: Mapping[str, Any], action: str) -> None:
    versions = context.get("supportedActionVersions", {}).get(action)
    if versions is None:
        declarations = context.get("capabilities", {}).get("actions", {})
        versions = declarations.get(action) if isinstance(declarations, dict) else None
    if isinstance(versions, dict):
        versions = versions.get("versions", versions.get("schemaVersions"))
    if isinstance(versions, str):
        versions = [versions]
    if not isinstance(versions, list) or PROPERTY_ACTION_VERSION not in versions:
        _reject("ACTION_VERSION_UNSUPPORTED", f"宿主未声明 {action} 的 {PROPERTY_ACTION_VERSION}。")


def _node_policy(node: Mapping[str, Any], context: Mapping[str, Any]) -> dict[str, Any]:
    policies = context.get("nodePolicies", context.get("capabilities", {}).get("nodePolicies", {}))
    policy = policies.get(node["id"]) if isinstance(policies, dict) else None
    if not isinstance(policy, dict):
        _reject("MISSING_NODE_POLICY", "缺少节点访问策略。")
    return policy


def _read_policy(node: Mapping[str, Any], prop: str, context: Mapping[str, Any]) -> None:
    policy = _node_policy(node, context)
    if policy.get("canRead") is False or policy.get("readable") is False:
        _reject("QUERY_UNSUPPORTED", "节点读取策略不允许访问此属性。")
    if "allowedProperties" in policy and prop not in policy["allowedProperties"] and _STORAGE.get(prop, prop) not in policy["allowedProperties"]:
        _reject("QUERY_UNSUPPORTED", "属性不在节点读取授权范围内。")


def _policy(node: dict[str, Any], prop: str, definition: dict[str, Any], context: Mapping[str, Any]) -> None:
    policy = _node_policy(node, context)
    modern = "canModify" in policy
    system = policy.get("system", policy.get("isSystem", policy.get("isSystemField", False if modern else None)))
    writable = policy.get("canModify", policy.get("writable"))
    if type(system) is not bool or type(writable) is not bool:
        _reject("MISSING_NODE_POLICY", "节点策略必须明确写入授权。")
    if not modern and (type(policy.get("saved")) is not bool or type(policy.get("disabledName")) is not bool):
        _reject("MISSING_NODE_POLICY", "节点策略必须明确 saved/disabledName。")
    if "allowedProperties" in policy and prop not in policy["allowedProperties"] and _STORAGE.get(prop, prop) not in policy["allowedProperties"]:
        _reject("PROPERTY_READ_ONLY", "属性不在节点授权列表中。")
    if modern and not isinstance(policy.get("allowedProperties"), list):
        _reject("MISSING_NODE_POLICY", "节点写入策略缺少 allowedProperties。")
    if system or not writable or node.get("isSystem") or node.get("componentCategory") in ("system", "layout", "container"):
        _reject("NODE_READ_ONLY", "系统字段、容器或只读节点禁止修改。")
    if definition.get("writable") is False or prop in policy.get("lockedProperties", []) or prop in policy.get("readOnlyProperties", []):
        _reject("PROPERTY_READ_ONLY", "属性已被宿主锁定。")
    locked = definition.get("savedLock", definition.get("lockedWhenSaved", False)) or prop == "options" or node["componentName"] == "NumberPicker" and prop in ("precision", "numberType") or node["componentName"] in ("DatePicker", "TimePicker") and prop == "format"
    if locked:
        saved = policy.get("saved", node.get("saved"))
        disabled = policy.get("disabledName", node.get("props", {}).get("disabledName"))
        if saved is True or disabled is True:
            _reject("SAVED_PROPERTY_LOCKED", "已保存字段的此属性不可修改。")
        if type(saved) is not bool or type(disabled) is not bool:
            _reject("MISSING_NODE_POLICY", "受保存锁保护的属性需要明确 saved/disabledName。")
    canvas = context.get("canvas", {})
    layout = canvas.get("layoutMode", context.get("currentSchema", {}).get("layoutMode"))
    if prop in ("titleHidden", "titleAlign", "titlePosition") and str(layout).lower() != "flow":
        _reject("LAYOUT_RESTRICTED", "该属性仅支持明确的 Flow 布局。")
    device = canvas.get("device", context.get("device"))
    if prop in ("size", "readOnlyDisplay") and device not in ("pc", "desktop", "PC"):
        _reject("DEVICE_RESTRICTED", "缺少 PC 设备信息或当前为移动端。")
    if "layouts" in definition and layout not in definition["layouts"] or "devices" in definition and device not in definition["devices"]:
        _reject("LAYOUT_RESTRICTED", "宿主布局或设备策略不允许该属性。")


def _snapshot(node: Mapping[str, Any], prop: str) -> dict[str, Any]:
    props = node.get("props", {})
    if prop in _ACCESS:
        access = props.get("access", {})
        if not isinstance(access, dict):
            _reject("INVALID_SNAPSHOT", "access 快照无效。")
        key = _ACCESS[prop]
        return {"exists": key in access, **({"value": deepcopy(access[key])} if key in access else {})}
    if prop == "defaultValue" and node["componentName"] not in ("SelectSingle", "SelectMulti"):
        if "defaultValueConfig" not in props and "defaultValue" not in props:
            return {"exists": False}
        mode = props.get("defaultValueConfig", "custom" if "defaultValue" in props else "undefined")
        value = {"mode": mode}
        if mode in ("custom", "formula") and "defaultValue" in props:
            value["value"] = deepcopy(props["defaultValue"])
        return {"exists": True, "value": value}
    if prop == "textLengthLimit":
        return {"exists": True, "value": {"enabled": props.get("showLimitHint", False), "maxLength": props.get("textMaxLength", 200)}} if "showLimitHint" in props or "textMaxLength" in props else {"exists": False}
    if prop == "formatValidation":
        return {"exists": True, "value": {"format": props.get("format", "none"), **({"message": props["formatMessage"]} if "formatMessage" in props else {})}} if "format" in props or "formatMessage" in props else {"exists": False}
    if prop == "numericRange":
        keys = ("minEnable", "min", "minMessage", "maxEnable", "max", "maxMessage")
        value = {bound: {"value": props[bound], **({"message": props[bound + "Message"]} if bound + "Message" in props else {})}
                 for bound in ("min", "max") if props.get(bound + "Enable") is True and bound in props}
        return {"exists": True, "value": value} if any(key in props for key in keys) else {"exists": False}
    if prop == "selectionLimit":
        value = {"count": props["maxTagCount"], **({"message": props["maxCountMessage"]} if "maxCountMessage" in props else {})} if props.get("maxCountEnable") is True and "maxTagCount" in props else None
        return {"exists": True, "value": value} if any(key in props for key in ("maxCountEnable", "maxTagCount", "maxCountMessage")) else {"exists": False}
    key = _STORAGE.get(prop, prop)
    return {"exists": key in props, **({"value": deepcopy(props[key])} if key in props else {})}


def _stored(node: dict[str, Any], prop: str, context: Mapping[str, Any]) -> dict[str, Any]:
    host = context.get("resolvedProperties", {}).get(node["id"], {}).get(prop)
    if isinstance(host, dict) and "stored" in host:
        state = host["stored"]
        if not isinstance(state, dict) or type(state.get("exists")) is not bool or set(state) - {"exists", "value"} or state["exists"] != ("value" in state) or not _json_safe(state):
            _reject("INVALID_RESOLVED_PROPERTY", "宿主 stored 属性快照无效。")
        return deepcopy(state)
    return _snapshot(node, prop)


def _resolved(node: dict[str, Any], prop: str, definition: dict[str, Any], context: Mapping[str, Any]) -> dict[str, Any]:
    stored = _stored(node, prop, context)
    host = context.get("resolvedProperties", {}).get(node["id"], {}).get(prop)
    if host is not None:
        if not isinstance(host, dict) or host.get("source") not in ("local", "inherited", "default") or "resolvedValue" not in host:
            _reject("INVALID_RESOLVED_PROPERTY", "宿主有效属性快照无效。")
        if host["source"] == "local" and not stored["exists"]:
            _reject("INVALID_RESOLVED_PROPERTY", "宿主来源与局部存储状态不一致。")
        return {"stored": stored, "source": host["source"], "resolvedValue": deepcopy(host["resolvedValue"])}
    if prop == "descriptionDisplay" and str(context.get("canvas", {}).get("layoutMode", context.get("currentSchema", {}).get("layoutMode", ""))).lower() == "grid":
        form_props = context.get("currentSchema", {}).get("props", {})
        if "extraType" in form_props:
            return {"stored": stored, "source": "inherited", "resolvedValue": deepcopy(form_props["extraType"])}
    if stored["exists"]:
        return {"stored": stored, "source": "local", "resolvedValue": deepcopy(stored["value"])}
    if prop in _ACCESS:
        value = _ACCESS_DEFAULTS[_ACCESS[prop]]
    elif "default" in definition:
        value = definition["default"]
    elif prop in ("titleAlign", "titlePosition"):
        key = _STORAGE[prop]
        form_props = context.get("currentSchema", {}).get("props", {})
        if key in form_props:
            return {"stored": stored, "source": "inherited", "resolvedValue": deepcopy(form_props[key])}
        value = "left"
    elif prop in _DEFAULTS:
        value = _DEFAULTS[prop]
    else:
        _reject("MISSING_RESOLVED_PROPERTY", "缺少实际有效值及其来源，不能推测。")
    return {"stored": stored, "source": "default", "resolvedValue": deepcopy(value)}


def _intrinsic_schema(component: str, prop: str) -> dict[str, Any] | None:
    if prop in _BOOLS:
        return {"type": "boolean"}
    if prop in _NUMBERS:
        minimum, maximum = _NUMBERS[prop]
        return {"type": "number", **({"minimum": minimum} if minimum is not None else {}), **({"maximum": maximum} if maximum is not None else {})}
    if prop in _ENUMS:
        return {"type": "string", "enum": _ENUMS[prop]}
    if prop == "format":
        return {"type": "string", "enum": _FORMATS[component]}
    if prop in {"label", "customTitle", "description", "placeholder", "requiredMessage", "uniqueMessage", "formatMessage", "innerAfter", "minMessage", "maxMessage", "maxCountMessage"}:
        return {"type": "string", **({"maxLength": 50, "minLength": 1 if prop == "label" else 0} if prop in ("label", "customTitle") else {"maxLength": 200} if prop == "description" else {})}
    return None


def _date(value: Any, fmt: str) -> None:
    formats = {"YYYY": "%Y", "YYYY-MM": "%Y-%m", "YYYY-MM-DD": "%Y-%m-%d", "YYYY-MM-DD HH": "%Y-%m-%d %H", "YYYY-MM-DD HH:mm": "%Y-%m-%d %H:%M", "YYYY-MM-DD HH:mm:ss": "%Y-%m-%d %H:%M:%S", "HH:mm": "%H:%M", "HH:mm:ss": "%H:%M:%S"}
    if fmt not in formats or not isinstance(value, str):
        _reject("INVALID_DATE", "缺少有效日期/时间格式。")
    try:
        parsed = datetime.strptime(value, formats[fmt])
        if parsed.strftime(formats[fmt]) != value:
            _reject("INVALID_DATE", "日期/时间格式不匹配。")
    except ValueError:
        _reject("INVALID_DATE", "日期/时间值无效。")


def _validate_value(node: dict[str, Any], prop: str, value: Any, definition: dict[str, Any]) -> None:
    component = node["componentName"]
    intrinsic = _intrinsic_schema(component, prop) if prop in _COMMON | _SPECIFIC[component] else None
    schema = definition.get("valueSchema", definition.get("schema"))
    if schema is None and "type" in definition:
        schema = {k: v for k, v in definition.items() if k in ("type", "enum", "minimum", "maximum", "minLength", "maxLength", "pattern", "items", "properties", "required", "additionalProperties")}
    if schema:
        _schema(value, schema)
    if prop == "defaultValue":
        if component in ("SelectSingle", "SelectMulti"):
            _schema(value, {"type": "string"} if component == "SelectSingle" else {"type": "array", "items": {"type": "string"}, "uniqueItems": True})
            options = node.get("props", {}).get("options", {}).get("dataSource")
            if not isinstance(options, list) or not all(isinstance(o, dict) and isinstance(o.get("value"), str) for o in options) or len({o["value"] for o in options}) != len(options):
                _reject("MISSING_OPTIONS", "复制或设置默认项需要真实且唯一的选项 value。")
            wanted = [value] if component == "SelectSingle" else value
            if any(not any(o["value"] == v and o.get("disabled") is False for o in options) for v in wanted):
                _reject("INVALID_DEFAULT_OPTION", "默认项必须存在且明确启用。")
        else:
            if not isinstance(value, dict) or set(value) - {"mode", "value"}:
                _reject("INVALID_DEFAULT", "默认值必须包含受控 mode/value。")
            mode = value.get("mode")
            modes = {"undefined", "custom"} | ({"systemDate"} if component == "DatePicker" else {"systemTime"} if component == "TimePicker" else set())
            if mode not in modes or (mode == "custom") != ("value" in value):
                _reject("UNSUPPORTED_DEFAULT_MODE", "默认值模式无效；公式执行未注册。")
            if mode == "custom":
                _schema(value["value"], {"type": "number" if component == "NumberPicker" else "string"})
                if component in ("DatePicker", "TimePicker"):
                    _date(value["value"], node.get("props", {}).get("format"))
    elif prop == "textLengthLimit":
        if isinstance(value, dict):
            _schema(value, {"type": "object", "properties": {"enabled": {"const": False}, "maxLength": _NUMBERS_SCHEMA}, "required": ["enabled"], "additionalProperties": False})
        else:
            _schema(value, _NUMBERS_SCHEMA)
    elif prop == "numericRange":
        bound_schema = {"type": "object", "properties": {"value": {"type": "number"}, "message": {"type": "string", "maxLength": 200}}, "required": ["value"], "additionalProperties": False}
        _schema(value, {"type": "object", "properties": {"min": bound_schema, "max": bound_schema}, "additionalProperties": False})
        if "min" in value and "max" in value and value["min"]["value"] > value["max"]["value"]:
            _reject("INVALID_RANGE", "最小值不能大于最大值。")
    elif prop == "selectionLimit":
        _schema(value, {"type": "object", "properties": {"count": {"type": "integer", "minimum": 1, "maximum": 1000}, "message": {"type": "string", "maxLength": 200}}, "required": ["count"], "additionalProperties": False})
    elif prop == "formatValidation":
        _schema(value, {"type": "object", "properties": {"format": {"type": "string", "enum": _FORMATS["Input"]}, "message": {"type": "string"}}, "required": ["format"], "additionalProperties": False})
    elif intrinsic:
        _schema(value, intrinsic)
    elif not schema or not definition.get("handlerId"):
        _reject("MISSING_COMPOUND_HANDLER", "未知或复合属性必须有结构化 schema 和专用宿主处理器。")
    if isinstance(value, (dict, list)) and prop not in ("defaultValue", "formatValidation", "textLengthLimit") and (not schema or not definition.get("handlerId")):
        _reject("MISSING_COMPOUND_HANDLER", "复合属性必须声明结构化 schema 和处理器。")
    if prop in ("relatedField", "options", "minTimeCondition", "maxTimeCondition", "disabledDays", "isUnique"):
        if not definition.get("handlerId") or not schema:
            _reject("MISSING_COMPOUND_HANDLER", "此属性依赖专用宿主校验与处理器。")
        if prop == "relatedField" and not definition.get("remoteMetadataAvailable"):
            _reject("MISSING_REMOTE_METADATA", "缺少关联字段远程元数据。")
        if prop == "isUnique" and value and not definition.get("serviceAvailable"):
            _reject("MISSING_UNIQUENESS_SERVICE", "未接入真实唯一性检查服务。")


def _compound_semantics(node: dict[str, Any], prop: str, value: Any, definition: dict[str, Any], original: list[dict[str, Any]], candidate: list[dict[str, Any]]) -> None:
    component = node["componentName"]
    props = node.get("props", {})
    if prop == "disabledDays" and value is not None:
        if not isinstance(value, dict) or set(value) != {"enabled", "days"} or type(value["enabled"]) is not bool or not isinstance(value["days"], list):
            _reject("INVALID_WEEKDAYS", "可选星期必须有 enabled 和 days。")
        if any(day not in [str(i) for i in range(7)] for day in value["days"]) or len(set(value["days"])) != len(value["days"]):
            _reject("INVALID_WEEKDAYS", "星期必须是唯一的 0–6 字符串。")
        if value["enabled"] and (not value["days"] or props.get("format") in ("YYYY", "YYYY-MM")):
            _reject("INVALID_WEEKDAYS", "年/月格式不支持可选星期；空数组不能表示禁止全部日期。")
    if prop in ("minTimeCondition", "maxTimeCondition") and value is not None:
        if not isinstance(value, dict) or value.get("enabled") is not True:
            _reject("INVALID_TIME_CONDITION", "时间范围必须启用或显式置 null。")
        source = value.get("source")
        common = {"enabled", "source"}
        if source == "fixed":
            if set(value) != common | {"fixedValue"}:
                _reject("INVALID_TIME_CONDITION", "固定时间范围不能残留其他 source 分支。")
            _date(value["fixedValue"], props.get("format"))
        elif source == "field":
            if set(value) != common | {"fieldName"}:
                _reject("INVALID_TIME_CONDITION", "字段时间范围不能残留其他分支。")
            matches = [n for n in candidate if n.get("props", {}).get("name") == value["fieldName"]]
            if len(matches) != 1 or matches[0]["id"] == node["id"] or matches[0]["componentName"] != component:
                _reject("INVALID_REFERENCE", "时间范围必须引用其他真实同类字段。")
        elif source == "dynamic":
            mode = value.get("dynamicMode")
            if mode == "current":
                allowed = common | {"dynamicMode", "dynamicAnchor"}
                anchors = {"today", "currentWeek", "currentMonth", "nextMonth", "currentQuarter", "currentYear"} if component == "DatePicker" else {"today"}
                if set(value) - allowed or value.get("dynamicAnchor", "today" if component == "TimePicker" else None) not in anchors:
                    _reject("INVALID_TIME_CONDITION", "动态当前时间分支参数无效。")
            elif component == "DatePicker" and mode in ("before", "after"):
                if set(value) != common | {"dynamicMode", "dynamicUnit", "offsetValue"} or value["dynamicUnit"] not in ("day", "week", "month", "quarter", "year"):
                    _reject("INVALID_TIME_CONDITION", "动态日期偏移分支无效。")
                _schema(value["offsetValue"], {"type": "number", "minimum": 0})
            else:
                _reject("INVALID_TIME_CONDITION", "时间仅支持 current；日期偏移需要完整参数。")
        else:
            _reject("INVALID_TIME_CONDITION", "时间范围 source 未注册。")
        low, high = props.get("minTimeCondition"), props.get("maxTimeCondition")
        if isinstance(low, dict) and isinstance(high, dict) and low.get("source") == high.get("source") == "fixed" and low.get("enabled") and high.get("enabled") and low.get("fixedValue", "") > high.get("fixedValue", ""):
            _reject("INVALID_RANGE", "最早时间不能晚于最晚时间。")
    if prop == "options":
        options = value.get("dataSource") if isinstance(value, dict) else None
        if not isinstance(options, list) or not all(isinstance(o, dict) and isinstance(o.get("primaryKey"), str) and isinstance(o.get("value"), str) and type(o.get("disabled")) is bool and type(o.get("activeKey")) is bool for o in options):
            _reject("INVALID_OPTIONS", "选项必须保留真实身份、业务 value 及状态。")
        if len({o["primaryKey"] for o in options}) != len(options) or len({o["value"] for o in options}) != len(options):
            _reject("INVALID_OPTIONS", "选项身份和业务 value 必须唯一。")
        active = [o for o in options if o["activeKey"]]
        if any(o["disabled"] for o in active) or component == "SelectSingle" and len(active) > 1:
            _reject("INVALID_DEFAULT_OPTION", "默认项必须启用，单选至多一个。")
        old = next(n for n in original if n["id"] == node["id"])["props"].get("options", {})
        old_options = old.get("dataSource", []) if isinstance(old, dict) else []
        for previous in old_options:
            match = next((o for o in options if o["primaryKey"] == previous.get("primaryKey")), None)
            if match is None:
                _reject("OPTION_REFERENCE_CHECK_REQUIRED", "删除选项需要专用引用检查，当前编译器不开放。")
            if match["value"] != previous.get("value"):
                _reject("OPTION_IDENTITY_CHANGED", "不得改变已有选项的业务 value。")
            for key in ("associateDirectory", "relatedParentField"):
                if key in previous and match.get(key) != previous[key]:
                    _reject("OPTION_RELATION_CHANGED", "选项目录和父子关系必须保留。")
        for key in ("associateDirectory", "relatedParentField"):
            if key in old and value.get(key) != old[key]:
                _reject("OPTION_RELATION_CHANGED", "选项配置关联关系必须保留。")
    if prop == "relatedField" and value is not None:
        if not definition.get("remoteMetadataAvailable"):
            _reject("MISSING_REMOTE_METADATA", "关联字段缺少远程目录。")
    _references(value, candidate, definition)


_NUMBERS_SCHEMA = {"type": "number", "minimum": 1}


def _after(node: dict[str, Any], prop: str, op: str, slots: Mapping[str, Any], definition: dict[str, Any]) -> dict[str, Any]:
    if op == "set":
        if "value" not in slots:
            _reject("VALUE_REQUIRED", "set 必须有 value。", True)
        value = deepcopy(slots["value"])
        if prop == "formatValidation" and isinstance(value, dict) and "message" not in value and "formatMessage" in node.get("props", {}):
            value["message"] = node["props"]["formatMessage"]
        return {"exists": True, "value": value}
    if "value" in slots:
        _reject("UNEXPECTED_VALUE", "clear/unset/reset 不携带 value。")
    if op == "unset":
        if prop in _ACCESS or prop in ("defaultValue", "textLengthLimit", "formatValidation", "label"):
            _reject("UNSET_UNSUPPORTED", "此语义属性不能用通用删除代替专用清空。")
        if prop not in ("titleAlign", "titlePosition") and not definition.get("allowUnset"):
            _reject("UNSET_UNSUPPORTED", "该属性不支持删除局部覆盖。")
        return {"exists": False}
    if op == "reset":
        reset = definition.get("reset")
        if prop in ("titleAlign", "titlePosition") or isinstance(reset, dict) and reset.get("source") == "inherited":
            return {"exists": False}
        if "default" in definition:
            value = deepcopy(definition["default"])
        elif prop in _DEFAULTS:
            value = _DEFAULTS[prop]
        elif prop in ("numericRange", "selectionLimit", "disabledDays", "minTimeCondition", "maxTimeCondition"):
            value = {} if prop == "numericRange" else None
        elif prop == "textLengthLimit":
            value = {"enabled": False, "maxLength": 200}
        elif prop == "formatValidation":
            return _after(node, prop, "clear", {}, definition)
        elif prop in ("description", "customTitle", "innerAfter"):
            value = ""
        elif prop == "placeholder":
            value = {"Input": "", "Input.TextArea": "", "NumberPicker": "请输入数字", "DatePicker": "年-月-日", "TimePicker": "请选择时间", "SelectSingle": "请选择", "SelectMulti": "请选择"}[node["componentName"]]
        elif prop in _ACCESS:
            value = _ACCESS_DEFAULTS[_ACCESS[prop]]
        elif prop == "allowClear":
            value = node["componentName"] != "Input"
        elif prop == "supportReverseSelect":
            value = True
        elif prop in _BOOLS:
            value = False
        elif prop == "format":
            value = {"Input": "none", "DatePicker": "YYYY-MM-DD", "TimePicker": "HH:mm:ss"}[node["componentName"]]
        elif prop == "defaultValue":
            return _after(node, prop, "clear", {}, definition)
        else:
            _reject("MISSING_RESET_DEFAULT", "宿主未声明重置值。")
        return {"exists": True, "value": value}
    if op == "clear":
        if prop == "label":
            _reject("TITLE_REQUIRED", "标题不能清空。")
        if prop == "defaultValue":
            if node["componentName"] == "SelectSingle":
                return {"exists": False}
            return {"exists": True, "value": [] if node["componentName"] == "SelectMulti" else {"mode": "undefined"}}
        if prop == "numericRange":
            return {"exists": True, "value": {}}
        if prop == "selectionLimit":
            return {"exists": True, "value": None}
        if prop == "textLengthLimit":
            props = node.get("props", {})
            return {"exists": True, "value": {"enabled": False, "maxLength": props.get("textMaxLength", 200)}}
        if prop == "formatValidation":
            props = node.get("props", {})
            return {"exists": True, "value": {"format": "none", **({"message": props["formatMessage"]} if "formatMessage" in props else {})}}
        if "clearValue" in definition:
            return {"exists": True, "value": deepcopy(definition["clearValue"])}
        if prop in ("disabledDays", "minTimeCondition", "maxTimeCondition"):
            return {"exists": True, "value": None}
        if prop == "format" and node["componentName"] == "Input":
            return {"exists": True, "value": "none"}
        if prop in _BOOLS:
            return {"exists": True, "value": False}
        intrinsic = _intrinsic_schema(node["componentName"], prop)
        if intrinsic and intrinsic.get("type") == "string" and "enum" not in intrinsic:
            return {"exists": True, "value": ""}
        _reject("CLEAR_UNSUPPORTED", "该属性没有已注册的清空语义。")
    _reject("UNSUPPORTED_OPERATION", "不支持此操作。")


def _simulate(node: dict[str, Any], prop: str, after: dict[str, Any]) -> list[str]:
    """Mirror documented intrinsic helpers on a private candidate, never the Store."""
    props = node.setdefault("props", {})
    value = after.get("value")
    if prop in _ACCESS:
        access = props.setdefault("access", {})
        for key, default in _ACCESS_DEFAULTS.items():
            access.setdefault(key, default)
        key = _ACCESS[prop]
        access[key] = value
        if prop == "display" and not value:
            access.update(editable=False, required=False, forbidManualInput=False)
        elif prop == "edit" and not value:
            access.update(required=False, forbidManualInput=False)
        elif prop in ("required", "disableManualEdit") and value:
            access.update(visible=True, editable=True)
        props["required"] = access["required"]
        return ["通过 access helper 同步权限及兼容 required；开启必填/禁止手工编辑会开启显示和编辑；关闭显示/编辑会关闭依赖权限"]
    if prop == "defaultValue":
        if node["componentName"] in ("SelectSingle", "SelectMulti"):
            if not isinstance(props.get("options"), dict) or not isinstance(props["options"].get("dataSource"), list):
                _reject("MISSING_OPTIONS", "设置或清空默认项需要真实选项快照。")
            wanted = value if isinstance(value, list) else [value] if after["exists"] else []
            for option in props.get("options", {}).get("dataSource", []):
                option["activeKey"] = option.get("value") in wanted
            if after["exists"]:
                props["defaultValue"] = deepcopy(value)
            else:
                props.pop("defaultValue", None)
            return ["同步选项 activeKey 与默认值，保留选项身份和业务 value"]
        props["defaultValueConfig"] = value["mode"]
        if value["mode"] == "custom":
            props["defaultValue"] = deepcopy(value["value"])
        else:
            props.pop("defaultValue", None)
        return ["成对更新默认值模式和内容；非静态模式删除静态值"]
    if prop == "textLengthLimit":
        enabled = not isinstance(value, dict)
        props["showLimitHint"] = enabled
        if enabled:
            props["textMaxLength"] = value
        elif "maxLength" in value:
            props["textMaxLength"] = value["maxLength"]
        return ["成组更新计数器与输入长度限制；关闭时保留历史阈值"]
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
    if prop == "selectionLimit":
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
    if prop == "formatValidation":
        props["format"] = value["format"]
        if "message" in value:
            props["formatMessage"] = value["message"]
        return ["同步内置格式校验及提示，不创建任意 rules 数组"]
    key = _STORAGE.get(prop, prop)
    previous = props.get(key)
    if after["exists"]:
        props[key] = deepcopy(value)
    else:
        props.pop(key, None)
    if prop == "format" and node["componentName"] == "DatePicker" and previous != value:
        props["placeholder"] = value.replace("YYYY", "年").replace("MM", "月").replace("DD", "日").replace("HH", "时").replace("mm", "分").replace("ss", "秒")
        if value in ("YYYY", "YYYY-MM"):
            props["disabledDays"] = None
        return ["仅真实日期格式变更触发占位提示更新；年/月格式清空可选星期"]
    if prop in ("titleAlign", "titlePosition") and not after["exists"]:
        return ["删除局部覆盖，有效值由表单布局继承决定"]
    if prop == "options" and isinstance(value, dict):
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
    if prop == "relatedField":
        return ["请求宿主专用处理器同步节点绑定及表单 relatedFields，并复核远程字段元数据"]
    if prop in ("minTimeCondition", "maxTimeCondition"):
        effects = ["按 source 替换范围分支并验证同类字段引用及上下界"]
        if isinstance(value, dict) and value.get("dynamicMode") in ("before", "after"):
            effects.append("日期 day/week/month/quarter/year 使用 1/7/30/90/365 天近似偏移")
        return effects
    if prop == "disabledDays":
        return ["days 表示允许选择的星期；null 关闭限制，不用空数组表示全部禁用"]
    if prop == "isUnique" and value:
        return ["请求已注册的唯一性检查服务；真实执行结果以宿主回执为准"]
    return []


def _operation_allowed(definition: dict[str, Any], operation: str) -> None:
    operations = definition.get("operations")
    if not isinstance(operations, list) or operation not in operations:
        _reject("OPERATION_UNSUPPORTED", f"宿主没有注册操作 {operation}。")


def _extension(kind: str, slots: dict[str, Any], node: dict[str, Any], context: dict[str, Any], nodes: list[dict[str, Any]]) -> tuple[str, dict[str, Any], dict[str, Any], dict[str, Any]]:
    type_key, id_key = ("rule_type", "rule_id") if kind == "rule" else ("linkage_type", "linkage_id")
    registered = context["capabilities"].get("ruleCatalog" if kind == "rule" else "linkageCatalog", {}).get(slots.get(type_key))
    if not isinstance(registered, dict) or not registered.get("handlerId") or not registered.get("valueSchema"):
        _reject("EXTENSION_UNSUPPORTED", "宿主未注册此规则/联动的有界验证器和处理器。")
    if node["componentName"] not in registered.get("components", []):
        _reject("EXTENSION_COMPONENT_UNSUPPORTED", "规则/联动不兼容当前组件。")
    op = slots.get("operation")
    _operation_allowed(registered, op)
    if op not in ("add", "replace", "remove") or not isinstance(slots.get(id_key), str) or not slots[id_key]:
        _reject("INVALID_EXTENSION", "规则/联动操作或标识无效。")
    _policy(node, kind, registered, context)
    action = "form.apply_property_rule" if kind == "rule" else "form.apply_property_linkage"
    _version(context, action)
    collection = context.get("rules" if kind == "rule" else "linkages", {}).get(node["id"])
    if not isinstance(collection, list) or not all(isinstance(v, dict) and isinstance(v.get("id"), str) for v in collection):
        _reject("MISSING_EXTENSION_SNAPSHOT", "缺少规则/联动历史快照。")
    matches = [v for v in collection if v["id"] == slots[id_key]]
    if len(matches) > 1 or (op == "add" and matches) or (op != "add" and not matches):
        _reject("EXTENSION_ID_CONFLICT", "规则/联动标识不存在或重复。", True)
    if matches and matches[0].get("type") != slots[type_key]:
        _reject("EXTENSION_TYPE_CONFLICT", "已存在的规则/联动类型不匹配。")
    before = {"exists": bool(matches), **({"value": deepcopy(matches[0]["value"])} if matches else {})}
    after = {"exists": op != "remove"}
    if op == "remove":
        if "value" in slots:
            _reject("UNEXPECTED_VALUE", "删除规则/联动不携带 value。")
    else:
        if "value" not in slots:
            _reject("VALUE_REQUIRED", "规则/联动参数缺失。", True)
        _schema(slots["value"], registered["valueSchema"])
        if kind == "linkage":
            _ast(slots["value"], nodes, registered)
        else:
            _references(slots["value"], nodes, registered)
        after["value"] = deepcopy(slots["value"])
    payload = {"nodeId": node["id"], "componentName": node["componentName"], "operation": op, "type": slots[type_key], "ruleId" if kind == "rule" else "linkageId": slots[id_key], **({"value": deepcopy(after["value"])} if after["exists"] else {})}
    return action, payload, before, after


def _references(value: Any, nodes: list[dict[str, Any]], definition: dict[str, Any]) -> None:
    ids = {n["id"] for n in nodes}
    if isinstance(value, dict):
        for key, child in value.items():
            if key in ("nodeId", "fieldId", "targetNodeId"):
                if not isinstance(child, str) or child not in ids:
                    _reject("INVALID_REFERENCE", "规则/联动引用必须指向真实节点。")
                actual = next(n for n in nodes if n["id"] == child)
                if "referenceComponents" in definition and actual["componentName"] not in definition["referenceComponents"]:
                    _reject("INVALID_REFERENCE", "规则/联动字段引用组件不兼容。")
            if key in ("expression", "javascript", "script", "eval", "formulaContent"):
                _reject("EXPRESSION_FORBIDDEN", "禁止执行表达式或 JavaScript。")
            _references(child, nodes, definition)
    elif isinstance(value, list):
        for child in value:
            _references(child, nodes, definition)


def _ast(value: Any, nodes: list[dict[str, Any]], definition: dict[str, Any], depth: int = 0) -> None:
    if depth > 8 or not isinstance(value, dict):
        _reject("INVALID_AST", "联动只接受有界条件 AST。")
    op = value.get("op")
    if op not in definition.get("astOperators", []) or op not in ("and", "or", "not", "eq", "ne", "gt", "gte", "lt", "lte", "in", "isEmpty"):
        _reject("UNSUPPORTED_AST_OPERATOR", "宿主未注册此 AST 操作。")
    if op in ("and", "or", "not"):
        args = value.get("args")
        if set(value) != {"op", "args"} or not isinstance(args, list) or not 1 <= len(args) <= 20 or op == "not" and len(args) != 1:
            _reject("INVALID_AST", "组合条件参数无效。")
        for child in args:
            _ast(child, nodes, definition, depth + 1)
    else:
        if set(value) != ({"op", "nodeId"} if op == "isEmpty" else {"op", "nodeId", "value"}):
            _reject("INVALID_AST", "比较条件参数无效。")
        _references(value, nodes, definition)
        if "value" in value and isinstance(value["value"], dict):
            _reject("INVALID_AST", "比较值必须为字面量。")
        if op in ("gt", "gte", "lt", "lte") and type(value.get("value")) not in (int, float):
            _reject("INVALID_AST", "数值比较必须提供有限数值。")


def compile_property_proposal(items: Any, context: Any, base: Any) -> dict[str, Any]:
    """Compile property_changes/property_query/property_undo IR into a proposal.

    Non-ready mutation results have no result. Successful queries use status
    'ready', no executable result, contract form_property_query.v1, and a read-only presentation.
    All data returned is detached from the caller's snapshots.
    """
    proposal = deepcopy(dict(base)) if isinstance(base, Mapping) else {}
    proposal.pop("result", None)
    proposal.pop("presentation", None)
    proposal.update(contractVersion="form_property_proposal.v1", diagnostics=[])
    try:
        if not isinstance(context, dict) or not isinstance(items, list) or not _json_safe(items) or not _json_safe(context):
            _reject("INVALID_INPUT", "属性请求或宿主上下文不是有限 JSON 数据。")
        context = deepcopy(context)
        begins = [i for i in items if isinstance(i, dict) and i.get("capability") == "proposal.begin"]
        if len(begins) != 1 or not isinstance(begins[0].get("slots"), dict):
            _reject("INVALID_IR", "必须有一个 proposal.begin。")
        begin = begins[0]["slots"]
        kind = begin.get("result_kind")
        if kind not in PROPERTY_RESULT_KINDS:
            _reject("UNSUPPORTED_RESULT_KIND", "不支持该属性结果类型。")
        work = [i for i in items if i is not begins[0]]
        if not work:
            _reject("EMPTY_PROPERTY_REQUEST", "请指定需要查询或修改的属性。", True)
        proposal["summary"] = begin.get("summary", proposal.get("summary", "属性提案"))
        proposal.setdefault("proposalId", _id("proposal-property-", [context.get("target"), items]))
        target = context.get("target", {})
        if not isinstance(target, dict) or not target.get("schemaId") or target.get("revision", target.get("baseRevision")) is None:
            _reject("MISSING_REVISION", "缺少表单及读取时 revision。")
        revision = target.get("revision", target.get("baseRevision"))
        if proposal.get("target") and (proposal["target"].get("schemaId") != target["schemaId"] or proposal["target"].get("baseRevision") != revision):
            _reject("REVISION_CONFLICT", "提案目标与当前快照版本不一致。")
        proposal["target"] = {"schemaId": target["schemaId"], "baseRevision": revision}
        caps = context.get("capabilities", {})
        if not isinstance(caps, dict) or not isinstance(caps.get("catalogVersion"), str) or not caps["catalogVersion"]:
            _reject("MISSING_CATALOG_VERSION", "缺少属性目录版本。")
        ir_definitions = {d["capability"]: d["slots_schema"] for d in property_capabilities()}
        for item in work:
            if not isinstance(item, dict) or item.get("capability") not in ir_definitions or not isinstance(item.get("slots"), dict):
                _reject("INVALID_IR", "请求包含未知能力或无效 slots。")
            ir_schema = ir_definitions[item["capability"]]
            slots = item["slots"]
            if set(slots) - set(ir_schema["properties"]):
                _reject("INVALID_IR", "请求包含未定义的 IR 参数。")
            if set(ir_schema["required"]) - set(slots):
                _reject("MISSING_IR_SLOT", "请求缺少必需参数。", True)
            for slot, value in slots.items():
                if ir_schema["properties"][slot]:
                    _schema(value, ir_schema["properties"][slot])
        proposal["catalogVersion"] = caps["catalogVersion"]
        if kind == "property_undo":
            if len(work) != 1 or work[0].get("capability") != "form.property.undo":
                _reject("INVALID_UNDO", "撤销必须独立提交。")
            slots = work[0].get("slots", {})
            history = context.get("history", {})
            current = history.get("current", history)
            if not isinstance(current, dict) or current.get("canUndo") is not True or not slots.get("transaction_id") or slots["transaction_id"] != current.get("transactionId") or current.get("revision") != revision:
                _reject("UNDO_UNAVAILABLE", "当前宿主历史不允许撤销此事务。")
            _version(context, "form.undo_property_transaction")
            action = {"actionId": _id("action-", [proposal["proposalId"], "undo", slots]), "action": "form.undo_property_transaction", "payload": {"transactionId": slots["transaction_id"], "revision": revision}}
            proposal.update(status="ready", presentation={"kind": "component_property_undo", "transactionId": slots["transaction_id"], "canUndo": True}, result={"kind": "form_actions", "mode": "append", "schemaVersion": PROPERTY_ACTION_VERSION, "actions": [action]})
            return proposal
        schema = context.get("currentSchema")
        if not isinstance(schema, dict):
            _reject("MISSING_SNAPSHOT", "缺少当前表单快照。")
        nodes = _nodes(schema)
        if context.get("executionResult", {}).get("status") == "conflict":
            _reject("REVISION_CONFLICT", "请刷新发生冲突的宿主快照。")
        if kind == "property_query":
            rows = []
            for item in work:
                if item.get("capability") != "form.property.query" or not isinstance(item.get("slots"), dict):
                    _reject("INVALID_QUERY", "查询不能混入修改。")
                slots = item["slots"]
                node = _target(slots, nodes, context)
                prop = _canonical(slots.get("property"))
                definition = _definition(node, prop, caps)
                _read_policy(node, prop, context)
                if definition.get("readable") is False or definition.get("readable") is not True and "query" not in definition.get("operations", []):
                    _reject("QUERY_UNSUPPORTED", "宿主不允许读取此属性。")
                rows.append({"nodeId": node["id"], "componentName": node["componentName"], "property": prop, **_resolved(node, prop, definition, context), "revision": revision})
            proposal.update(contractVersion="form_property_query.v1", status="ready", presentation={"kind": "component_property_query", "readOnly": True, "items": rows})
            return proposal
        candidate = deepcopy(nodes)
        rows, actions, touched, conditions, validations = [], [], set(), [], []
        selected_values = {}
        for item in work:
            if not isinstance(item, dict) or not isinstance(item.get("slots"), dict):
                _reject("INVALID_IR", "属性项目缺少 slots。")
            slots = item["slots"]
            if "selected" in slots and type(slots["selected"]) is not bool:
                _reject("INVALID_SELECTION", "selected 必须为 boolean。")
            node = _target(slots, nodes, context)
            next_node = next(n for n in candidate if n["id"] == node["id"])
            capability = item.get("capability")
            source = None
            if capability in ("form.property.rule", "form.property.linkage"):
                extension_kind = capability.rsplit(".", 1)[1]
                action_name, payload, before, after = _extension(extension_kind, slots, node, context, nodes)
                prop = extension_kind + ":" + slots["rule_id" if extension_kind == "rule" else "linkage_id"]
                effects = ["宿主注册处理器执行规则/联动；不执行模型生成的表达式"]
            elif capability == "form.property.change":
                prop = _canonical(slots.get("property"))
                definition = _definition(node, prop, caps)
                op = slots.get("operation")
                _operation_allowed(definition, op)
                _policy(node, prop, definition, context)
                _version(context, "form.apply_property_change")
                action_name = "form.apply_property_change"
                before = _stored(node, prop, context)
                payload = {"nodeId": node["id"], "componentName": node["componentName"], "property": prop, "operation": op}
                if op == "copy":
                    if "value" in slots or not isinstance(slots.get("source_node_id"), str):
                        _reject("INVALID_COPY", "复制必须指定真实来源，不携带 value。", True)
                    source_node = _target({"node_id": slots["source_node_id"]}, nodes, context)
                    source_prop = _canonical(slots.get("source_property", prop))
                    source_def = _definition(source_node, source_prop, caps)
                    _read_policy(source_node, source_prop, context)
                    if source_def.get("readable") is False:
                        _reject("COPY_SOURCE_UNREADABLE", "复制来源不可读。")
                    resolved = _resolved(source_node, source_prop, source_def, context)
                    if source_prop != prop and definition.get("copyGroup") != source_def.get("copyGroup") or source_prop != prop and not definition.get("copyGroup"):
                        _reject("COPY_INCOMPATIBLE", "复制属性语义不兼容。")
                    copied = deepcopy(resolved["resolvedValue"])
                    if prop == "textLengthLimit" and isinstance(copied, dict) and copied.get("enabled") is True:
                        copied = copied.get("maxLength")
                    after = {"exists": True, "value": copied}
                    source = {"nodeId": source_node["id"], "property": source_prop, **resolved}
                    payload.update(sourceNodeId=source_node["id"], sourceProperty=source_prop, value=deepcopy(after["value"]), sourceSnapshot=deepcopy(resolved))
                else:
                    after = _after(node, prop, op, slots, definition)
                    if op == "set":
                        payload["value"] = deepcopy(after["value"])
                derived_reset = op in ("clear", "reset") and prop in {"textLengthLimit", "selectionLimit", "numericRange", "defaultValue", "minTimeCondition", "maxTimeCondition", "disabledDays"}
                if after["exists"] and not derived_reset:
                    validations.append((node["id"], prop, deepcopy(after["value"]), definition))
                effects = _simulate(next_node, prop, after)
                if prop == "textLengthLimit":
                    after = _snapshot(next_node, prop)
                conditions.append((node["id"], prop, definition, len(rows)))
            else:
                _reject("UNSUPPORTED_CAPABILITY", "属性提案包含不受支持的 IR 能力。")
            identity = (node["id"], prop)
            if identity in touched:
                _reject("PROPERTY_CONFLICT", "同一节点同一语义属性不能重复或互斥设置。")
            touched.add(identity)
            seed = [proposal["proposalId"], payload]
            action_id, change_id = _id("action-", seed), _id("change-", seed)
            rows.append({"changeId": change_id, "nodeId": node["id"], "componentName": node["componentName"], "property": prop, "text": f"{node.get('props', {}).get('label', node['id'])} · {prop} · {slots.get('operation')}", "selectedByDefault": slots.get("selected", True), "before": before, "after": after, "actionIds": [action_id], "dependsOn": [], "effects": effects, **({"source": source} if source else {})})
            actions.append({"actionId": action_id, "action": action_name, "payload": payload})
            selected_values[identity] = (after, slots.get("selected", True), change_id)
        for node_id, prop, value, definition in validations:
            node = next(n for n in candidate if n["id"] == node_id)
            _validate_value(node, prop, value, definition)
            _compound_semantics(node, prop, value, definition, nodes, candidate)
        for node_id, prop, definition, index in conditions:
            node = next(n for n in candidate if n["id"] == node_id)
            prerequisite = _CONDITIONS.get(prop)
            requirements = dict(definition.get("conditions", {}))
            if prerequisite:
                requirements.setdefault(prerequisite, True)
            for required_prop, expected in requirements.items():
                normalized = _canonical(required_prop)
                actual = _snapshot(node, normalized)
                if not actual["exists"] or actual.get("value") != expected:
                    _reject("PROPERTY_CONDITION_UNMET", f"{prop} 需要 {normalized}={expected}。", True)
                dependency = selected_values.get((node_id, normalized))
                if dependency:
                    rows[index]["dependsOn"].append(dependency[2])
                    if rows[index]["selectedByDefault"] and not dependency[1]:
                        _reject("SELECTION_DEPENDENCY", "所选属性依赖未勾选的启用项。", True)
            props = node.get("props", {})
            if prop == "formatMessage" and props.get("format", "none") == "none":
                _reject("PROPERTY_CONDITION_UNMET", "格式提示需要启用格式校验。", True)
            if node["componentName"] == "NumberPicker":
                for bound in ("min", "max"):
                    if props.get(bound + "Enable"):
                        _schema(props.get(bound), {"type": "number"})
            if props.get("minEnable") and props.get("maxEnable") and (type(props.get("min")) not in (int, float) or type(props.get("max")) not in (int, float) or props["min"] > props["max"]):
                _reject("INVALID_RANGE", "最小值与最大值配置矛盾。")
        for row in rows:
            node = next(n for n in candidate if n["id"] == row["nodeId"])
            dependent = []
            if row["property"] in ("defaultValue", "disabledDays", "minTimeCondition", "maxTimeCondition") and node["componentName"] in ("DatePicker", "TimePicker"):
                dependent.append("format")
            if row["property"] == "defaultValue" and node["componentName"] in ("SelectSingle", "SelectMulti"):
                dependent.append("options")
            if row["property"] == "formatMessage":
                dependent.append("format")
            for prerequisite in dependent:
                dependency = selected_values.get((row["nodeId"], prerequisite))
                if dependency:
                    if dependency[2] not in row["dependsOn"]:
                        row["dependsOn"].append(dependency[2])
                    if row["selectedByDefault"] and not dependency[1]:
                        _reject("SELECTION_DEPENDENCY", "所选属性依赖未勾选的格式或选项修改。", True)
        for node in candidate:
            props = node.get("props", {})
            changed = {prop for node_id, prop in touched if node_id == node["id"]}
            component = node["componentName"]
            if component in ("Input", "Input.TextArea") and changed & {"textLengthLimit", "defaultValue"}:
                default = props.get("defaultValue")
                if props.get("defaultValueConfig") == "custom" and isinstance(default, str) and props.get("showLimitHint") is True:
                    maximum = props.get("textMaxLength", 200)
                    if type(maximum) in (int, float) and len(default) > maximum:
                        _reject("INVALID_DEFAULT_RANGE", "默认文本超过输入长度限制。")
            if component == "NumberPicker" and changed & {"numericRange", "defaultValue", "min", "max", "minEnable", "maxEnable"}:
                default = props.get("defaultValue")
                if props.get("defaultValueConfig") == "custom" and type(default) in (int, float):
                    if any(props.get(bound + "Enable") is True and type(props.get(bound)) in (int, float) and (default < props[bound] if bound == "min" else default > props[bound]) for bound in ("min", "max")):
                        _reject("INVALID_DEFAULT_RANGE", "默认数字超出配置范围。")
            if component in ("DatePicker", "TimePicker") and changed & {"defaultValue", "format", "minTimeCondition", "maxTimeCondition"}:
                default = props.get("defaultValue")
                if props.get("defaultValueConfig") == "custom" and isinstance(default, str):
                    _date(default, props.get("format"))
                    for bound in ("minTimeCondition", "maxTimeCondition"):
                        condition = props.get(bound)
                        if isinstance(condition, dict) and condition.get("enabled") is True and condition.get("source") == "fixed":
                            fixed = condition.get("fixedValue")
                            if isinstance(fixed, str) and (default < fixed if bound == "minTimeCondition" else default > fixed):
                                _reject("INVALID_DEFAULT_RANGE", "默认日期或时间超出固定范围。")
            if component == "SelectMulti" and changed & {"selectionLimit", "defaultValue"} and props.get("maxCountEnable") is True:
                default = props.get("defaultValue")
                limit = props.get("maxTagCount")
                if isinstance(default, list) and type(limit) in (int, float) and len(default) > limit:
                    _reject("INVALID_DEFAULT_RANGE", "默认选项超过最多选择数量。")
        # Helper interactions must not silently invalidate another displayed intent.
        for row in rows:
            if ":" in row["property"]:
                continue
            node = next(n for n in candidate if n["id"] == row["nodeId"])
            actual = _snapshot(node, row["property"])
            if row["property"] == "textLengthLimit":
                expected = row["after"]["value"]
                valid = actual == row["after"] if isinstance(expected, dict) else actual.get("value", {}).get("enabled") is True and actual["value"].get("maxLength") == expected
            else:
                valid = actual == row["after"]
            if not valid:
                _reject("SEMANTIC_CONFLICT", "权限或复合处理器的派生影响与另一项请求冲突。")
        # A missing local override differs from an explicitly stored default.
        if all(row["before"] == row["after"] for row in rows) and candidate == nodes:
            proposal["status"] = "no_change"
            return proposal
        proposal.update(status="ready", presentation={"kind": "component_property_checklist", "title": begin.get("title", "组件属性修改建议"), "items": rows}, result={"kind": "form_actions", "mode": "append", "schemaVersion": PROPERTY_ACTION_VERSION, "actions": actions})
        return proposal
    except _Rejected as error:
        proposal.update(status="needs_clarification" if error.clarify else "unsupported", diagnostics=[{"code": error.code, "message": error.message}])
        if error.clarify:
            proposal.update(question=error.message, choices=[])
        proposal.pop("result", None)
        proposal.pop("presentation", None)
        return proposal
    except (TypeError, ValueError, KeyError, AttributeError, OverflowError, RecursionError, re.error):
        proposal.update(status="unsupported", diagnostics=[{"code": "INVALID_METADATA", "message": "宿主目录、策略或属性数据格式无效；请刷新上下文。"}])
        proposal.pop("result", None)
        proposal.pop("presentation", None)
        return proposal
