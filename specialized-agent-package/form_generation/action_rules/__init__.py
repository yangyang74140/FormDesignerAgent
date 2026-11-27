"""One action registry drives model declarations and deterministic validation."""

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from ..host import component_catalog, node_index, target_node_id
from ..modes import require_flow, validate_scope
from .component import (
    CLIENT_REF_PATTERN,
    validate_add, validate_component_payload, validate_convert, validate_move, validate_options, validate_remove, validate_update,
)
from .extensions import validate_config, validate_formula, validate_linkage, validate_validation


@dataclass(frozen=True)
class _ActionRule:
    name: str
    validate: Callable[[dict[str, Any], Mapping[str, Any], Mapping[str, Any], set[str]], None]
    requires_node: bool = False


_RULES = (
    _ActionRule("form.add_component", validate_add),
    _ActionRule("form.update_component", validate_update, True),
    _ActionRule("form.update_component_options", validate_options, True),
    _ActionRule("form.move_component", validate_move, True),
    _ActionRule("form.remove_component", validate_remove, True),
    _ActionRule("form.convert_component", validate_convert, True),
    _ActionRule("form.update_form_config", validate_config),
    _ActionRule("form.set_validation", validate_validation),
    _ActionRule("form.upsert_linkage", validate_linkage),
    _ActionRule("form.set_formula", validate_formula),
)
_REGISTRY = {rule.name: rule for rule in _RULES}
ACTION_KINDS = tuple(_REGISTRY)


def action_capabilities() -> list[dict[str, Any]]:
    """Return fresh Native Capability declarations for the production actions."""
    return [
        {
            "capability": name,
            "semantics": f"生成 {name} 增量动作；payload 只能引用宿主真实节点或本批 clientRef。",
            "slots_schema": {
                "type": "object", "required": ["payload"],
                "properties": {"payload": {"type": "object"}, "action_id": {"type": "string"}},
            },
        }
        for name in ACTION_KINDS
    ]


def validate_action(action: str, payload: dict[str, Any], context: Mapping[str, Any], batch_refs: set[str]) -> None:
    """Validate one payload; host authorization and batch ordering stay with the compiler."""
    require_flow(context)
    rule = _REGISTRY.get(action)
    if rule is None:
        raise ValueError(f"提案包含未注册动作: {action}")
    schema = context.get("currentSchema") if isinstance(context.get("currentSchema"), Mapping) else {}
    nodes = node_index(schema)
    if action not in {"form.add_component", "form.update_form_config"}:
        node_id = target_node_id(payload, context)
        if node_id and node_id not in nodes and node_id not in batch_refs:
            raise ValueError(f"动作引用了不存在的节点: {node_id}")
        if rule.requires_node and not node_id:
            raise ValueError(f"{action} 必须包含真实节点 ID")
    if rule.requires_node:
        node = nodes.get(target_node_id(payload, context), {})
        metadata = component_catalog(context.get("capabilities")).get(node.get("componentName"), {})
        validate_scope(metadata, context, str(node.get("componentName", "组件")))
    validate_component_payload(action, payload)
    rule.validate(payload, context, nodes, batch_refs)
