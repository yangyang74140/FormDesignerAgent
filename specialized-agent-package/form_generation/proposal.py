"""Capability-aware compiler for the form-agent.v1 proposal protocol."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any, Mapping

from .action_rules import ACTION_KINDS, CLIENT_REF_PATTERN, action_capabilities, validate_action
from .components import FLOW_COMPONENTS, OPTION_COMPONENTS
from .host import (
    CapabilityUnavailable, component_catalog, component_names, node_index, reject_properties,
    require_component, target_node_id, validate_writable_props, writable_props,
)
from .properties import compile_property_request, property_capabilities
from .drafts import set_action_draft
from .contracts import CHANGE_CONTRACT, CHANGE_VERSION, CREATE_KIND, CHANGE_KIND, change_enabled, declared

FORM_AGENT_PROTOCOL = "form-agent.v1"
FORM_PROPOSAL_CONTRACT = "form_agent_proposal.v1"
FORM_PROPOSAL_EVENT = "form.proposal.completed"
FORM_PROPOSAL_PIPELINE = "form_proposal_generation"
FORM_PROPOSAL_STEP = "form.proposal.generate"
FORM_SCHEMA_VERSION = "1.0.0"


class _AnchorRequired(ValueError):
    """A missing or ambiguous host anchor needs a user decision."""

_STATE_CAPABILITIES = frozenset({
    "proposal.begin", "proposal.needs_clarification", "proposal.unsupported", "proposal.no_change",
})
_FIELD_CAPABILITY = "form.field.define"
_FIELD_NAME_PATTERN = r"^[a-z][a-z0-9_]*$"


def proposal_capabilities(context: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return controlled IR, narrowing generation to the current host catalog."""
    available = component_names(context.get("capabilities")) if context is not None else set(FLOW_COMPONENTS)
    components = [component for component in FLOW_COMPONENTS if component in available]
    capabilities = [
        {
            "capability": "proposal.begin",
            "semantics": (
                "开始一个 ready 提案。空白表单使用 form_fields + replace_empty_form；"
                "已有表单新增字段使用 form_fields + append，可用 target 指定插入位置；"
                "其他修改使用 form_actions + append。"
            ),
            "slots_schema": {
                "type": "object",
                "required": ["summary", "result_kind"],
                "properties": {
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "result_kind": {"type": "string", "enum": ["form_fields", "form_actions", "form_changes", "property_changes", "property_query", "property_undo"]},
                    "mode": {"type": "string", "enum": ["replace_empty_form", "append"]},
                    "target": {
                        "type": "object",
                        "required": ["kind"],
                        "properties": {
                            "kind": {"type": "string", "enum": ["root", "relative"]},
                            "index": {"type": "integer", "minimum": 0},
                            "anchorNodeId": {"type": "string"},
                            "anchorName": {"type": "string"},
                            "anchorLabel": {"type": "string"},
                            "useSelection": {"type": "boolean"},
                            "position": {"type": "string", "enum": ["before", "after"]},
                        },
                    },
                },
            },
        },
        {
            "capability": _FIELD_CAPABILITY,
            "semantics": (
                "定义一个新表单字段的业务语义。不得输出 id、完整 Schema、Action 或组件内部属性；"
                "Python 编译器负责生成唯一 form.add_component 动作草稿。"
            ),
            "slots_schema": {
                "type": "object",
                "required": ["client_ref", "component_name", "label", "name"],
                "additionalProperties": False,
                "properties": {
                    "client_ref": {
                        "type": "string",
                        "description": "本批唯一引用，以小写字母开头，其后可用小写字母、数字、下划线或连字符，例如 student_no 或 student-name；原样用于展示与动作关联。",
                    },
                    "component_name": {"type": "string", "enum": components},
                    "label": {"type": "string"},
                    "name": {"type": "string"},
                    "required": {"type": "boolean"},
                    "placeholder": {"type": "string"},
                    "options": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["label", "value"],
                            "properties": {
                                "label": {"type": "string"},
                                "value": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
        {
            "capability": "proposal.needs_clarification",
            "semantics": "缺失信息会改变结果或存在有损决策时发起澄清，本轮不交付动作。",
            "slots_schema": {
                "type": "object",
                "required": ["summary", "question"],
                "properties": {
                    "summary": {"type": "string"},
                    "question": {"type": "string"},
                    "choices": {"type": "array", "items": {"type": "string"}},
                    "code": {"type": "string"},
                },
            },
        },
        {
            "capability": "proposal.unsupported",
            "semantics": "宿主能力不足时明确拒绝，不把缺失功能伪装为已配置。",
            "slots_schema": {
                "type": "object",
                "required": ["summary", "code"],
                "properties": {"summary": {"type": "string"}, "code": {"type": "string"}},
            },
        },
        {
            "capability": "proposal.no_change",
            "semantics": "当前状态已经满足需求，或仅解释执行回执且无需新动作。",
            "slots_schema": {
                "type": "object",
                "required": ["summary"],
                "properties": {"summary": {"type": "string"}},
            },
        },
    ]
    if not components:
        capabilities = [entry for entry in capabilities if entry["capability"] != _FIELD_CAPABILITY]
    return capabilities + action_capabilities() + property_capabilities()


def _host_context_source(step_context: Any) -> Any:
    source = step_context if isinstance(step_context, Mapping) else getattr(step_context, "context", None)
    if isinstance(source, Mapping) and isinstance(source.get("context"), Mapping):
        source = source["context"]
    return source


def host_context_diagnostic(context: Any, stage: str) -> dict[str, Any]:
    """Describe the boundary shape without serializing arbitrary keys or values."""
    source = _host_context_source(context)
    normalized = normalize_host_context(context)
    known_keys = set(normalized) | {
        "context", "host_context", "input_data", "user_input", "supportedProposalVersions", "snapshotScope",
        "request_id", "schema_version", "current_form_schema", "current_page_schema", "form_schema",
    }
    keys = sorted(key for key in source if isinstance(key, str) and key in known_keys) if isinstance(source, Mapping) else []
    return {
        "code": "FORM_HOST_CONTEXT_TRACE",
        "stage": stage,
        "input_type": type(context).__name__,
        "context_type": type(source).__name__,
        "keys": keys,
        "present": {
            key: bool(normalized.get(key))
            for key in ("requestId", "target", "currentSchema", "capabilities", "supportedActionVersions")
        },
    }


def normalize_host_context(step_context: Any) -> dict[str, Any]:
    """Normalize the host snapshot without guessing missing canvas state."""
    source = _host_context_source(step_context)
    source = source if isinstance(source, Mapping) else {}
    capabilities = deepcopy(source.get("capabilities")) if isinstance(source.get("capabilities"), (Mapping, list)) else {}
    nested_capabilities = capabilities if isinstance(capabilities, Mapping) else {}
    schema = _first_mapping(source, "currentSchema", "current_form_schema", "current_page_schema", "form_schema")
    return {
        "requestId": _text(source.get("requestId") or source.get("request_id")),
        "schemaVersion": _text(source.get("schemaVersion") or source.get("schema_version") or schema.get("schemaVersion"), FORM_SCHEMA_VERSION),
        "target": _first_mapping(source, "target"),
        "currentSchema": schema,
        "selection": _first_mapping(source, "selection"),
        "canvas": _first_mapping(source, "canvas"),
        "capabilities": capabilities,
        "fieldNameRules": _first_mapping(source, "fieldNameRules") or deepcopy(nested_capabilities.get("fieldNameRules", {})),
        "optionRules": _first_mapping(source, "optionRules") or deepcopy(nested_capabilities.get("optionRules", {})),
        "supportedActionVersions": deepcopy(source.get("supportedActionVersions")) if isinstance(source.get("supportedActionVersions"), (Mapping, list, str)) else {},
        "executionResult": deepcopy(source.get("executionResult")) if isinstance(source.get("executionResult"), Mapping) else {},
        "resolvedProperties": _first_mapping(source, "resolvedProperties"),
        "history": _first_mapping(source, "history"),
        "rules": _first_mapping(source, "rules"),
        "linkages": _first_mapping(source, "linkages"),
        "nodePolicies": _first_mapping(source, "nodePolicies") or _first_mapping(nested_capabilities, "nodePolicies"),
    }


def compile_form_proposal(ir_payload: Any, step_context: Any) -> dict[str, Any]:
    """Compile IR, explaining unavailable capabilities without executable actions."""
    try:
        return _compile_form_proposal(ir_payload, step_context)
    except CapabilityUnavailable as error:
        result = _compile_form_proposal({"plan_items": [{
            "capability": "proposal.unsupported",
            "slots": {"summary": str(error), "code": error.code},
        }]}, step_context)
        items = ir_payload.get("plan_items", [ir_payload]) if isinstance(ir_payload, Mapping) else [ir_payload]
        result["output"]["form_proposal"]["proposalId"] = _proposal_id(normalize_host_context(step_context), items)
        return result


def _compile_form_proposal(ir_payload: Any, step_context: Any) -> dict[str, Any]:
    context = normalize_host_context(step_context)
    items = ir_payload.get("plan_items") if isinstance(ir_payload, Mapping) else None
    if not isinstance(items, list):
        items = [ir_payload]
    if not items or any(not isinstance(item, Mapping) for item in items):
        raise ValueError("提案没有有效项目或包含非法项目")
    if any(item.get("capability") in {"form.property.rule", "form.property.linkage"} for item in items):
        raise CapabilityUnavailable("PROPERTY_PROTOCOL_UNSUPPORTED", "规则和联动尚无已约定的统一变更协议，暂不支持。")
    known = _STATE_CAPABILITIES | {_FIELD_CAPABILITY} | set(ACTION_KINDS) | {
        entry["capability"] for entry in property_capabilities()
    }
    unknown = [item.get("capability") for item in items
               if not isinstance(item.get("capability"), str) or item["capability"] not in known]
    if unknown:
        raise ValueError(f"提案包含未注册能力: {unknown}")

    state_items = [item for item in items if _text(item.get("capability")) in _STATE_CAPABILITIES]
    if len(state_items) != 1:
        raise ValueError("每个提案必须且只能包含一个 proposal.* 状态项目")
    state_item = state_items[0]
    state = _text(state_item.get("capability")).removeprefix("proposal.")
    slots = state_item.get("slots") if isinstance(state_item.get("slots"), Mapping) else {}
    summary = _text(slots.get("summary"), "表单提案已整理。")
    base: dict[str, Any] = {
        "protocol": FORM_AGENT_PROTOCOL,
        "contractVersion": FORM_PROPOSAL_CONTRACT,
        "schemaVersion": context["schemaVersion"],
        "status": state,
        "proposalId": _proposal_id(context, items),
        "target": _proposal_target(context),
        "summary": summary,
        "diagnostics": [],
    }
    if context.get("requestId"):
        base["requestId"] = context["requestId"]

    non_state_items = [item for item in items if item is not state_item]
    if state != "begin" and non_state_items:
        raise ValueError(f"{state} 状态不能同时交付字段或动作")
    if state == "needs_clarification":
        question = _text(slots.get("question"))
        if not question:
            raise ValueError("needs_clarification 必须包含 question")
        choices = [_text(choice) for choice in slots.get("choices", []) if _text(choice)] if isinstance(slots.get("choices"), list) else []
        base["question"] = question
        if choices:
            base["choices"] = choices
        base["diagnostics"] = [_diagnostic(_text(slots.get("code"), "CLARIFICATION_REQUIRED"), summary)]
        return _completed(base)
    if state == "unsupported":
        base["diagnostics"] = [_diagnostic(_text(slots.get("code"), "CAPABILITY_UNAVAILABLE"), summary)]
        return _completed(base)
    if state == "no_change":
        return _completed(base)
    if state != "begin":
        raise ValueError(f"不支持的提案状态: {state}")

    base["status"] = "ready"
    result_kind = _text(slots.get("result_kind"))
    work_capabilities = {item.get("capability") for item in non_state_items}
    if "form.property.change" in work_capabilities and work_capabilities.intersection(set(ACTION_KINDS) | {_FIELD_CAPABILITY}):
        if not change_enabled(context):
            raise CapabilityUnavailable("CHANGE_CONTRACT_UNSUPPORTED", "宿主未协商统一变更能力，不支持混合修改。")
        result_kind = "form_changes"
    if result_kind == "property_changes" and work_capabilities == {"form.property.change"}:
        result_kind = "form_changes"
    if result_kind == "form_changes":
        return _completed(_compile_changes(base, slots, items, context))
    if result_kind in {"property_changes", "property_query", "property_undo"}:
        return _completed(compile_property_request(items, context, base))
    execution_result = context.get("executionResult") if isinstance(context.get("executionResult"), Mapping) else {}
    if _text(execution_result.get("status")).lower() == "conflict":
        raise ValueError("前次执行发生 revision conflict，必须刷新宿主上下文后生成新提案")
    result_kind = _text(slots.get("result_kind"))
    if any(str(item.get("capability", "")).startswith("form.property.") for item in items):
        raise ValueError("属性 IR 必须使用 property_changes/property_query/property_undo")
    if result_kind == "form_fields":
        try:
            _compile_form_fields(base, slots, items, context)
        except _AnchorRequired as error:
            base["status"] = "needs_clarification"
            base["question"] = str(error)
            base["summary"] = "需要确认新增字段的插入位置。"
            base["diagnostics"] = [_diagnostic("ANCHOR_FIELD_REQUIRED", str(error))]
        return _completed(base)
    if result_kind != "form_actions":
        raise ValueError("result_kind 必须是 form_fields 或 form_actions")
    _compile_form_actions(base, slots, items, context)
    return _completed(base)


def _compile_form_fields(
    base: dict[str, Any],
    slots: Mapping[str, Any],
    items: list[Mapping[str, Any]],
    context: Mapping[str, Any],
    *,
    removals_before: Mapping[int, list[dict[str, Any]]] | None = None,
) -> None:
    mode = _text(slots.get("mode"), "replace_empty_form")
    if mode not in {"replace_empty_form", "append"}:
        raise ValueError("字段生成只支持 replace_empty_form 或 append")
    schema = context.get("currentSchema", {})
    canvas = context.get("canvas") if isinstance(context.get("canvas"), Mapping) else {}
    if _text(canvas.get("layoutMode"), "flow").lower() != "flow" or _text(schema.get("layoutMode"), "flow").lower() != "flow":
        raise ValueError("字段生成只支持 flow 布局")
    if mode == "replace_empty_form" and not _is_blank_canvas(context):
        raise ValueError("replace_empty_form 只允许用于空白表单")
    existing = schema.get("fields")
    if not isinstance(existing, list):
        raise ValueError("currentSchema 必须包含 fields 数组")
    if any(not isinstance(field, Mapping) or field.get("children") or field.get("fields") for field in existing):
        raise ValueError("字段生成只支持单层 Flow 组件")
    if existing:
        _validate_schema(schema, context)
    insertion_index = _field_insertion_index(slots.get("target"), existing, context) if mode == "append" else 0

    if mode == "append":
        if not change_enabled(context):
            raise CapabilityUnavailable("CHANGE_CONTRACT_UNSUPPORTED", "宿主未声明统一变更协议、展示组件及动作版本。")
        _require_change_target(base)
        version = CHANGE_VERSION
    else:
        caps = context.get("capabilities", {})
        if not declared(caps.get("supportedPresentationKinds"), CREATE_KIND):
            raise CapabilityUnavailable("CREATE_CONTRACT_UNSUPPORTED", "宿主未声明新建表单确认组件。")
        versions = caps.get("supportedActionVersions", context.get("supportedActionVersions"))
        declaration = versions.get("form.add_component") if isinstance(versions, Mapping) and "form.add_component" in versions else versions
        if not declared(declaration, "1.0"):
            raise CapabilityUnavailable("ACTION_VERSION_UNSUPPORTED", "新建确认要求 form.add_component 的 1.0 动作版本。")
        version = "1.0"
    supported_actions = _supported_actions(context)
    if "form.add_component" not in supported_actions:
        raise CapabilityUnavailable("ACTION_UNSUPPORTED", "宿主未声明 form.add_component，暂时无法生成完整表单。")
    if not component_catalog(context.get("capabilities")):
        raise CapabilityUnavailable("MISSING_COMPONENT_CATALOG", "宿主 capabilities 未提供组件目录，暂时无法生成字段。")

    field_items = [item for item in items if _text(item.get("capability")) == _FIELD_CAPABILITY]
    other_items = [
        item for item in items
        if item not in field_items and _text(item.get("capability")) not in _STATE_CAPABILITIES
    ]
    if other_items:
        raise ValueError("form_fields 提案不能混入增量 Action")
    if not field_items:
        raise ValueError("完整表单至少包含一个字段")
    max_fields = _positive_int(_field_name_rules(context).get("maxFields"), 32)
    if removals_before is None and len(field_items) + sum(_is_field_node(field) for field in existing) > max_fields:
        raise ValueError(f"字段数量超过宿主限制: {max_fields}")

    actions: list[dict[str, Any]] = []
    candidate_fields = list(existing)
    seen_refs: set[str] = {
        _text(field.get("clientRef") or field.get("id")) for field in existing
    }
    seen_refs.update(_text(field.get("id")) for field in existing)
    seen_names = _existing_field_names(context)
    for index, item in enumerate(field_items):
        position = insertion_index + index
        if removals_before is not None:
            removed = {target_node_id(action["payload"], context) for action in removals_before[id(item)]}
            candidate_fields = [node for node in candidate_fields if node.get("id") not in removed]
            if sum(_is_field_node(node) for node in candidate_fields) >= max_fields:
                raise ValueError(f"字段数量超过宿主限制: {max_fields}")
            position = _field_insertion_index(None, candidate_fields, context)
        field_slots = item.get("slots") if isinstance(item.get("slots"), Mapping) else {}
        field = _compile_field(field_slots, context, seen_refs, seen_names)
        if removals_before is not None:
            candidate_fields.insert(position, field)
        actions.append({
            "actionId": f"add-field-{index + 1:03d}",
            "action": "form.add_component",
            "payload": {
                "clientRef": field["clientRef"],
                "componentName": field["componentName"],
                "props": deepcopy(field["props"]),
                "target": {"kind": "root", "index": position},
            },
        })

    set_action_draft(
        base, actions, mode=mode, action_version=version,
        kind=CHANGE_KIND if mode == "append" else CREATE_KIND, title=_proposal_title(slots, context),
    )
    if mode == "append":
        base["contractVersion"] = CHANGE_CONTRACT


def _is_field_node(node: Mapping[str, Any]) -> bool:
    return node.get("componentCategory", "field") == "field"


def _field_insertion_index(value: Any, fields: list, context: Mapping[str, Any]) -> int:
    if value is None:
        return next((index + 1 for index in range(len(fields) - 1, -1, -1) if _is_field_node(fields[index])), len(fields))
    if not isinstance(value, Mapping):
        raise ValueError("target 必须是对象")
    kind = _text(value.get("kind"))
    if kind == "root":
        index = value.get("index", len(fields))
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index <= len(fields):
            raise ValueError("root target.index 超出当前组件列表范围")
        return index
    if kind != "relative":
        raise ValueError(f"首期单层 Flow 不支持 target.kind: {kind}")
    if value.get("position") not in {"before", "after"}:
        raise ValueError("relative target 必须声明 before/after")
    selectors = {key: _text(value.get(key)) for key in ("anchorNodeId", "anchorName", "anchorLabel") if _text(value.get(key))}
    if value.get("useSelection") is True:
        selected = _text(context.get("selection", {}).get("nodeId"))
        if not selected:
            raise _AnchorRequired("请先选择一个字段，或提供插入位置的字段名称或 ID。")
        if "anchorNodeId" in selectors and selectors["anchorNodeId"] != selected:
            raise _AnchorRequired("当前选中字段与指定 ID 不一致，请确认插入位置。")
        selectors["anchorNodeId"] = selected
    if not selectors:
        raise _AnchorRequired("请提供插入位置的字段名称、name 或 ID。")
    matches = []
    for index, node in enumerate(fields):
        props = node.get("props") if isinstance(node.get("props"), Mapping) else {}
        values = {
            "anchorNodeId": {_text(node.get("id"))},
            "anchorName": {_text(props.get("name"))},
            "anchorLabel": {_text(props.get("label")), _text(node.get("fieldTitle"))},
        }
        if all(selector in values[key] for key, selector in selectors.items()):
            matches.append(index)
    if len(matches) != 1:
        raise _AnchorRequired("目标字段不存在或名称重复，请提供唯一的字段 name 或 ID。")
    anchor = fields[matches[0]]
    if not _text(anchor.get("id")):
        raise _AnchorRequired("目标字段缺少真实 ID，请刷新画布上下文后重试。")
    return matches[0] + (value["position"] == "after")


def _proposal_title(slots: Mapping[str, Any], context: Mapping[str, Any]) -> str:
    schema = context.get("currentSchema", {})
    return _text(slots.get("title") or schema.get("title"), "新表单" if _is_blank_canvas(context) else "表单字段")


def _compile_field(
    slots: Mapping[str, Any],
    context: Mapping[str, Any],
    seen_refs: set[str],
    seen_names: set[str],
) -> dict[str, Any]:
    client_ref = _text(slots.get("client_ref"))
    component = _text(slots.get("component_name"))
    unknown = set(slots) - {"client_ref", "component_name", "label", "name", "required", "placeholder", "options"}
    if unknown:
        reject_properties(component, unknown, "字段定义未支持这些属性")
    label = _text(slots.get("label"))
    name = _text(slots.get("name"))
    if not client_ref or not CLIENT_REF_PATTERN.fullmatch(client_ref):
        raise ValueError(f"clientRef 非法: {client_ref or '<empty>'}")
    if client_ref in seen_refs:
        raise ValueError(f"重复 clientRef: {client_ref}")
    if component not in FLOW_COMPONENTS:
        raise CapabilityUnavailable("UNSUPPORTED_COMPONENT", f"首期不支持组件: {component}。")
    require_component(component, context.get("capabilities"))
    if not label:
        raise ValueError("字段 label 不能为空")
    _validate_field_name(name, context, seen_names)

    if "required" in slots and type(slots["required"]) is not bool:
        raise ValueError("required 必须为 boolean")
    props: dict[str, Any] = {"label": label, "name": name}
    writable = writable_props(component, context.get("capabilities"), creation=True)
    if "required" in writable or slots.get("required") is True or ("required" in slots and component != "Switch"):
        props["required"] = slots.get("required") is True
    placeholder = _text(slots.get("placeholder"))
    if placeholder:
        if component == "Switch":
            reject_properties(component, {"placeholder"}, "字段定义未支持此属性")
        props["placeholder"] = placeholder
    raw_options = slots.get("options")
    if component in OPTION_COMPONENTS:
        props["options"] = _normalize_options(raw_options, context)
    elif isinstance(raw_options, list) and raw_options:
        raise ValueError(f"{component} 不支持 options")
    validate_writable_props(component, props, context.get("capabilities"), creation=True)

    seen_refs.add(client_ref)
    seen_names.add(name)
    return {
        "clientRef": client_ref,
        "componentName": component,
        "props": props,
    }


def _compile_form_actions(
    base: dict[str, Any],
    slots: Mapping[str, Any],
    items: list[Mapping[str, Any]],
    context: Mapping[str, Any],
) -> None:
    supported_actions = _supported_actions(context)
    if not supported_actions:
        raise CapabilityUnavailable("ACTION_UNSUPPORTED", "宿主 capabilities 未声明可执行表单动作。")
    action_items = [item for item in items if _text(item.get("capability")) in ACTION_KINDS]
    if any(_text(item.get("capability")) == _FIELD_CAPABILITY for item in items):
        raise ValueError("form_actions 提案不能混入字段定义")
    if not action_items:
        raise ValueError("ready 的 form_actions 提案至少包含一个动作")
    if not change_enabled(context):
        raise CapabilityUnavailable("CHANGE_CONTRACT_UNSUPPORTED", "宿主未声明统一变更协议、展示组件及动作版本。")
    version = CHANGE_VERSION
    _require_change_target(base)
    actions = []
    batch_refs: set[str] = set()
    existing_nodes = node_index(context.get("currentSchema", {}))
    existing_refs = set(existing_nodes) | {_text(node.get("clientRef")) for node in existing_nodes.values()}
    for index, item in enumerate(action_items, start=1):
        action = _text(item.get("capability"))
        if action not in supported_actions:
            raise CapabilityUnavailable("ACTION_UNSUPPORTED", f"宿主未声明支持动作: {action}。")
        action_slots = item.get("slots") if isinstance(item.get("slots"), Mapping) else {}
        payload = deepcopy(action_slots.get("payload")) if isinstance(action_slots.get("payload"), Mapping) else {}
        validate_action(action, payload, context, batch_refs)
        if payload.get("useSelection") is True:
            if not any(payload.get(key) for key in ("nodeId", "fieldId", "containerId")):
                payload["nodeId"] = target_node_id(payload, context)
            payload.pop("useSelection")
        action_id = _text(action_slots.get("action_id"), f"action-{index:03d}")
        references = _action_references(payload)
        dependencies = [previous["actionId"] for previous in actions
                        if previous["action"] == "form.add_component" and previous["payload"]["clientRef"] in references]
        actions.append({"actionId": action_id, "action": action, "payload": payload, "dependsOn": dependencies})
        client_ref = _text(payload.get("clientRef"))
        if action == "form.add_component" and client_ref:
            if client_ref in batch_refs or client_ref in existing_refs:
                raise ValueError(f"重复 clientRef: {client_ref}")
            batch_refs.add(client_ref)
    if _text(slots.get("mode"), "append") != "append":
        raise ValueError("增量动作必须使用 append，不能替换已有表单")
    _validate_action_sequence(actions, context)
    set_action_draft(
        base, actions, mode="append", action_version=version,
        kind=CHANGE_KIND, title=_proposal_title(slots, context),
    )
    _reject_overlaps(actions)
    base["contractVersion"] = CHANGE_CONTRACT


def _require_change_target(base):
    target = base.get("target", {})
    if not target.get("schemaId") or target.get("baseRevision") is None:
        raise CapabilityUnavailable("MISSING_REVISION", "统一变更需要固定 schemaId 和 baseRevision。")


def _reject_overlaps(actions):
    removed = {action["payload"].get("nodeId") or action["payload"].get("fieldId")
               for action in actions if action["action"] == "form.remove_component"}
    for action in actions:
        payload = action["payload"]
        references = _action_references(payload)
        if payload.get("sourceNodeId"):
            references.add(payload["sourceNodeId"])
        if action["action"] != "form.remove_component" and references.intersection(removed):
            raise CapabilityUnavailable("CHANGE_OVERLAP", "本批其他动作引用了将被删除的节点，无法安全合并。")
        if action["action"] == "form.apply_property_change" and payload.get("sourceNodeId"):
            others = [other for other in actions if other is not action and
                      (other["payload"].get("nodeId") or other["payload"].get("fieldId")) == payload["sourceNodeId"]]
            if others:
                raise CapabilityUnavailable("CHANGE_OVERLAP", "属性复制来源同时被修改，无法证明快照仍有效。")
    by_node = {}
    global_actions = []
    for action in actions:
        payload = action["payload"]
        node = payload.get("nodeId") or payload.get("fieldId")
        if node:
            by_node.setdefault(node, []).append(action)
        elif action["action"] != "form.add_component":
            global_actions.append(action)
    if global_actions and len(actions) > 1:
        raise CapabilityUnavailable("CHANGE_OVERLAP", "无法证明表单级或跨字段动作与本批其他动作互不影响，请拆分需求。")
    for group in by_node.values():
        if len(group) < 2:
            continue
        if not all(action["action"] == "form.apply_property_change" for action in group):
            raise CapabilityUnavailable("CHANGE_OVERLAP", "同一节点的生命周期或字段修改与其他动作重叠，无法安全合并。")
        props = [action["payload"]["property"] for action in group]
        if len(props) != len(set(props)):
            raise CapabilityUnavailable("PROPERTY_CONFLICT", "同一节点同一语义属性不能重复写入。")


def _compile_changes(base, slots, items, context):
    if not change_enabled(context):
        raise CapabilityUnavailable("CHANGE_CONTRACT_UNSUPPORTED", "宿主尚未声明统一变更协议、展示组件及动作版本，不能生成可执行变更提案。")
    _require_change_target(base)
    if slots.get("mode", "append") != "append":
        raise ValueError("统一变更必须使用 append")
    work = [item for item in items if item["capability"] not in _STATE_CAPABILITIES]
    if not work:
        raise ValueError("统一变更至少包含一个动作")
    allowed = set(ACTION_KINDS) | {_FIELD_CAPABILITY, "form.property.change"}
    if any(item["capability"] not in allowed for item in work):
        raise CapabilityUnavailable("CHANGE_ACTION_UNSUPPORTED", "统一变更仅支持字段动作及既有节点的属性修改。")
    fields = [item for item in work if item["capability"] == _FIELD_CAPABILITY]
    raw = [item for item in work if item["capability"] in ACTION_KINDS]
    properties = [item for item in work if item["capability"] == "form.property.change"]
    structural = {item["capability"] for item in raw} & {
        "form.add_component", "form.remove_component", "form.move_component", "form.convert_component",
    }
    default_append_with_removals = structural == {"form.remove_component"} and slots.get("target") is None
    if fields and structural and not default_append_with_removals:
        raise CapabilityUnavailable("CHANGE_POSITION_OVERLAP", "本批结构变更无法确定字段定义的插入位置，请使用明确位置的原始新增动作。")
    compiled = {}
    if raw:
        temp = deepcopy(base)
        _compile_form_actions(temp, {**slots, "mode": "append"}, raw, context)
        for item, action in zip(raw, temp["actions"]):
            compiled[id(item)] = action
    if fields:
        removals_before = None
        if default_append_with_removals:
            removals_before = {}
            preceding_removals = []
            for item in work:
                if item["capability"] == "form.remove_component":
                    preceding_removals.append(compiled[id(item)])
                elif item["capability"] == _FIELD_CAPABILITY:
                    removals_before[id(item)] = preceding_removals.copy()
        temp = deepcopy(base)
        _compile_form_fields(temp, {**slots, "mode": "append"}, fields, context, removals_before=removals_before)
        for item, action in zip(fields, temp["actions"]):
            compiled[id(item)] = action
        if removals_before is not None:
            # These indexes assume all earlier structural actions are selected.
            preceding_structure = []
            for item in work:
                if item["capability"] in {"form.remove_component", _FIELD_CAPABILITY}:
                    action = compiled[id(item)]
                    if item["capability"] == _FIELD_CAPABILITY:
                        action["dependsOn"] = preceding_structure.copy()
                    preceding_structure.append(action["actionId"])
    if properties:
        begin = {"capability": "proposal.begin", "slots": {**slots, "result_kind": "property_changes"}}
        temp = compile_property_request([begin, *properties], context, base)
        if temp["status"] != "ready":
            if temp["status"] != "no_change" or not (fields or raw):
                return temp
            raise CapabilityUnavailable("CHANGE_NOOP_PROPERTIES", "混合批次包含无变化属性，请刷新并移除这些建议。")
        for item, action in zip(properties, temp["actions"]):
            compiled[id(item)] = action
        base["catalogVersion"] = temp["catalogVersion"]
    actions = [compiled[id(item)] for item in work]
    _reject_overlaps(actions)
    _validate_action_sequence(actions, context)
    set_action_draft(base, actions, mode="append", action_version=CHANGE_VERSION,
                     kind=CHANGE_KIND, title=_proposal_title(slots, context))
    base["contractVersion"] = CHANGE_CONTRACT
    return base


def _action_references(value: Any) -> set[str]:
    references: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in {"fieldId", "nodeId", "fieldRef", "clientRef", "sourceFieldId", "targetFieldId"} and isinstance(child, str):
                references.add(child)
            else:
                references.update(_action_references(child))
    elif isinstance(value, list):
        for child in value:
            references.update(_action_references(child))
    return references


def _validate_action_sequence(actions: list[dict[str, Any]], context: Mapping[str, Any]) -> None:
    schema = context.get("currentSchema", {})
    fields = deepcopy(schema.get("fields"))
    canvas = context.get("canvas", {})
    if not isinstance(fields, list) or any(not isinstance(field, Mapping) or field.get("children") or field.get("fields") for field in fields):
        return
    if _text(canvas.get("layoutMode") or schema.get("layoutMode"), "flow").lower() != "flow":
        return
    for action in actions:
        payload = action["payload"]
        kind = action["action"]
        if kind == "form.add_component":
            target = payload.get("target", {})
            index = len(fields) if target.get("kind") == "root" and "index" not in target else _field_insertion_index(target, fields, context)
            field = {key: deepcopy(payload[key]) for key in ("clientRef", "componentName", "props") if key in payload}
            fields.insert(index, field)
            continue
        if kind not in {"form.update_component", "form.update_component_options", "form.convert_component", "form.remove_component", "form.move_component"}:
            continue
        node_id = target_node_id(payload, context)
        index = next((index for index, field in enumerate(fields) if node_id in {field.get("id"), field.get("clientRef")}), None)
        if index is None:
            raise ValueError(f"动作引用了已删除或不存在的节点: {node_id}")
        field = fields[index]
        if kind == "form.remove_component":
            fields.pop(index)
        elif kind == "form.move_component":
            fields.pop(index)
            target = payload.get("target", {})
            if target.get("kind") == "relative" and target.get("anchorNodeId") == node_id:
                destination = index
            elif target.get("kind") == "root" and "index" not in target:
                destination = len(fields)
            else:
                destination = _field_insertion_index(target, fields, context)
            fields.insert(destination, field)


def _validate_field_name(name: str, context: Mapping[str, Any], seen_names: set[str]) -> None:
    rules = _field_name_rules(context)
    pattern = _text(rules.get("pattern"), _FIELD_NAME_PATTERN)
    max_length = _positive_int(rules.get("maxLength"), 50)
    reserved = {str(value) for value in rules.get("reserved", [])} if isinstance(rules.get("reserved"), list) else set()
    if not name or len(name) > max_length or not re.fullmatch(pattern, name):
        raise ValueError(f"字段 name 不符合规则: {name or '<empty>'}")
    if name in reserved:
        raise ValueError(f"字段 name 为保留名: {name}")
    if name in seen_names:
        raise ValueError(f"字段 name 重复: {name}")


def _normalize_options(value: Any, context: Mapping[str, Any]) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise ValueError("选项组件必须包含至少一个 option")
    rules = context.get("optionRules") if isinstance(context.get("optionRules"), Mapping) else {}
    max_options = _positive_int(rules.get("maxOptions"), 100)
    if len(value) > max_options:
        raise ValueError(f"选项数量超过宿主限制: {max_options}")
    result: list[dict[str, str]] = []
    seen_values: set[str] = set()
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError("option 必须是对象")
        label = _text(item.get("label"))
        option_value = _text(item.get("value"))
        if not label or not option_value:
            raise ValueError("option.label 和 option.value 不能为空")
        if option_value in seen_values:
            raise ValueError(f"option.value 重复: {option_value}")
        seen_values.add(option_value)
        result.append({"label": label, "value": option_value})
    return result


def _validate_schema(schema: Mapping[str, Any], context: Mapping[str, Any]) -> None:
    fields = schema.get("fields")
    if not isinstance(fields, list):
        raise ValueError("完整 FormSchema 必须包含 fields 数组")
    allowed = component_names(context.get("capabilities"))
    if fields and not allowed:
        raise CapabilityUnavailable("MISSING_COMPONENT_CATALOG", "宿主 capabilities 未提供可用组件目录，不能校验完整 FormSchema。")
    seen: set[str] = set()
    for field in fields:
        if not isinstance(field, Mapping):
            raise ValueError("fields 中存在非法节点")
        node_id = _text(field.get("id"))
        component = _text(field.get("componentName"))
        if not node_id or node_id in seen:
            raise ValueError("完整 FormSchema 的节点 ID 必须存在且唯一")
        seen.add(node_id)
        if allowed and component not in allowed:
            raise CapabilityUnavailable("UNSUPPORTED_COMPONENT", f"完整 FormSchema 使用了未声明组件: {component}。")


def _supported_actions(context: Mapping[str, Any]) -> set[str]:
    result: set[str] = set()
    _collect_action_names(context.get("capabilities"), result)
    _collect_action_names(context.get("supportedActionVersions"), result)
    return result


def _collect_action_names(value: Any, output: set[str]) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if isinstance(key, str) and key.startswith("form."):
                output.add(key)
            if key in {"action", "actionName"} and isinstance(child, str) and child.startswith("form."):
                output.add(child)
            elif key in {"actions", "supportedActions"}:
                _collect_action_names(child, output)
    elif isinstance(value, list):
        for child in value:
            if isinstance(child, str) and child.startswith("form."):
                output.add(child)
            else:
                _collect_action_names(child, output)


def _field_name_rules(context: Mapping[str, Any]) -> dict[str, Any]:
    value = context.get("fieldNameRules")
    return dict(value) if isinstance(value, Mapping) else {}


def _existing_field_names(context: Mapping[str, Any]) -> set[str]:
    schema = context.get("currentSchema") if isinstance(context.get("currentSchema"), Mapping) else {}
    names: set[str] = set()
    for node in node_index(schema).values():
        props = node.get("props") if isinstance(node.get("props"), Mapping) else {}
        name = _text(props.get("name"))
        if name:
            names.add(name)
    return names


def _is_blank_canvas(context: Mapping[str, Any]) -> bool:
    canvas = context.get("canvas") if isinstance(context.get("canvas"), Mapping) else {}
    schema = context.get("currentSchema") if isinstance(context.get("currentSchema"), Mapping) else {}
    fields = schema.get("fields")
    return isinstance(fields, list) and not fields and canvas.get("isBlank") is not False


def _proposal_target(context: Mapping[str, Any]) -> dict[str, Any]:
    target = context.get("target") if isinstance(context.get("target"), Mapping) else {}
    result = {
        key: deepcopy(target[key])
        for key in ("schemaId", "appId", "formId", "layoutId", "baseRevision")
        if key in target
    }
    if "baseRevision" not in result and "revision" in target:
        result["baseRevision"] = deepcopy(target["revision"])
    return result


def _proposal_id(context: Mapping[str, Any], items: list[Mapping[str, Any]]) -> str:
    raw = json.dumps(
        {"requestId": context.get("requestId"), "target": context.get("target", {}), "items": items},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return "proposal-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _diagnostic(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _completed(proposal: dict[str, Any]) -> dict[str, Any]:
    return {"status": "completed", "output": {"form_proposal": proposal}, "summary": proposal["summary"]}


def _first_mapping(source: Mapping[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        value = source.get(key)
        if isinstance(value, Mapping):
            return deepcopy(dict(value))
    return {}


def _positive_int(value: Any, fallback: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else fallback


def _text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback
