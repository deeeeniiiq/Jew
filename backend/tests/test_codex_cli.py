"""Offline contract checks for the ChatGPT-authenticated Codex intermediary."""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.agent.chatgpt_auth import ChatGPTError
from app.agent.codex_cli import CodexCLIClient, _command


class CodexCLIStatusTests(unittest.IsolatedAsyncioTestCase):
    async def test_status_reads_stderr_without_publishing_it(self):
        with patch("app.agent.codex_cli._command", new=AsyncMock(return_value=(0, "\nLogged in using ChatGPT\n"))) as command:
            result = await CodexCLIClient().status()
        self.assertEqual(result, {"installed": True, "authenticated": True, "method": "chatgpt"})
        self.assertTrue(command.await_args.kwargs["include_stderr"])

    async def test_api_key_login_is_not_accepted(self):
        with patch("app.agent.codex_cli._command", new=AsyncMock(return_value=(0, "Logged in using an API key"))):
            result = await CodexCLIClient().status()
        self.assertFalse(result["authenticated"])
        self.assertEqual(result["method"], "other")

    async def test_model_catalog_only_advertises_automatic(self):
        client = CodexCLIClient()
        with patch.object(client, "status", new=AsyncMock(return_value={"installed": True, "authenticated": True})):
            models = await client.list_models()
        self.assertEqual([item["model"] for item in models], ["codex-default"])

    async def test_missing_login_rejected(self):
        client = CodexCLIClient()
        with patch.object(client, "status", new=AsyncMock(return_value={"installed": True, "authenticated": False})):
            with self.assertRaises(ChatGPTError) as ctx:
                await client.list_models()
        self.assertEqual(ctx.exception.code, "codex_login_required")

    async def test_environment_api_keys_stripped(self):
        with patch("app.agent.codex_cli._executable", return_value=sys.executable), \
                patch("app.agent.codex_cli.asyncio.create_subprocess_exec", wraps=asyncio.create_subprocess_exec) as spawn, \
                patch.dict("os.environ", {"OPENAI_API_KEY": "sensitive", "CODEX_API_KEY": "sensitive",
                                          "KG_DESKTOP_TOKEN": "private-desktop-session",
                                          "GITHUB_TOKEN": "private-github-key", "CODEX_HOME": "example-codex-home"}):
            code, output = await _command(["-c", "import sys; sys.stderr.write('Logged in using ChatGPT')"], include_stderr=True)
        self.assertEqual((code, output.strip()), (0, "Logged in using ChatGPT"))
        self.assertNotIn("OPENAI_API_KEY", spawn.await_args.kwargs["env"])
        self.assertNotIn("CODEX_API_KEY", spawn.await_args.kwargs["env"])
        self.assertNotIn("KG_DESKTOP_TOKEN", spawn.await_args.kwargs["env"])
        self.assertNotIn("GITHUB_TOKEN", spawn.await_args.kwargs["env"])
        self.assertEqual(spawn.await_args.kwargs["env"]["CODEX_HOME"], "example-codex-home")

    async def test_output_is_bounded_while_child_is_running(self):
        with patch("app.agent.codex_cli._executable", return_value=sys.executable), \
                patch("app.agent.codex_cli.MAX_OUTPUT_BYTES", 1024):
            with self.assertRaises(ChatGPTError) as ctx:
                await _command(["-c", "import sys; sys.stdout.buffer.write(b'x' * 65536); sys.stdout.flush()"], timeout=10)
        self.assertEqual(ctx.exception.code, "codex_invalid_response")

    async def test_excessive_prompt_is_rejected_before_launch(self):
        with patch("app.agent.codex_cli.MAX_PROMPT_BYTES", 5), \
                patch("app.agent.codex_cli.asyncio.create_subprocess_exec", new=AsyncMock()) as spawn:
            with self.assertRaises(ChatGPTError) as ctx:
                await _command(["exec"], prompt="too long")
        self.assertEqual(ctx.exception.code, "codex_input_too_large")
        spawn.assert_not_awaited()


class CodexCLIResponseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = CodexCLIClient()
        self.status_patch = patch.object(self.client, "status", new=AsyncMock(return_value={"installed": True, "authenticated": True}))
        self.status_patch.start()
        self.addCleanup(self.status_patch.stop)
        self.events = []
        self.payload = {"model": "codex-default", "instructions": "Teach clearly", "input": [{"role": "user", "content": "Hello"}],
                        "tools": [{"type": "function", "name": "read_graph", "description": "read", "parameters": {"type": "object"}}]}

    async def event(self, item):
        self.events.append(item)

    async def run_with(self, response, *, code=0):
        line = json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(response)}})
        with patch("app.agent.codex_cli._command", new=AsyncMock(return_value=(code, line))) as command:
            result = await self.client.stream(self.payload, self.event)
        self.assertNotIn("--model", command.await_args.args[0])
        self.assertIn("--ignore-user-config", command.await_args.args[0])
        self.assertIn("read-only", command.await_args.args[0])
        return result

    async def test_valid_message_and_response_events(self):
        result = await self.run_with({"kind": "message", "text": "Hello!", "name": "", "arguments": ""})
        self.assertEqual(result["output"][0]["content"][0]["text"], "Hello!")
        self.assertEqual([e["type"] for e in self.events], ["response.output_item.added", "response.output_text.delta"])

    async def test_valid_tool_call(self):
        result = await self.run_with({"kind": "function_call", "text": "", "name": "read_graph", "arguments": "{}"})
        self.assertEqual(result["output"][0]["name"], "read_graph")

    async def test_unknown_tool_rejected(self):
        with self.assertRaises(ChatGPTError) as ctx:
            await self.run_with({"kind": "function_call", "text": "", "name": "shell", "arguments": "{}"})
        self.assertEqual(ctx.exception.code, "codex_invalid_response")

    async def test_malformed_tool_arguments_rejected(self):
        with self.assertRaises(ChatGPTError) as ctx:
            await self.run_with({"kind": "function_call", "text": "", "name": "read_graph", "arguments": "[]"})
        self.assertEqual(ctx.exception.code, "codex_invalid_response")

    async def test_cli_failure_does_not_fallback_to_api(self):
        with patch("app.agent.codex_cli._command", new=AsyncMock(return_value=(1, ""))):
            with self.assertRaises(ChatGPTError) as ctx:
                await self.client.stream(self.payload, self.event)
        self.assertEqual(ctx.exception.code, "codex_failed")

    async def test_provider_rejects_unknown_model_before_launch(self):
        with patch("app.agent.codex_cli._command", new=AsyncMock()) as command:
            with self.assertRaises(ChatGPTError) as ctx:
                await self.client.stream({**self.payload, "model": "gpt-6-sol-web"}, self.event)
        self.assertEqual(ctx.exception.code, "codex_model_unavailable")
        command.assert_not_awaited()

    async def test_malformed_jsonl_is_reported_as_invalid_response(self):
        output = '\n'.join(['null', '["unexpected"]', '{"type":"item.completed","item":null}', '{}'])
        with patch("app.agent.codex_cli._command", new=AsyncMock(return_value=(0, output))):
            with self.assertRaises(ChatGPTError) as ctx:
                await self.client.stream(self.payload, self.event)
        self.assertEqual(ctx.exception.code, "codex_invalid_response")

    async def test_oversized_output_is_not_parsed(self):
        with patch("app.agent.codex_cli._command", new=AsyncMock(return_value=(0, "x" * (8 * 1024 * 1024 + 1)))):
            with self.assertRaises(ChatGPTError) as ctx:
                await self.client.stream(self.payload, self.event)
        self.assertEqual(ctx.exception.code, "codex_invalid_response")


if __name__ == "__main__":
    unittest.main()
