"""Property compiler regression tests, loaded independently of proposal imports."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("standalone_properties", Path(__file__).resolve().parents[1] / "form_generation" / "properties.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
compile_property_proposal = MODULE.compile_property_proposal


def host(component="Input"):
    properties = {prop: {"operations": ["set", "clear", "unset", "reset", "copy", "query"]} for prop in MODULE._COMMON | MODULE._SPECIFIC[component]}
    return {
        "target": {"schemaId": "form", "revision": "r1"},
        "canvas": {"layoutMode": "flow", "device": "pc"},
        "currentSchema": {"fields": [{"id": "a", "componentName": component, "props": {"label": "说明", "name": "note", "identifiers": {"name": "note"}, "placeholder": "旧", "size": "medium", "defaultValueConfig": "undefined", "access": {"required": False, "visible": False, "editable": False, "forbidManualInput": False}}}], "props": {"textAlign": "right"}},
        "selection": {"nodeId": "a"},
        "capabilities": {"catalogVersion": "properties.v1", "components": {component: {"properties": properties}}},
        "nodePolicies": {"a": {"system": False, "saved": False, "disabledName": False, "writable": True}},
        "supportedActionVersions": {"form.apply_property_change": ["form_property_actions.v1"]},
    }


def change(prop="placeholder", value="新", operation="set", **extra):
    slots = {"node_id": "a", "property": prop, "operation": operation, **extra}
    if operation == "set":
        slots["value"] = value
    return {"capability": "form.property.change", "slots": slots}


def run(items, context=None, kind="property_changes", base=None):
    return compile_property_proposal([{"capability": "proposal.begin", "slots": {"result_kind": kind, "summary": "调整属性"}}, *items], context if context is not None else host(), base or {"protocol": "form-agent.v1", "schemaVersion": "1.1.0", "proposalId": "p1"})


class PropertyTests(unittest.TestCase):
    def rejected(self, result, code=None, status="unsupported"):
        self.assertEqual(result["status"], status, result)
        self.assertNotIn("result", result)
        if code:
            self.assertEqual(result["diagnostics"][0]["code"], code, result)

    def test_stable_detached_checklist_and_mapping(self):
        context = host()
        before = deepcopy(context)
        items = [change("extra", "描述", selected=False)]
        first = run(items, context)
        self.assertEqual(first, run(items, context))
        self.assertEqual(context, before)
        row = first["presentation"]["items"][0]
        self.assertEqual(row["property"], "description")
        self.assertFalse(row["selectedByDefault"])
        self.assertEqual(row["before"], {"exists": False})
        self.assertEqual(row["after"], {"exists": True, "value": "描述"})
        action = first["result"]["actions"][0]
        self.assertEqual(row["actionIds"], [action["actionId"]])
        self.assertEqual(action["payload"]["property"], "description")
        first["presentation"]["items"][0]["after"]["value"] = "mutated"
        self.assertEqual(context, before)

    def test_required_alias_access_effect(self):
        for alias in ("required", "必添", "requried"):
            result = run([change(alias, True)])
            self.assertEqual(result["status"], "ready", result)
            row = result["presentation"]["items"][0]
            self.assertEqual(row["before"], {"exists": True, "value": False})
            self.assertIn("显示和编辑", row["effects"][0])
            self.assertNotIn("access", result["result"]["actions"][0]["payload"])

    def test_all_seven_components_support_common_semantics(self):
        for component in sorted(MODULE.COMPONENTS):
            with self.subTest(component=component):
                result = run([change()], host(component))
                self.assertEqual(result["status"], "ready", result)
                self.assertEqual(result["result"]["actions"][0]["payload"]["componentName"], component)

    def test_finite_types_and_intrinsic_ranges(self):
        for value in (True, "5", float("nan"), float("inf"), 11, 2):
            self.rejected(run([change("rows", value)], host("Input.TextArea")))
        self.assertEqual(run([change("rows", 5)], host("Input.TextArea"))["status"], "ready")
        self.rejected(run([change("description", "x" * 201)]), "INVALID_VALUE")
        self.rejected(run([change("label", "")]), "INVALID_VALUE")
        self.rejected(run([change("size", "middle")]), "INVALID_VALUE")
        self.rejected(run([change("required", 1)]), "INVALID_VALUE")

    def test_saved_locks_and_missing_policies(self):
        for component, prop, value in (("NumberPicker", "precision", 2), ("DatePicker", "format", "YYYY"), ("TimePicker", "format", "HH:mm")):
            for flag in ("saved", "disabledName"):
                context = host(component)
                context["nodePolicies"]["a"][flag] = True
                self.rejected(run([change(prop, value)], context), "SAVED_PROPERTY_LOCKED")
        context = host()
        del context["nodePolicies"]
        self.rejected(run([change()], context), "MISSING_NODE_POLICY")
        for key in ("system", "writable", "saved", "disabledName"):
            context = host()
            del context["nodePolicies"]["a"][key]
            self.rejected(run([change()], context), "MISSING_NODE_POLICY")
        context = host()
        context["nodePolicies"]["a"]["system"] = True
        self.rejected(run([change()], context), "NODE_READ_ONLY")

    def test_layout_device_restrictions(self):
        context = host()
        context["canvas"]["layoutMode"] = "grid"
        self.rejected(run([change("textAlign", "left")], context), "LAYOUT_RESTRICTED")
        context = host()
        context["canvas"]["device"] = "mobile"
        self.rejected(run([change("size", "large")], context), "DEVICE_RESTRICTED")

    def test_default_zero_and_paired_clear(self):
        context = host("NumberPicker")
        result = run([change("defaultValue", {"mode": "custom", "value": 0})], context)
        self.assertEqual(result["status"], "ready", result)
        self.assertEqual(result["presentation"]["items"][0]["after"]["value"]["value"], 0)
        self.assertIn("成对", result["presentation"]["items"][0]["effects"][0])
        context["currentSchema"]["fields"][0]["props"].update(defaultValueConfig="custom", defaultValue=4)
        cleared = run([change("defaultValue", operation="clear")], context)
        self.assertEqual(cleared["presentation"]["items"][0]["after"], {"exists": True, "value": {"mode": "undefined"}})
        for value in ({"mode": "custom", "value": "0"}, {"mode": "custom", "value": True}, {"mode": "formula", "value": "1+1"}):
            self.rejected(run([change("defaultValue", value)], context))

    def test_date_format_and_default_validation(self):
        context = host("DatePicker")
        context["currentSchema"]["fields"][0]["props"]["format"] = "YYYY-MM-DD"
        self.rejected(run([change("defaultValue", {"mode": "custom", "value": "2026-02-30"})], context), "INVALID_DATE")
        result = run([change("defaultValue", {"mode": "custom", "value": "2026-11-18"})], context)
        self.assertEqual(result["status"], "ready", result)
        self.assertEqual(run([change("description", "说明")], context)["presentation"]["items"][0]["effects"], [])
        self.assertIn("日期格式", run([change("format", "YYYY")], context)["presentation"]["items"][0]["effects"][0])

    def test_select_defaults_real_values_and_copy_incompatibility(self):
        context = host("SelectSingle")
        context["currentSchema"]["fields"][0]["props"]["options"] = {"dataSource": [{"primaryKey": "1", "value": "business", "label": "名称", "disabled": False}]}
        result = run([change("defaultValue", "business")], context)
        self.assertEqual(result["status"], "ready", result)
        self.assertIn("activeKey", result["presentation"]["items"][0]["effects"][0])
        for value in ("名称", "1", "missing"):
            self.rejected(run([change("defaultValue", value)], context), "INVALID_DEFAULT_OPTION")
        source = deepcopy(host("NumberPicker")["currentSchema"]["fields"][0])
        source["id"] = "b"
        source["props"].update(defaultValueConfig="custom", defaultValue=0)
        context = host()
        context["capabilities"]["components"].update(host("NumberPicker")["capabilities"]["components"])
        context["currentSchema"]["fields"].append(source)
        context["nodePolicies"]["b"] = deepcopy(context["nodePolicies"]["a"])
        self.rejected(run([change("defaultValue", operation="copy", source_node_id="b")], context), "INVALID_VALUE")

    def test_copy_resolved_source_snapshot(self):
        context = host()
        source = deepcopy(context["currentSchema"]["fields"][0])
        source["id"] = "b"
        source["props"].pop("placeholder")
        context["currentSchema"]["fields"].append(source)
        context["nodePolicies"]["b"] = deepcopy(context["nodePolicies"]["a"])
        context["resolvedProperties"] = {"b": {"placeholder": {"source": "default", "resolvedValue": "有效提示"}}}
        result = run([change(operation="copy", source_node_id="b")], context)
        self.assertEqual(result["status"], "ready", result)
        self.assertEqual(result["result"]["actions"][0]["payload"]["value"], "有效提示")
        self.assertEqual(result["presentation"]["items"][0]["source"]["stored"], {"exists": False})

    def test_queries_without_action_version_and_inheritance(self):
        context = host()
        del context["supportedActionVersions"]
        query = {"capability": "form.property.query", "slots": {"use_selection": True, "property": "titleAlign"}}
        result = run([query], context, "property_query")
        self.assertEqual(result["status"], "ready", result)
        self.assertEqual(result["contractVersion"], "form_property_query.v1")
        row = result["presentation"]["items"][0]
        self.assertEqual((row["source"], row["resolvedValue"], row["stored"]), ("inherited", "right", {"exists": False}))
        self.assertNotIn("result", result)
        context["resolvedProperties"] = {"a": {"titleAlign": {"source": "inherited", "resolvedValue": "left"}}}
        self.assertEqual(run([query], context, "property_query")["presentation"]["items"][0]["resolvedValue"], "left")

    def test_empty_or_ambiguous_selection_clarifies(self):
        item = change()
        item["slots"].pop("node_id")
        item["slots"]["use_selection"] = True
        context = host()
        context["selection"] = {}
        self.rejected(run([item], context), "TARGET_REQUIRED", "needs_clarification")
        context = host()
        duplicate = deepcopy(context["currentSchema"]["fields"][0])
        duplicate["id"] = "b"
        context["currentSchema"]["fields"].append(duplicate)
        item["slots"] = {"node_label": "说明", "property": "placeholder", "operation": "set", "value": "新"}
        self.rejected(run([item], context), "TARGET_REQUIRED", "needs_clarification")

    def test_action_versions_catalogs_and_operations_fail_closed(self):
        for versions in (None, ["1.0"], ["form_property_actions.v2"]):
            context = host()
            context["supportedActionVersions"]["form.apply_property_change"] = versions
            self.rejected(run([change()], context), "ACTION_VERSION_UNSUPPORTED")
        context = host()
        del context["capabilities"]["catalogVersion"]
        self.rejected(run([change()], context), "MISSING_CATALOG_VERSION")
        context = host()
        context["capabilities"]["components"]["Input"]["properties"]["placeholder"]["operations"] = ["query"]
        self.rejected(run([change()], context), "OPERATION_UNSUPPORTED")

    def test_reset_missing_vs_local_and_clear_different_from_default(self):
        context = host()
        self.assertEqual(run([change("titleAlign", operation="reset")], context)["status"], "no_change")
        context["currentSchema"]["fields"][0]["props"]["textAlign"] = "right"
        row = run([change("titleAlign", operation="unset")], context)["presentation"]["items"][0]
        self.assertEqual(row["before"], {"exists": True, "value": "right"})
        self.assertEqual(row["after"], {"exists": False})
        context = host("SelectSingle")
        self.assertEqual(run([change("allowClear", operation="clear")], context)["presentation"]["items"][0]["after"]["value"], False)
        self.assertEqual(run([change("allowClear", operation="reset")], context)["presentation"]["items"][0]["after"]["value"], True)
        self.rejected(run([change("label", operation="clear")]), "TITLE_REQUIRED")
        self.rejected(run([change("step", operation="clear")], host("NumberPicker")), "CLEAR_UNSUPPORTED")

    def test_conflicts_and_final_candidate_conditions(self):
        self.rejected(run([change(), change(value="另一值")]), "PROPERTY_CONFLICT")
        self.rejected(run([change("required", True), change("display", False)]), "SEMANTIC_CONFLICT")
        self.rejected(run([change("requiredMessage", "必填")]), "PROPERTY_CONDITION_UNMET", "needs_clarification")
        result = run([change("requiredMessage", "必填"), change("required", True)])
        self.assertEqual(result["status"], "ready", result)
        rows = result["presentation"]["items"]
        self.assertEqual(rows[0]["dependsOn"], [rows[1]["changeId"]])
        self.rejected(run([change("requiredMessage", "必填"), change("required", True, selected=False)]), "SELECTION_DEPENDENCY", "needs_clarification")

    def test_identity_prototype_rules_and_unknown_compounds(self):
        for prop in ("name", "identifiers", "__proto__", "constructor", "props.name", "width", "rules", "defaultValueConfig"):
            self.rejected(run([change(prop, "bad")]))
        context = host()
        context["capabilities"]["components"]["Input"]["properties"]["relatedField"].update(valueSchema={"type": "object", "properties": {}, "additionalProperties": False})
        self.rejected(run([change("relatedField", {})], context), "MISSING_COMPOUND_HANDLER")
        result = run([{"capability": "form.property.rule", "slots": {"node_id": "a", "operation": "add", "rule_id": "r", "rule_type": "regex", "value": "script"}}])
        self.rejected(result, "EXTENSION_UNSUPPORTED")

    def test_registered_bounded_rule_and_remove(self):
        context = host()
        context["capabilities"]["ruleCatalog"] = {"length": {"handlerId": "length.v1", "components": ["Input"], "operations": ["add", "replace", "remove"], "valueSchema": {"type": "object", "properties": {"max": {"type": "integer", "minimum": 1, "maximum": 200}}, "required": ["max"], "additionalProperties": False}}}
        context["supportedActionVersions"]["form.apply_property_rule"] = [MODULE.PROPERTY_ACTION_VERSION]
        context["rules"] = {"a": []}
        item = {"capability": "form.property.rule", "slots": {"node_id": "a", "operation": "add", "rule_type": "length", "rule_id": "r1", "value": {"max": 10}}}
        result = run([item], context)
        self.assertEqual(result["status"], "ready", result)
        self.assertEqual(result["result"]["actions"][0]["action"], "form.apply_property_rule")
        context["rules"]["a"] = [{"id": "r1", "type": "length", "value": {"max": 10}}]
        item["slots"].update(operation="remove")
        item["slots"].pop("value")
        result = run([item], context)
        self.assertEqual(result["status"], "ready", result)
        self.assertEqual(result["presentation"]["items"][0]["after"], {"exists": False})

    def test_linkage_ast_action_version_and_references(self):
        context = host()
        context["capabilities"]["linkageCatalog"] = {"visible": {"handlerId": "visible.v1", "components": ["Input"], "operations": ["add"], "astOperators": ["eq"], "valueSchema": {"type": "object", "properties": {"op": {"enum": ["eq"]}, "nodeId": {"type": "string"}, "value": {"type": "string"}}, "required": ["op", "nodeId", "value"], "additionalProperties": False}}}
        context["linkages"] = {"a": []}
        item = {"capability": "form.property.linkage", "slots": {"node_id": "a", "operation": "add", "linkage_type": "visible", "linkage_id": "l1", "value": {"op": "eq", "nodeId": "a", "value": "yes"}}}
        self.rejected(run([item], context), "ACTION_VERSION_UNSUPPORTED")
        context["supportedActionVersions"]["form.apply_property_linkage"] = [MODULE.PROPERTY_ACTION_VERSION]
        result = run([item], context)
        self.assertEqual(result["status"], "ready", result)
        item["slots"]["value"]["nodeId"] = "unknown"
        self.rejected(run([item], context), "INVALID_REFERENCE")
        item["slots"]["value"] = "eval('bad')"
        self.rejected(run([item], context), "INVALID_VALUE")

    def test_undo_current_history_only_and_no_inverse_patch(self):
        context = host()
        context["history"] = {"current": {"canUndo": True, "transactionId": "tx1", "revision": "r1"}}
        item = {"capability": "form.property.undo", "slots": {"transaction_id": "tx1"}}
        self.rejected(run([item], context, "property_undo"), "ACTION_VERSION_UNSUPPORTED")
        context["supportedActionVersions"]["form.undo_property_transaction"] = [MODULE.PROPERTY_ACTION_VERSION]
        result = run([item], context, "property_undo")
        self.assertEqual(result["result"]["actions"][0]["payload"], {"transactionId": "tx1", "revision": "r1"})
        context["history"]["current"]["revision"] = "old"
        self.rejected(run([item], context, "property_undo"), "UNDO_UNAVAILABLE")

    def test_malformed_metadata_and_ir_never_escape(self):
        for context in ({}, {"selection": []}, None, []):
            self.rejected(run([change()], context if context is not None else {}))
        for items in (None, [None], [{"capability": "form.property.change", "slots": []}]):
            result = compile_property_proposal(items, host(), {})
            self.rejected(result)
        context = host()
        context["capabilities"]["components"] = []
        self.rejected(run([change()], context))

    def test_documented_capability_policy_shape_and_read_denial(self):
        context = host()
        context.pop("nodePolicies")
        context["capabilities"]["nodePolicies"] = {"a": {"canRead": True, "canModify": True, "allowedProperties": ["placeholder"]}}
        self.assertEqual(run([change()], context)["status"], "ready")
        self.rejected(run([change("description", "文案")], context), "PROPERTY_READ_ONLY")
        query = {"capability": "form.property.query", "slots": {"node_id": "a", "property": "placeholder"}}
        context["capabilities"]["nodePolicies"]["a"]["canRead"] = False
        self.rejected(run([query], context, "property_query"), "QUERY_UNSUPPORTED")

    def test_final_date_format_is_validated_independent_of_ir_order(self):
        context = host("DatePicker")
        context["currentSchema"]["fields"][0]["props"]["format"] = "YYYY-MM-DD"
        default = change("defaultValue", {"mode": "custom", "value": "2026-11"})
        fmt = change("format", "YYYY-MM")
        for items in ([default, fmt], [fmt, default]):
            self.assertEqual(run(items, context)["status"], "ready")

    def test_numeric_range_and_conditional_format_message(self):
        context = host("NumberPicker")
        self.rejected(run([change("minEnable", True), change("min", 10), change("maxEnable", True), change("max", 5)], context), "INVALID_RANGE")
        self.assertEqual(run([change("min", 0), change("minEnable", True)], context)["status"], "ready")
        self.rejected(run([change("formatMessage", "提示")]), "PROPERTY_CONDITION_UNMET", "needs_clarification")

    def test_registered_weekday_structure_and_semantics(self):
        context = host("DatePicker")
        context["currentSchema"]["fields"][0]["props"]["format"] = "YYYY-MM-DD"
        definition = context["capabilities"]["components"]["DatePicker"]["properties"]["disabledDays"]
        definition.update(handlerId="weekdays.v1", valueSchema={"type": ["object", "null"], "properties": {"enabled": {"type": "boolean"}, "days": {"type": "array", "items": {"type": "string"}}}, "required": ["enabled", "days"], "additionalProperties": False}, clearValue=None)
        self.assertEqual(run([change("disabledDays", {"enabled": True, "days": ["1", "2"]})], context)["status"], "ready")
        self.rejected(run([change("disabledDays", {"enabled": True, "days": []})], context), "INVALID_WEEKDAYS")
        self.assertEqual(run([change("disabledDays", operation="clear")], context)["status"], "ready")

    def test_text_limit_copy_reset_and_default_cleanup(self):
        context = host()
        props = context["currentSchema"]["fields"][0]["props"]
        props.update(showLimitHint=True, textMaxLength=20)
        source = deepcopy(context["currentSchema"]["fields"][0])
        source["id"] = "b"
        source["props"]["textMaxLength"] = 30
        context["currentSchema"]["fields"].append(source)
        context["nodePolicies"]["b"] = deepcopy(context["nodePolicies"]["a"])
        result = run([change("textLengthLimit", operation="copy", source_node_id="b")], context)
        self.assertEqual(result["status"], "ready", result)
        self.assertEqual(result["presentation"]["items"][0]["after"]["value"], {"enabled": True, "maxLength": 30})
        reset = run([change("textLengthLimit", operation="reset")], context)
        self.assertEqual(reset["presentation"]["items"][0]["after"]["value"], {"enabled": False, "maxLength": 200})
        props["defaultValue"] = "stale"
        self.assertEqual(run([change("defaultValue", operation="clear")], context)["status"], "ready")

    def test_ir_extraneous_slots_and_unimplemented_json_schema(self):
        self.rejected(run([change(path=["props", "placeholder"])]), "INVALID_IR")
        context = host()
        context["capabilities"]["components"]["Input"]["properties"]["placeholder"]["valueSchema"] = {"type": "string", "not": {"const": "x"}}
        self.rejected(run([change()], context), "UNSUPPORTED_VALUE_SCHEMA")

    def test_native_capability_schema_fresh_and_complete(self):
        definitions = MODULE.property_capabilities()
        self.assertEqual(len(definitions), 5)
        schema = definitions[0]["slots_schema"]
        self.assertEqual(schema["properties"]["selected"]["default"], True)
        self.assertEqual(schema["properties"]["operation"]["enum"], ["set", "clear", "unset", "reset", "copy"])
        definitions[0]["slots_schema"]["properties"].clear()
        self.assertIn("property", MODULE.property_capabilities()[0]["slots_schema"]["properties"])


if __name__ == "__main__":
    unittest.main()
