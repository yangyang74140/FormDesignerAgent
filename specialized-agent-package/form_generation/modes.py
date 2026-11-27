"""Canonical canvas modes and host-declared capability scopes."""

from copy import deepcopy
from typing import Any, Mapping


class CapabilityUnavailable(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _default(value: Any, fallback: str) -> Any:
    return fallback if value is None or isinstance(value, str) and not value.strip() else value


def canonical_canvas(value: Any) -> dict[str, Any]:
    canvas = deepcopy(dict(value)) if isinstance(value, Mapping) else {}
    canvas.pop("device", None)
    canvas["deviceMode"] = _default(canvas.get("deviceMode"), "pc")
    canvas["layoutMode"] = _default(canvas.get("layoutMode"), "flow")
    return canvas


def resolve_modes(context: Mapping[str, Any]) -> tuple[str, str]:
    canvas = canonical_canvas(context.get("canvas"))
    device, layout = canvas["deviceMode"], canvas["layoutMode"]
    if not isinstance(device, str) or device not in ("pc", "mobile"):
        raise CapabilityUnavailable("INVALID_DEVICE_MODE", "canvas.deviceMode 仅支持 pc/mobile。")
    if not isinstance(layout, str) or layout not in ("flow", "grid"):
        raise CapabilityUnavailable("INVALID_LAYOUT_MODE", "canvas.layoutMode 仅支持 flow/grid。")
    schema = context.get("currentSchema")
    declared = _default(schema.get("layoutMode"), None) if isinstance(schema, Mapping) else None
    if declared is not None:
        if not isinstance(declared, str) or declared not in ("flow", "grid"):
            raise CapabilityUnavailable("INVALID_LAYOUT_MODE", "currentSchema.layoutMode 仅支持 flow/grid。")
        if declared != layout:
            raise CapabilityUnavailable("LAYOUT_MODE_CONFLICT", "canvas 与 currentSchema 明确声明的布局不一致，请刷新上下文。")
    return device, layout


def require_flow(context: Mapping[str, Any], *, properties: bool = False) -> tuple[str, str]:
    device, layout = resolve_modes(context)
    if layout != "flow":
        raise CapabilityUnavailable("LAYOUT_RESTRICTED", "当前 Agent 仅支持单层 Flow，暂不支持 Grid。")
    if properties and device != "pc":
        raise CapabilityUnavailable("DEVICE_RESTRICTED", "当前语义属性处理器仅支持 PC Flow，暂不支持移动端。")
    return device, layout


def validate_scope(metadata: Mapping[str, Any], context: Mapping[str, Any], label: str) -> None:
    device, layout = resolve_modes(context)
    for key, actual, code in (("devices", device, "DEVICE_RESTRICTED"), ("layouts", layout, "LAYOUT_RESTRICTED")):
        if key not in metadata:
            continue
        values = metadata[key]
        if not isinstance(values, list) or not values or any(not isinstance(v, str) for v in values) or actual not in values:
            raise CapabilityUnavailable(code, f"{label} 的宿主 {key} 范围不支持当前 {actual}。")
