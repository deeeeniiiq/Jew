"""Ruflo's stdio session must remain inside the task that opened it."""
from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError

from app.agent.ruflo_mcp import MODELS, RufloMCP


class RufloMCPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="jew-ruflo-test-")
        self.addCleanup(self.temp.cleanup)
        self.client = RufloMCP(Path(self.temp.name))
        self.addAsyncCleanup(self.client.close)
        self.calls = []
        self.opens = []
        self.closes = []

    def fake_contexts(self):
        @asynccontextmanager
        async def fake_stdio(params):
            self.opens.append((asyncio.current_task(), params))
            try:
                yield object(), object()
            finally:
                self.closes.append(asyncio.current_task())

        class Session:
            def __init__(session, *args, **kwargs):
                pass

            async def __aenter__(session):
                return session

            async def __aexit__(session, *_):
                return None

            async def initialize(session):
                return None

            async def list_tools(session):
                return SimpleNamespace(tools=[SimpleNamespace(name=name) for name in MODELS])

            async def call_tool(session, name, arguments):
                self.calls.append((name, arguments))
                return SimpleNamespace(isError=False, content=[SimpleNamespace(text='{"ok":true}')])

        async def fake_prepare_memory(client):
            client.directory.mkdir(parents=True, exist_ok=True)

        return (patch("app.agent.ruflo_mcp.stdio_client", fake_stdio),
                patch("app.agent.ruflo_mcp.ClientSession", Session),
                patch.object(RufloMCP, "_prepare_memory", fake_prepare_memory))

    async def test_disabled_by_default_and_disallowed_calls_do_not_start_process(self):
        status = await self.client.status(False)
        self.assertFalse(status["enabled"])
        self.assertIsNone(self.client._worker)
        with self.assertRaises(ValueError):
            await self.client.call("memory_store", {"key": "x", "value": "v"}, enabled=False)
        with self.assertRaises(ValueError):
            await self.client.call("agent_spawn", {}, enabled=True)
        with self.assertRaises(ValidationError):
            await self.client.call("memory_search", {"query": "x", "dbPath": "C:/unsafe.db"}, enabled=True)
        self.assertIsNone(self.client._worker)

    async def test_global_installation_is_preferred_but_offline_npx_is_supported(self):
        command = "ruflo.cmd" if os.name == "nt" else "ruflo"
        with patch("app.agent.ruflo_mcp.shutil.which", return_value=command):
            self.assertEqual(RufloMCP._launcher(), (command, []))
        with patch("app.agent.ruflo_mcp.shutil.which", return_value=None):
            executable, args = RufloMCP._launcher()
            self.assertEqual(executable, "npx.cmd" if os.name == "nt" else "npx")
            self.assertEqual(args, ["--no-install", "ruflo@3.59.17"])

    async def test_status_memory_isolation_concurrency_and_task_owned_shutdown(self):
        stdio_patch, session_patch, memory_patch = self.fake_contexts()
        with stdio_patch, session_patch, memory_patch, patch.dict(os.environ, {"OPENAI_API_KEY": "never-forward", "CODEX_HOME": "never-forward"}):
            connected, memory, agents = await asyncio.gather(
                self.client.status(True),
                self.client.call("memory_store", {"key": "test", "value": "short note"}, enabled=True),
                self.client.call("agent_list", {}, enabled=True),
            )
            self.assertTrue(connected["connected"])
            self.assertTrue(memory["ok"])
            self.assertTrue(agents["ok"])
            self.assertEqual(len(self.opens), 1)
            env = self.opens[0][1].env
            self.assertNotIn("OPENAI_API_KEY", env)
            self.assertNotIn("CODEX_HOME", env)
            name, arguments = self.calls[0]
            self.assertEqual(name, "memory_store")
            self.assertEqual(arguments["namespace"], "jew")
            self.assertEqual(arguments["dbPath"], str(self.client.directory / "memory.sqlite3"))
            await self.client.close()
            self.assertEqual(self.opens[0][0], self.closes[0])
            self.assertIsNone(self.client._worker)

    async def test_disabling_closes_an_existing_session(self):
        stdio_patch, session_patch, memory_patch = self.fake_contexts()
        with stdio_patch, session_patch, memory_patch:
            self.assertTrue((await self.client.status(True))["connected"])
            self.assertFalse((await self.client.status(False))["connected"])
        self.assertEqual(self.opens[0][0], self.closes[0])


if __name__ == "__main__":
    unittest.main()
