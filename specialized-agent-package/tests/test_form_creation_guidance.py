"""Require explicit form creation before field changes on an empty host canvas."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from compiler_package import load_compiler_module
from test_form_field_list import blank_context, assert_non_executable
from test_existing_canvas import saved_context as existing_context
import test_output_preview

guidance = load_compiler_module("guidance")
compiler = load_compiler_module("proposal")


def field_request(intent="field_change", mode="replace_empty_form"):
    return {"plan_items": [
        {"capability": "proposal.begin", "slots": {
            "request_intent": intent, "summary": "新增姓名字段", "result_kind": "form_fields", "mode": mode,
            "field_requirements": {"fields": [{"label": "姓名", "component_name": "Input", "required": True, "placeholder": "请输入姓名"}]},
        }},
        {"capability": "form.field.define", "slots": {
            "client_ref": "person-name", "component_name": "Input", "label": "姓名", "name": "person_name",
        }},
    ]}


class FormCreationGuidanceTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        test_output_preview.OutputPreviewTests.setUpClass.__func__(cls)

    def context(self, answer=None, host=None):
        context = SimpleNamespace(inputs="新增必填的姓名单行输入字段，提示请输入姓名", context=host if host is not None else blank_context(),
                                  event_publisher=AsyncMock())

        async def generate(**kwargs):
            return kwargs["compiler"](field_request(), None)

        context.native_capability = SimpleNamespace(generate=AsyncMock(side_effect=generate))
        context.clarification = SimpleNamespace(request=AsyncMock(return_value=answer))
        return context

    async def prepared_context(self, answer):
        context = self.context(answer)
        prepared = await self.agent.prepare_form_requirement(context)
        self.assertEqual(prepared["status"], "completed", prepared)
        context.inputs = prepared["output"]
        return context

    def test_field_addition_cannot_create_or_append_without_confirmation(self):
        for mode in ("replace_empty_form", "append"):
            with self.subTest(mode=mode):
                ir = field_request(mode=mode)
                ir["plan_items"][0]["slots"]["form_creation_confirmed"] = True
                result = compiler.compile_form_proposal(ir, blank_context())
                proposal = result["output"]["form_proposal"]
                self.assertEqual(proposal["clarificationKind"], "form_creation_required")
                self.assertEqual([o["id"] for o in proposal["clarificationOptions"]], ["create-form", "cancel"])
                assert_non_executable(self, proposal)

    def test_modification_deletion_and_field_draft_all_hit_precondition(self):
        requests = [
            {"plan_items": [
                {"capability": "proposal.begin", "slots": {"request_intent": "field_change", "result_kind": "property_changes"}},
                {"capability": "form.property.change", "slots": {"node_id": "missing", "property": "required", "operation": "set", "value": True}},
            ]},
            {"plan_items": [
                {"capability": "proposal.begin", "slots": {"request_intent": "field_change", "result_kind": "form_actions"}},
                {"capability": "form.remove_component", "slots": {"payload": {"nodeId": "missing"}}},
            ]},
            {"plan_items": [{"capability": "proposal.needs_clarification", "slots": {
                "request_intent": "field_change", "clarification_kind": "field_addition",
                "question": "字段是什么？", "field_draft": {},
            }}]},
        ]
        for ir in requests:
            with self.subTest(ir=ir):
                proposal = compiler.compile_form_proposal(ir, blank_context())["output"]["form_proposal"]
                self.assertEqual(proposal["clarificationKind"], "form_creation_required")
                self.assertNotIn("fieldGuidance", proposal)
                assert_non_executable(self, proposal)

    async def test_confirmation_retains_original_and_generates_initial_form(self):
        context = await self.prepared_context({"kind": "selected", "selected_option_id": "create-form"})
        self.assertEqual(context.native_capability.generate.await_count, 1)
        context.event_publisher.assert_not_awaited()
        collected = await self.agent.collect_guidance(context)
        call = context.clarification.request.await_args.kwargs
        self.assertEqual(call["key"], "form_creation_confirmation")
        self.assertFalse(call["allow_free_text"])
        context.inputs = collected["output"]
        result = await self.agent.generate_confirmed_proposal(context)
        proposal = result["output"]["form_proposal"]
        self.assertEqual(proposal["status"], "ready", result)
        self.assertEqual(proposal["mode"], "replace_empty_form")
        self.assertEqual(proposal["presentation"]["kind"], "shared.form-create-confirm")
        self.assertEqual([a["payload"]["props"]["label"] for a in proposal["actions"]], ["姓名"])
        self.assertEqual(context.inputs["original_input"], "新增必填的姓名单行输入字段，提示请输入姓名")
        context.native_capability.generate.assert_awaited_once()
        self.assertEqual(proposal["actions"][0]["payload"]["props"]["placeholder"], "请输入姓名")
        self.assertNotIn("formCreationConfirmation", proposal)
        context.event_publisher.assert_awaited_once()

    async def test_cancellation_ends_request_without_regeneration(self):
        for answer in ({"kind": "cancelled"}, {"kind": "selected", "selected_option_id": "cancel"}):
            context = await self.prepared_context(answer)
            collected = await self.agent.collect_guidance(context)
            context.inputs = collected["output"]
            result = await self.agent.generate_confirmed_proposal(context)
            proposal = result["output"]["form_proposal"]
            self.assertEqual(proposal["status"], "no_change")
            assert_non_executable(self, proposal)
            self.assertNotIn("formCreationFingerprint", proposal)
            self.assertNotIn("formCreationConfirmation", context.inputs)
            context.native_capability.generate.assert_awaited_once()

    async def test_arbitrary_text_and_unknown_option_cannot_confirm(self):
        for answer in ({"kind": "text", "text": "确认"}, {"kind": "selected", "selected_option_id": "other"}, {"kind": "exhausted"}):
            context = await self.prepared_context(answer)
            result = await self.agent.collect_guidance(context)
            self.assertEqual(result["error_code"], "form_creation_invalid_answer")
            context.native_capability.generate.assert_awaited_once()

    async def test_missing_sdk_returns_non_executable_guidance(self):
        context = await self.prepared_context(None)
        del context.clarification
        collected = await self.agent.collect_guidance(context)
        context.inputs = collected["output"]
        result = await self.agent.generate_confirmed_proposal(context)
        proposal = result["output"]["form_proposal"]
        self.assertEqual(proposal["status"], "needs_clarification")
        assert_non_executable(self, proposal)
        context.native_capability.generate.assert_awaited_once()

    async def test_replay_uses_same_question_and_confirmation(self):
        context = await self.prepared_context({"kind": "selected", "selected_option_id": "create-form"})
        before = deepcopy(context.inputs)
        first = await self.agent.collect_guidance(context)
        second = await self.agent.collect_guidance(context)
        self.assertEqual(first, second)
        self.assertEqual(context.inputs, before)
        calls = context.clarification.request.await_args_list
        self.assertEqual(calls[0], calls[1])
        context.native_capability.generate.assert_awaited_once()

    async def test_changed_snapshot_or_confirmation_identity_is_rejected(self):
        for change in ("revision", "capabilities", "form", "identity"):
            context = await self.prepared_context({"kind": "selected", "selected_option_id": "create-form"})
            context.inputs = (await self.agent.collect_guidance(context))["output"]
            if change == "revision":
                context.context["target"]["revision"] = "rev-new"
            elif change == "capabilities":
                context.context["capabilities"]["components"] = {}
            elif change == "form":
                context.context = existing_context()
            else:
                context.inputs["formCreationConfirmation"]["proposalId"] = "other-proposal"
            result = await self.agent.generate_confirmed_proposal(context)
            self.assertEqual(result["error_code"], "form_creation_confirmation_stale")
            context.native_capability.generate.assert_awaited_once()

    async def test_existing_form_addition_bypasses_confirmation(self):
        context = self.context(host=existing_context())

        async def generate(**kwargs):
            return kwargs["compiler"](field_request(mode="append"), None)

        context.native_capability.generate.side_effect = generate
        prepared = await self.agent.prepare_form_requirement(context)
        self.assertEqual(prepared["output"]["proposal"]["status"], "ready", prepared)
        context.inputs = prepared["output"]
        await self.agent.collect_guidance(context)
        context.clarification.request.assert_not_awaited()
        context.native_capability.generate.assert_awaited_once()

    async def test_explicit_form_creation_still_bypasses_confirmation(self):
        context = self.context()
        context.inputs = "生成包含姓名的表单"

        async def generate(**kwargs):
            return kwargs["compiler"](field_request(intent="form_creation"), None)

        context.native_capability.generate.side_effect = generate
        result = await self.agent.prepare_form_requirement(context)
        self.assertEqual(result["output"]["proposal"]["status"], "ready", result)
        context.clarification.request.assert_not_awaited()
        context.native_capability.generate.assert_awaited_once()

    async def test_no_form_classification_is_required_by_schema_and_callback(self):
        context = self.context()

        async def generate(**kwargs):
            for entry in kwargs["allowed_capabilities"]:
                if entry["capability"].startswith("proposal."):
                    self.assertIn("request_intent", entry["slots_schema"]["required"])
            ir = field_request()
            ir["plan_items"][0]["slots"].pop("request_intent")
            return kwargs["compiler"](ir, None)

        context.native_capability.generate.side_effect = generate
        result = await self.agent.prepare_form_requirement(context)
        self.assertEqual(result["status"], "failed")
        self.assertIn("request_intent", result["summary"])
        context.clarification.request.assert_not_awaited()

    def test_missing_canvas_signal_and_existing_fields_do_not_prove_absence(self):
        existing, missing_signal, unknown_schema = existing_context(), blank_context(), blank_context()
        existing["canvas"]["isBlank"] = True
        missing_signal["canvas"].pop("isBlank")
        unknown_schema.pop("currentSchema")
        for host in (existing, missing_signal, unknown_schema):
            self.assertFalse(guidance.has_no_form(compiler.normalize_host_context(host)))

    def test_confirmed_creation_must_not_drop_fields_or_modify_missing_nodes(self):
        for ir in (field_request(mode="append"), {"plan_items": [{"capability": "proposal.no_change", "slots": {"request_intent": "field_change"}}]}):
            with self.subTest(ir=ir), self.assertRaises(ValueError):
                compiler.compile_form_proposal(ir, blank_context(), form_creation_confirmed=True)
