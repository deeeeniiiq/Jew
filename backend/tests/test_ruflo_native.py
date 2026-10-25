"""Ruflo commands stay local; freeform lessons use only local Ollama."""
from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from app.agent.chatgpt_auth import ChatGPTError
from app.agent.contracts import ClosureQuizDraft
from app.agent.ruflo_native import execute_native_command
from app.core.config import Settings
from app.models.domain import GraphChatRequest, UpdateWorkspaceConfigRequest, WorkspaceConfig
from app.services.repository import GraphRepository
from fake_chatgpt import FakeChatGPT, fake_runtime


class FakeRuflo:
    def __init__(self):
        self.calls = []

    async def call(self, name, args, *, enabled):
        self.calls.append((name, args, enabled))
        return {"ok": True, "result": '{"from":"ruflo"}'}

    async def status(self, enabled):
        self.calls.append(("status", {}, enabled))
        return {"enabled": enabled, "connected": True}

    async def close(self):
        pass


class RufloNativeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="jew-ruflo-native-")
        self.addCleanup(temporary.cleanup)
        self.repo = GraphRepository(Path(temporary.name) / "state.sqlite3")
        self.runtime = fake_runtime(Settings(db_path=Path(temporary.name) / "state.sqlite3"),
                                    self.repo, FakeChatGPT(), signed=False)
        self.repo.update_workspace_config(UpdateWorkspaceConfigRequest(agent_backend="ruflo_native", ruflo_enabled=False))
        self.ruflo = FakeRuflo()
        self.runtime.ruflo = self.ruflo
        self.addAsyncCleanup(self.runtime.close)
        for client in (self.runtime.client, self.runtime.codex_cli, self.runtime.openai_api):
            client.stream = AsyncMock(side_effect=AssertionError("Ruflo mode called a commercial provider"))
            client.list_models = AsyncMock(side_effect=AssertionError("Ruflo mode requested commercial models"))
        self.runtime.ollama.list_models = AsyncMock(return_value=[{"model": "qwen3:4b", "id": "qwen3:4b", "displayName": "qwen3:4b", "isDefault": True}])
        self.runtime.ollama.stream = AsyncMock(side_effect=AssertionError("Ollama chat must be configured in the test"))

    async def run_prompt(self, prompt, session_id=None):
        sid, run_id = await self.runtime.start_chat("mathematics-demo", GraphChatRequest(
            prompt=prompt, session_id=session_id))
        run = self.runtime.runs[run_id]
        await asyncio.wait_for(run.done, 5)
        return sid, self.runtime.store.thread_payload("mathematics-demo", sid), run

    async def test_native_default_and_local_model_catalog(self):
        self.assertEqual(WorkspaceConfig().agent_backend, "ruflo_native")
        self.assertEqual([m["model"] for m in await self.runtime.models()], ["qwen3:4b"])
        self.assertFalse(self.runtime.auth.status()["authenticated"])

    async def test_help_works_without_ollama_and_freeform_uses_only_ollama(self):
        self.runtime.ollama.list_models.side_effect = AssertionError("Help must not query Ollama")
        sid, thread, run = await self.run_prompt("/help")
        self.assertEqual(run.status, "completed")
        self.assertIn("sem GPT", thread["messages"][-1]["content"])
        self.assertEqual(self.ruflo.calls, [])
        self.runtime.ollama.list_models.side_effect = None
        self.runtime.ollama.stream = AsyncMock(return_value={"status": "completed", "output": [
            {"type": "message", "id": "local-reply", "content": [{"type": "output_text", "text": "Integrais somam pequenas áreas."}]}
        ]})
        _, thread, run = await self.run_prompt("Explique cálculo integral", sid)
        self.assertEqual(run.status, "completed")
        self.assertIn("Integrais somam", thread["messages"][-1]["content"])
        self.assertEqual(len(thread["messages"]), 4)
        self.assertEqual(self.ruflo.calls, [])
        self.runtime.ollama.stream.assert_awaited_once()
        self.assertEqual(self.runtime.ollama.stream.call_args.args[0]["model"], "qwen3:4b")

    async def test_native_commands_work_when_ollama_is_unavailable(self):
        self.runtime.ollama.list_models.side_effect = OSError("no local Ollama")
        sid, thread, run = await self.run_prompt("/ruflo memory search local")
        self.assertEqual(run.status, "completed")
        self.assertIn("from", thread["messages"][-1]["content"])
        self.assertEqual(self.ruflo.calls[-1][0], "memory_search")

    async def test_quiz_generated_locally_is_persisted_and_graded(self):
        from app.services.quiz_service import QuizService
        questions = [{"prompt": f"Qual é {index}+1?", "choices": ["0", "1", "2", "3"],
                      "correct_choice_index": 1, "explanation": "Adição."} for index in range(6)]
        draft = ClosureQuizDraft.model_validate({"topic_id": "arithmetics", "questions": questions})
        self.runtime.ollama.generate_quiz = AsyncMock(return_value=draft)
        session = await self.runtime.generate_closure_quiz("mathematics-demo", "arithmetics", 6, "qwen3:4b")
        self.runtime.ollama.generate_quiz.assert_awaited_once()
        self.assertEqual(self.runtime.ollama.generate_quiz.call_args.args[:2],
                         ("qwen3:4b", self.repo.graph("mathematics-demo").topics[0].model_dump(mode="json")))
        self.assertEqual(session.generator, "qwen3:4b")
        persisted = self.repo.quiz_session(session.session_id)
        self.assertEqual(persisted.question_count, 6)
        answers = {question.id: question.correct_choice_index for question in persisted.questions}
        attempt, _, new_state, reviews = QuizService(self.runtime.settings).grade_session(
            self.repo.graph("mathematics-demo"), persisted, answers)
        self.assertTrue(attempt.passed)
        self.assertEqual(new_state, "solid")
        self.assertTrue(all(review.was_correct for review in reviews))

    async def test_quiz_failure_never_creates_a_partial_session(self):
        self.runtime.ollama.generate_quiz = AsyncMock(side_effect=ChatGPTError("invalid_local_quiz", "invalid JSON"))
        previous = self.repo.latest_quiz_session_for_topic("mathematics-demo", "arithmetics")
        with self.assertRaises(ChatGPTError):
            await self.runtime.generate_closure_quiz("mathematics-demo", "arithmetics", 6, "qwen3:4b")
        self.assertEqual(self.repo.latest_quiz_session_for_topic("mathematics-demo", "arithmetics"), previous)

    async def test_commands_only_use_ruflo_and_persist_sessions(self):
        sid, thread, run = await self.run_prompt('/ruflo memory store note "meu texto"')
        self.assertEqual(run.status, "completed")
        self.assertIn("from", thread["messages"][-1]["content"])
        self.assertEqual(self.ruflo.calls, [("memory_store", {"key": "note", "value": "meu texto"}, True)])
        _, thread, run = await self.run_prompt("/ruflo memory search meu texto", sid)
        self.assertEqual(run.status, "completed")
        self.assertEqual(self.ruflo.calls[-1], ("memory_search", {"query": "meu texto"}, True))
        self.assertEqual(len(thread["messages"]), 4)
        self.assertEqual(len([e async for e in self.runtime.events(sid, run.id) if e["type"] == "turn_completed"]), 1)

    async def test_invalid_commands_and_unsafe_tools_are_never_dispatched(self):
        self.assertIn("desconhecido", await execute_native_command(self.ruflo, "/ruflo agent spawn claude"))
        self.assertIn("incompletas", await execute_native_command(self.ruflo, '/ruflo memory store "bad'))
        self.assertEqual(self.ruflo.calls, [])


if __name__ == "__main__":
    unittest.main()
