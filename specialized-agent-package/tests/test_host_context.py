"""Exercise the handler/compiler boundary with independent runtime contexts."""

import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from test_form_field_list import assert_non_executable, blank_context
import test_output_preview


class HostContextBoundaryTests(IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        test_output_preview.OutputPreviewTests.setUpClass.__func__(cls)

    def host(self):
        host = blank_context()
        host["schemaVersion"] = "1.1.0"
        host["currentSchema"]["schemaVersion"] = "1.1.0"
        return host

    async def test_compiler_uses_handler_snapshot_with_different_callback_contexts(self):
        host = self.host()
        stale = self.host()
        stale["requestId"] = "stale-request"
        stale["target"] = {"schemaId": "stale-form", "revision": "stale-revision"}
        callbacks = [
            None,
            {},
            {"user_input": "生成学生表", "host_context": host},
            SimpleNamespace(context={}),
            stale,
        ]
        for callback in callbacks:
            for keyword in (False, True):
                with self.subTest(callback=type(callback).__name__, keyword=keyword):
                    step = SimpleNamespace(inputs="生成学生表", context=host)

                    async def generate(**kwargs):
                        compiler = kwargs["compiler"]
                        ir = kwargs["examples"][0]["output"]
                        return compiler(ir_payload=ir, context=callback) if keyword else compiler(ir, callback)

                    step.native_capability = SimpleNamespace(generate=generate)
                    result = await self.agent.generate_form_proposal(step)
                    proposal = result["output"]["form_proposal"]
                    self.assertEqual(proposal["status"], "ready", result)
                    self.assertEqual(proposal["schemaVersion"], "1.1.0")
                    self.assertEqual(proposal["requestId"], host["requestId"])
                    self.assertEqual(proposal["target"]["schemaId"], host["target"]["schemaId"])
                    self.assertEqual(proposal["target"]["baseRevision"], host["target"]["revision"])
                    self.assertEqual(len(proposal["actions"]), 2)

    async def test_snapshot_is_isolated_from_generator_and_live_context_mutation(self):
        host = self.host()
        expected = deepcopy(host)
        step = SimpleNamespace(inputs="生成学生表", context=host)

        async def generate(**kwargs):
            kwargs["input_data"]["host_context"]["target"].clear()
            kwargs["input_data"]["host_context"]["currentSchema"].clear()
            host.clear()
            return kwargs["compiler"](kwargs["examples"][0]["output"], None)

        step.native_capability = SimpleNamespace(generate=generate)
        result = await self.agent.generate_form_proposal(step)
        proposal = result["output"]["form_proposal"]
        self.assertEqual(proposal["status"], "ready", result)
        self.assertEqual(proposal["requestId"], expected["requestId"])
        self.assertEqual(proposal["target"]["baseRevision"], expected["target"]["revision"])

    async def test_concurrent_runs_keep_their_own_host_snapshot(self):
        started = 0
        all_started = asyncio.Event()

        async def run(index):
            host = self.host()
            host["requestId"] = f"request-{index}"
            host["target"] = {"schemaId": f"form-{index}", "revision": f"rev-{index}"}
            step = SimpleNamespace(inputs="生成学生表", context=host)

            async def generate(**kwargs):
                nonlocal started
                started += 1
                if started == 2:
                    all_started.set()
                await all_started.wait()
                return kwargs["compiler"](kwargs["examples"][0]["output"], None)

            step.native_capability = SimpleNamespace(generate=generate)
            result = await self.agent.generate_form_proposal(step)
            return result["output"]["form_proposal"]

        proposals = await asyncio.wait_for(asyncio.gather(run(1), run(2)), timeout=2)
        for index, proposal in enumerate(proposals, 1):
            self.assertEqual(proposal["status"], "ready", proposal)
            self.assertEqual(proposal["requestId"], f"request-{index}")
            self.assertEqual(proposal["target"], {"schemaId": f"form-{index}", "baseRevision": f"rev-{index}"})

    async def test_missing_handler_snapshot_cannot_borrow_callback_context(self):
        step = SimpleNamespace(inputs="生成学生表", context={}, event_publisher=AsyncMock())

        async def generate(**kwargs):
            return kwargs["compiler"](kwargs["examples"][0]["output"], self.host())

        step.native_capability = SimpleNamespace(generate=generate)
        result = await self.agent.generate_form_proposal(step)
        proposal = result["output"]["form_proposal"]
        self.assertEqual(proposal["status"], "needs_clarification", result)
        self.assertEqual(proposal["diagnostics"][0]["code"], "HOST_CONTEXT_REQUIRED")
        assert_non_executable(self, proposal)
        self.assertNotIn("component", result["output"])
        traces = result["diagnostics"]
        self.assertEqual([entry["stage"] for entry in traces], ["handler", "compiler"])
        self.assertFalse(traces[0]["present"]["currentSchema"])
        self.assertTrue(traces[1]["present"]["currentSchema"])
        self.assertEqual(traces[1]["compile_source"], "handler_snapshot")
        step.event_publisher.assert_awaited_once()

    async def test_context_diagnostics_contain_only_safe_metadata(self):
        secret = "private-business-data-not-for-diagnostics"
        host = self.host()
        host["requestId"] = secret
        host["target"]["schemaId"] = secret
        host["currentSchema"]["props"] = {"description": secret}
        host["request_token"] = secret
        host[secret] = {"token": secret}
        step = SimpleNamespace(inputs=secret, context=host, event_publisher=AsyncMock())
        native_diagnostic = {"code": "NATIVE_VALIDATED", "message": "IR validated"}

        async def generate(**kwargs):
            result = kwargs["compiler"](kwargs["examples"][0]["output"], {"host_context": host, secret: secret})
            result["diagnostics"] = [native_diagnostic]
            return result

        step.native_capability = SimpleNamespace(generate=generate)
        result = await self.agent.generate_form_proposal(step)
        self.assertEqual(result["diagnostics"][0], native_diagnostic)
        traces = result["diagnostics"][1:]
        self.assertEqual([entry["stage"] for entry in traces], ["handler", "compiler"])
        self.assertTrue(all(entry["code"] == "FORM_HOST_CONTEXT_TRACE" for entry in traces))
        self.assertEqual(traces[0]["input_type"], "SimpleNamespace")
        self.assertEqual(traces[0]["context_type"], "dict")
        self.assertIn("currentSchema", traces[0]["keys"])
        self.assertEqual(traces[1]["keys"], ["host_context"])
        serialized = json.dumps(result["diagnostics"])
        self.assertNotIn(secret, serialized)
        self.assertNotIn("request_token", serialized)
        self.assertNotIn("diagnostics", result["output"])
        step.event_publisher.assert_awaited_once()
        self.assertNotIn("diagnostics", step.event_publisher.await_args.args[1])

    async def test_generation_failure_keeps_native_and_handler_diagnostics(self):
        failure = {"status": "failed", "error_code": "native_generation_failed", "diagnostics": [{"code": "NATIVE_FAILED"}]}
        step = SimpleNamespace(
            inputs="生成学生表", context=self.host(), event_publisher=AsyncMock(),
            native_capability=SimpleNamespace(generate=AsyncMock(return_value=failure)),
        )
        result = await self.agent.generate_form_proposal(step)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], failure["error_code"])
        self.assertEqual(result["diagnostics"][0], failure["diagnostics"][0])
        self.assertEqual(result["diagnostics"][1]["stage"], "handler")
        self.assertTrue(result["diagnostics"][1]["present"]["currentSchema"])
        self.assertEqual(failure["diagnostics"], [{"code": "NATIVE_FAILED"}])
        step.event_publisher.assert_not_awaited()
