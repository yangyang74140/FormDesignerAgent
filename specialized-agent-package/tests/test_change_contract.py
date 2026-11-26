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
    value["supportedActionVersions"] = ["1.0", "form_change_actions.v1"]
    value["currentSchema"]["fields"].append({"id": "b", "componentName": "Input", "props": {"label": "待删", "name": "old"}})
    return value


def compile_work(work, ctx=None, kind="form_changes", mode="append", **placement):
    items = [{"capability": "proposal.begin", "slots": {"summary": "新增备注、修改提示并删除旧字段", "title": "表单变更", "result_kind": kind, "mode": mode, **placement}}, *work]
    return proposal.compile_form_proposal({"plan_items": items}, ctx or context())["output"]["form_proposal"]


def add():
    return {"capability": "form.add_component", "slots": {"payload": {"clientRef": "new-note", "componentName": "Input", "props": {"label": "备注", "name": "new_note"}, "target": {"kind": "root", "index": 2}}}}


def remove(node="b"):
    return {"capability": "form.remove_component", "slots": {"payload": {"nodeId": node}}}


def define_field(name, label):
    return {"capability": "form.field.define", "slots": {"client_ref": name, "component_name": "Input", "label": label, "name": name}}


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

    def test_missing_negotiation_rejects_mixed_and_pure_paths(self):
        for key in ("supportedProposalContracts", "supportedPresentationKinds"):
            ctx = context()
            ctx["capabilities"].pop(key)
            self.assertEqual(compile_work([add(), change()], ctx)["status"], "unsupported")
            legacy = compile_work([remove()], ctx, "form_actions")
            self.assertEqual(legacy["status"], "unsupported")
            self.assertNotIn("actions", legacy)
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

    def test_published_examples_are_current_compiler_output(self):
        import json
        from pathlib import Path
        root = Path(__file__).resolve().parents[2] / "doc"
        for prefix in ("form-change", "form-create", "property"):
            with self.subTest(prefix=prefix):
                ctx = json.loads((root / (prefix + "-context.example.json")).read_text())
                ir = json.loads((root / (prefix + "-ir.example.json")).read_text())
                expected = json.loads((root / (prefix + "-proposal.example.json")).read_text())
                self.assertEqual(proposal.compile_form_proposal(ir, ctx)["output"]["form_proposal"], expected)

    def test_old_cards_and_property_write_versions_never_authorize_mutations(self):
        for kinds in (["shared.table-field-confirm"], ["shared.component-property-checklist"], []):
            ctx = context()
            ctx["capabilities"]["supportedPresentationKinds"] = kinds
            for work, kind in (([remove()], "form_actions"), ([change()], "property_changes")):
                result = compile_work(work, ctx, kind)
                self.assertEqual(result["status"], "unsupported", result)
                self.assertNotIn("actions", result)
                self.assertNotIn("presentation", result)
        ctx = context()
        ctx["supportedActionVersions"] = {"form.apply_property_change": ["form_property_actions.v1"]}
        result = compile_work([change()], ctx, "property_changes")
        self.assertEqual(result["status"], "unsupported", result)
        self.assertNotIn("actions", result)

    def test_create_nested_version_authority_and_no_old_kind_fallback(self):
        ctx = context()
        ctx["currentSchema"]["fields"] = []
        field = {"capability": "form.field.define", "slots": {"client_ref": "note", "component_name": "Input", "label": "备注", "name": "note_new"}}
        for declaration in (None, [], ["form_change_actions.v1"], ["form_actions.v2"]):
            ctx["capabilities"]["supportedActionVersions"] = declaration
            result = compile_work([field], ctx, "form_fields", "replace_empty_form")
            self.assertEqual(result["status"], "unsupported", result)
            self.assertNotIn("presentation", result)
        ctx["capabilities"]["supportedActionVersions"] = ["1.0"]
        self.assertEqual(compile_work([field], ctx, "form_fields", "replace_empty_form")["status"], "ready")
        ctx["capabilities"]["supportedPresentationKinds"] = ["shared.table-field-confirm"]
        result = compile_work([field], ctx, "form_fields", "replace_empty_form")
        self.assertEqual(result["status"], "unsupported", result)
        self.assertNotIn("actions", result)

    def test_query_and_undo_do_not_require_change_negotiation(self):
        from test_properties import run
        ctx = context()
        for key in ("supportedProposalContracts", "supportedPresentationKinds", "supportedActionVersions"):
            ctx["capabilities"].pop(key, None)
        ctx["supportedActionVersions"] = {"form.undo_property_transaction": ["form_property_actions.v1"]}
        ctx["history"] = {"canUndo": True, "transactionId": "tx1", "revision": "r1"}
        query = run([{"capability": "form.property.query", "slots": {"node_id": "a", "property": "placeholder"}}], ctx, "property_query")
        self.assertEqual(query["status"], "ready", query)
        self.assertEqual(query["presentation"]["kind"], "component_property_query")
        undo = run([{"capability": "form.property.undo", "slots": {"transaction_id": "tx1"}}], ctx, "property_undo")
        self.assertEqual(undo["status"], "ready", undo)
        self.assertEqual(undo["presentation"]["kind"], "component_property_undo")

    def test_student_form_changes_compile_as_one_ordered_proposal(self):
        ctx = context()
        ctx["currentSchema"]["fields"][0]["props"].update(label="姓名", name="student_name")
        ctx["currentSchema"]["fields"][1]["props"].update(label="性别", name="gender")
        ctx["currentSchema"]["fields"].append({"id": "age", "componentName": "Input", "props": {"label": "年龄", "name": "age"}})
        ctx["nodePolicies"]["b"] = deepcopy(ctx["nodePolicies"]["a"])
        before = deepcopy(ctx)
        interest = define_field("interest", "兴趣")
        result = compile_work([change("label", "学生姓名"), change("required", True, node_id="b"), remove("age"), interest], ctx)
        self.assertEqual(result["status"], "ready", result)
        self.assertEqual(result["presentation"]["kind"], "shared.form-change-confirm")
        actions = result["actions"]
        self.assertEqual([a["action"] for a in actions], ["form.apply_property_change", "form.apply_property_change", "form.remove_component", "form.add_component"])
        self.assertEqual([a["payload"].get("value") for a in actions[:2]], ["学生姓名", True])
        self.assertEqual(actions[2]["payload"]["nodeId"], "age")
        self.assertEqual(actions[3]["payload"]["props"]["label"], "兴趣")
        self.assertEqual(actions[3]["payload"]["target"], {"kind": "root", "index": 2})
        self.assertEqual(actions[3]["dependsOn"], [actions[2]["actionId"]])
        self.assertEqual(ctx, before)

    def test_default_append_with_interleaved_delete_keeps_trailing_non_field(self):
        ctx = context()
        ctx["currentSchema"]["fields"] += [
            {"id": "c", "componentName": "Input", "props": {"name": "keep"}},
            {"id": "trailing", "componentName": "Input", "componentCategory": "display", "props": {}},
        ]
        result = compile_work([define_field("first", "新增一"), remove(), define_field("second", "新增二")], ctx)
        self.assertEqual(result["status"], "ready", result)
        first, deletion, second = result["actions"]
        self.assertEqual([first["payload"]["target"]["index"], second["payload"]["target"]["index"]], [3, 3])
        self.assertEqual(first["dependsOn"], [])
        self.assertEqual(second["dependsOn"], [first["actionId"], deletion["actionId"]])

    def test_delete_then_default_append_at_field_limit(self):
        ctx = context()
        ctx["fieldNameRules"] = {"maxFields": 2}
        field = define_field("interest", "兴趣")
        result = compile_work([remove(), field], ctx)
        self.assertEqual(result["status"], "ready", result)
        self.assertEqual(result["actions"][1]["payload"]["target"]["index"], 1)
        with self.assertRaisesRegex(ValueError, "字段数量超过宿主限制"):
            compile_work([field, remove()], ctx)

    def test_unresolved_structural_field_ir_overlap_is_rejected(self):
        field = define_field("note_new", "备注")
        for work, slots in (([field, add()], {}), ([remove(), field], {"target": {"kind": "root", "index": 0}})):
            with self.subTest(work=work, slots=slots):
                result = compile_work(work, **slots)
                self.assertEqual(result["status"], "unsupported")
                self.assertEqual(result["diagnostics"][0]["code"], "CHANGE_POSITION_OVERLAP")
                self.assertNotIn("actions", result)
