"""在不安装平台 SDK 的情况下校验页面节点事件协议和完整表单输出。"""

from collections import UserDict
from dataclasses import dataclass
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from test_form_field_list import apply_field_actions, assert_action_draft, assert_non_executable


class OutputPreviewTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        package_name = "form_preview_test_package"
        package = ModuleType(package_name)
        package.__path__ = [str(root)]
        sdk = ModuleType("specialized.builder.sdk")
        sdk.create_external_agent = MagicMock()
        cls.modules = patch.dict(sys.modules, {
            package_name: package,
            "specialized": ModuleType("specialized"),
            "specialized.builder": ModuleType("specialized.builder"),
            "specialized.builder.sdk": sdk,
        })
        cls.modules.start()
        cls.addClassCleanup(cls.modules.stop)
        spec = importlib.util.spec_from_file_location(
            f"{package_name}.agent_definition", root / "agent_definition.py"
        )
        cls.agent = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.agent
        spec.loader.exec_module(cls.agent)

    def test_agent_registers_one_final_proposal_pipeline(self):
        builder = MagicMock()
        for method in (
            "use_append_intent", "use_plan", "output_structured",
            "pipeline_step", "output_pipeline",
        ):
            getattr(builder, method).return_value = builder
        with patch.object(self.agent, "create_external_agent", return_value=builder):
            self.agent.register_agent(SimpleNamespace())
        steps = {call.kwargs["key"]: call.kwargs for call in builder.pipeline_step.call_args_list}
        self.assertEqual(list(steps), [self.agent.FORM_PROPOSAL_STEP])
        step = steps[self.agent.FORM_PROPOSAL_STEP]
        self.assertEqual(step["output_visibility"], "final_artifact")
        self.assertEqual(step["reasoning_visibility"], "trace_only")
        self.assertEqual(step["output_contract"], self.agent.FORM_PROPOSAL_CONTRACT)
        builder.output_structured.assert_called_once_with(
            kind="form_proposal", schema=self.agent.FORM_PROPOSAL_CONTRACT, schema_version="1",
        )
        pipelines = {call.kwargs["key"]: call.kwargs for call in builder.output_pipeline.call_args_list}
        pipeline = pipelines[self.agent.FORM_PROPOSAL_PIPELINE]
        self.assertEqual(pipeline["artifact_kind"], "form_proposal")
        self.assertEqual(pipeline["final_contract"], self.agent.FORM_PROPOSAL_CONTRACT)
        self.assertEqual(pipeline["steps"], [self.agent.FORM_PROPOSAL_STEP])

    def test_bootstrap_uses_revision_package_relative_import(self):
        root = Path(__file__).resolve().parents[1]
        from importlib import import_module

        for package_name in ("form_revision_a", "form_revision_b"):
            package = ModuleType(package_name)
            package.__path__ = [str(root)]
            with patch.dict(sys.modules, {package_name: package}):
                bootstrap = import_module(f"{package_name}.bootstrap")
                definition = import_module(f"{package_name}.agent_definition")
                compiler = import_module(f"{package_name}.form_generation.proposal")
                self.assertIs(bootstrap.register_agent, definition.register_agent)
                self.assertIs(definition.compile_form_proposal, compiler.compile_form_proposal)
                self.assertEqual(compiler.__package__, f"{package_name}.form_generation")
                context = SimpleNamespace()
                with patch.object(bootstrap, "register_agent") as register:
                    bootstrap.register_specialized_agent(context)
                register.assert_called_once_with(context)

    async def test_proposal_generation_publishes_only_final_event(self):
        proposal = {
            "protocol": "form-agent.v1", "status": "no_change", "proposalId": "proposal-test",
            "target": {"baseRevision": "rev-1"}, "summary": "当前配置已满足要求。", "diagnostics": [],
        }
        context = SimpleNamespace(
            inputs="检查当前表单", context={"target": {"revision": "rev-1"}},
            native_capability=SimpleNamespace(generate=AsyncMock(return_value={
                "status": "completed", "output": {"form_proposal": proposal},
            })),
            event_publisher=AsyncMock(),
        )
        result = await self.agent.generate_form_proposal(context)
        self.assertEqual(result["output"], {"form_proposal": proposal})
        generate_kwargs = context.native_capability.generate.await_args.kwargs
        self.assertTrue(generate_kwargs["allow_plan_items"])
        self.assertIn("根对象必须且只能是 {plan_items", " ".join(generate_kwargs["prompt_rules"]))
        self.assertIn("根对象除 plan_items 外不得包含其他字段", " ".join(generate_kwargs["prompt_rules"]))
        self.assertEqual(generate_kwargs["examples"][0]["output"]["plan_items"][0]["capability"], "proposal.begin")
        self.assertTrue(any(example["output"]["plan_items"][0]["capability"] == "proposal.needs_clarification" for example in generate_kwargs["examples"]))
        context.event_publisher.assert_awaited_once_with("form.proposal.completed", {
            "block_id": "form_proposal", "title": "表单设计提案", "status": "no_change", "proposal": proposal,
        })

    async def test_generation_executes_compiler_with_keyword_context(self):
        from test_form_field_list import blank_context

        context = SimpleNamespace(inputs="生成入职表", context=blank_context())

        async def generate(**kwargs):
            return kwargs["compiler"](
                ir_payload=kwargs["examples"][0]["output"], context=context,
            )

        context.native_capability = SimpleNamespace(generate=generate)
        result = await self.agent.generate_form_proposal(context)
        proposal = result["output"]["form_proposal"]
        self.assertEqual(proposal["status"], "ready")
        assert_action_draft(self, proposal)
        self.assertEqual(len(proposal["actions"]), 2)

    async def test_output_uses_registered_presentation_kind_without_a_duplicate_component(self):
        from test_form_field_list import blank_context
        import json

        context = SimpleNamespace(inputs="生成学生表", context=blank_context(), event_publisher=AsyncMock())

        async def generate(**kwargs):
            return kwargs["compiler"](kwargs["examples"][0]["output"], None)

        context.native_capability = SimpleNamespace(generate=generate)
        result = await self.agent.generate_form_proposal(context)
        proposal = result["output"]["form_proposal"]
        self.assertEqual(proposal["presentation"]["kind"], "shared.form-create-confirm")
        self.assertEqual(set(result["output"]), {"form_proposal"})
        self.assertEqual(json.dumps(result["output"]).count('"proposalId"'), 1)
        self.assertNotIn("component", proposal)
        self.assertNotIn("component", context.event_publisher.await_args.args[1])

    async def test_blank_schema_1_1_0_uses_registered_field_presentation(self):
        from test_form_field_list import blank_context

        host = blank_context()
        host["schemaVersion"] = host["currentSchema"]["schemaVersion"] = "1.1.0"
        context = SimpleNamespace(inputs="生成学生表", context=host, event_publisher=AsyncMock())

        async def generate(**kwargs):
            return kwargs["compiler"](kwargs["examples"][0]["output"], None)

        context.native_capability = SimpleNamespace(generate=generate)
        result = await self.agent.generate_form_proposal(context)
        proposal = result["output"]["form_proposal"]
        self.assertEqual(proposal["schemaVersion"], "1.1.0")
        self.assertEqual(proposal["status"], "ready")
        self.assertEqual(proposal["mode"], "replace_empty_form")
        self.assertEqual(proposal["presentation"]["kind"], "shared.form-create-confirm")
        assert_action_draft(self, proposal)
        self.assertEqual([action["payload"]["clientRef"] for action in proposal["actions"]],
                         ["employee-name", "hire-date"])
        self.assertNotIn("component", result["output"])
        self.assertEqual(context.event_publisher.await_args.args[1]["proposal"], proposal)

    async def test_native_result_objects_keep_proposal_events_and_diagnostics(self):
        from test_form_field_list import blank_context

        @dataclass(frozen=True)
        class StepResult:
            status: str
            output: object = None
            summary: str = ""
            diagnostics: object = None
            error_code: str = ""
            abort_run: bool = False
            artifact_ref: str = ""

        for result_type in (dict, UserDict, SimpleNamespace, StepResult):
            with self.subTest(result_type=result_type.__name__):
                host = blank_context()
                host["schemaVersion"] = host["currentSchema"]["schemaVersion"] = "1.1.0"
                context = SimpleNamespace(inputs="生成学生表", context=host, event_publisher=AsyncMock())
                native_diagnostics = [{"code": "NATIVE_VALIDATED"}]

                async def generate(**kwargs):
                    compiled = kwargs["compiler"](kwargs["examples"][0]["output"], None)
                    return result_type(**compiled, diagnostics=native_diagnostics)

                context.native_capability = SimpleNamespace(generate=generate)
                result = await self.agent.generate_form_proposal(context)
                self.assertIsInstance(result, dict)
                self.assertEqual(result["status"], "completed")
                proposal = result["output"]["form_proposal"]
                self.assertEqual(proposal["presentation"]["kind"], "shared.form-create-confirm")
                assert_action_draft(self, proposal)
                self.assertEqual(len(proposal["actions"]), 2)
                self.assertNotIn("component", result["output"])
                self.assertEqual(result["diagnostics"][0], native_diagnostics[0])
                self.assertEqual([item["stage"] for item in result["diagnostics"][1:]], ["handler", "compiler"])
                self.assertEqual(result["diagnostics"][1]["native_result_type"], result_type.__name__)
                self.assertEqual(native_diagnostics, [{"code": "NATIVE_VALIDATED"}])
                context.event_publisher.assert_awaited_once()
                self.assertEqual(context.event_publisher.await_args.args[1]["proposal"], proposal)
                self.assertNotIn("component", context.event_publisher.await_args.args[1])

    async def test_failed_native_result_object_preserves_failure_metadata(self):
        from test_form_field_list import blank_context

        failure = SimpleNamespace(
            status="failed", output=None, summary="原生生成失败", error_code="native_generation_failed",
            diagnostics=[{"code": "NATIVE_FAILED"}], abort_run=True, artifact_ref="failure-ref",
        )
        context = SimpleNamespace(
            inputs="生成学生表", context=blank_context(), event_publisher=AsyncMock(),
            native_capability=SimpleNamespace(generate=AsyncMock(return_value=failure)),
        )
        result = await self.agent.generate_form_proposal(context)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["summary"], failure.summary)
        self.assertEqual(result["error_code"], failure.error_code)
        self.assertTrue(result["abort_run"])
        self.assertEqual(result["artifact_ref"], failure.artifact_ref)
        self.assertEqual(result["diagnostics"][0], failure.diagnostics[0])
        self.assertEqual(result["diagnostics"][1]["stage"], "handler")
        self.assertNotIn("component", result.get("output") or {})
        self.assertEqual(failure.diagnostics, [{"code": "NATIVE_FAILED"}])
        context.event_publisher.assert_not_awaited()

    async def test_field_action_payloads_preserve_labels_and_option_values(self):
        from test_form_field_list import blank_context

        context = SimpleNamespace(inputs="创建员工表", context=blank_context(), event_publisher=AsyncMock())

        async def generate(**kwargs):
            ir = kwargs["examples"][0]["output"]
            ir["plan_items"].append({"capability": "form.field.define", "slots": {
                "client_ref": "employment-type", "component_name": "SelectSingle",
                "label": "用工类型", "name": "employment_type",
                "options": [{"label": "正式员工", "value": "regular"}, {"label": "实习生", "value": "intern"}],
            }})
            return kwargs["compiler"](ir, context)

        context.native_capability = SimpleNamespace(generate=generate)
        result = await self.agent.generate_form_proposal(context)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["summary"], "创建包含姓名和入职日期的员工入职登记表。")
        proposal = result["output"]["form_proposal"]
        assert_action_draft(self, proposal)
        self.assertEqual(proposal["actions"][2]["payload"]["props"]["options"][0],
                         {"label": "正式员工", "value": "regular"})
        self.assertEqual(proposal["actions"][2]["payload"]["props"]["options"][1]["value"], "intern")
        self.assertEqual(proposal["presentation"]["kind"], "shared.form-create-confirm")
        self.assertEqual(proposal["presentation"]["title"], "员工入职登记表")
        self.assertEqual(len(proposal["actions"]), 3)
        self.assertEqual(set(result["output"]), {"form_proposal"})
        context.event_publisher.assert_awaited_once_with("form.proposal.completed", {
            "block_id": "form_proposal", "title": "表单设计提案", "status": "ready",
            "proposal": proposal,
        })

    async def test_saved_canvas_insertion_publishes_only_the_new_action_draft(self):
        from test_existing_canvas import saved_context

        context = SimpleNamespace(
            inputs="在学号后新增监护人字段", context=saved_context(),
            event_publisher=AsyncMock(),
        )

        async def generate(**kwargs):
            example = next(item for item in kwargs["examples"] if item["input"].startswith("在学号后新增监护人字段"))
            return kwargs["compiler"](ir_payload=example["output"], context=context)

        context.native_capability = SimpleNamespace(generate=generate)
        result = await self.agent.generate_form_proposal(context)
        proposal = result["output"]["form_proposal"]
        self.assertEqual(proposal["schemaVersion"], "1.1.0")
        assert_action_draft(self, proposal)
        self.assertEqual(proposal["mode"], "append")
        self.assertEqual(len(proposal["actions"]), 1)
        payload = proposal["actions"][0]["payload"]
        self.assertEqual(payload["target"], {"kind": "root", "index": 2})
        self.assertEqual(payload["clientRef"], "guardian")
        self.assertEqual(payload["props"]["label"], "监护人")
        fields = apply_field_actions(context.context["currentSchema"]["fields"], proposal["actions"])
        self.assertEqual(len(fields), 8)
        self.assertEqual(fields[:2] + fields[3:], context.context["currentSchema"]["fields"])
        self.assertEqual(context.event_publisher.await_count, 1)
        self.assertEqual(context.event_publisher.await_args.args[1]["proposal"], proposal)
        self.assertNotIn("component", result["output"])

    async def test_missing_host_context_returns_non_executable_clarification(self):
        context = SimpleNamespace(inputs="新增字段", context={}, event_publisher=AsyncMock())

        async def generate(**kwargs):
            return kwargs["compiler"](kwargs["examples"][0]["output"], context)

        context.native_capability = SimpleNamespace(generate=generate)
        result = await self.agent.generate_form_proposal(context)
        proposal = result["output"]["form_proposal"]
        self.assertEqual(proposal["status"], "needs_clarification")
        self.assertEqual(proposal["diagnostics"][0]["code"], "HOST_CONTEXT_REQUIRED")
        self.assertIn("supportedActionVersions", proposal["question"])
        assert_non_executable(self, proposal)
        self.assertNotIn("component", result["output"])
        context.event_publisher.assert_awaited_once_with("form.proposal.completed", {
            "block_id": "form_proposal", "title": "表单设计提案", "status": "needs_clarification", "proposal": proposal,
        })

    async def test_compiler_validation_keeps_reason_without_executable_output(self):
        from test_form_field_list import blank_context

        context = SimpleNamespace(inputs="生成表单", context=blank_context(), event_publisher=AsyncMock())

        async def generate(**kwargs):
            return kwargs["compiler"](
                {"capability": "proposal.begin", "slots": {"result_kind": "form_fields"}}, context,
            )

        context.native_capability = SimpleNamespace(generate=generate)
        result = await self.agent.generate_form_proposal(context)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "form_proposal_validation_failed")
        self.assertIn("至少包含一个字段", result["summary"])
        self.assertNotIn("output", result)

    async def test_student_fields_with_snake_case_refs_emit_a_complete_confirmation_card(self):
        from test_form_field_list import blank_context

        definitions = [
            ("student_name", "姓名", "Input"), ("student_no", "学号", "Input"),
            ("gender", "性别", "SelectSingle"), ("birth_date", "出生日期", "DatePicker"),
            ("class_name", "班级", "Input"), ("contact_phone", "联系电话", "Input"),
            ("home_address", "家庭住址", "Input.TextArea"), ("remarks", "备注", "Input.TextArea"),
        ]
        items = [{"capability": "proposal.begin", "slots": {
            "summary": "生成学生信息表。", "result_kind": "form_fields", "mode": "replace_empty_form",
        }}]
        for ref, label, component in definitions:
            slots = {"client_ref": ref, "component_name": component, "label": label, "name": ref}
            if component == "SelectSingle":
                slots["options"] = [{"label": "男", "value": "male"}, {"label": "女", "value": "female"}]
            items.append({"capability": "form.field.define", "slots": slots})
        host = blank_context()
        host["schemaVersion"] = host["currentSchema"]["schemaVersion"] = "1.1.0"
        context = SimpleNamespace(inputs="生成学生信息表", context=host, event_publisher=AsyncMock())

        async def generate(**kwargs):
            compiled = kwargs["compiler"]({"plan_items": items}, None)
            return SimpleNamespace(**compiled)

        context.native_capability = SimpleNamespace(generate=generate)
        result = await self.agent.generate_form_proposal(context)
        self.assertEqual(result["status"], "completed", result)
        proposal = result["output"]["form_proposal"]
        refs = [ref for ref, _, _ in definitions]
        self.assertEqual([action["payload"]["clientRef"] for action in proposal["actions"]], refs)
        self.assertEqual(proposal["presentation"]["kind"], "shared.form-create-confirm")
        assert_action_draft(self, proposal)
        self.assertEqual(len(proposal["actions"]), 8)
        self.assertEqual([action["payload"]["props"]["label"] for action in proposal["actions"]],
                         [label for _, label, _ in definitions])
        self.assertEqual(proposal["actions"][2]["payload"]["props"]["options"],
                         [{"label": "男", "value": "male"}, {"label": "女", "value": "female"}])
        self.assertNotIn("component", result["output"])
        context.event_publisher.assert_awaited_once()

    async def test_compiler_failure_aborts_run_instead_of_reaching_generic_final_response(self):
        from test_form_field_list import blank_context

        compiler_result = self.agent.compile_platform_proposal({
            "capability": "proposal.begin", "slots": {"result_kind": "form_fields"},
        }, blank_context())
        self.assertEqual(compiler_result["status"], "failed")
        self.assertTrue(compiler_result.get("abort_run"), compiler_result)
        for error_code in ("form_proposal_validation_failed", "native_capability_invalid_ir"):
            with self.subTest(error_code=error_code):
                context = SimpleNamespace(
                    inputs="生成学生表", context=blank_context(), event_publisher=AsyncMock(),
                    native_capability=SimpleNamespace(generate=AsyncMock(return_value=SimpleNamespace(
                        status="failed", error_code=error_code, summary="校验未通过：具体原因。", abort_run=False,
                    ))),
                )
                result = await self.agent.generate_form_proposal(context)
                self.assertTrue(result.get("abort_run"), result)
                self.assertEqual(result["error_code"], error_code)
                self.assertEqual(result["summary"], "校验未通过：具体原因。")
                self.assertNotIn("component", result.get("output") or {})
                context.event_publisher.assert_not_awaited()

    async def test_event_publishers_support_sync_and_async_fallback(self):
        payload = {"block_id": "form_proposal"}
        publisher = MagicMock()
        emitter = AsyncMock()
        await self.agent._publish_event(SimpleNamespace(
            event_publisher=publisher, emit=emitter,
        ), "form.proposal.completed", payload)
        publisher.assert_called_once_with("form.proposal.completed", payload)
        emitter.assert_not_awaited()
        await self.agent._publish_event(SimpleNamespace(emit=emitter), "form.proposal.completed", payload)
        emitter.assert_awaited_once_with("form.proposal.completed", payload)


if __name__ == "__main__":
    unittest.main()
