"""在不安装平台 SDK 的情况下校验页面节点事件协议和完整表单输出。"""

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


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
        self.assertEqual(result["output"]["form_proposal"], proposal)
        generate_kwargs = context.native_capability.generate.await_args.kwargs
        self.assertTrue(generate_kwargs["allow_plan_items"])
        self.assertIn("根对象必须且只能是 {plan_items", " ".join(generate_kwargs["prompt_rules"]))
        self.assertIn("根对象除 plan_items 外不得包含其他字段", " ".join(generate_kwargs["prompt_rules"]))
        self.assertEqual(generate_kwargs["examples"][0]["output"]["plan_items"][0]["capability"], "proposal.begin")
        self.assertEqual(generate_kwargs["examples"][2]["output"]["plan_items"][0]["capability"], "proposal.needs_clarification")
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
        self.assertEqual(proposal["presentation"]["fieldCount"], 2)
        self.assertEqual(len(proposal["result"]["actions"]), 2)

    def test_missing_host_context_returns_non_executable_clarification(self):
        result = self.agent.compile_platform_proposal(
            {"capability": "proposal.begin", "slots": {"result_kind": "form_fields"}},
            context=SimpleNamespace(context={}),
        )
        proposal = result["output"]["form_proposal"]
        self.assertEqual(proposal["status"], "needs_clarification")
        self.assertEqual(proposal["diagnostics"][0]["code"], "HOST_CONTEXT_REQUIRED")
        self.assertIn("supportedActionVersions", proposal["question"])
        self.assertNotIn("result", proposal)

    def test_compiler_validation_keeps_reason_without_executable_output(self):
        from test_form_field_list import blank_context

        result = self.agent.compile_platform_proposal(
            {"capability": "proposal.begin", "slots": {"result_kind": "form_fields"}},
            context=SimpleNamespace(context=blank_context()),
        )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "form_proposal_validation_failed")
        self.assertIn("至少包含一个字段", result["summary"])
        self.assertNotIn("output", result)

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
