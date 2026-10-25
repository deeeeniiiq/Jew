"""Roadmap tickets remain reserved until the real SQLite write finishes."""
from __future__ import annotations

import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.agent.runtime import AgentRuntime
from app.api.routes import RoadmapConfirmRequest, roadmap_confirm
from app.core.config import Settings
from app.models.domain import CreateGraphRequest
from app.services.repository import GraphRepository
from app.services.roadmap_studio import RoadmapPreview


def roadmap() -> RoadmapPreview:
    return RoadmapPreview(
        title="Learning Python", subject="Python", description="A progressive Python learning pathway.",
        topics=[{
            "title": f"Python foundation {i + 1}",
            "description": "Practice an essential Python concept and apply it in a small project.",
            "outcome": "Write and understand a working Python program.",
            "stage": i, "estimated_minutes": 60,
            "prerequisites": [i - 1] if i else [],
        } for i in range(5)],
    )


class RoadmapConfirmationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="jew-roadmap-confirm-")
        self.settings = Settings(db_path=Path(self.temp.name) / "study.sqlite3")
        self.repository = GraphRepository(self.settings.db_path)
        self.runtime = AgentRuntime(self.settings, self.repository)
        self.preview = roadmap()
        self.before = self.repository.current().snapshot.id
        self.runtime.remember_roadmap = AsyncMock()

    async def asyncTearDown(self):
        await self.runtime.close()
        self.temp.cleanup()

    def ticket(self, letter="a", *, age=0):
        ticket = letter * 32
        with self.runtime._roadmap_ticket_lock:
            self.runtime._roadmap_previews[ticket] = (time.monotonic() - age, self.before, self.preview)
        return RoadmapConfirmRequest(ticket=ticket)

    async def confirm(self, request):
        return await roadmap_confirm(request, self.repository, self.runtime, self.settings)

    async def test_single_use_and_persistent_roadmap(self):
        request = self.ticket()
        response = await self.confirm(request)
        self.assertEqual(response["workspace"]["active_graph_id"], "learning-python")
        self.assertEqual(self.repository.current().snapshot.id, self.before + 1)
        self.assertEqual(len(GraphRepository(self.settings.db_path).graph("learning-python").topics), 5)
        self.runtime.remember_roadmap.assert_awaited_once()
        with self.assertRaises(HTTPException) as caught:
            await self.confirm(request)
        self.assertEqual(caught.exception.status_code, 409)

    async def test_stale_preview_conflicts_without_new_snapshot(self):
        request = self.ticket()
        self.repository.create_graph(CreateGraphRequest(title="Changed", subject="something"))
        before = self.repository.current().snapshot.id
        with self.assertRaises(HTTPException) as caught:
            await self.confirm(request)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(self.repository.current().snapshot.id, before)
        self.assertNotIn(request.ticket, self.runtime._roadmap_inflight)

    async def test_expired_ticket_is_rejected(self):
        with self.assertRaises(HTTPException) as caught:
            await self.confirm(self.ticket(age=1201))
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(self.repository.current().snapshot.id, self.before)

    async def test_auxiliary_memory_failure_does_not_undo_commit(self):
        self.runtime.remember_roadmap.side_effect = RuntimeError("Ruflo unavailable")
        await self.confirm(self.ticket())
        self.assertEqual(self.repository.current().snapshot.id, self.before + 1)

    async def test_cancelled_http_does_not_release_ongoing_write(self):
        request = self.ticket()
        started, continue_write = Event(), Event()
        original = self.repository.create_roadmap

        def slow_write(*args, **kwargs):
            started.set()
            if not continue_write.wait(10):
                raise TimeoutError("test worker blocked")
            return original(*args, **kwargs)

        try:
            with patch.object(self.repository, "create_roadmap", side_effect=slow_write):
                pending = asyncio.create_task(self.confirm(request))
                self.assertTrue(await asyncio.to_thread(started.wait, 5))
                pending.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await pending
                with self.assertRaises(ValueError):
                    self.runtime.confirmed_roadmap(request.ticket)
                continue_write.set()
                for _ in range(100):
                    if request.ticket not in self.runtime._roadmap_inflight:
                        break
                    await asyncio.sleep(.02)
                self.assertNotIn(request.ticket, self.runtime._roadmap_inflight)
                self.assertNotIn(request.ticket, self.runtime._roadmap_previews)
                self.assertEqual(self.repository.current().snapshot.id, self.before + 1)
        finally:
            continue_write.set()


if __name__ == "__main__":
    unittest.main()
