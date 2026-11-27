"""Sequential, replayable metadata collection without inferred field values."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from compiler_package import load_compiler_module
from test_form_field_list import blank_context, assert_non_executable
import test_output_preview

metadata = load_compiler_module("field_clarification")


def selected(option):
    return {"kind": "selected", "selected_option_id": option}


def text(value):
    return {"kind": "text", "text": value}


class FieldClarificationLoopTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        test_output_preview.OutputPreviewTests.setUpClass.__func__(cls)

    def context(self, fields, answers, reason=""):
        context = SimpleNamespace(inputs="生成一个字段", context=blank_context(), event_publisher=AsyncMock())
        ir = {"plan_items": [{"capability": "proposal.needs_clarification", "slots": {
            "summary": "先确认生成表单，再补齐字段", "question": "是否先生成表单？", "request_intent": "field_change",
            "clarification_kind": "field_addition", "field_requirements": {"fields": fields, "unsupported_reason": reason},
        }}]}

        async def generate(**kwargs):
            return kwargs["compiler"](deepcopy(ir), None)

        context.native_capability = SimpleNamespace(generate=AsyncMock(side_effect=generate))
        context.clarification = SimpleNamespace(request=AsyncMock(side_effect=[selected("create-form"), *answers]))
        return context

    async def confirm(self, context):
        prepared = await self.agent.prepare_form_requirement(context)
        self.assertEqual(prepared["status"], "completed", prepared)
        self.assertEqual(prepared["output"]["proposal"]["status"], "needs_clarification")
        context.inputs = prepared["output"]
        context.inputs = (await self.agent.collect_guidance(context))["output"]
        return deepcopy(context.inputs)

    async def run_dialogue(self, fields, answers, reason=""):
        context = self.context(fields, answers, reason)
        await self.confirm(context)
        result = await self.agent.generate_confirmed_proposal(context)
        return context, result

    async def test_iterates_label_type_and_properties_without_model_regeneration(self):
        context, result = await self.run_dialogue([{}], [
            text("姓名"), text("随便一个框"), text("就普通的"), selected("component:Input"),
            selected("required:yes"), text("请输入姓名"),
        ])
        proposal = result["output"]["form_proposal"]
        self.assertEqual(proposal["status"], "ready", result)
        props = proposal["actions"][0]["payload"]["props"]
        self.assertEqual(props, {"label": "姓名", "name": "field_1", "required": True, "placeholder": "请输入姓名"})
        calls = context.clarification.request.await_args_list
        questions = [c.kwargs["question"] for c in calls[1:]]
        self.assertIn("展示名称", questions[0])
        self.assertTrue(all("组件类型" in q for q in questions[1:4]))
        self.assertIn("是否必填", questions[4])
        self.assertIn("占位提示", questions[5])
        self.assertEqual(len({c.kwargs["key"] for c in calls}), len(calls))
        self.assertEqual({c.kwargs["max_rounds"] for c in calls}, {128})
        context.native_capability.generate.assert_awaited_once()
        context.event_publisher.assert_awaited_once()
        self.assertNotIn("fieldClarification", proposal)
        self.assertNotIn("fieldMetadataSelection", proposal)
        self.assertEqual(context.context["currentSchema"]["fields"], [])

    async def test_explicit_label_is_not_reasked_and_no_type_fallback(self):
        context, result = await self.run_dialogue([{"label": "姓名"}], [
            selected("component:NumberPicker"), selected("later")])
        proposal = result["output"]["form_proposal"]
        self.assertEqual(proposal["status"], "ready", result)
        self.assertEqual(proposal["actions"][0]["payload"]["componentName"], "NumberPicker")
        self.assertNotIn("required", proposal["actions"][0]["payload"]["props"])
        self.assertNotIn("placeholder", proposal["actions"][0]["payload"]["props"])
        self.assertIn("部分属性待后续", proposal["summary"])
        self.assertIn("组件类型", context.clarification.request.await_args_list[1].kwargs["question"])

    async def test_free_text_later_defers_optional_values_without_false_default(self):
        _, result = await self.run_dialogue([{"label": "姓名", "component_name": "Input"}], [text("先这样，剩下我后面在设计器改")])
        proposal = result["output"]["form_proposal"]
        self.assertEqual(proposal["status"], "ready")
        self.assertNotIn("required", proposal["actions"][0]["payload"]["props"])

    async def test_later_does_not_invent_missing_type_or_label(self):
        for fields in ([{}], [{"label": "姓名"}], [{"label": "状态", "component_name": "SelectSingle"}]):
            context, result = await self.run_dialogue(fields, [selected("later")])
            proposal = result["output"]["form_proposal"]
            self.assertEqual(proposal["status"], "needs_clarification", result)
            self.assertEqual(proposal["fieldClarification"]["status"], "incomplete")
            assert_non_executable(self, proposal)
            context.native_capability.generate.assert_awaited_once()

    async def test_real_options_required_invalid_values_are_reasked(self):
        context, result = await self.run_dialogue([{"label": "状态", "component_name": "SelectSingle"}], [
            text("在职，离职"), text("在职=employee\n离职=former"), selected("required:no"), selected("later")])
        proposal = result["output"]["form_proposal"]
        self.assertEqual(proposal["status"], "ready", result)
        props = proposal["actions"][0]["payload"]["props"]
        self.assertEqual(props["options"], [{"label": "在职", "value": "employee"}, {"label": "离职", "value": "former"}])
        self.assertFalse(props["required"])
        self.assertIn("真实业务值", context.clarification.request.await_args_list[2].kwargs["question"])

    async def test_unknown_or_old_option_fails_without_partial_actions(self):
        _, result = await self.run_dialogue([{"label": "姓名"}], [selected("old-question:component:Input")])
        self.assertEqual(result["error_code"], "field_metadata_invalid")
        self.assertNotIn("output", result)

    async def test_cancel_during_collection_never_creates_or_adds(self):
        for answer in ({"kind": "cancelled"}, selected("cancel")):
            context, result = await self.run_dialogue([{}], [text("姓名"), answer])
            proposal = result["output"]["form_proposal"]
            self.assertEqual(proposal["status"], "no_change")
            assert_non_executable(self, proposal)
            self.assertNotIn("fieldClarification", proposal)
            self.assertEqual(context.context["currentSchema"]["fields"], [])

    async def test_pause_preserves_pending_and_resume_requires_explicit_confirmation(self):
        context, result = await self.run_dialogue([{}], [text("姓名"), selected("pause")])
        pending = result["output"]["form_proposal"]
        self.assertEqual(pending["fieldClarification"]["fields"], [{"label": "姓名"}])
        self.assertFalse(pending["fieldClarification"]["isClarifyingField"])
        self.assertFalse(pending["fieldClarification"]["hasCurrentForm"])
        assert_non_executable(self, pending)
        context.context["requestId"] = "request-resume"
        context.inputs = {"resume_field_clarification": pending}
        resumed = await self.agent.prepare_form_requirement(context)
        self.assertEqual(resumed["status"], "completed", resumed)
        context.inputs = resumed["output"]
        context.clarification.request.side_effect = [selected("create-form"), selected("component:Input"), selected("later")]
        context.inputs = (await self.agent.collect_guidance(context))["output"]
        result = await self.agent.generate_confirmed_proposal(context)
        self.assertEqual(result["output"]["form_proposal"]["status"], "ready", result)
        context.native_capability.generate.assert_awaited_once()

    async def test_new_request_is_not_silently_used_as_field_value(self):
        context, result = await self.run_dialogue([{"label": "姓名"}], [text("修改表单标题为登记表"), selected("pause")])
        proposal = result["output"]["form_proposal"]
        self.assertEqual(proposal["fieldClarification"]["fields"], [{"label": "姓名"}])
        self.assertEqual(proposal["fieldClarification"]["queuedRequests"], ["修改表单标题为登记表"])
        self.assertIn("是否先完成", context.clarification.request.await_args_list[-1].kwargs["question"])
        assert_non_executable(self, proposal)

    async def test_continue_locked_field_keeps_new_request_pending(self):
        _, result = await self.run_dialogue([{"label": "姓名"}], [
            text("新增一个年龄字段"), selected("continue"), selected("component:Input"), selected("later")])
        proposal = result["output"]["form_proposal"]
        self.assertEqual(proposal["status"], "ready", result)
        self.assertEqual(len(proposal["actions"]), 1)
        self.assertIn("新增一个年龄字段", proposal["summary"])

    async def test_missing_sdk_after_confirmation_keeps_partial_metadata(self):
        context = self.context([{"label": "姓名"}], [])
        await self.confirm(context)
        del context.clarification
        result = await self.agent.generate_confirmed_proposal(context)
        proposal = result["output"]["form_proposal"]
        self.assertEqual(proposal["status"], "needs_clarification")
        self.assertEqual(proposal["fieldClarification"]["fields"], [{"label": "姓名"}])
        assert_non_executable(self, proposal)

    async def test_all_known_information_needs_no_more_questions(self):
        context, result = await self.run_dialogue([{"label": "姓名", "component_name": "Input", "required": True, "placeholder": "姓名"}], [])
        self.assertEqual(result["output"]["form_proposal"]["status"], "ready", result)
        context.clarification.request.assert_awaited_once()
        context.native_capability.generate.assert_awaited_once()

    async def test_only_host_authorized_components_are_recommended(self):
        context = self.context([{"label": "姓名"}], [selected("component:Input"), selected("later")])
        context.context["capabilities"]["components"] = {"Input": {"writableProps": ["label", "name", "required"]}, "NumberPicker": {"supported": False}}
        await self.confirm(context)
        result = await self.agent.generate_confirmed_proposal(context)
        self.assertEqual(result["output"]["form_proposal"]["status"], "ready", result)
        options = context.clarification.request.await_args_list[1].kwargs["options"]
        self.assertEqual([o["id"] for o in options if o["id"].startswith("component:")], ["component:Input"])

    async def test_unsupported_requirements_or_upload_are_not_dropped(self):
        for fields, answers, reason in (([{"label": "姓名"}], [], "新增字段暂不支持最大长度"),
                                        ([{"label": "附件"}], [text("上传")], "")):
            context, result = await self.run_dialogue(fields, answers, reason)
            proposal = result["output"]["form_proposal"]
            self.assertEqual(proposal["status"], "unsupported", result)
            assert_non_executable(self, proposal)
            context.native_capability.generate.assert_awaited_once()

    async def test_replay_has_identical_requests_and_values(self):
        context = self.context([{}], [])
        await self.confirm(context)
        answers = iter([text("姓名"), selected("component:Input"), selected("later")])
        record = {}
        async def respond(**kwargs):
            key = kwargs["key"]
            if key not in record:
                record[key] = (deepcopy(kwargs), next(answers))
            self.assertEqual(kwargs, record[key][0])
            return deepcopy(record[key][1])
        context.clarification.request.side_effect = respond
        before = deepcopy(context.inputs)
        first = await self.agent.generate_confirmed_proposal(context)
        second = await self.agent.generate_confirmed_proposal(context)
        self.assertEqual(first["output"], second["output"])
        self.assertEqual(before, context.inputs)
        self.assertEqual(len(record), 3)
        context.native_capability.generate.assert_awaited_once()

    async def test_snapshot_change_during_answer_rejects_generation(self):
        context = self.context([{"label": "姓名"}], [])
        await self.confirm(context)
        async def respond(**kwargs):
            context.context["target"]["revision"] = "changed"
            return selected("component:Input")
        context.clarification.request.side_effect = respond
        result = await self.agent.generate_confirmed_proposal(context)
        self.assertEqual(result["error_code"], "field_metadata_invalid")

    async def test_round_exhaustion_preserves_draft_without_generation(self):
        _, result = await self.run_dialogue([{}], [{"kind": "exhausted"}])
        proposal = result["output"]["form_proposal"]
        self.assertEqual(proposal["fieldClarification"]["status"], "paused")
        assert_non_executable(self, proposal)

    async def test_natural_language_pause_retains_new_request(self):
        _, result = await self.run_dialogue([{"label": "姓名"}], [text("先把上一个字段放一放，新增一个年龄字段")])
        proposal = result["output"]["form_proposal"]
        self.assertEqual(proposal["fieldClarification"]["queuedRequests"], ["新增一个年龄字段"])
        self.assertEqual(proposal["fieldClarification"]["status"], "paused")
        assert_non_executable(self, proposal)

    async def test_resume_rejects_changed_revision_without_model_call(self):
        context, result = await self.run_dialogue([{}], [selected("pause")])
        context.inputs = {"resume_field_clarification": result["output"]["form_proposal"]}
        context.context["target"]["revision"] = "different"
        resumed = await self.agent.prepare_form_requirement(context)
        self.assertEqual(resumed["error_code"], "field_metadata_resume_invalid")
        context.native_capability.generate.assert_awaited_once()

    async def test_missing_partial_requirements_fails_instead_of_guessing(self):
        context = self.context([{}], [])
        async def generate(**kwargs):
            return kwargs["compiler"]({"plan_items": [{"capability": "proposal.needs_clarification", "slots": {
                "request_intent": "field_change", "summary": "字段", "question": "字段？",
            }}]}, None)
        context.native_capability.generate.side_effect = generate
        result = await self.agent.prepare_form_requirement(context)
        self.assertEqual(result["status"], "failed")
        self.assertIn("field_requirements", result["summary"])
        context.clarification.request.assert_not_awaited()

    async def test_question_budget_is_not_permission_to_guess(self):
        context = self.context([{"label": "姓名"}], [text("随便一个框"), text("就普通的")])
        await self.confirm(context)
        module_name = self.agent.__package__ + ".form_generation.field_clarification"
        import importlib
        module = importlib.import_module(module_name)
        with patch.object(module, "MAX_QUESTIONS", 2):
            result = await self.agent.generate_confirmed_proposal(context)
        proposal = result["output"]["form_proposal"]
        self.assertEqual(proposal["fieldClarification"]["status"], "paused")
        self.assertNotIn("component_name", proposal["fieldClarification"]["fields"][0])
        assert_non_executable(self, proposal)

    async def test_multiple_fields_are_asked_in_stable_order(self):
        context, result = await self.run_dialogue([{"label": "姓名"}, {"label": "生日", "component_name": "DatePicker"}], [
            selected("component:Input"), selected("required:no"), text("请输入姓名"), selected("required:yes"), selected("later")])
        proposal = result["output"]["form_proposal"]
        self.assertEqual([a["payload"]["props"]["label"] for a in proposal["actions"]], ["姓名", "生日"])
        context.native_capability.generate.assert_awaited_once()
