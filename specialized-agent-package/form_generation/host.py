"""Read host catalogs and node identities without inferring missing capabilities."""

from copy import deepcopy
from typing import Any, Mapping


class CapabilityUnavailable(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def component_names(value: Any) -> set[str]:
    return {name for name, metadata in component_catalog(value).items() if metadata.get("supported") is not False}


def require_component(component: str, capabilities: Any) -> dict[str, Any]:
    catalog = component_catalog(capabilities)
    if not catalog:
        raise CapabilityUnavailable("MISSING_COMPONENT_CATALOG", "宿主未提供非空组件目录，暂时无法确认可用组件。")
    if component not in catalog:
        raise CapabilityUnavailable("UNSUPPORTED_COMPONENT", f"组件不在宿主能力目录中: {component}。")
    if catalog[component].get("supported") is False:
        raise CapabilityUnavailable("UNSUPPORTED_COMPONENT", f"宿主明确不支持组件: {component}。")
    return catalog[component]


def reject_properties(component: str, names: Any, reason: str) -> None:
    names = sorted(str(name) for name in names)
    prefix = "暂时还不支持禁用" if "disabled" in names else "暂时还不支持所请求的属性"
    raise CapabilityUnavailable("UNSUPPORTED_PROPERTY", f"{prefix}：{component} {reason}: {', '.join(names)}。")


def component_catalog(value: Any) -> dict[str, dict[str, Any]]:
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
            for key in catalog_keys:
                if key in current:
                    collect(current[key])
        elif isinstance(current, list):
            for child in current:
                visit(child)

    visit(value)
    return result


def writable_props(component: str, capabilities: Any, *, creation: bool = False) -> set[str]:
    metadata = require_component(component, capabilities)
    if creation and isinstance(metadata.get("create"), Mapping):
        metadata = metadata["create"]
    raw = metadata.get("writableProps") if "writableProps" in metadata else metadata.get("editableProps")
    if not isinstance(raw, list) or not raw or any(not isinstance(item, str) or not item for item in raw):
        raise CapabilityUnavailable(
            "MISSING_WRITABLE_PROPS",
            f"{component} 缺少有效的宿主可写属性目录，暂时无法生成属性配置。",
        )
    return set(raw)


def validate_writable_props(component: str, props: Mapping[str, Any], capabilities: Any, *, creation: bool = False) -> None:
    try:
        writable = writable_props(component, capabilities, creation=creation)
    except CapabilityUnavailable as error:
        if "disabled" in props:
            raise CapabilityUnavailable(error.code, "暂时还不支持禁用：" + str(error)) from error
        raise
    unsupported = set(props) - writable
    if unsupported:
        reject_properties(component, unsupported, "存在宿主不可写属性")


def node_index(schema: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
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


def target_node_id(payload: Mapping[str, Any], context: Mapping[str, Any]) -> str:
    direct = _text(payload.get("fieldId") or payload.get("nodeId") or payload.get("containerId"))
    if direct:
        return direct
    if payload.get("useSelection") is True:
        selection = context.get("selection") if isinstance(context.get("selection"), Mapping) else {}
        return _text(selection.get("nodeId"))
    return ""


def explicitly_unsaved(node: Mapping[str, Any]) -> bool:
    for key in ("isSaved", "saved", "persisted"):
        if key in node:
            return node.get(key) is False
    meta = node.get("meta") if isinstance(node.get("meta"), Mapping) else {}
    return any(meta.get(key) is False for key in ("isSaved", "saved", "persisted"))


def _text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


