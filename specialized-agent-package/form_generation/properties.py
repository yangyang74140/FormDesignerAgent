"""Deterministic property IR compiler; host execution is deliberately external.

Host metadata: capabilities.catalogVersion and components[name].properties map
semantic names to definitions (operations, valueSchema, handlerId, default,
clearValue, reset={"source": "inherited"}). capabilities.nodePolicies[id] declares
canRead/canModify/allowedProperties; legacy top-level nodePolicies with explicit
writable/saved/disabledName/system is also accepted. Saved-lock properties always
need saved/disabledName information. Structured values require a handlerId and a
bounded JSON schema. supportedActionVersions maps action names to exact versions.
resolvedProperties[id][property] supplies validated stored state for preconditions
and source/resolvedValue for query and copy.

Registered ruleCatalog/linkageCatalog entries contain handlerId, valueSchema,
operations and compatible components. Linkages additionally declare astOperators.
The rules/linkages context maps node IDs to current [{id, type, value}] snapshots.
Extension actions use form.apply_property_rule/form.apply_property_linkage, with
the same exact action contract version. Queries have a read-only presentation,
status ready, contract form_property_query.v1 and no executable actions.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import re
from typing import Any, Mapping

from .host import CapabilityUnavailable, require_component
from .drafts import set_action_draft
from .components import PROPERTY_COMPONENTS, get_component_rules, property_names
from .components.common import ACCESS as _ACCESS, ACCESS_DEFAULTS as _ACCESS_DEFAULTS, ALIASES as _ALIASES, STORAGE as _STORAGE
from .components.validation import Rejected as _Rejected, reject as _reject, validate_schema as _schema

PROPERTY_RESULT_KINDS = frozenset({"property_changes", "property_query", "property_undo"})
PROPERTY_ACTION_VERSION = "form_property_actions.v1"
COMPONENTS = PROPERTY_COMPONENTS
_FORBIDDEN = frozenset({"name", "identifiers", "id", "__proto__", "prototype", "constructor"})


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
    if prop not in property_names(component):
        prefix = "暂时还不支持禁用" if prop == "disabled" else "暂时还不支持所请求的属性"
        _reject("UNSUPPORTED_PROPERTY", f"{prefix}：组件 {component} 没有注册的内置语义 {prop}。")
    try:
        require_component(component, caps)
    except CapabilityUnavailable as error:
        _reject(error.code, str(error))
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
    rule = get_component_rules(node["componentName"]).properties.get(prop) if node["componentName"] in COMPONENTS else None
    locked = definition.get("savedLock", definition.get("lockedWhenSaved", False)) or rule is not None and rule.saved_lock
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
    return get_component_rules(node["componentName"]).snapshot(node, prop)


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
    else:
        exists, value = get_component_rules(node["componentName"]).default(prop)
        if not exists:
            _reject("MISSING_RESOLVED_PROPERTY", "缺少实际有效值及其来源，不能推测。")
    return {"stored": stored, "source": "default", "resolvedValue": deepcopy(value)}


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

    Non-ready mutations and queries have no actions. Successful queries use
    status 'ready', contract form_property_query.v1, and a read-only presentation.
    All data returned is detached from the caller's snapshots.
    """
    proposal = deepcopy(dict(base)) if isinstance(base, Mapping) else {}
    for key in ("result", "presentation", "actions", "mode", "actionVersion", "validation"):
        proposal.pop(key, None)
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
        proposal["target"] = {key: deepcopy(target[key]) for key in ("schemaId", "formId", "appId", "layoutId") if key in target}
        proposal["target"]["baseRevision"] = revision
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
            set_action_draft(proposal, [action], mode="append", action_version=PROPERTY_ACTION_VERSION,
                             kind="component_property_undo", title="撤销属性修改")
            proposal["presentation"].update(transactionId=slots["transaction_id"], canUndo=True)
            proposal["status"] = "ready"
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
                    copied = get_component_rules(node["componentName"]).normalize_copy(prop, copied)
                    after = {"exists": True, "value": copied}
                    payload.update(sourceNodeId=source_node["id"], sourceProperty=source_prop, value=deepcopy(after["value"]), sourceSnapshot=deepcopy(resolved))
                else:
                    after = get_component_rules(node["componentName"]).after(node, prop, op, slots, definition)
                    if op == "set":
                        payload["value"] = deepcopy(after["value"])
                if after["exists"] and op not in get_component_rules(node["componentName"]).properties[prop].unvalidated_operations:
                    validations.append((node["id"], prop, deepcopy(after["value"]), definition))
                effects = get_component_rules(node["componentName"]).simulate(next_node, prop, after)
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
            action_id = _id("action-", seed)
            rows.append({"nodeId": node["id"], "componentName": node["componentName"], "property": prop,
                         "selectedByDefault": slots.get("selected", True), "before": before, "after": after,
                         "dependsOn": [], "effects": effects})
            actions.append({
                "actionId": action_id, "action": action_name, "payload": payload,
                "preconditions": {"before": deepcopy(before)},
                "dependsOn": rows[-1]["dependsOn"],
                "display": {"selectedByDefault": slots.get("selected", True), "effects": effects},
            })
            selected_values[identity] = (after, slots.get("selected", True), action_id)
        for node_id, prop, value, definition in validations:
            node = next(n for n in candidate if n["id"] == node_id)
            rules = get_component_rules(node["componentName"])
            rules.validate(node, prop, value, definition)
            rules.validate_compound(node, prop, value, definition, nodes, candidate)
            _references(value, candidate, definition)
        for node_id, prop, definition, index in conditions:
            node = next(n for n in candidate if n["id"] == node_id)
            prerequisite = get_component_rules(node["componentName"]).properties[prop].prerequisite
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
            get_component_rules(node["componentName"]).validate_candidate(node, prop)
        for row in rows:
            node = next(n for n in candidate if n["id"] == row["nodeId"])
            dependent = get_component_rules(node["componentName"]).dependencies(row["property"]) if node["componentName"] in COMPONENTS else ()
            for prerequisite in dependent:
                dependency = selected_values.get((row["nodeId"], prerequisite))
                if dependency:
                    if dependency[2] not in row["dependsOn"]:
                        row["dependsOn"].append(dependency[2])
                    if row["selectedByDefault"] and not dependency[1]:
                        _reject("SELECTION_DEPENDENCY", "所选属性依赖未勾选的格式或选项修改。", True)
        # Helper interactions must not silently invalidate another displayed intent.
        for row in rows:
            if ":" in row["property"]:
                continue
            node = next(n for n in candidate if n["id"] == row["nodeId"])
            actual = _snapshot(node, row["property"])
            valid = get_component_rules(node["componentName"]).matches(row["property"], actual, row["after"])
            if not valid:
                _reject("SEMANTIC_CONFLICT", "权限或复合处理器的派生影响与另一项请求冲突。")
        # A missing local override differs from an explicitly stored default.
        if all(row["before"] == row["after"] for row in rows) and candidate == nodes:
            proposal["status"] = "no_change"
            return proposal
        set_action_draft(proposal, actions, mode="append", action_version=PROPERTY_ACTION_VERSION,
                         kind="shared.component-property-checklist", title=begin.get("title", "组件属性修改建议"))
        proposal["status"] = "ready"
        return proposal
    except _Rejected as error:
        proposal.update(status="needs_clarification" if error.clarify else "unsupported", summary=error.message, diagnostics=[{"code": error.code, "message": error.message}])
        if error.clarify:
            proposal.update(question=error.message, choices=[])
        proposal.pop("result", None)
        proposal.pop("presentation", None)
        return proposal
    except (TypeError, ValueError, KeyError, AttributeError, OverflowError, RecursionError, re.error):
        message = "宿主目录、策略或属性数据格式无效；请刷新上下文。"
        proposal.update(status="unsupported", summary=message, diagnostics=[{"code": "INVALID_METADATA", "message": message}])
        proposal.pop("result", None)
        proposal.pop("presentation", None)
        return proposal
