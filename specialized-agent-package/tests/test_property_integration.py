"""Exercise property output through the production compiler and event handler."""

from copy import deepcopy
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from test_form_field_list import assert_action_draft
import test_output_preview


class PropertyIntegrationTests(IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        test_output_preview.OutputPreviewTests.setUpClass.__func__(cls)

    def context(self):
        return {
            "requestId": "request-properties",
            "schemaVersion": "1.1.0",
            "target": {"schemaId": "form-1", "revision": "rev-1"},
            "selection": {"nodeId": "field-1"},
            "canvas": {"layoutMode": "flow", "device": "pc"},
            "currentSchema": {"schemaVersion": "1.1.0", "fields": [{
                "id": "field-1", "componentName": "Input", "props": {
                    "label": "说明", "name": "note", "placeholder": "",
                    "access": {"visible": True, "editable": True, "required": False,
                               "forbidManualInput": False},
                },
            }]},
            "resolvedProperties": {"field-1": {}},
            "history": {},
            "capabilities": {
                "catalogVersion": "component-properties.v1",
                "actions": ["form.apply_property_change"],
                "components": {"Input": {"properties": {
                    "placeholder": {"title": "占位提示", "valueSchema": {"type": "string"},
                                    "operations": ["set", "query"]},
                }}},
                "nodePolicies": {"field-1": {"canRead": True, "canModify": True,
                                            "allowedProperties": ["placeholder"]}},
            },
            "supportedActionVersions": {"form.apply_property_change": ["form_property_actions.v1"]},
        }

    def ir(self, kind="property_changes", capability="form.property.change"):
        slots = {"use_selection": True, "property": "placeholder"}
        if kind == "property_changes":
            slots.update(operation="set", value="请输入说明")
        return {"plan_items": [
            {"capability": "proposal.begin", "slots": {"result_kind": kind, "summary": "调整提示"}},
            {"capability": capability, "slots": slots},
        ]}

    async def test_property_request_emits_checklist_without_changing_snapshot(self):
        snapshot = self.context()
        before = deepcopy(snapshot)
        context = SimpleNamespace(inputs="改提示文字", context=snapshot, event_publisher=AsyncMock())

        async def generate(**kwargs):
            return kwargs["compiler"](self.ir(), context)

        context.native_capability = SimpleNamespace(generate=generate)
        result = await self.agent.generate_form_proposal(context)
        proposal = result["output"]["form_proposal"]
        self.assertEqual(proposal["status"], "ready", proposal)
        self.assertEqual(proposal["contractVersion"], "form_property_proposal.v1")
        assert_action_draft(self, proposal, "shared.component-property-checklist", property_actions=True)
        self.assertEqual(proposal["actionVersion"], "form_property_actions.v1")
        self.assertEqual(proposal["actions"][0]["payload"]["value"], "请输入说明")
        self.assertEqual(proposal["actions"][0]["preconditions"]["before"], {"exists": True, "value": ""})
        self.assertEqual(snapshot, before)
        self.assertEqual(set(result["output"]), {"form_proposal"})
        context.event_publisher.assert_awaited_once_with("form.proposal.completed", {
            "block_id": "form_proposal", "title": "表单设计提案", "status": "ready",
            "proposal": proposal,
        })

    def test_direct_mapping_context_is_supported(self):
        result = self.agent.compile_platform_proposal(self.ir(), self.context())
        self.assertEqual(result["output"]["form_proposal"]["status"], "ready", result)

    async def test_query_needs_no_write_action_version_or_component(self):
        snapshot = self.context()
        snapshot["supportedActionVersions"] = {}
        context = SimpleNamespace(inputs="查提示文字", context=snapshot, event_publisher=AsyncMock())

        async def generate(**kwargs):
            return kwargs["compiler"](self.ir("property_query", "form.property.query"), context)

        context.native_capability = SimpleNamespace(generate=generate)
        result = await self.agent.generate_form_proposal(context)
        proposal = result["output"]["form_proposal"]
        self.assertEqual(proposal["status"], "ready", proposal)
        self.assertEqual(proposal["presentation"]["kind"], "component_property_query")
        self.assertTrue(proposal["presentation"]["readOnly"])
        self.assertEqual(len(proposal["presentation"]["items"]), 1)
        self.assertEqual(proposal["presentation"]["items"][0]["stored"], {"exists": True, "value": ""})
        for key in ("actions", "mode", "actionVersion", "result", "validation"):
            self.assertNotIn(key, proposal)
        self.assertNotIn("component", result["output"])
        context.event_publisher.assert_awaited_once_with("form.proposal.completed", {
            "block_id": "form_proposal", "title": "表单设计提案", "status": "ready", "proposal": proposal,
        })

    async def test_undo_preserves_its_action_without_declaring_a_component(self):
        snapshot = self.context()
        action = "form.undo_property_transaction"
        snapshot["capabilities"]["actions"].append(action)
        snapshot["supportedActionVersions"][action] = ["form_property_actions.v1"]
        snapshot["history"] = {"canUndo": True, "transactionId": "tx-1", "revision": "rev-1"}
        context = SimpleNamespace(inputs="撤销上次属性变更", context=snapshot, event_publisher=AsyncMock())

        async def generate(**kwargs):
            return kwargs["compiler"]({"plan_items": [
                {"capability": "proposal.begin", "slots": {"result_kind": "property_undo"}},
                {"capability": "form.property.undo", "slots": {"transaction_id": "tx-1"}},
            ]}, context)

        context.native_capability = SimpleNamespace(generate=generate)
        result = await self.agent.generate_form_proposal(context)
        proposal = result["output"]["form_proposal"]
        self.assertEqual(proposal["status"], "ready", proposal)
        self.assertEqual(proposal["presentation"], {"kind": "component_property_undo", "title": "撤销属性修改", "transactionId": "tx-1", "canUndo": True})
        self.assertEqual(proposal["mode"], "append")
        self.assertEqual(proposal["actionVersion"], "form_property_actions.v1")
        self.assertNotIn("result", proposal)
        self.assertNotIn("validation", proposal)
        self.assertEqual(len(proposal["actions"]), 1)
        self.assertEqual(proposal["actions"][0]["action"], action)
        self.assertEqual(proposal["actions"][0]["payload"], {"transactionId": "tx-1", "revision": "rev-1"})
        self.assertEqual(proposal["actions"][0]["dependsOn"], [])
        self.assertEqual(proposal["actions"][0]["display"], {"selectedByDefault": True})
        self.assertNotIn("component", result["output"])
        context.event_publisher.assert_awaited_once_with("form.proposal.completed", {
            "block_id": "form_proposal", "title": "表单设计提案", "status": "ready", "proposal": proposal,
        })

    def test_registered_rule_removal_uses_existing_snapshot(self):
        snapshot = self.context()
        snapshot["capabilities"]["actions"].append("form.apply_property_rule")
        snapshot["supportedActionVersions"]["form.apply_property_rule"] = ["form_property_actions.v1"]
        snapshot["capabilities"]["nodePolicies"]["field-1"]["allowedProperties"].append("rule")
        snapshot["capabilities"]["ruleCatalog"] = {"length": {
            "handlerId": "length", "components": ["Input"], "operations": ["remove"],
            "valueSchema": {"type": "object"},
        }}
        snapshot["rules"] = {"field-1": [{"id": "rule-1", "type": "length", "value": {"max": 10}}]}
        ir = {"plan_items": [
            {"capability": "proposal.begin", "slots": {"result_kind": "property_changes", "summary": "删除规则"}},
            {"capability": "form.property.rule", "slots": {"use_selection": True,
             "operation": "remove", "rule_type": "length", "rule_id": "rule-1"}},
        ]}
        result = self.agent.compile_platform_proposal(ir, snapshot)["output"]["form_proposal"]
        self.assertEqual(result["status"], "ready", result)
        self.assertEqual(result["actions"][0]["action"], "form.apply_property_rule")
        self.assertEqual(snapshot["rules"]["field-1"][0]["id"], "rule-1")

    def test_normalization_preserves_new_host_fields_and_copies_them(self):
        snapshot = self.context()
        snapshot["resolvedProperties"] = {"field-1": {"placeholder": {"value": "", "source": "local"}}}
        snapshot["history"] = {"canUndo": False}
        snapshot["rules"] = {"field-1": [{"id": "rule-1", "type": "length", "value": {"max": 10}}]}
        snapshot["linkages"] = {"field-1": []}
        normalized = self.agent.normalize_host_context(snapshot)
        self.assertEqual(normalized["rules"], snapshot["rules"])
        self.assertEqual(normalized["linkages"], snapshot["linkages"])
        self.assertEqual(normalized["history"], snapshot["history"])
        self.assertEqual(normalized["resolvedProperties"], snapshot["resolvedProperties"])
        normalized["history"]["canUndo"] = True
        self.assertFalse(snapshot["history"]["canUndo"])
