"""Saved canvas additions and incremental action drafts."""

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from test_form_field_list import apply_field_actions, assert_action_draft, assert_non_executable, blank_context
from form_generation import compile_form_proposal


SCHEMA = json.loads((Path(__file__).parent / "fixtures" / "student-form-data.json").read_text())
NEW_FIELDS = [
    {"client_ref": "guardian", "component_name": "Input", "label": "监护人", "name": "guardian"},
    {"client_ref": "guardian-phone", "component_name": "Input", "label": "监护人电话", "name": "guardian_phone"},
]


def saved_context():
    context = blank_context()
    context.pop("schemaVersion")
    context["currentSchema"] = deepcopy(SCHEMA)
    context["canvas"] = {"layoutMode": "flow", "isBlank": False}
    context["target"] = {"schemaId": "student", "revision": "saved-rev-1"}
    return context


def compile_additions(context=None, target=None, fields=None, **slot_overrides):
    slots = {"result_kind": "form_fields", "mode": "append", "summary": "新增监护人字段"}
    if target is not None:
        slots["target"] = target
    slots.update(slot_overrides)
    items = [{"capability": "proposal.begin", "slots": slots}]
    items.extend({"capability": "form.field.define", "slots": field} for field in (NEW_FIELDS if fields is None else fields))
    return compile_form_proposal({"plan_items": items}, SimpleNamespace(context=context or saved_context()))["output"]["form_proposal"]


class ExistingCanvasTests(unittest.TestCase):
    def test_saved_student_schema_appends_without_recreating_existing_fields(self):
        context = saved_context()
        original = deepcopy(context)
        result = compile_additions(context)
        self.assertEqual(context, original)
        self.assertEqual(result["schemaVersion"], "1.1.0")
        assert_action_draft(self, result)
        self.assertEqual(result["mode"], "append")
        self.assertEqual(result["target"]["baseRevision"], "saved-rev-1")
        actions = result["actions"]
        self.assertEqual(len(actions), 2)
        self.assertEqual([action["action"] for action in actions], ["form.add_component", "form.add_component"])
        self.assertEqual([action["payload"]["target"]["index"] for action in actions], [7, 8])
        fields = apply_field_actions(context["currentSchema"]["fields"], actions)
        self.assertEqual(len(fields), 9)
        self.assertEqual(fields[:7], SCHEMA["fields"])
        for field, definition in zip(fields[7:], NEW_FIELDS):
            self.assertNotIn("id", field)
            self.assertEqual(field["clientRef"], definition["client_ref"])
            self.assertEqual(field["componentName"], definition["component_name"])
            self.assertEqual(field["props"]["label"], definition["label"])
            self.assertEqual(field["props"]["name"], definition["name"])

    def test_name_only_addition_preserves_existing_components_outside_creation_catalog(self):
        for result_kind in ("form_fields", "form_changes"):
            for metadata in (None, {"supported": False}):
                with self.subTest(result_kind=result_kind, metadata=metadata):
                    context = saved_context()
                    context["capabilities"] = deepcopy(context["capabilities"])
                    context["currentSchema"]["fields"] = [{
                        "id": "existing-department", "componentName": "DepartmentSelect",
                        "props": {"label": "部门选择", "name": "department", "multiple": True},
                    }]
                    if metadata is not None:
                        context["capabilities"]["components"]["DepartmentSelect"] = metadata
                    original = deepcopy(context)
                    result = compile_additions(context, fields=[{
                        "client_ref": "student-name", "component_name": "Input",
                        "label": "姓名", "name": "student_name",
                    }], result_kind=result_kind)
                    self.assertEqual(result["status"], "ready", result)
                    assert_action_draft(self, result)
                    self.assertEqual(context, original)
                    self.assertEqual(len(result["actions"]), 1)
                    payload = result["actions"][0]["payload"]
                    self.assertEqual(payload["componentName"], "Input")
                    self.assertEqual(payload["props"]["label"], "姓名")
                    self.assertEqual(payload["target"], {"kind": "root", "index": 1})
                    fields = apply_field_actions(context["currentSchema"]["fields"], result["actions"])
                    self.assertEqual(fields[:1], original["currentSchema"]["fields"])
                    self.assertEqual(fields[1]["props"]["name"], "student_name")

    def test_preserving_an_existing_department_does_not_authorize_adding_one(self):
        context = saved_context()
        context["currentSchema"]["fields"] = [{
            "id": "existing-department", "componentName": "DepartmentSelect",
            "props": {"label": "部门选择", "name": "department"},
        }]
        result = compile_additions(context, fields=[{
            "client_ref": "new-department", "component_name": "DepartmentSelect",
            "label": "新部门", "name": "new_department",
        }])
        self.assertEqual(result["status"], "unsupported", result)
        self.assertIn("首期不支持组件: DepartmentSelect", result["summary"])
        assert_non_executable(self, result)

    def test_preserved_nodes_still_require_valid_structure_and_unique_identity(self):
        valid = {"id": "existing-department", "componentName": "DepartmentSelect", "props": {"name": "department"}}
        for fields, message in (
            ([{**valid, "id": ""}], "节点 ID"),
            ([valid, deepcopy(valid)], "节点 ID"),
            ([{**valid, "componentName": ""}], "componentName"),
            ([{**valid, "children": [valid]}], "单层 Flow"),
            ([None], "单层 Flow"),
        ):
            with self.subTest(fields=fields), self.assertRaisesRegex(ValueError, message):
                context = saved_context()
                context["currentSchema"]["fields"] = fields
                compile_additions(context)

    def test_matching_by_label_name_id_and_selection_keeps_batch_order(self):
        anchor = SCHEMA["fields"][1]
        for selector in (
            {"anchorLabel": "学号"}, {"anchorName": "student_no"},
            {"anchorNodeId": anchor["id"]}, {"useSelection": True},
        ):
            with self.subTest(selector=selector):
                context = saved_context()
                context["selection"] = {"nodeId": anchor["id"]}
                result = compile_additions(context, {"kind": "relative", "position": "after", **selector})
                assert_action_draft(self, result)
                actions = result["actions"]
                self.assertEqual([action["payload"]["target"]["index"] for action in actions], [2, 3])
                fields = apply_field_actions(context["currentSchema"]["fields"], actions)
                self.assertEqual([field["props"]["label"] for field in fields[:5]], ["姓名", "学号", "监护人", "监护人电话", "性别"])
                self.assertEqual(fields[:2] + fields[4:], SCHEMA["fields"])

    def test_before_and_explicit_root_positions(self):
        for target in (
            {"kind": "relative", "anchorLabel": "姓名", "position": "before"},
            {"kind": "root", "index": 0},
        ):
            with self.subTest(target=target):
                result = compile_additions(target=target)
                self.assertEqual([action["payload"]["target"]["index"] for action in result["actions"]], [0, 1])
                fields = apply_field_actions(SCHEMA["fields"], result["actions"])
                self.assertEqual(fields[0]["props"]["name"], "guardian")
                self.assertEqual(fields[2:], SCHEMA["fields"])

    def test_default_inserts_after_last_field_before_trailing_non_field(self):
        context = saved_context()
        context["currentSchema"]["fields"].append({"id": "footer", "componentName": "Divider", "componentCategory": "layout", "props": {}})
        context["capabilities"]["components"] = {**context["capabilities"]["components"], "Divider": {}}
        result = compile_additions(context)
        fields = apply_field_actions(context["currentSchema"]["fields"], result["actions"])
        self.assertEqual(fields[-1], context["currentSchema"]["fields"][-1])
        self.assertEqual(fields[:7], SCHEMA["fields"])
        self.assertEqual([action["payload"]["target"]["index"] for action in result["actions"]], [7, 8])

    def test_missing_ambiguous_or_conflicting_anchor_returns_clarification(self):
        for selector in (
            {"anchorLabel": "不存在"}, {"anchorLabel": "重复"},
            {"useSelection": True}, {},
            {"anchorNodeId": SCHEMA["fields"][0]["id"], "anchorName": "student_no"},
        ):
            with self.subTest(selector=selector):
                context = saved_context()
                for field in context["currentSchema"]["fields"][:2]:
                    field["props"]["label"] = "重复"
                result = compile_additions(context, {"kind": "relative", "position": "after", **selector})
                self.assertEqual(result["status"], "needs_clarification")
                self.assertEqual(result["diagnostics"][0]["code"], "ANCHOR_FIELD_REQUIRED")
                assert_non_executable(self, result)

    def test_existing_names_and_refs_cannot_be_reused(self):
        context = saved_context()
        context["currentSchema"]["fields"][0]["clientRef"] = "existing-ref"
        for field, message in (
            ({**NEW_FIELDS[0], "name": "student_name"}, "name 重复"),
            ({**NEW_FIELDS[0], "client_ref": "existing-ref"}, "重复 clientRef"),
        ):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, message):
                compile_additions(context, fields=[field])

    def test_field_limit_includes_saved_fields(self):
        context = saved_context()
        context["fieldNameRules"] = {"maxFields": 8}
        with self.assertRaisesRegex(ValueError, "字段数量"):
            compile_additions(context)

    def test_nonempty_schema_cannot_be_replaced_even_with_stale_blank_flag(self):
        context = saved_context()
        context["canvas"]["isBlank"] = True
        with self.assertRaisesRegex(ValueError, "空白"):
            compile_additions(context, mode="replace_empty_form")

    def test_schema_version_metadata_does_not_gate_generation_but_invalid_positions_are_rejected(self):
        context = saved_context()
        context["schemaVersion"] = "custom-schema"
        result = compile_additions(context)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["schemaVersion"], "custom-schema")
        for target in ({"kind": "root", "index": 99}, {"kind": "root", "index": True}, {"kind": "relative", "anchorLabel": "学号"}):
            with self.subTest(target=target), self.assertRaises(ValueError):
                compile_additions(target=target)

    def test_edit_actions_preserve_order_identity_and_untouched_configuration(self):
        context = saved_context()
        original = deepcopy(context)
        items = [
            {"capability": "proposal.begin", "slots": {"result_kind": "form_actions", "summary": "调整学生字段"}},
            {"capability": "form.update_component", "slots": {"payload": {"fieldId": SCHEMA["fields"][1]["id"], "changes": {"label": "学生编号"}}}},
            {"capability": "form.update_component_options", "slots": {"payload": {"fieldId": SCHEMA["fields"][2]["id"], "options": [{"label": "保密", "value": "private"}]}}},
            {"capability": "form.remove_component", "slots": {"payload": {"fieldId": SCHEMA["fields"][5]["id"]}}},
            {"capability": "form.move_component", "slots": {"payload": {"fieldId": SCHEMA["fields"][6]["id"], "target": {"kind": "relative", "anchorNodeId": SCHEMA["fields"][0]["id"], "position": "after"}}}},
        ]
        result = compile_form_proposal({"plan_items": items}, SimpleNamespace(context=context))["output"]["form_proposal"]
        self.assertEqual(context, original)
        assert_action_draft(self, result)
        actions = result["actions"]
        self.assertEqual([action["action"] for action in actions], ["form.update_component", "form.update_component_options", "form.remove_component", "form.move_component"])
        self.assertEqual([action["payload"] for action in actions], [item["slots"]["payload"] for item in items[1:]])
        fields = apply_field_actions(context["currentSchema"]["fields"], actions)
        self.assertEqual([field["props"]["label"] for field in fields], ["姓名", "备注", "学生编号", "性别", "出生日期", "班级"])
        self.assertEqual([field["id"] for field in fields], [SCHEMA["fields"][index]["id"] for index in (0, 6, 1, 2, 3, 4)])
        self.assertEqual(fields[2]["fieldTitle"], "学生编号")
        self.assertEqual(fields[3]["props"]["options"], [{"label": "保密", "value": "private"}])
        for index, original_index in enumerate((0, 6, 1, 2, 3, 4)):
            expected = deepcopy(SCHEMA["fields"][original_index])
            if original_index == 1:
                expected["props"]["label"] = expected["fieldTitle"] = "学生编号"
            elif original_index == 2:
                expected["props"]["options"] = [{"label": "保密", "value": "private"}]
            self.assertEqual(fields[index], expected)


if __name__ == "__main__":
    unittest.main()
