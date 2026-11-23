"""Registered rule, formula and linkage references for generic form actions."""

from typing import Any, Mapping

from ..host import target_node_id


def validate_config(payload: dict[str, Any], context: Mapping[str, Any], nodes: Mapping[str, Any], batch_refs: set[str]) -> None:
    if not isinstance(payload.get("changes"), Mapping) or not payload["changes"]:
        raise ValueError("表单配置动作必须包含 changes")


def _validate_extension(action: str, payload: dict[str, Any], context: Mapping[str, Any], nodes: Mapping[str, Any], batch_refs: set[str]) -> None:
    _validate_references(payload, nodes, batch_refs)
    if action == "form.set_formula":
        formula = payload.get("formula") if isinstance(payload.get("formula"), Mapping) else {}
        references: set[str] = set()
        _collect_reference_values(formula, references)
        node_id = target_node_id(payload, context)
        if node_id and node_id in references:
            raise ValueError("公式不能直接引用目标字段自身")
    _validate_registered_resources(action, payload, context.get("capabilities"))


def validate_validation(payload: dict[str, Any], context: Mapping[str, Any], nodes: Mapping[str, Any], batch_refs: set[str]) -> None:
    _validate_extension("form.set_validation", payload, context, nodes, batch_refs)


def validate_linkage(payload: dict[str, Any], context: Mapping[str, Any], nodes: Mapping[str, Any], batch_refs: set[str]) -> None:
    _validate_extension("form.upsert_linkage", payload, context, nodes, batch_refs)


def validate_formula(payload: dict[str, Any], context: Mapping[str, Any], nodes: Mapping[str, Any], batch_refs: set[str]) -> None:
    _validate_extension("form.set_formula", payload, context, nodes, batch_refs)


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


def _text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


