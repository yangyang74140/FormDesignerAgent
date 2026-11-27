"""Mode defaults, catalog scopes and compiler bypass regressions."""
from copy import deepcopy
import unittest

from test_form_field_list import blank_context, compile_fields, assert_non_executable
from test_form_proposal import compile_items, host_context, proposal
from test_properties import host, run, change
from form_generation.model_context import model_host_context
from form_generation.modes import resolve_modes, CapabilityUnavailable
from form_generation.action_rules import validate_action


class ModeTests(unittest.TestCase):
    field = {"client_ref": "person", "component_name": "Input", "label": "姓名", "name": "person"}

    def refused(self, result, code=None):
        self.assertEqual(result["status"], "unsupported", result)
        assert_non_executable(self, result)
        if code:
            self.assertEqual(result["diagnostics"][0]["code"], code, result)

    def test_defaults_are_canonical_and_do_not_mutate_context(self):
        for value in (None, "", "  "):
            context = deepcopy(blank_context())
            context["canvas"].update(deviceMode=value, layoutMode=value)
            before = deepcopy(context)
            normalized = proposal.normalize_host_context(context)
            self.assertEqual(resolve_modes(normalized), ("pc", "flow"))
            self.assertEqual(compile_fields([self.field], context)["status"], "ready")
            self.assertEqual(context, before)
            property_context = host()
            property_context["canvas"] = {"deviceMode": value, "layoutMode": value}
            self.assertEqual(run([change("size", "large")], property_context)["status"], "ready")
        context = host()
        context.pop("canvas")
        self.assertEqual(run([change()], context)["status"], "ready")
        context = blank_context()
        context["canvas"] = {"isBlank": True, "device": "mobile"}
        self.assertEqual(proposal.normalize_host_context(context)["canvas"]["deviceMode"], "pc")
        self.assertNotIn("device", proposal.normalize_host_context(context)["canvas"])

    def test_invalid_values_and_schema_conflicts_are_refused(self):
        for key, code in (("deviceMode", "INVALID_DEVICE_MODE"), ("layoutMode", "INVALID_LAYOUT_MODE")):
            for value in (False, 0, [], {}, "unknown", "PC", " flow "):
                context = deepcopy(blank_context())
                context["canvas"][key] = value
                self.refused(compile_fields([self.field], context), code)
                property_context = host()
                property_context["canvas"][key] = value
                self.refused(run([change()], property_context), code)
        for canvas, schema in (("flow", "grid"), ("grid", "flow"), (None, "grid")):
            context = deepcopy(blank_context())
            context["canvas"]["layoutMode"] = canvas
            context["currentSchema"]["layoutMode"] = schema
            self.refused(compile_fields([self.field], context), "LAYOUT_MODE_CONFLICT")
        context["canvas"]["layoutMode"] = "flow"
        context["currentSchema"]["layoutMode"] = "invalid"
        self.refused(compile_fields([self.field], context), "INVALID_LAYOUT_MODE")

    def test_four_combinations_and_no_grid_inference(self):
        for device in ("pc", "mobile"):
            for layout in ("flow", "grid"):
                context = deepcopy(blank_context())
                context["canvas"].update(deviceMode=device, layoutMode=layout)
                result = compile_fields([self.field], context)
                self.assertEqual(result["status"], "ready" if layout == "flow" else "unsupported", result)
                property_context = host()
                property_context["canvas"] = {"deviceMode": device, "layoutMode": layout}
                for kind, item in (("property_changes", change()), ("property_query", {"capability": "form.property.query", "slots": {"node_id": "a", "property": "size"}})):
                    result = run([item], property_context, kind=kind)
                    self.assertEqual(result["status"], "ready" if (device, layout) == ("pc", "flow") else "unsupported", result)
        context = deepcopy(blank_context())
        context["currentSchema"]["grid"] = {"some": "metadata"}
        self.assertEqual(compile_fields([self.field], context)["status"], "ready")

    def test_component_create_and_property_scopes(self):
        for layer in ("root", "create", "property"):
            for key, value, code in (("devices", ["mobile"], "DEVICE_RESTRICTED"), ("layouts", ["grid"], "LAYOUT_RESTRICTED"), ("devices", [], "DEVICE_RESTRICTED"), ("devices", "pc", "DEVICE_RESTRICTED")):
                context = deepcopy(blank_context())
                metadata = context["capabilities"]["components"]["Input"]
                scoped = metadata if layer == "root" else metadata.setdefault("create", {"writableProps": ["label", "name", "required"]}) if layer == "create" else metadata.setdefault("properties", {}).setdefault("label", {})
                scoped[key] = value
                self.refused(compile_fields([self.field], context), code)
                candidates = proposal.proposal_capabilities(context)
                fields = next((c for c in candidates if c["capability"] == "form.field.define"), None)
                if layer != "property":
                    self.assertNotIn("Input", fields["slots_schema"]["properties"]["component_name"]["enum"] if fields else [])
        context = deepcopy(blank_context())
        context["capabilities"]["components"]["Input"]["create"] = {"writableProps": [], "devices": ["pc"]}
        self.refused(compile_fields([self.field], context), "MISSING_WRITABLE_PROPS")

    def test_raw_actions_and_edited_payloads_revalidate_scopes(self):
        for action, payload in (
            ("form.add_component", {"clientRef": "person", "componentName": "Input", "props": {"label": "姓名"}, "target": {"kind": "root"}}),
            ("form.update_component", {"fieldId": "reason", "changes": {"label": "姓名"}}),
            ("form.convert_component", {"fieldId": "draft-choice", "componentName": "Input"}),
        ):
            context = host_context()
            context.context["capabilities"]["components"] = {"Input": {"devices": ["mobile"], "writableProps": ["label"]}}
            items = [{"capability": "proposal.begin", "slots": {"result_kind": "form_actions"}}, {"capability": action, "slots": {"payload": payload}}]
            self.refused(compile_items(items, context), "DEVICE_RESTRICTED")
            with self.assertRaises(CapabilityUnavailable):
                validate_action(action, deepcopy(payload), proposal.normalize_host_context(context), set())
        context = host_context()
        context.context["canvas"]["layoutMode"] = "grid"
        with self.assertRaises(CapabilityUnavailable):
            validate_action("form.remove_component", {"nodeId": "reason"}, proposal.normalize_host_context(context), set())

    def test_query_and_copy_source_respect_property_scopes(self):
        context = host()
        context["capabilities"]["components"]["Input"]["properties"]["size"]["devices"] = ["mobile"]
        item = {"capability": "form.property.query", "slots": {"node_id": "a", "property": "size"}}
        self.refused(run([item], context, kind="property_query"), "DEVICE_RESTRICTED")
        self.refused(run([change("size", "large")], context), "DEVICE_RESTRICTED")
        context["currentSchema"]["fields"].append({"id": "b", "componentName": "Input", "props": {"size": "large"}})
        context["nodePolicies"]["b"] = deepcopy(context["nodePolicies"]["a"])
        self.refused(run([change("size", operation="copy", source_node_id="b")], context), "DEVICE_RESTRICTED")

    def test_mobile_creation_is_independent_of_pc_semantic_properties(self):
        context = deepcopy(blank_context())
        context["canvas"]["deviceMode"] = "mobile"
        metadata = context["capabilities"]["components"]["Input"]
        metadata.update(devices=["pc", "mobile"], layouts=["flow", "grid"])
        metadata["properties"] = {"label": {"devices": ["pc"], "layouts": ["flow"]}}
        metadata["create"] = {"devices": ["mobile"], "layouts": ["flow"], "writableProps": ["label", "name"]}
        result = compile_fields([self.field], context)
        self.assertEqual(result["status"], "ready", result)
        visible = model_host_context(context)["capabilities"]["components"]["Input"]
        self.assertEqual(visible["create"]["writableProps"], ["label", "name"])
        self.assertNotIn("properties", visible)
        metadata["create"]["devices"] = []
        self.refused(compile_fields([self.field], context), "DEVICE_RESTRICTED")

    def test_option_updates_and_undo_cannot_bypass_modes(self):
        context = host_context()
        context.context["capabilities"]["components"] = {"SelectSingle": {"writableProps": ["options"], "properties": {"options": {"devices": ["pc"]}}}}
        context.context["canvas"]["deviceMode"] = "mobile"
        items = [{"capability": "proposal.begin", "slots": {"result_kind": "form_actions"}}, {"capability": "form.update_component_options", "slots": {"payload": {"nodeId": "draft-choice", "options": [{"label": "A", "value": "a"}]}}}]
        self.refused(compile_items(items, context), "DEVICE_RESTRICTED")
        property_context = host()
        property_context["canvas"]["deviceMode"] = "mobile"
        self.refused(run([{"capability": "form.property.undo", "slots": {"transaction_id": "tx"}}], property_context, kind="property_undo"), "DEVICE_RESTRICTED")

    def test_model_context_filters_candidates_without_changing_authorization(self):
        context = host()
        metadata = context["capabilities"]["components"]["Input"]
        metadata["create"] = {"devices": ["mobile"], "writableProps": ["label"]}
        metadata["properties"]["size"]["devices"] = ["mobile"]
        before = deepcopy(context)
        filtered = model_host_context(context)
        current = filtered["capabilities"]["components"]["Input"]
        self.assertFalse(current["create"]["supported"])
        self.assertNotIn("size", current["properties"])
        self.assertEqual(context, before)
        context["canvas"]["layoutMode"] = "grid"
        self.assertEqual(model_host_context(context)["capabilities"]["components"], {})
