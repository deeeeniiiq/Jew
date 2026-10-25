from __future__ import annotations
import unittest
from unittest.mock import AsyncMock

import httpx

from app.agent.chatgpt_auth import ChatGPTError
from agent_test_support import install_client


class AccessBoundaryTests(unittest.TestCase):
    def test_callback_failure_is_an_html_page_without_internal_error(self):
        client, repo, runtime = install_client(self, signed=False)
        response = client.get("/auth/callback?code=fake", headers={"host": "127.0.0.1:8787"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Sign-in did not finish", response.text)
        self.assertNotIn("Internal Server Error", response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_signed_out_workspace_can_be_read_and_mutated_locally(self):
        client, repo, runtime = install_client(self, signed=False)
        snapshot = repo.current().snapshot.id
        self.assertEqual(client.get("/api/v1/workspace/current").status_code, 200)
        response = client.post("/api/v1/workspace/graphs", json={"title": "Offline graph", "subject": "Algebra"})
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(repo.current().snapshot.id, snapshot)
        self.assertTrue(any(graph.title == "Offline graph" for graph in repo.graph_summaries()))
        self.assertEqual(client.get("/api/v1/chatgpt/account").status_code, 200)

    def test_chatgpt_plan_permission_and_logout_do_not_relock_workspace(self):
        client, repo, runtime = install_client(self)
        self.assertEqual(client.get("/api/v1/workspace/current").status_code, 200)
        connection = runtime.auth.store.read()
        runtime.auth.store.write({**connection, "scopes": []})
        self.assertEqual(client.get("/api/v1/workspace/current").status_code, 200)
        runtime.auth.store.write(connection)
        self.assertEqual(client.post("/api/v1/chatgpt/logout").status_code, 200)
        self.assertEqual(client.get("/api/v1/workspace/current").status_code, 200)

    def test_desktop_transport_requires_launch_session(self):
        client, repo, runtime = install_client(self)
        runtime.settings.desktop_token = "a-private-launch-session"
        self.assertEqual(client.get("/api/v1/chatgpt/account").status_code, 403)
        self.assertEqual(client.get("/api/v1/chatgpt/account", headers={"x-clew-session": "forged"}).status_code, 403)
        self.assertEqual(client.get("/api/v1/chatgpt/account", headers={"x-clew-session": "a-private-launch-session"}).status_code, 200)
        self.assertEqual(client.get("/api/v1/chatgpt/account", headers={b"x-clew-session": b"\xff"}).status_code, 403)

    def test_corrupt_credentials_expose_recovery_without_locking_workspace(self):
        client, repo, runtime = install_client(self)
        runtime.auth.store.write({**runtime.auth.store.read(), "expires_at": None})
        account = client.get("/api/v1/chatgpt/account").json()
        self.assertFalse(account["authenticated"])
        self.assertTrue(account["can_disconnect"])
        self.assertEqual(client.get("/api/v1/workspace/current").status_code, 200)
        self.assertTrue(client.post("/api/v1/chatgpt/logout").json()["ok"])
        account = client.get("/api/v1/chatgpt/account").json()
        self.assertFalse(account["authenticated"])
        self.assertFalse(account["can_disconnect"])

    def test_catalog_rejection_disconnects_chatgpt_but_preserves_local_access(self):
        client, repo, runtime = install_client(self)
        http = httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(401, json={"error": {"code": "invalid_token"}})))
        runtime.client.http = http
        try:
            response = client.get("/api/v1/chatgpt/account")
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.json()["authenticated"])
            self.assertFalse(response.json()["can_disconnect"])
            self.assertEqual(client.get("/api/v1/workspace/current").status_code, 200)
        finally:
            import asyncio
            asyncio.run(http.aclose())

    def test_retryable_provider_failure_does_not_block_local_data(self):
        client, repo, runtime = install_client(self)
        runtime.auth.access_token = AsyncMock(side_effect=ChatGPTError("transport_error", "Cannot reach ChatGPT", retryable=True))
        self.assertEqual(client.get("/api/v1/workspace/current").status_code, 200)
        response = client.get("/api/v1/agent/models")
        self.assertEqual(response.status_code, 503)
        self.assertIn("Cannot reach ChatGPT", response.json()["detail"])
