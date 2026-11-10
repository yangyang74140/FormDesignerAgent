"""在不安装平台 SDK 的情况下校验页面节点事件协议和完整表单输出。"""

import importlib.util
import json
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

    def test_node_display_previews_form_artifacts_and_keeps_final_artifacts(self):
        builder = MagicMock()
        for method in (
            "use_append_intent", "use_plan", "output_structured",
            "pipeline_step", "output_pipeline",
        ):
            getattr(builder, method).return_value = builder
        with patch.object(self.agent, "create_external_agent", return_value=builder):
            self.agent.register_agent(SimpleNamespace())
        steps = {call.kwargs["key"]: call.kwargs for call in builder.pipeline_step.call_args_list}
        for key, contract in (
            (self.agent.FORM_SKELETON_STEP, self.agent.FORM_SKELETON_CONTRACT),
            (self.agent.FORM_HYDRATE_STEP, self.agent.FORM_FIELD_BATCH_CONTRACT),
        ):
            with self.subTest(step=key):
                self.assertEqual(steps[key]["output_visibility"], "preview")
                self.assertEqual(steps[key]["reasoning_visibility"], "visible")
                self.assertEqual(steps[key]["output_type"], "json")
                self.assertEqual(steps[key]["output_contract"], contract)
        for key in (self.agent.FORM_VALIDATE_STEP, self.agent.FORM_ACTION_STEP):
            self.assertEqual(steps[key]["output_visibility"], "final_artifact")
        self.assertEqual(steps[self.agent.FORM_VALIDATE_STEP]["completed_title"], "表单结构已校验")
        builder.output_structured.assert_called_once_with(
            kind="form_output", schema=self.agent.FORM_OUTPUT_CONTRACT, schema_version="1",
        )
        pipelines = {call.kwargs["key"]: call.kwargs for call in builder.output_pipeline.call_args_list}
        pipeline = pipelines[self.agent.FORM_PIPELINE]
        self.assertEqual(pipeline["artifact_kind"], "form_output")
        self.assertEqual(pipeline["final_contract"], self.agent.FORM_OUTPUT_CONTRACT)
        self.assertEqual(pipeline["steps"], [
            self.agent.FORM_SKELETON_STEP, self.agent.FORM_HYDRATE_STEP, self.agent.FORM_VALIDATE_STEP,
        ])

    async def test_page_node_events_preserve_complete_form_schema(self):
        agent = self.agent
        skeleton_result = agent.compile_form_skeleton({"plan_items": [
            {"capability": "form.create", "slots": {"title": "学生信息表"}},
            *[
                {"capability": "form.skeleton.add_field", "slots": {
                    "componentName": component, "field_key": key, "purpose": label,
                }}
                for component, key, label in (
                    ("Input", "name", "姓名"),
                    ("SelectSingle", "gender", "性别"),
                    ("CheckboxGroup", "interests", "兴趣"),
                )
            ],
        ]})
        context = SimpleNamespace(
            root_inputs="生成学生信息表", inputs={},
            native_capability=SimpleNamespace(generate=AsyncMock(return_value=skeleton_result)),
            event_publisher=AsyncMock(),
        )
        skeleton_output = await agent.generate_form_skeleton(context)
        schema = skeleton_result["output"]["skeleton_json"]
        for field in schema["fields"]:
            self.assertEqual(field["componentCategory"], "field")
        self.assertEqual(skeleton_output["output"]["skeleton_json"], schema)
        context.event_publisher.assert_awaited_once_with("page_output.skeleton", {
            "block_id": "page_output", "title": "学生信息表", "status": "generating",
            "skeleton_json": schema, "skeleton_source": "external_native_capability",
        })
        context.inputs = skeleton_output
        hydrated_result = agent.compile_form_field_hydration({"plan_items": [
            {"capability": "form.field.configure", "slots": {
                "field_key": key, "config": config,
            }}
            for key, config in (
                ("name", {"label": "姓名", "required": True}),
                ("gender", {"options": [{"value": "1", "label": "选项1"}]}),
                ("interests", {"options": [{"value": "2", "label": "选项2"}]}),
            )
        ]}, context)
        context.native_capability.generate.return_value = hydrated_result
        fields_output = await agent.hydrate_form_fields(context)
        preview = json.loads(json.dumps(fields_output["output"], ensure_ascii=False))
        hydrated_schema = hydrated_result["output"]["form_schema"]
        for field in hydrated_schema["fields"]:
            self.assertEqual(field["componentCategory"], "field")
        self.assertEqual(preview["skeleton_json"], schema)
        self.assertEqual(preview["form_schema"], hydrated_schema)
        self.assertNotIn("hydrated_fields", hydrated_result["output"])
        self.assertNotIn("hydrated_fields", preview)
        self.assertTrue(preview["form_schema"]["fields"][0]["props"]["required"])
        for field in preview["form_schema"]["fields"][1:]:
            option = field["props"]["options"]["dataSource"][0]
            self.assertEqual(set(option), {"primaryKey", "value", "label", "activeKey", "color", "disabled"})
        self.assertEqual(context.event_publisher.await_count, 4)
        for index, (call, field) in enumerate(zip(
            context.event_publisher.await_args_list[1:], preview["form_schema"]["fields"],
        ), start=1):
            self.assertEqual(call.args, ("page_output.node.completed", {
                "block_id": "page_output", "title": "组件生成", "status": "generating",
                "node_id": field["id"], "component_name": field["componentName"],
                "component_index": index, "component_total": 3, "node": field,
            }))
        context.inputs = fields_output
        final = await agent.finalize_form_output(context)
        self.assertEqual(final["output"]["form_schema_json"], hydrated_schema)
        for field in final["output"]["form_schema_json"]["fields"]:
            self.assertEqual(field["componentCategory"], "field")
        self.assertEqual(final["output"]["output_kind"], "form_schema_json")
        self.assertNotIn("page_schema_json", final["output"])
        self.assertEqual(final["output"]["validation"]["field_count"], 3)
        self.assertEqual([call.args[0] for call in context.event_publisher.await_args_list], [
            "page_output.skeleton",
            *["page_output.node.completed"] * 3,
            "page_output.completed",
        ])
        self.assertEqual(context.event_publisher.await_args.args, ("page_output.completed", {
            "block_id": "page_output", "title": "表单生成", "status": "completed",
            "output_kind": "form_schema_json", "form_schema_json": hydrated_schema,
            "validation": final["output"]["validation"],
        }))

    def test_final_schema_requires_category_from_component_metadata(self):
        for component in ("Input", "SelectSingle", "CheckboxGroup"):
            for category in ("missing", "field", "container", None):
                with self.subTest(component=component, category=category):
                    field = {
                        "id": "fld_test", "componentName": component,
                        "title": "测试字段", "props": {"label": "测试字段"},
                    }
                    if category != "missing":
                        field["componentCategory"] = category
                    schema = self.agent.finalize_form_schema({"fields": [field]})
                    self.assertEqual(schema["fields"], [{**field, "componentCategory": "field"}])

    async def test_creation_failure_does_not_publish_completed_nodes(self):
        failure = {"status": "failed", "error_code": "generation_failed"}
        context = SimpleNamespace(
            root_inputs="生成表单", inputs={},
            native_capability=SimpleNamespace(generate=AsyncMock(return_value=failure)),
            event_publisher=AsyncMock(),
        )
        self.assertIs(await self.agent.generate_form_skeleton(context), failure)
        context.inputs = self.agent.compile_form_skeleton({"plan_items": [
            {"capability": "form.skeleton.add_field", "slots": {
                "componentName": "Input", "field_key": "name", "purpose": "姓名",
            }},
        ]})
        self.assertIs(await self.agent.hydrate_form_fields(context), failure)
        context.inputs = {"form_schema": {"fields": []}}
        final = await self.agent.finalize_form_output(context)
        self.assertEqual(final["status"], "failed")
        context.event_publisher.assert_not_awaited()

    async def test_modify_retains_form_event_and_action(self):
        action = {"schema_version": "form_actions.v1", "actions": []}
        context = SimpleNamespace(event_publisher=AsyncMock())
        with patch.object(self.agent, "build_form_actions", new=AsyncMock(return_value={
            "status": "completed", "output": {"form_action_json": action},
        })):
            result = await self.agent.generate_form_action(context)
        self.assertEqual(result["output"]["output_kind"], "form_action_json")
        self.assertEqual(result["output"]["form_action_json"], action)
        context.event_publisher.assert_awaited_once_with("form_output.completed", {
            "block_id": "form_output", "title": "修改表单", "status": "completed",
            "output_kind": "form_action_json", "form_action_json": action,
            "validation": result["output"]["validation"],
        })

    async def test_event_publishers_support_sync_and_async_fallback(self):
        payload = {"block_id": "page_output"}
        publisher = MagicMock()
        emitter = AsyncMock()
        await self.agent._publish_event(SimpleNamespace(
            event_publisher=publisher, emit=emitter,
        ), "page_output.skeleton", payload)
        publisher.assert_called_once_with("page_output.skeleton", payload)
        emitter.assert_not_awaited()
        await self.agent._publish_event(SimpleNamespace(emit=emitter), "page_output.skeleton", payload)
        emitter.assert_awaited_once_with("page_output.skeleton", payload)


if __name__ == "__main__":
    unittest.main()
