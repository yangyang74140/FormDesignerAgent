"""Negotiated PC creation and ordered mixed change contracts."""
from copy import deepcopy
import unittest

from compiler_package import load_compiler_module
from test_properties import host, change

proposal = load_compiler_module("proposal")


def context():
    value = host()
    value["capabilities"].update(
        supportedProposalContracts=["form_change_proposal.v1"],
        supportedPresentationKinds=["shared.form-create-confirm", "shared.form-change-confirm"],
        actions=list(proposal.ACTION_KINDS),
    )
    value["capabilities"]["components"]["Input"]["writableProps"] = ["name", "label", "placeholder", "required"]
    value["supportedActionVersions"] = ["1.0", "form_change_actions.v1", "form_actions.v2"]
    value["currentSchema"]["fields"].append({"id": "b", "componentName": "Input", "props": {"label": "待删", "name": "old"}})
    return value


def compile_work(work, ctx=None, kind="form_changes", mode="append"):
    items = [{"capability": "proposal.begin", "slots": {"summary": "新增备注、修改提示并删除旧字段", "title": "表单变更", "result_kind": kind, "mode": mode}}, *work]
    return proposal.compile_form_proposal({"plan_items": items}, ctx or context())["output"]["form_proposal"]


def add():
    return {"capability": "form.add_component", "slots": {"payload": {"clientRef": "new-note", "componentName": "Input", "props": {"label": "备注", "name": "new_note"}, "target": {"kind": "root", "index": 2}}}}


def remove(node="b"):
    return {"capability": "form.remove_component", "slots": {"payload": {"nodeId": node}}}


class ChangeContractTests(unittest.TestCase):
    def test_mixed_order_single_source_and_snapshot_isolation(self):
        ctx = context()
        before = deepcopy(ctx)
        result = compile_work([add(), change(), remove()], ctx)
        self.assertEqual(result["status"], "ready", result)
        self.assertEqual(result["contractVersion"], "form_change_proposal.v1")
        self.assertEqual(result["actionVersion"], "form_change_actions.v1")
        self.assertEqual(result["presentation"], {"kind": "shared.form-change-confirm", "title": "表单变更"})
        self.assertEqual([a["action"] for a in result["actions"]], ["form.add_component", "form.apply_property_change", "form.remove_component"])
        self.assertEqual(result["actions"][1]["preconditions"]["before"], {"exists": True, "value": "旧"})
        self.assertEqual(result["catalogVersion"], "properties.v1")
        self.assertEqual(ctx, before)

    def test_nested_versions_are_authoritative_with_top_level_fallback(self):
        ctx = context()
        ctx["capabilities"]["supportedActionVersions"] = ["form_change_actions.v1"]
        ctx.pop("supportedActionVersions")
        self.assertEqual(compile_work([add(), change(), remove()], ctx)["status"], "ready")
        ctx["supportedActionVersions"] = ["form_change_actions.v1"]
        for denied in ([], ["1.0"], None, "unknown"):
            ctx["capabilities"]["supportedActionVersions"] = denied
            result = compile_work([remove()], ctx)
            self.assertEqual(result["status"], "unsupported", result)
        ctx["capabilities"].pop("supportedActionVersions")
        self.assertEqual(compile_work([remove()], ctx)["status"], "ready")

    def test_overlap_is_nonexecutable(self):
        for work in ([remove("a"), change()], [change(), remove("a")], [change(), change()], [change(), {"capability": "form.update_component", "slots": {"payload": {"nodeId": "a", "changes": {"label": "新名"}}}}]):
            result = compile_work(work)
            self.assertEqual(result["status"], "unsupported", result)
            self.assertNotIn("actions", result)

    def test_missing_negotiation_rejects_mixed_but_preserves_legacy(self):
        for key in ("supportedProposalContracts", "supportedPresentationKinds"):
            ctx = context()
            ctx["capabilities"].pop(key)
            self.assertEqual(compile_work([add(), change()], ctx)["status"], "unsupported")
            legacy = compile_work([remove()], ctx, "form_actions")
            self.assertEqual(legacy["presentation"]["kind"], "shared.table-field-confirm")
        ctx = context()
        ctx["supportedActionVersions"].remove("form_change_actions.v1")
        self.assertEqual(compile_work([add(), change()], ctx)["status"], "unsupported")

    def test_pure_paths_upgrade_and_catalog_is_conditional(self):
        ctx = context()
        ctx["capabilities"].pop("catalogVersion")
        result = compile_work([remove()], ctx, "form_actions")
        self.assertEqual(result["contractVersion"], "form_change_proposal.v1")
        self.assertNotIn("catalogVersion", result)
        self.assertEqual(compile_work([change()], ctx)["status"], "unsupported")
        self.assertEqual(compile_work([change()], kind="property_changes")["contractVersion"], "form_change_proposal.v1")

    def test_creation_uses_negotiated_kind_and_exact_version(self):
        ctx = context()
        ctx["currentSchema"]["fields"] = []
        field = {"capability": "form.field.define", "slots": {"client_ref": "name", "component_name": "Input", "label": "姓名", "name": "name"}}
        result = compile_work([field], ctx, "form_fields", "replace_empty_form")
        self.assertEqual(result["contractVersion"], "form_agent_proposal.v1")
        self.assertEqual(result["actionVersion"], "1.0")
        self.assertEqual(result["presentation"]["kind"], "shared.form-create-confirm")
        self.assertEqual([a["action"] for a in result["actions"]], ["form.add_component"])
        self.assertEqual(compile_work([field], kind="form_fields")["contractVersion"], "form_change_proposal.v1")

    def test_revision_and_existing_property_target_required(self):
        for key in ("schemaId", "revision"):
            ctx = context()
            ctx["target"].pop(key)
            self.assertEqual(compile_work([remove()], ctx)["status"], "unsupported")
        self.assertNotEqual(compile_work([add(), change(node_id="new-note")])["status"], "ready")

    def test_property_dependencies_survive_interleaving(self):
        result = compile_work([change("required", True), add(), change("requiredMessage", "请填写")])
        self.assertEqual(result["status"], "ready", result)
        self.assertEqual(result["actions"][2]["dependsOn"], [result["actions"][0]["actionId"]])

    def test_legacy_result_kind_mixed_request_is_negotiated_or_refused(self):
        result = compile_work([add(), change()], kind="form_actions")
        self.assertEqual(result["contractVersion"], "form_change_proposal.v1")
        ctx = context()
        ctx["capabilities"].pop("supportedProposalContracts")
        result = compile_work([add(), change()], ctx, "property_changes")
        self.assertEqual(result["status"], "unsupported")
        self.assertNotIn("actions", result)

    def test_copy_source_modified_in_same_batch_is_refused(self):
        ctx = context()
        ctx["nodePolicies"]["b"] = deepcopy(ctx["nodePolicies"]["a"])
        result = compile_work([change("placeholder", "new"), change("placeholder", operation="copy", node_id="b", source_node_id="a")], ctx)
        self.assertEqual(result["status"], "unsupported", result)
        self.assertNotIn("actions", result)

    def test_published_example_is_current_compiler_output(self):
        import json
        from pathlib import Path
        root = Path(__file__).resolve().parents[2] / "doc"
        ctx = json.loads((root / "form-change-context.example.json").read_text())
        ir = json.loads((root / "form-change-ir.example.json").read_text())
        expected = json.loads((root / "form-change-proposal.example.json").read_text())
        self.assertEqual(proposal.compile_form_proposal(ir, ctx)["output"]["form_proposal"], expected)

    def test_structural_field_ir_overlap_rejected(self):
        field = {"capability": "form.field.define", "slots": {"client_ref": "note", "component_name": "Input", "label": "备注", "name": "note_new"}}
        result = compile_work([field, remove()])
        self.assertEqual(result["status"], "unsupported")
        self.assertNotIn("actions", result)
