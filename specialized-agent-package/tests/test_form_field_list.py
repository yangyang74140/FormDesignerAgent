from copy import deepcopy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from form_generation import FLOW_COMPONENTS, compile_form_proposal


COMPONENT_CATALOG = {
    component: {
        "componentLabel": component,
        "writableProps": ["label", "name", "required", "placeholder", "options"],
    }
    for component in FLOW_COMPONENTS
}


def blank_context():
    return {
        "requestId": "req-onboarding",
        "schemaVersion": "1.0.0",
        "target": {"schemaId": "employee-onboarding", "formId": "form-new", "revision": "rev-0"},
        "currentSchema": {"schemaVersion": "1.0.0", "fields": []},
        "selection": {},
        "canvas": {"layoutMode": "flow", "isBlank": True},
        "capabilities": {
            "supportedProposalContracts": ["form_change_proposal.v1"],
            "supportedPresentationKinds": ["shared.form-create-confirm", "shared.form-change-confirm"],
            "supportedActionVersions": ["1.0", "form_change_actions.v1"],
            "components": COMPONENT_CATALOG,
            "fieldNameRules": {"pattern": "^[a-z][a-z0-9_]*$", "maxLength": 50, "reserved": ["id"]},
            "optionRules": {"maxOptions": 20},
        },
        "supportedActionVersions": {
            "form.add_component": ["1.0"],
            "form.update_component": ["1.0"],
            "form.update_component_options": ["1.0"],
            "form.move_component": ["1.0"],
            "form.remove_component": ["1.0"],
            "form.convert_component": ["1.0"],
            "form.update_field_rules": ["1.0"],
            "form.update_form_rules": ["1.0"],
            "form.upsert_formula": ["1.0"],
        },
    }


def compile_fields(fields, context=None):
    items = [{
        "capability": "proposal.begin",
        "slots": {
            "summary": "生成员工入职登记表",
            "result_kind": "form_fields",
            "mode": "replace_empty_form",
            "scope": "form",
        },
    }]
    items.extend({"capability": "form.field.define", "slots": field} for field in fields)
    compiled = compile_form_proposal({"plan_items": items}, SimpleNamespace(context=context or blank_context()))
    return compiled["output"]["form_proposal"]


def assert_action_draft(test, proposal, kind=None, property_actions=False):
    kind = kind or ("shared.form-create-confirm" if proposal.get("mode") == "replace_empty_form" else "shared.form-change-confirm")
    test.assertNotIn("result", proposal)
    test.assertNotIn("validation", proposal)
    test.assertEqual(set(proposal["presentation"]), {"kind", "title"})
    test.assertEqual(proposal["presentation"]["kind"], kind)
    test.assertIsInstance(proposal["presentation"]["title"], str)
    test.assertTrue(proposal["actionVersion"])
    test.assertIn(proposal["mode"], {"append", "replace_empty_form"})
    actions = proposal["actions"]
    test.assertTrue(actions)
    test.assertIsInstance(actions, list)
    ids = [action["actionId"] for action in actions]
    test.assertTrue(all(isinstance(action_id, str) and action_id.strip() for action_id in ids))
    test.assertEqual(len(ids), len(set(ids)))
    for action in actions:
        expected = {"actionId", "action", "payload", "dependsOn", "display"}
        if property_actions:
            expected.add("preconditions")
            test.assertEqual(set(action["preconditions"]), {"before"})
        test.assertEqual(set(action), expected)
        test.assertIsInstance(action["payload"], dict)
        test.assertEqual(set(action["display"]), {"selectedByDefault", "effects"} if property_actions else {"selectedByDefault"})
        test.assertIsInstance(action["display"]["selectedByDefault"], bool)
        if property_actions:
            test.assertIsInstance(action["display"]["effects"], list)
            test.assertTrue(all(isinstance(effect, str) for effect in action["display"]["effects"]))
        test.assertIsInstance(action["dependsOn"], list)
        test.assertTrue(set(action["dependsOn"]) <= set(ids) - {action["actionId"]})


def assert_non_executable(test, proposal):
    for key in ("result", "validation", "actions", "presentation", "mode", "actionVersion"):
        test.assertNotIn(key, proposal)


def apply_field_actions(fields, actions):
    """Apply lifecycle drafts to a private host copy without a preview response."""
    fields = deepcopy(fields)

    def insertion_index(target):
        if target["kind"] == "root":
            return target.get("index", len(fields))
        anchor = next(index for index, field in enumerate(fields)
                      if target["anchorNodeId"] in {field.get("id"), field.get("clientRef")})
        return anchor + (target["position"] == "after")

    for action in actions:
        payload = action["payload"]
        kind = action["action"]
        if kind == "form.add_component":
            field = {key: deepcopy(payload[key]) for key in ("clientRef", "componentName", "props") if key in payload}
            fields.insert(insertion_index(payload["target"]), field)
            continue
        node_id = payload.get("nodeId") or payload.get("fieldId")
        index = next(index for index, field in enumerate(fields)
                     if node_id in {field.get("id"), field.get("clientRef")})
        field = fields[index]
        if kind == "form.update_component":
            field.setdefault("props", {}).update(deepcopy(payload["changes"]))
            if "label" in payload["changes"] and "fieldTitle" in field:
                field["fieldTitle"] = payload["changes"]["label"]
        elif kind == "form.update_component_options":
            field.setdefault("props", {})["options"] = deepcopy(payload["options"])
        elif kind == "form.remove_component":
            fields.pop(index)
        elif kind == "form.move_component":
            fields.pop(index)
            target = payload["target"]
            destination = index if target.get("anchorNodeId") == node_id else insertion_index(target)
            fields.insert(destination, field)
        elif kind == "form.convert_component":
            field["componentName"] = payload.get("componentName") or payload["targetComponentName"]
        else:
            raise AssertionError(f"Unsupported test action: {kind}")
    return fields


class FormFieldListTests(unittest.TestCase):
    def test_complete_field_list_and_actions_share_one_source(self):
        fields = [
            {
                "client_ref": f"field-{index}",
                "component_name": component,
                "label": f"字段 {index}",
                "name": f"field_{index}",
                "required": index == 1,
                "placeholder": "请输入" if component in {"Input", "Input.TextArea"} else "",
                "options": [
                    {"label": "选项 A", "value": "a"},
                    {"label": "选项 B", "value": "b"},
                ] if component in {"SelectSingle", "SelectMulti", "CheckboxGroup"} else [],
            }
            for index, component in enumerate(FLOW_COMPONENTS, start=1)
        ]

        result = compile_fields(fields)

        self.assertEqual(result["contractVersion"], "form_agent_proposal.v1")
        assert_action_draft(self, result)
        self.assertEqual(result["schemaVersion"], "1.0.0")
        self.assertEqual(result["requestId"], "req-onboarding")
        self.assertEqual(result["mode"], "replace_empty_form")
        self.assertEqual(len(result["actions"]), 9)
        for index, (definition, action) in enumerate(zip(fields, result["actions"])):
            payload = action["payload"]
            self.assertEqual(action["action"], "form.add_component")
            self.assertNotIn("id", payload)
            self.assertEqual(payload["clientRef"], definition["client_ref"])
            self.assertEqual(payload["componentName"], definition["component_name"])
            expected_props = {key: definition[key] for key in ("label", "name", "required")}
            if definition["placeholder"]:
                expected_props["placeholder"] = definition["placeholder"]
            if definition["options"]:
                expected_props["options"] = definition["options"]
            self.assertEqual(payload["props"], expected_props)
            self.assertEqual(payload["target"], {"kind": "root", "index": index})
        applied = apply_field_actions([], result["actions"])
        self.assertEqual([field["clientRef"] for field in applied], [field["client_ref"] for field in fields])

    def test_full_generation_requires_blank_flow_schema_1_0(self):
        field = {"client_ref": "name", "component_name": "Input", "label": "姓名", "name": "name"}
        for mutation, message in (
            ({"canvas": {"layoutMode": "grid", "isBlank": True}}, "flow"),
            ({"canvas": {"layoutMode": "flow", "isBlank": False}}, "空白"),
        ):
            context = blank_context()
            context.update(mutation)
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, message):
                compile_fields([field], context)

    def test_schema_version_is_metadata_not_a_generation_gate(self):
        field = {"client_ref": "name", "component_name": "Input", "label": "姓名", "name": "name"}
        for version in ("2.0.0", "custom-schema", "", None):
            context = blank_context()
            context["schemaVersion"] = version
            context["currentSchema"]["schemaVersion"] = version
            with self.subTest(version=version):
                result = compile_fields([field], context)
                self.assertEqual(result["status"], "ready")
                assert_action_draft(self, result)
                self.assertEqual(len(result["actions"]), 1)
                if version:
                    self.assertEqual(result["schemaVersion"], version)

    def test_field_name_client_ref_and_option_rules_are_enforced(self):
        base = {"client_ref": "choice", "component_name": "SelectSingle", "label": "类型", "name": "type"}
        invalid_cases = (
            ({**base, "client_ref": "bad ref", "options": [{"label": "A", "value": "a"}]}, "clientRef"),
            ({**base, "name": "Type", "options": [{"label": "A", "value": "a"}]}, "不符合规则"),
            ({**base, "name": "id", "options": [{"label": "A", "value": "a"}]}, "保留名"),
            ({**base, "options": []}, "至少一个 option"),
            ({**base, "options": [{"label": "A", "value": "a"}, {"label": "B", "value": "a"}]}, "value 重复"),
        )
        for field, message in invalid_cases:
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, message):
                compile_fields([field])

    def test_duplicate_names_and_client_refs_are_rejected(self):
        first = {"client_ref": "field-one", "component_name": "Input", "label": "姓名", "name": "name"}
        with self.assertRaisesRegex(ValueError, "重复 clientRef"):
            compile_fields([first, {**first, "name": "other"}])
        with self.assertRaisesRegex(ValueError, "字段 name 重复"):
            compile_fields([first, {**first, "client_ref": "field-two"}])

    def test_client_refs_accept_snake_case_and_kebab_case_without_rewriting(self):
        refs = ["student_no", "student-name", "student_home-address2"]
        fields = [{
            "client_ref": ref, "component_name": "Input", "label": f"字段 {index}", "name": f"field_{index}",
        } for index, ref in enumerate(refs)]
        result = compile_fields(fields)
        assert_action_draft(self, result)
        self.assertEqual([action["payload"]["clientRef"] for action in result["actions"]], refs)
        self.assertEqual([field["clientRef"] for field in apply_field_actions([], result["actions"])], refs)
        with self.assertRaisesRegex(ValueError, "重复 clientRef"):
            compile_fields([fields[0], {**fields[0], "name": "another_name"}])
        for ref in ("", "Student_no", "1student", "student no", "student.no", "学生", "student/no"):
            with self.subTest(ref=ref), self.assertRaisesRegex(ValueError, "clientRef"):
                compile_fields([{**fields[0], "client_ref": ref}])

    def test_non_option_component_rejects_options(self):
        with self.assertRaisesRegex(ValueError, "不支持 options"):
            compile_fields([{
                "client_ref": "name", "component_name": "Input", "label": "姓名", "name": "name",
                "options": [{"label": "A", "value": "a"}],
            }])


if __name__ == "__main__":
    unittest.main()
