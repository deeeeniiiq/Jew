import unittest
from unittest.mock import AsyncMock, patch
from app.models.domain import GraphProposal, PatchOperation, ProposalEdge, UpdateWorkspaceConfigRequest
from app.services.quiz_service import QuizService
from app.agent.chatgpt_auth import ChatGPTError
from agent_test_support import install_client

class QuizRouteTests(unittest.TestCase):
    def setUp(self):
        self.client, self.repo, self.runtime = install_client(self, "closure")
        self.url = "/api/v1/graphs/mathematics-demo/topics/arithmetics/quiz"

    def test_quiz_start_uses_native_tool_and_public_response_hides_answers(self):
        self.repo.update_workspace_config(UpdateWorkspaceConfigRequest(quiz_question_count=6))
        response = self.client.post(self.url+"/start", json={"question_count": 6})
        self.assertEqual(response.status_code, 200, response.text)
        session = response.json()["session"]
        self.assertEqual(len(session["questions"]), 6)
        self.assertNotIn("correct_choice_index", session["questions"][0])
        second = self.client.post(self.url+"/start", json={})
        self.assertEqual(second.json()["session"]["session_id"], session["session_id"])
        answers = [{"question_id": q["id"], "choice_index": 1} for q in session["questions"]]
        submitted = self.client.post(self.url+"/submit", json={"session_id": session["session_id"], "answers": answers})
        self.assertEqual(submitted.status_code, 200, submitted.text)
        self.assertTrue(submitted.json()["attempt"]["passed"])
        self.assertTrue(submitted.json()["attempt"]["closure_awarded"])
        self.assertEqual(self.client.post(self.url+"/submit", json={"session_id": session["session_id"], "answers": answers}).status_code, 404)

    def test_native_failure_returns_explicit_502(self):
        self.runtime.generate_closure_quiz = AsyncMock(side_effect=ChatGPTError("usage", "ChatGPT plan limit reached"))
        response = self.client.post(self.url+"/start", json={})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "ChatGPT plan limit reached")

    def test_saved_workspace_policy_controls_generation_and_grading(self):
        saved = self.client.post("/api/v1/workspace/config", json={"quiz_question_count": 6, "pass_threshold": 1})
        self.assertEqual(saved.status_code, 200, saved.text)
        response = self.client.post(self.url + "/start", json={})
        self.assertEqual(response.status_code, 200, response.text)
        session = response.json()["session"]
        self.assertEqual(session["question_count"], 6)
        answers = [{"question_id": q["id"], "choice_index": 1 if i < 5 else 0}
                   for i, q in enumerate(session["questions"])]
        response = self.client.post(self.url + "/submit", json={"session_id": session["session_id"], "answers": answers})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertAlmostEqual(response.json()["attempt"]["score"], 5 / 6)
        self.assertFalse(response.json()["attempt"]["passed"])
        self.assertFalse(response.json()["attempt"]["closure_awarded"])

    def test_saved_policy_does_not_override_explicit_question_count(self):
        self.repo.update_workspace_config(UpdateWorkspaceConfigRequest(quiz_question_count=6))
        response = self.client.post(self.url + "/start", json={"question_count": 8})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["session"]["question_count"], 8)

    def test_changed_question_count_does_not_resume_an_old_test(self):
        previous = self.client.post(self.url + "/start", json={}).json()["session"]
        self.assertEqual(previous["question_count"], 12)
        self.repo.update_workspace_config(UpdateWorkspaceConfigRequest(quiz_question_count=6))
        response = self.client.post(self.url + "/start", json={})
        self.assertEqual(response.status_code, 200, response.text)
        session = response.json()["session"]
        self.assertEqual(session["question_count"], 6)
        self.assertNotEqual(session["session_id"], previous["session_id"])

    def test_saved_threshold_rejects_nine_of_twelve_correct(self):
        self.repo.update_workspace_config(UpdateWorkspaceConfigRequest(pass_threshold=1))
        session = self.client.post(self.url + "/start", json={"question_count": 12}).json()["session"]
        answers = [{"question_id": q["id"], "choice_index": 1 if i < 9 else 0}
                   for i, q in enumerate(session["questions"])]
        result = self.client.post(self.url + "/submit", json={"session_id": session["session_id"], "answers": answers})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["attempt"]["score"], 0.75)
        self.assertFalse(result.json()["attempt"]["closure_awarded"])

    def test_open_prerequisites_block_test(self):
        response = self.client.post("/api/v1/graphs/mathematics-demo/topics/embeddings/quiz/start", json={})
        self.assertEqual(response.status_code, 400)

    def test_quiz_cannot_be_submitted_to_another_topic(self):
        session = self.client.post(self.url+"/start", json={"question_count": 6}).json()["session"]
        response = self.client.post("/api/v1/graphs/mathematics-demo/topics/functions/quiz/submit", json={"session_id": session["session_id"], "answers": []})
        self.assertEqual(response.status_code, 400)

    def test_duplicate_unknown_and_out_of_range_answers_are_explicit(self):
        session = self.client.post(self.url+"/start", json={"question_count": 6}).json()["session"]
        qid = session["questions"][0]["id"]
        for answers in ([{"question_id": qid, "choice_index": 0}, {"question_id": qid, "choice_index": 1}],
                        [{"question_id": "unknown", "choice_index": 0}], [{"question_id": qid, "choice_index": 4}]):
            before = self.repo.current().snapshot.id
            response = self.client.post(self.url+"/submit", json={"session_id": session["session_id"], "answers": answers})
            self.assertEqual(response.status_code, 400, response.text)
            self.assertEqual(self.repo.current().snapshot.id, before)
            self.assertEqual(self.repo.quiz_session(session["session_id"]).session_id, session["session_id"])

    def test_prerequisite_change_during_grading_cannot_award_completion(self):
        session = self.client.post(self.url+"/start", json={"question_count": 6}).json()["session"]
        original = QuizService.grade_session
        def grade(service, graph, quiz, answers, **policy):
            result = original(service, graph, quiz, answers, **policy)
            self.repo.apply_proposal(GraphProposal(graph_id=graph.graph_id, proposal_id="new-prerequisite",
                base_graph_version=graph.version, user_prompt="", summary="Add prerequisite", assistant_message="",
                operations=[PatchOperation(op="upsert_edge", edge=ProposalEdge(id="angles-arithmetics",
                    source_topic_id="angles", target_topic_id="arithmetics"))]))
            return result
        answers = [{"question_id": q["id"], "choice_index": 1} for q in session["questions"]]
        with patch.object(QuizService, "grade_session", grade):
            response = self.client.post(self.url+"/submit", json={"session_id": session["session_id"], "answers": answers})
        self.assertEqual(response.status_code, 409, response.text)
        graph = self.repo.graph("mathematics-demo")
        self.assertEqual(next(t for t in graph.topics if t.id == "arithmetics").state, "not_started")
        self.assertEqual(graph.quiz_attempts, [])
        self.assertEqual(self.repo.quiz_session(session["session_id"]).session_id, session["session_id"])

    def test_quiz_inputs_reject_invalid_counts_and_boolean_choices(self):
        for body in ({"question_count": 5}, {"question_count": 13}, {"model": ""}):
            self.assertEqual(self.client.post(self.url+"/start", json=body).status_code, 422)
        session = self.client.post(self.url+"/start", json={"question_count": 6}).json()["session"]
        response = self.client.post(self.url+"/submit", json={"session_id": session["session_id"],
            "answers": [{"question_id": session["questions"][0]["id"], "choice_index": True}]})
        self.assertEqual(response.status_code, 422)
