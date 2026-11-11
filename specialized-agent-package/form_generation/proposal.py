"""Capability-aware compiler for the form-agent.v1 proposal protocol."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any, Mapping

FORM_AGENT_PROTOCOL = "form-agent.v1"
FORM_PROPOSAL_CONTRACT = "form_agent_proposal.v1"
FORM_FIELD_LIST_CONTRACT = "form_field_list.v1"
FORM_PROPOSAL_EVENT = "form.proposal.completed"
FORM_PROPOSAL_PIPELINE = "form_proposal_generation"
FORM_PROPOSAL_STEP = "form.proposal.generate"
FORM_SCHEMA_VERSION = "1.0.0"

FLOW_COMPONENTS = (
    "Input",
    "Input.TextArea",
    "DatePicker",
    "TimePicker",
    "NumberPicker",
    "SelectSingle",
    "SelectMulti",
    "CheckboxGroup",
    "Switch",
)
OPTION_COMPONENTS = frozenset({"SelectSingle", "SelectMulti", "CheckboxGroup"})
COMPONENT_LABELS = {
    "Input": "单行文本",
    "Input.TextArea": "多行文本",
    "DatePicker": "日期",
    "TimePicker": "时间",
    "NumberPicker": "数字",
    "SelectSingle": "下拉单选",
    "SelectMulti": "下拉多选",
    "CheckboxGroup": "复选框组",
    "Switch": "开关",
}

ACTION_KINDS = (
    "form.add_component",
    "form.update_component",
    "form.update_component_options",
    "form.move_component",
    "form.remove_component",
    "form.convert_component",
    "form.update_form_config",
    "form.set_validation",
    "form.upsert_linkage",
    "form.set_formula",
)

_STATE_CAPABILITIES = frozenset({
    "proposal.begin", "proposal.needs_clarification", "proposal.unsupported", "proposal.no_change",
})
_FIELD_CAPABILITY = "form.field.define"
_FIELD_NAME_PATTERN = r"^[a-z][a-z0-9_]*$"
_CLIENT_REF_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")


def proposal_capabilities() -> list[dict[str, Any]]:
    """Return the controlled IR exposed to the model."""
    capabilities = [
        {
            "capability": "proposal.begin",
            "semantics": (
                "开始一个 ready 提案。创建完整表单时使用 form_fields + replace_empty_form；"
                "修改现有表单时使用 form_actions + append。"
            ),
            "slots_schema": {
                "type": "object",
                "required": ["summary", "result_kind"],
                "properties": {
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "result_kind": {"type": "string", "enum": ["form_fields", "form_actions"]},
                    "mode": {"type": "string", "enum": ["replace_empty_form", "append"]},
                },
            },
        },
        {
            "capability": _FIELD_CAPABILITY,
            "semantics": (
                "定义一个新表单字段的业务语义。不得输出 id、完整 Schema、Action 或组件内部属性；"
                "Python 编译器负责生成展示字段和 form.add_component。"
            ),
            "slots_schema": {
                "type": "object",
                "required": ["client_ref", "component_name", "label", "name"],
                "properties": {
                    "client_ref": {"type": "string"},
                    "component_name": {"type": "string", "enum": list(FLOW_COMPONENTS)},
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
    for action in ACTION_KINDS:
        capabilities.append(
            {
                "capability": action,
                "semantics": f"生成 {action} 增量动作；payload 只能引用宿主真实节点或本批 clientRef。",
                "slots_schema": {
                    "type": "object",
                    "required": ["payload"],
                    "properties": {"payload": {"type": "object"}, "action_id": {"type": "string"}},
                },
            }
        )
    return capabilities


def normalize_host_context(step_context: Any) -> dict[str, Any]:
    """Normalize the host snapshot without guessing missing canvas state."""
    source = getattr(step_context, "context", None)
    source = source if isinstance(source, Mapping) else {}
    capabilities = deepcopy(source.get("capabilities")) if isinstance(source.get("capabilities"), (Mapping, list)) else {}
    nested_capabilities = capabilities if isinstance(capabilities, Mapping) else {}
    return {
        "requestId": _text(source.get("requestId") or source.get("request_id")),
        "schemaVersion": _text(source.get("schemaVersion") or source.get("schema_version"), FORM_SCHEMA_VERSION),
        "target": _first_mapping(source, "target"),
        "currentSchema": _first_mapping(source, "currentSchema", "current_form_schema", "current_page_schema", "form_schema"),
        "selection": _first_mapping(source, "selection"),
        "canvas": _first_mapping(source, "canvas"),
        "capabilities": capabilities,
        "fieldNameRules": _first_mapping(source, "fieldNameRules") or deepcopy(nested_capabilities.get("fieldNameRules", {})),
        "optionRules": _first_mapping(source, "optionRules") or deepcopy(nested_capabilities.get("optionRules", {})),
        "supportedActionVersions": deepcopy(source.get("supportedActionVersions")) if isinstance(source.get("supportedActionVersions"), (Mapping, list)) else {},
        "executionResult": deepcopy(source.get("executionResult")) if isinstance(source.get("executionResult"), Mapping) else {},
    }


def compile_form_proposal(ir_payload: Any, step_context: Any) -> dict[str, Any]:
    """Compile model IR into one deterministic, validated form-agent.v1 proposal."""
    context = normalize_host_context(step_context)
    items = ir_payload.get("plan_items") if isinstance(ir_payload, Mapping) else None
    if not isinstance(items, list):
        items = [ir_payload]
    items = [item for item in items if isinstance(item, Mapping)]
    if not items:
        raise ValueError("提案没有任何有效项目")

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
    execution_result = context.get("executionResult") if isinstance(context.get("executionResult"), Mapping) else {}
    if _text(execution_result.get("status")).lower() == "conflict":
        raise ValueError("前次执行发生 revision conflict，必须刷新宿主上下文后生成新提案")
    result_kind = _text(slots.get("result_kind"))
    if result_kind == "form_fields":
        _compile_form_fields(base, slots, items, context)
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
) -> None:
    if _text(slots.get("mode"), "replace_empty_form") != "replace_empty_form":
        raise ValueError("完整表单生成必须使用 replace_empty_form")
    if context.get("schemaVersion") != FORM_SCHEMA_VERSION:
        raise ValueError(f"首期只支持 Schema {FORM_SCHEMA_VERSION}")
    canvas = context.get("canvas") if isinstance(context.get("canvas"), Mapping) else {}
    if _text(canvas.get("layoutMode"), "flow").lower() != "flow":
        raise ValueError("首期完整表单生成只支持 flow 布局")
    if not _is_blank_canvas(context):
        raise ValueError("replace_empty_form 只允许用于空白表单")

    version = _action_version(context)
    supported_actions = _supported_actions(context)
    if "form.add_component" not in supported_actions:
        raise ValueError("宿主未声明 form.add_component，不能生成完整表单")
    host_components = _component_names(context.get("capabilities"))
    if not host_components:
        raise ValueError("宿主 capabilities 未提供组件目录")

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
    if len(field_items) > max_fields:
        raise ValueError(f"字段数量超过宿主限制: {max_fields}")

    fields: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    seen_refs: set[str] = set()
    seen_names = _existing_field_names(context)
    for index, item in enumerate(field_items):
        field_slots = item.get("slots") if isinstance(item.get("slots"), Mapping) else {}
        field = _compile_field(field_slots, context, host_components, seen_refs, seen_names)
        fields.append(field)
        actions.append({
            "actionId": f"add-field-{index + 1:03d}",
            "action": "form.add_component",
            "payload": {
                "clientRef": field["clientRef"],
                "componentName": field["componentName"],
                "props": deepcopy(field["props"]),
                "target": {"kind": "root", "index": index},
            },
        })

    title = _text(slots.get("title"), "新表单")
    base["presentation"] = {
        "kind": "form_field_list",
        "contractVersion": FORM_FIELD_LIST_CONTRACT,
        "title": title,
        "layoutMode": "flow",
        "fieldCount": len(fields),
        "fields": fields,
    }
    base["result"] = {
        "kind": "form_actions",
        "mode": "replace_empty_form",
        "schemaVersion": version,
        "actions": actions,
    }
    base["validation"] = {
        "status": "passed",
        "schemaVersion": FORM_SCHEMA_VERSION,
        "actionVersion": version,
        "fieldCount": len(fields),
    }


def _compile_field(
    slots: Mapping[str, Any],
    context: Mapping[str, Any],
    host_components: set[str],
    seen_refs: set[str],
    seen_names: set[str],
) -> dict[str, Any]:
    client_ref = _text(slots.get("client_ref"))
    component = _text(slots.get("component_name"))
    label = _text(slots.get("label"))
    name = _text(slots.get("name"))
    if not client_ref or not _CLIENT_REF_PATTERN.fullmatch(client_ref):
        raise ValueError(f"clientRef 非法: {client_ref or '<empty>'}")
    if client_ref in seen_refs:
        raise ValueError(f"重复 clientRef: {client_ref}")
    if component not in FLOW_COMPONENTS:
        raise ValueError(f"首期不支持组件: {component}")
    if component not in host_components:
        raise ValueError(f"组件不在宿主能力目录中: {component}")
    if not label:
        raise ValueError("字段 label 不能为空")
    _validate_field_name(name, context, seen_names)

    props: dict[str, Any] = {"label": label, "name": name, "required": slots.get("required") is True}
    placeholder = _text(slots.get("placeholder"))
    if placeholder and component != "Switch":
        props["placeholder"] = placeholder
    raw_options = slots.get("options")
    if component in OPTION_COMPONENTS:
        props["options"] = _normalize_options(raw_options, context)
    elif isinstance(raw_options, list) and raw_options:
        raise ValueError(f"{component} 不支持 options")
    _validate_writable_props(component, props, context.get("capabilities"))

    seen_refs.add(client_ref)
    seen_names.add(name)
    return {
        "clientRef": client_ref,
        "componentName": component,
        "componentLabel": _component_label(component, context.get("capabilities")),
        "props": props,
    }


def _compile_form_actions(
    base: dict[str, Any],
    slots: Mapping[str, Any],
    items: list[Mapping[str, Any]],
    context: Mapping[str, Any],
) -> None:
    version = _action_version(context)
    supported_actions = _supported_actions(context)
    if not supported_actions:
        raise ValueError("宿主 capabilities 未声明可执行表单动作")
    action_items = [item for item in items if _text(item.get("capability")) in ACTION_KINDS]
    if any(_text(item.get("capability")) == _FIELD_CAPABILITY for item in items):
        raise ValueError("form_actions 提案不能混入字段定义")
    if not action_items:
        raise ValueError("ready 的 form_actions 提案至少包含一个动作")
    actions = []
    batch_refs: set[str] = set()
    for index, item in enumerate(action_items, start=1):
        action = _text(item.get("capability"))
        if action not in supported_actions:
            raise ValueError(f"宿主未声明支持动作: {action}")
        action_slots = item.get("slots") if isinstance(item.get("slots"), Mapping) else {}
        payload = deepcopy(action_slots.get("payload")) if isinstance(action_slots.get("payload"), Mapping) else {}
        _validate_action(action, payload, context, batch_refs)
        action_id = _text(action_slots.get("action_id"), f"action-{index:03d}")
        actions.append({"actionId": action_id, "action": action, "payload": payload})
        client_ref = _text(payload.get("clientRef"))
        if action == "form.add_component" and client_ref:
            if client_ref in batch_refs:
                raise ValueError(f"重复 clientRef: {client_ref}")
            batch_refs.add(client_ref)
    base["result"] = {
        "kind": "form_actions",
        "mode": _text(slots.get("mode"), "append"),
        "schemaVersion": version,
        "actions": actions,
    }


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


def _validate_action(action: str, payload: dict[str, Any], context: Mapping[str, Any], batch_refs: set[str]) -> None:
    schema = context.get("currentSchema") if isinstance(context.get("currentSchema"), Mapping) else {}
    nodes = _node_index(schema)
    component_names = _component_names(context.get("capabilities"))
    if action == "form.add_component":
        component = _text(payload.get("componentName"))
        client_ref = _text(payload.get("clientRef"))
        if not client_ref or not _CLIENT_REF_PATTERN.fullmatch(client_ref):
            raise ValueError("新增组件必须包含合法 clientRef")
        if component not in FLOW_COMPONENTS:
            raise ValueError(f"首期不支持组件: {component}")
        if component_names and component not in component_names:
            raise ValueError(f"组件不在宿主能力目录中: {component}")
        props = payload.get("props") if isinstance(payload.get("props"), Mapping) else {}
        _validate_writable_props(component, props, context.get("capabilities"))
        _validate_target(payload.get("target"), nodes, context)
        return
    if action == "form.update_form_config":
        if not isinstance(payload.get("changes"), Mapping) or not payload["changes"]:
            raise ValueError("表单配置动作必须包含 changes")
        return
    node_id = _target_node_id(payload, context)
    if node_id and node_id not in nodes and node_id not in batch_refs:
        raise ValueError(f"动作引用了不存在的节点: {node_id}")
    if action in {"form.update_component", "form.update_component_options", "form.move_component", "form.remove_component", "form.convert_component"} and not node_id:
        raise ValueError(f"{action} 必须包含真实节点 ID")
    if action == "form.update_component":
        changes = payload.get("changes") if isinstance(payload.get("changes"), Mapping) else {}
        if not changes:
            raise ValueError("form.update_component 必须包含 changes")
        if "name" in changes or "identifiers" in changes:
            raise ValueError("现有字段 props.name 不可修改")
        component = _text(nodes.get(node_id, {}).get("componentName"))
        if component:
            _validate_writable_props(component, changes, context.get("capabilities"))
    if action == "form.update_component_options":
        component = _text(nodes.get(node_id, {}).get("componentName"))
        if component not in OPTION_COMPONENTS:
            raise ValueError(f"{component or node_id} 不支持 options")
        _validate_writable_props(component, {"options": payload.get("options")}, context.get("capabilities"))
    if action == "form.move_component":
        _validate_target(payload.get("target"), nodes, context)
    if action == "form.convert_component":
        node = nodes.get(node_id, {})
        if not _explicitly_unsaved(node):
            raise ValueError("首期只允许转换明确标记为未保存的新字段")
        target_component = _text(payload.get("componentName") or payload.get("targetComponentName"))
        if target_component not in FLOW_COMPONENTS:
            raise ValueError(f"首期不支持目标组件: {target_component}")
        if component_names and target_component not in component_names:
            raise ValueError(f"目标组件不在宿主能力目录中: {target_component}")
    if action in {"form.set_validation", "form.upsert_linkage", "form.set_formula"}:
        _validate_references(payload, nodes, batch_refs)
        if action == "form.set_formula":
            formula = payload.get("formula") if isinstance(payload.get("formula"), Mapping) else {}
            formula_refs: set[str] = set()
            _collect_reference_values(formula, formula_refs)
            if node_id and node_id in formula_refs:
                raise ValueError("公式不能直接引用目标字段自身")
        _validate_registered_resources(action, payload, context.get("capabilities"))


def _validate_target(value: Any, nodes: Mapping[str, Any], context: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping):
        raise ValueError("组件动作必须包含明确 target")
    kind = _text(value.get("kind"))
    if kind == "relative":
        anchor = _text(value.get("anchorNodeId"))
        if anchor not in nodes or value.get("position") not in {"before", "after"}:
            raise ValueError("relative target 必须引用真实锚点并声明 before/after")
    elif kind == "root":
        index = value.get("index")
        if index is not None and (not isinstance(index, int) or isinstance(index, bool) or index < 0):
            raise ValueError("root target.index 必须是非负整数")
    else:
        raise ValueError(f"首期单层 Flow 不支持 target.kind: {kind}")


def _validate_references(value: Any, nodes: Mapping[str, Any], batch_refs: set[str]) -> None:
    references: set[str] = set()
    _collect_reference_values(value, references)
    missing = sorted(ref for ref in references if ref not in nodes and ref not in batch_refs)
    if missing:
        raise ValueError(f"规则或公式包含悬空引用: {', '.join(missing)}")


def _collect_reference_values(value: Any, output: set[str]) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in {"fieldId", "nodeId", "fieldRef", "clientRef", "sourceFieldId", "targetFieldId"} and isinstance(child, str):
                output.add(child)
            else:
                _collect_reference_values(child, output)
    elif isinstance(value, list):
        for child in value:
            _collect_reference_values(child, output)


def _validate_registered_resources(action: str, payload: Mapping[str, Any], capabilities: Any) -> None:
    if action == "form.set_validation":
        requested = _named_resource(payload.get("validator")) or _text(payload.get("validatorName"))
        available = _resource_names(capabilities, {"validators", "validationCatalog", "remoteValidators"})
        label = "校验器"
    elif action == "form.set_formula":
        formula = payload.get("formula") if isinstance(payload.get("formula"), Mapping) else payload
        requested = _text(formula.get("function") or formula.get("functionName"))
        available = _resource_names(capabilities, {"functions", "formulaFunctions", "functionCatalog"})
        label = "公式函数"
    else:
        requested = _text(payload.get("dataSourceId") or payload.get("dataSource"))
        available = _resource_names(capabilities, {"dataSources", "dataSourceCatalog", "queries"})
        label = "数据源"
    if requested and (not available or requested not in available):
        raise ValueError(f"{label}未在宿主能力目录注册: {requested}")


def _named_resource(value: Any) -> str:
    if isinstance(value, Mapping):
        return _text(value.get("name") or value.get("key") or value.get("id"))
    return _text(value)


def _resource_names(value: Any, catalog_keys: set[str]) -> set[str]:
    result: set[str] = set()
    identity_keys = {"name", "key", "id", "validatorName", "functionName", "dataSourceId"}

    def collect_catalog(catalog: Any) -> None:
        if isinstance(catalog, Mapping):
            identity = next((_text(catalog.get(key)) for key in identity_keys if _text(catalog.get(key))), "")
            if identity:
                result.add(identity)
                return
            for key in catalog:
                if isinstance(key, str):
                    result.add(key)
        elif isinstance(catalog, list):
            for child in catalog:
                if isinstance(child, str):
                    result.add(child)
                else:
                    collect_catalog(child)
        elif isinstance(catalog, str):
            result.add(catalog)

    def visit(current: Any) -> None:
        if isinstance(current, Mapping):
            for key, child in current.items():
                if key in catalog_keys:
                    collect_catalog(child)
                else:
                    visit(child)
        elif isinstance(current, list):
            for child in current:
                visit(child)

    visit(value)
    return result


def _validate_schema(schema: Mapping[str, Any], context: Mapping[str, Any]) -> None:
    fields = schema.get("fields")
    if not isinstance(fields, list):
        raise ValueError("完整 FormSchema 必须包含 fields 数组")
    allowed = _component_names(context.get("capabilities"))
    if fields and not allowed:
        raise ValueError("宿主 capabilities 未提供组件目录，不能校验完整 FormSchema")
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
            raise ValueError(f"完整 FormSchema 使用了未声明组件: {component}")


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


def _component_names(value: Any) -> set[str]:
    return set(_component_catalog(value))


def _component_catalog(value: Any) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    catalog_keys = {"components", "componentCatalog", "componentCapabilities"}

    def collect(catalog: Any) -> None:
        if isinstance(catalog, Mapping):
            component_name = _text(catalog.get("componentName"))
            if component_name:
                result[component_name] = deepcopy(dict(catalog))
            else:
                for key, child in catalog.items():
                    if isinstance(key, str):
                        result[key] = deepcopy(dict(child)) if isinstance(child, Mapping) else {}
        elif isinstance(catalog, list):
            for child in catalog:
                if isinstance(child, str):
                    result[child] = {}
                else:
                    collect(child)

    def visit(current: Any) -> None:
        if isinstance(current, Mapping):
            for key, child in current.items():
                if key in catalog_keys:
                    collect(child)
                else:
                    visit(child)
        elif isinstance(current, list):
            for child in current:
                visit(child)

    visit(value)
    return result


def _component_label(component: str, capabilities: Any) -> str:
    metadata = _component_catalog(capabilities).get(component, {})
    return _text(
        metadata.get("componentLabel") or metadata.get("title") or metadata.get("label"),
        COMPONENT_LABELS[component],
    )


def _validate_writable_props(component: str, props: Mapping[str, Any], capabilities: Any) -> None:
    metadata = _component_catalog(capabilities).get(component, {})
    raw = metadata.get("writableProps") or metadata.get("editableProps")
    if not isinstance(raw, list) or not raw:
        return
    writable = {str(item) for item in raw}
    unsupported = sorted(set(props) - writable)
    if unsupported:
        raise ValueError(f"{component} 存在宿主不可写属性: {', '.join(unsupported)}")


def _field_name_rules(context: Mapping[str, Any]) -> dict[str, Any]:
    value = context.get("fieldNameRules")
    return dict(value) if isinstance(value, Mapping) else {}


def _existing_field_names(context: Mapping[str, Any]) -> set[str]:
    schema = context.get("currentSchema") if isinstance(context.get("currentSchema"), Mapping) else {}
    names: set[str] = set()
    for node in _node_index(schema).values():
        props = node.get("props") if isinstance(node.get("props"), Mapping) else {}
        name = _text(props.get("name"))
        if name:
            names.add(name)
    return names


def _is_blank_canvas(context: Mapping[str, Any]) -> bool:
    canvas = context.get("canvas") if isinstance(context.get("canvas"), Mapping) else {}
    if isinstance(canvas.get("isBlank"), bool):
        return canvas["isBlank"]
    schema = context.get("currentSchema") if isinstance(context.get("currentSchema"), Mapping) else {}
    fields = schema.get("fields")
    return isinstance(fields, list) and not fields


def _action_version(context: Mapping[str, Any]) -> str:
    versions = context.get("supportedActionVersions")
    candidates: list[str] = []
    if isinstance(versions, Mapping):
        for key, value in versions.items():
            if isinstance(value, str):
                candidates.append(value)
            elif value is True and isinstance(key, str):
                candidates.append(key)
            elif isinstance(value, list):
                candidates.extend(str(item) for item in value)
    elif isinstance(versions, list):
        candidates.extend(str(item) for item in versions)
    candidates = [item for item in candidates if item.strip()]
    if not candidates:
        raise ValueError("宿主未声明 supportedActionVersions，不能交付可执行动作")
    return sorted(candidates)[-1]


def _node_index(schema: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            node_id = _text(value.get("id"))
            if node_id and ("componentName" in value or "props" in value):
                result[node_id] = dict(value)
            for key in ("fields", "children"):
                visit(value.get(key))
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(schema)
    return result


def _target_node_id(payload: Mapping[str, Any], context: Mapping[str, Any]) -> str:
    direct = _text(payload.get("fieldId") or payload.get("nodeId") or payload.get("containerId"))
    if direct:
        return direct
    if payload.get("useSelection") is True:
        selection = context.get("selection") if isinstance(context.get("selection"), Mapping) else {}
        return _text(selection.get("nodeId"))
    return ""


def _explicitly_unsaved(node: Mapping[str, Any]) -> bool:
    for key in ("isSaved", "saved", "persisted"):
        if key in node:
            return node.get(key) is False
    meta = node.get("meta") if isinstance(node.get("meta"), Mapping) else {}
    return any(meta.get(key) is False for key in ("isSaved", "saved", "persisted"))


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
