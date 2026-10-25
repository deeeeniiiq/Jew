"""End-to-end HTTP tests of local lessons with an in-memory Ollama substitute."""
import unittest
from unittest.mock import AsyncMock

from agent_test_support import install_client
from app.agent.chatgpt_auth import ChatGPTError
from app.agent.contracts import LessonDraft
from app.models.domain import QuizQuestion
from app.services.quiz_service import QuizService
from app.services.repository import GraphRepository


def lesson(title: str) -> LessonDraft:
    return LessonDraft(
        title=title,
        objectives=["Understand a concept", "Solve a related problem"],
        explanation="A detailed and coherent explanation of the topic with enough supporting information "
                    "for a student to learn the underlying concept and apply it.",
        examples=["2 + 2 = 4, so combining two pairs gives four."],
        practice=["Calculate 3 + 4.", "Explain why addition is commutative."],
        summary="Addition combines quantities, and the examples demonstrate how to use it.",
    )


class LessonRouteTests(unittest.TestCase):
    def setUp(self):
        self.client, self.repo, self.runtime = install_client(self)
        self.url = "/api/v1/graphs/mathematics-demo/topics/arithmetics/lessons/generate"
        self.runtime.ollama.list_models = AsyncMock(return_value=[
            {"model": "qwen3.5:4b"}, {"model": "other:4b"},
        ])
        self.runtime.ollama.generate_lesson = AsyncMock(side_effect=[lesson("Version one"), lesson("Version two")])

    def test_versions_survive_sqlite_reopen_and_preserve_progress(self):
        before = self.repo.current().snapshot.id
        first = self.client.post(self.url, json={"model": "qwen3.5:4b"})
        self.assertEqual(first.status_code, 200, first.text)
        second = self.client.post(self.url, json={"model": "other:4b"})
        self.assertEqual(second.status_code, 200, second.text)
        self.assertNotEqual(first.json()["artifact"]["id"], second.json()["artifact"]["id"])
        self.assertIn("## Objetivos de aprendizagem", first.json()["artifact"]["body"])
        self.assertEqual(first.json()["artifact"]["kind"], "lesson")
        self.assertGreater(second.json()["workspace"]["snapshot"]["id"], before)
        self.assertEqual([call.args[0] for call in self.runtime.ollama.generate_lesson.await_args_list],
                         ["qwen3.5:4b", "other:4b"])

        reopened = GraphRepository(self.repo._db_path)
        graph = reopened.graph("mathematics-demo")
        topic = next(topic for topic in graph.topics if topic.id == "arithmetics")
        self.assertEqual([artifact.title for artifact in topic.artifacts if artifact.kind == "lesson"],
                         ["Version one", "Version two"])
        self.assertEqual(topic.state, "not_started")
        self.assertEqual(graph.quiz_attempts, [])

    def test_invalid_inputs_and_ollama_failure_do_not_persist(self):
        before = self.repo.current().snapshot.id
        self.assertEqual(self.client.post(self.url, json={"model": ""}).status_code, 422)
        self.assertEqual(self.client.post(self.url, json={"model": "uninstalled"}).status_code, 400)
        self.assertEqual(self.client.post(self.url.replace("arithmetics", "missing"), json={}).status_code, 404)
        self.assertEqual(self.client.post(self.url.replace("mathematics-demo", "missing"), json={}).status_code, 404)
        self.runtime.ollama.generate_lesson.side_effect = ChatGPTError("ollama_error", "Ollama stopped")
        failed = self.client.post(self.url, json={})
        self.assertEqual(failed.status_code, 502, failed.text)
        self.assertIn("Ollama stopped", failed.json()["detail"])
        self.assertEqual(self.repo.current().snapshot.id, before)

    def test_selects_installed_local_model_without_explicit_selection(self):
        response = self.client.post(self.url, json={})
        self.assertEqual(response.status_code, 200, response.text)
        self.runtime.ollama.generate_lesson.assert_awaited_once()
        self.assertEqual(self.runtime.ollama.generate_lesson.await_args.args[0], "qwen3.5:4b")


class QuizModelSelectionTests(unittest.TestCase):
    def setUp(self):
        self.client, self.repo, self.runtime = install_client(self)
        self.url = "/api/v1/graphs/mathematics-demo/topics/arithmetics/quiz/start"

    def _session(self, model):
        questions = [QuizQuestion(
            id=f"{model}-q{index}", prompt=f"Question {index}?",
            choices=["1", "2", "3", "4"], correct_choice_index=0,
            explanation="The correct answer is 1.",
        ) for index in range(6)]
        return QuizService(self.runtime.settings).start_session(
            self.repo.graph("mathematics-demo"), "arithmetics", 6,
            questions=questions, generator=model,
        )

    def test_reuses_matching_session_but_honors_explicit_new_model(self):
        original = self._session("model-a")
        self.repo.save_quiz_session(original)
        self.runtime.generate_closure_quiz = AsyncMock()

        resumed = self.client.post(self.url, json={"model": "model-a", "question_count": 6})
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual(resumed.json()["session"]["session_id"], original.session_id)
        self.runtime.generate_closure_quiz.assert_not_awaited()

        replacement = self._session("model-b")

        async def generate(*args):
            self.repo.save_quiz_session(replacement)
            return replacement

        self.runtime.generate_closure_quiz.side_effect = generate
        changed = self.client.post(self.url, json={"model": "model-b", "question_count": 6})
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(changed.json()["session"]["session_id"], replacement.session_id)
        self.runtime.generate_closure_quiz.assert_awaited_once_with(
            "mathematics-demo", "arithmetics", 6, "model-b",
        )
