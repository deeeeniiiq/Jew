from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from app.agent.chatgpt_auth import ChatGPTError
from app.agent.providers import OllamaClient, _quiz_numerical_answer_conflict
from app.agent.contracts import QuizQuestionDraft


class OllamaProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_lesson_uses_structured_json_and_recovers_from_malformed_output(self) -> None:
        requests = []
        unloads = []
        lesson = {
            "title": "Understanding fractions",
            "objectives": ["Recognize fractions", "Add fractions"],
            "explanation": "Fractions represent parts of a whole. The denominator names the number of equal parts, "
                           "while the numerator indicates how many of those equal parts are selected.",
            "examples": ["1/4 + 1/4 = 1/2"],
            "practice": ["Add 1/3 and 1/3", "Draw a picture of 2/5"],
            "summary": "Fractions describe quantities in equal parts and support arithmetic operations.",
        }

        def respond(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            if request.url.path == "/api/generate":
                unloads.append(payload)
                return httpx.Response(200)
            requests.append(payload)
            return httpx.Response(200, json={"message": {"content":
                "not valid json" if len(requests) == 1 else json.dumps(lesson)}})

        http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        self.addAsyncCleanup(http.aclose)
        result = await OllamaClient(http=http).generate_lesson("qwen3.5:4b", {
            "subject": "mathematics", "topic": {"title": "fractions"},
        })
        self.assertEqual(result.title, lesson["title"])
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0]["model"], "qwen3.5:4b")
        self.assertIs(requests[0]["think"], False)
        self.assertIs(requests[0]["stream"], False)
        self.assertIn("objectives", requests[0]["format"]["properties"])
        self.assertIn("invalid", requests[1]["messages"][-1]["content"])
        self.assertEqual(unloads, [{"model": "qwen3.5:4b", "keep_alive": 0}] * 2)
        self.assertEqual(requests[0]["keep_alive"], 0)

    async def test_lesson_ollama_http_error_is_explicit_without_remote_fallback(self) -> None:
        calls = []
        def reject(request: httpx.Request) -> httpx.Response:
            calls.append(request.url)
            return httpx.Response(500)
        http = httpx.AsyncClient(transport=httpx.MockTransport(reject))
        self.addAsyncCleanup(http.aclose)
        with self.assertRaises(ChatGPTError) as raised:
            await OllamaClient(http=http).generate_lesson("qwen3.5:4b", {"topic": {"title": "fractions"}})
        self.assertEqual(raised.exception.code, "ollama_error")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].host, "127.0.0.1")
        self.assertEqual(calls[-1].path, "/api/generate")

    def test_explicit_numeric_equation_cannot_mark_different_choice(self) -> None:
        question = QuizQuestionDraft(
            prompt="Se x/9 = 2/3, qual é o valor de x?",
            choices=[r"\(6\)", r"\(4\)", r"\(8\)", r"\(10\)"],
            correct_choice_index=1,
            explanation=r"Multiplicando por 3, temos \(x = 6\).",
        )
        self.assertIn("marks 4", _quiz_numerical_answer_conflict([question]))
        question.correct_choice_index = 0
        self.assertIsNone(_quiz_numerical_answer_conflict([question]))

    def setUp(self) -> None:
        self.requests = []

    def _client(self, *, malformed: bool = False) -> OllamaClient:
        def handle(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/generate":
                return httpx.Response(200)
            payload = json.loads(request.content)
            self.requests.append(payload)
            questions = [
                {"prompt": f"Question {i}?", "choices": ["A", "B", "C", "D"],
                 "correct_choice_index": (i % 4), "explanation": "Verified."}
                for i in range(6)
            ]
            content = "invalid JSON" if malformed else json.dumps({"topic_id": "fractions", "questions": questions})
            return httpx.Response(200, json={"message": {"content": content}})

        http = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        self.addAsyncCleanup(http.aclose)
        return OllamaClient(http=http)

    async def test_quiz_requests_structured_json_without_thinking(self) -> None:
        client = self._client()
        quiz = await client.generate_quiz("qwen3.5:4b", {"id": "fractions", "language": "pt-BR"}, 6)
        self.assertEqual(len(quiz.questions), 6)
        self.assertEqual(len(self.requests), 1)
        request = self.requests[0]
        self.assertIs(request["think"], False)
        self.assertIs(request["stream"], False)
        self.assertEqual(request["format"]["properties"]["topic_id"]["type"], "string")
        self.assertGreaterEqual(request["options"]["num_predict"], 2700)

    async def test_malformed_responses_are_retried_then_rejected(self) -> None:
        client = self._client(malformed=True)
        with self.assertRaises(ChatGPTError) as raised:
            await client.generate_quiz("qwen3.5:4b", {"id": "fractions"}, 6)
        self.assertEqual(raised.exception.code, "invalid_local_quiz")
        self.assertEqual(len(self.requests), 3)

    async def test_real_world_wrong_fraction_key_is_retried_before_publishing(self) -> None:
        calls = []

        def respond(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/generate":
                return httpx.Response(200)
            calls.append(json.loads(request.content))
            questions = [{
                "prompt": f"Question {i}?", "choices": ["A", "B", "C", "D"],
                "correct_choice_index": i % 4, "explanation": "Verified.",
            } for i in range(6)]
            questions[4] = {
                "prompt": "Se x/9 = 2/3, qual e o valor de x?",
                "choices": [r"\(6\)", r"\(4\)", r"\(8\)", r"\(10\)"],
                "correct_choice_index": 1 if len(calls) == 1 else 0,
                "explanation": r"Multiplicando, temos \(x = 6\).",
            }
            return httpx.Response(200, json={"message": {"content": json.dumps({
                "topic_id": "fractions", "questions": questions,
            })}})

        http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        self.addAsyncCleanup(http.aclose)
        draft = await OllamaClient(http=http).generate_quiz(
            "qwen3.5:4b", {"id": "fractions", "language": "pt-BR"}, 6,
        )
        self.assertEqual(len(calls), 2)
        self.assertIn("marks 4", calls[1]["messages"][-1]["content"])
        self.assertEqual(draft.questions[4].correct_choice_index, 0)

    async def test_cancellation_unloads_selected_model_but_preserves_external_server(self) -> None:
        chat_started = asyncio.Event()
        hold_chat = asyncio.Event()
        operations = []

        async def handle(request: httpx.Request) -> httpx.Response:
            operations.append((request.url.path, json.loads(request.content)))
            if request.url.path == "/api/chat":
                chat_started.set()
                await hold_chat.wait()
            return httpx.Response(200, json={"message": {"content": ""}})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            client = OllamaClient(http=http)
            with patch.object(client, "_stop_owned_server", new_callable=AsyncMock) as stop:
                pending = asyncio.create_task(client._chat({"model": "qwen3.5:4b", "messages": []}))
                await asyncio.wait_for(chat_started.wait(), timeout=2)
                pending.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await pending
                self.assertEqual([path for path, _ in operations], ["/api/chat", "/api/generate"])
                self.assertEqual(operations[-1][1], {"model": "qwen3.5:4b", "keep_alive": 0})
                stop.assert_awaited_once()

    async def test_owned_server_is_terminated_after_failed_generation(self) -> None:
        requests = []

        def fail(request: httpx.Request) -> httpx.Response:
            requests.append(request.url.path)
            return httpx.Response(500)

        async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as http:
            client = OllamaClient(http=http)
            with patch.object(client, "_stop_owned_server", new_callable=AsyncMock) as stop:
                with self.assertRaises(ChatGPTError):
                    await client.generate_lesson("qwen3.5:4b", {"topic": {"title": "Numbers"}})
                stop.assert_awaited_once()
        self.assertEqual(requests, ["/api/chat", "/api/generate"])

    async def test_repeated_cancellation_waits_for_ollama_eviction(self) -> None:
        unload_started = asyncio.Event()
        release_unload = asyncio.Event()
        operations = []

        async def handle(request: httpx.Request) -> httpx.Response:
            operations.append(request.url.path)
            if request.url.path == "/api/generate":
                unload_started.set()
                await release_unload.wait()
            return httpx.Response(200, json={"message": {"content": "ok"}})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            client = OllamaClient(http=http)
            with patch.object(client, "_stop_owned_server", new_callable=AsyncMock) as stop:
                pending = asyncio.create_task(client._chat({"model": "qwen3.5:4b", "messages": []}))
                await asyncio.wait_for(unload_started.wait(), timeout=2)
                pending.cancel()
                await asyncio.sleep(0)
                pending.cancel()
                await asyncio.sleep(0)
                self.assertFalse(pending.done(), "Eviction must finish before cancellation completes")
                release_unload.set()
                with self.assertRaises(asyncio.CancelledError):
                    await asyncio.wait_for(pending, timeout=2)
                self.assertEqual(operations, ["/api/chat", "/api/generate"])
                stop.assert_awaited_once()

    async def test_concurrent_generations_serialize_eviction(self) -> None:
        first_unload_started = asyncio.Event()
        release_first_unload = asyncio.Event()
        operations = []

        async def handle(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            operations.append(path)
            if path == "/api/generate" and not first_unload_started.is_set():
                first_unload_started.set()
                await release_first_unload.wait()
            return httpx.Response(200, json={"message": {"content": "ok"}})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            client = OllamaClient(http=http)
            first = asyncio.create_task(client._chat({"model": "qwen3.5:4b", "messages": []}))
            await asyncio.wait_for(first_unload_started.wait(), timeout=2)
            second = asyncio.create_task(client._chat({"model": "qwen3.5:4b", "messages": []}))
            await asyncio.sleep(0)
            self.assertEqual(operations, ["/api/chat", "/api/generate"])
            release_first_unload.set()
            await asyncio.wait_for(asyncio.gather(first, second), timeout=2)
            self.assertEqual(operations, ["/api/chat", "/api/generate", "/api/chat", "/api/generate"])
