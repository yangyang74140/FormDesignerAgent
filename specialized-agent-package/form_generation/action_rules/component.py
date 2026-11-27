"""Validation shared by component lifecycle actions."""

from typing import Any, Mapping
import re

from ..components import FLOW_COMPONENTS, OPTION_COMPONENTS
from ..host import CapabilityUnavailable, explicitly_unsaved, reject_properties, require_component, target_node_id, validate_writable_props


CLIENT_REF_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")
_IDENTITY_KEYS = {"nodeId", "fieldId", "containerId", "useSelection"}
_PAYLOAD_KEYS = {
    "form.add_component": {"clientRef", "componentName", "props", "target"},
    "form.update_component": _IDENTITY_KEYS | {"changes"},
    "form.update_component_options": _IDENTITY_KEYS | {"options"},
    "form.move_component": _IDENTITY_KEYS | {"target"},
    "form.remove_component": _IDENTITY_KEYS,
    "form.convert_component": _IDENTITY_KEYS | {"componentName", "targetComponentName"},
}


def validate_component_payload(action: str, payload: Mapping[str, Any]) -> None:
    allowed = _PAYLOAD_KEYS.get(action)
    if allowed is not None and set(payload) - allowed:
        reject_properties(action, set(payload) - allowed, "包含未支持的动作参数")


def validate_position(value: Any, nodes: Mapping[str, Any], context: Mapping[str, Any]) -> None:
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


def validate_add(payload: dict[str, Any], context: Mapping[str, Any], nodes: Mapping[str, Any], batch_refs: set[str]) -> None:
    component = _text(payload.get("componentName"))
    client_ref = _text(payload.get("clientRef"))
    if not client_ref or not CLIENT_REF_PATTERN.fullmatch(client_ref):
        raise ValueError("新增组件必须包含合法 clientRef")
    if component not in FLOW_COMPONENTS:
        raise CapabilityUnavailable("UNSUPPORTED_COMPONENT", f"首期不支持组件: {component}。")
    require_component(component, context.get("capabilities"), context=context, creation=True)
    if "props" in payload and not isinstance(payload["props"], Mapping):
        raise ValueError("新增组件 props 必须是对象")
    props = payload.get("props", {})
    validate_writable_props(component, props, context.get("capabilities"), creation=True, context=context)
    validate_position(payload.get("target"), nodes, context)


def validate_update(payload: dict[str, Any], context: Mapping[str, Any], nodes: Mapping[str, Any], batch_refs: set[str]) -> None:
    node_id = target_node_id(payload, context)
    changes = payload.get("changes") if isinstance(payload.get("changes"), Mapping) else {}
    if not changes:
        raise ValueError("form.update_component 必须包含 changes")
    if "name" in changes or "identifiers" in changes:
        raise ValueError("现有字段 props.name 不可修改")
    component = _text(nodes.get(node_id, {}).get("componentName"))
    validate_writable_props(component, changes, context.get("capabilities"), context=context)


def validate_options(payload: dict[str, Any], context: Mapping[str, Any], nodes: Mapping[str, Any], batch_refs: set[str]) -> None:
    node_id = target_node_id(payload, context)
    component = _text(nodes.get(node_id, {}).get("componentName"))
    if component not in OPTION_COMPONENTS:
        raise ValueError(f"{component or node_id} 不支持 options")
    validate_writable_props(component, {"options": payload.get("options")}, context.get("capabilities"), context=context)


def validate_move(payload: dict[str, Any], context: Mapping[str, Any], nodes: Mapping[str, Any], batch_refs: set[str]) -> None:
    validate_position(payload.get("target"), nodes, context)


def validate_remove(payload: dict[str, Any], context: Mapping[str, Any], nodes: Mapping[str, Any], batch_refs: set[str]) -> None:
    """Removal has no extra payload beyond the shared identity check."""


def validate_convert(payload: dict[str, Any], context: Mapping[str, Any], nodes: Mapping[str, Any], batch_refs: set[str]) -> None:
    node = nodes.get(target_node_id(payload, context), {})
    if not explicitly_unsaved(node):
        raise ValueError("首期只允许转换明确标记为未保存的新字段")
    component = _text(payload.get("componentName") or payload.get("targetComponentName"))
    if component not in FLOW_COMPONENTS:
        raise CapabilityUnavailable("UNSUPPORTED_COMPONENT", f"首期不支持目标组件: {component}。")
    require_component(component, context.get("capabilities"), context=context, creation=True)


def _text(value: Any) -> str:
    return str(value or "").strip()
