"""Public output contract for editable, single-source action drafts."""

from copy import deepcopy
import json
import unittest

from compiler_package import load_compiler_module
from test_form_field_list import compile_fields
from test_form_proposal import compile_items
from test_properties import change, host, run

drafts = load_compiler_module("drafts")


class ActionDraftTests(unittest.TestCase):
    def assert_draft(self, proposal, kind):
        self.assertEqual(set(proposal["presentation"]), {"kind", "title"})
        self.assertEqual(proposal["presentation"]["kind"], kind)
        for removed in ("result", "validation", "fields", "changes", "edits"):
            self.assertNotIn(removed, proposal)
        for action in proposal["actions"]:
            self.assertIn("actionId", action)
            self.assertIn("payload", action)
            self.assertEqual(action["display"]["selectedByDefault"], True)
            self.assertIsInstance(action["dependsOn"], list)

    def test_field_configuration_is_serialized_once(self):
        proposal = compile_fields([{
            "client_ref": "employee", "component_name": "Input", "name": "employee",
            "label": "unique-business-label", "placeholder": "unique-placeholder",
        }])
        self.assert_draft(proposal, "shared.table-field-confirm")
        serialized = json.dumps(proposal)
        self.assertEqual(serialized.count("unique-business-label"), 1)
        self.assertEqual(serialized.count("unique-placeholder"), 1)
        self.assertEqual(proposal["actionVersion"], "1.0")
        self.assertEqual(proposal["mode"], "replace_empty_form")

    def test_property_value_before_and_target_keep_distinct_semantics(self):
        context = host()
        context["target"].update(formId="form-1", appId="app-1", layoutId="layout-1")
        original = deepcopy(context)
        proposal = run([change(value="unique-updated-value")], context)
        self.assert_draft(proposal, "shared.component-property-checklist")
        self.assertEqual(json.dumps(proposal).count("unique-updated-value"), 1)
        action = proposal["actions"][0]
        self.assertEqual(action["preconditions"]["before"], {"exists": True, "value": "旧"})
        self.assertEqual(action["payload"]["value"], "unique-updated-value")
        self.assertNotIn("after", action)
        self.assertEqual(proposal["target"], {"schemaId": "form", "formId": "form-1", "appId": "app-1", "layoutId": "layout-1", "baseRevision": "r1"})
        action["preconditions"]["before"]["value"] = "mutated"
        self.assertEqual(context, original)

    def test_dependencies_use_action_ids_without_change_id_mappings(self):
        proposal = run([change("required", True), change("requiredMessage", "请填写")])
        actions = proposal["actions"]
        self.assertEqual(actions[1]["dependsOn"], [actions[0]["actionId"]])
        self.assertNotIn("changeId", json.dumps(proposal))
        self.assertNotIn("actionIds", json.dumps(proposal))

    def test_clear_unset_reset_remain_semantic_operations(self):
        context = host()
        context["currentSchema"]["fields"][0]["props"].update(textAlign="left", size="large")
        for operation, prop in (("clear", "placeholder"), ("unset", "titleAlign"), ("reset", "size")):
            with self.subTest(operation=operation):
                result = run([change(prop, operation=operation)], context)
                self.assertEqual(result["status"], "ready", result)
                payload = result["actions"][0]["payload"]
                self.assertEqual(payload["operation"], operation)
                self.assertNotIn("value", payload)
                self.assertIn("before", result["actions"][0]["preconditions"])

    def test_use_selection_is_bound_to_a_real_node_before_delivery(self):
        proposal = compile_items([
            {"capability": "proposal.begin", "slots": {"summary": "修改", "result_kind": "form_actions"}},
            {"capability": "form.update_component", "slots": {"payload": {"useSelection": True, "changes": {"label": "标题"}}}},
        ])
        self.assert_draft(proposal, "shared.table-field-confirm")
        self.assertEqual(proposal["actions"][0]["payload"], {"nodeId": "reason", "changes": {"label": "标题"}})

    def test_new_reference_dependencies_are_explicit(self):
        proposal = compile_items([
            {"capability": "proposal.begin", "slots": {"summary": "新增校验", "result_kind": "form_actions"}},
            {"capability": "form.add_component", "slots": {"payload": {"clientRef": "note", "componentName": "Input", "props": {"label": "备注"}, "target": {"kind": "root"}}}},
            {"capability": "form.set_validation", "slots": {"payload": {"fieldRef": "note", "validatorName": "required"}}},
        ])
        self.assertEqual(proposal["actions"][1]["dependsOn"], [proposal["actions"][0]["actionId"]])

    def test_duplicate_action_ids_and_reused_client_refs_are_rejected(self):
        begin = {"capability": "proposal.begin", "slots": {"summary": "修改", "result_kind": "form_actions"}}
        update = {"capability": "form.update_component", "slots": {"action_id": "same", "payload": {"nodeId": "reason", "changes": {"label": "标题"}}}}
        with self.assertRaisesRegex(ValueError, "actionId"):
            compile_items([begin, update, deepcopy(update)])
        with self.assertRaisesRegex(ValueError, "clientRef"):
            compile_items([begin, {"capability": "form.add_component", "slots": {"payload": {
                "clientRef": "reason", "componentName": "Input", "props": {"label": "备注"}, "target": {"kind": "root"},
            }}}])

    def test_sequence_validation_does_not_stop_after_conversion(self):
        begin = {"capability": "proposal.begin", "slots": {"summary": "调整", "result_kind": "form_actions"}}
        convert = {"capability": "form.convert_component", "slots": {"payload": {"nodeId": "draft-choice", "componentName": "CheckboxGroup"}}}
        remove = {"capability": "form.remove_component", "slots": {"payload": {"nodeId": "reason"}}}
        with self.assertRaisesRegex(ValueError, "已删除"):
            compile_items([begin, convert, remove, deepcopy(remove)])

    def test_nonready_and_queries_are_not_executable_drafts(self):
        for state in ("unsupported", "no_change", "needs_clarification"):
            slots = {"summary": "不执行", "code": "TEST", "question": "请确认"}
            result = compile_items([{"capability": "proposal." + state, "slots": slots}])
            for key in ("actions", "mode", "actionVersion", "presentation"):
                self.assertNotIn(key, result)
        query = run([{"capability": "form.property.query", "slots": {"node_id": "a", "property": "placeholder"}}], kind="property_query")
        self.assertEqual(query["contractVersion"], "form_property_query.v1")
        self.assertNotIn("actions", query)
        self.assertTrue(query["presentation"]["readOnly"])

    def test_draft_graph_rejects_dangling_and_cyclic_dependencies(self):
        for actions in (
            [{"actionId": "a", "dependsOn": ["missing"]}],
            [{"actionId": "a", "dependsOn": ["b"]}, {"actionId": "b", "dependsOn": ["a"]}],
        ):
            with self.assertRaises(ValueError):
                drafts.set_action_draft({}, actions, mode="append", action_version="1.0", kind="test", title="test")
