"""Negotiation for the optional PC confirmation contracts."""
from collections.abc import Mapping

CHANGE_CONTRACT = "form_change_proposal.v1"
CHANGE_VERSION = "form_change_actions.v1"
CREATE_KIND = "shared.form-create-confirm"
CHANGE_KIND = "shared.form-change-confirm"


def declared(value, name):
    if isinstance(value, str):
        return value == name
    if isinstance(value, (list, tuple)):
        return name in value
    if isinstance(value, Mapping):
        if "versions" in value or "schemaVersions" in value:
            return declared(value.get("versions", value.get("schemaVersions")), name)
        return value.get(name) is True
    return False


def change_enabled(context):
    caps = context.get("capabilities", {})
    return isinstance(caps, Mapping) and all((
        declared(caps.get("supportedProposalContracts"), CHANGE_CONTRACT),
        declared(caps.get("supportedPresentationKinds"), CHANGE_KIND),
        declared(caps.get("supportedActionVersions", context.get("supportedActionVersions")), CHANGE_VERSION),
    ))
