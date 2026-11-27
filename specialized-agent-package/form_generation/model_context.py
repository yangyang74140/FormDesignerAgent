"""Expose mode-compatible candidates without changing compiler authorization."""

from copy import deepcopy
from typing import Any, Mapping

from .host import component_catalog
from .modes import CapabilityUnavailable, canonical_canvas, require_flow, validate_scope


def model_host_context(context: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(context))
    result["canvas"] = canonical_canvas(context.get("canvas"))
    caps = result.get("capabilities")
    if not isinstance(caps, dict):
        return result
    catalog = component_catalog(caps)
    filtered = {}
    for name, metadata in catalog.items():
        try:
            device, _ = require_flow(context)
            validate_scope(metadata, context, name)
            if metadata.get("supported") is False:
                continue
        except CapabilityUnavailable:
            continue
        metadata = deepcopy(metadata)
        sources = [metadata]
        if "create" in metadata:
            create = metadata["create"]
            try:
                if not isinstance(create, Mapping) or create.get("supported") is False:
                    raise CapabilityUnavailable("UNSUPPORTED_COMPONENT", "新增未开放")
                validate_scope(create, context, name)
                sources.append(create)
            except CapabilityUnavailable:
                metadata["create"] = {"supported": False, "writableProps": []}
        for source in sources:
            definitions = source.get("properties")
            if not isinstance(definitions, dict):
                continue
            allowed = {}
            for prop, definition in definitions.items():
                try:
                    if not isinstance(definition, Mapping) or definition.get("supported") is False:
                        continue
                    validate_scope(definition, context, f"{name}.{prop}")
                    allowed[prop] = definition
                except CapabilityUnavailable:
                    continue
            source["properties"] = allowed
            for key in ("writableProps", "editableProps"):
                if isinstance(source.get(key), list):
                    source[key] = [p for p in source[key] if p not in definitions or p in allowed]
        if device != "pc":
            metadata.pop("properties", None)
        filtered[name] = metadata
    for key in ("componentCatalog", "componentCapabilities"):
        caps.pop(key, None)
    caps["components"] = filtered
    return result
