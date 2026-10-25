import unittest
from unittest.mock import AsyncMock, patch
from app.models.domain import GraphProposal, PatchOperation, ProposalEdge, QuizQuestion, UpdateWorkspaceConfigRequest
from app.core.config import Settings
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

    def test_submission_returns_structured_report_and_consumes_session(self):
        session = self.client.post(self.url + "/start", json={"question_count": 6}).json()["session"]
        # A deliberately incomplete submission must distinguish an unanswered
        # question from an incorrect selected alternative.
        answers = [{"question_id": session["questions"][0]["id"], "choice_index": 1},
                   {"question_id": session["questions"][1]["id"], "choice_index": 0}]
        response = self.client.post(self.url + "/submit", json={"session_id": session["session_id"],
                                                               "answers": answers})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        report = body["report"]
        self.assertEqual(report["attempt_id"], body["attempt"]["id"])
        self.assertEqual((report["question_count"], report["answered_count"],
                          report["correct_count"], report["incorrect_count"], report["unanswered_count"]),
                         (6, 2, 1, 1, 4))
        self.assertEqual(report["score"], body["attempt"]["score"])
        self.assertEqual([item["question_id"] for item in report["question_findings"]],
                         [item["id"] for item in session["questions"]])
        self.assertEqual(report["historical_comparison"], None)
        self.assertEqual(self.client.get(f"{self.url}/{session['session_id']}/draft").status_code, 404)

    def test_study_draft_persists_and_rejects_stale_revision(self):
        session = self.client.post(self.url + "/start", json={"question_count": 6}).json()["session"]
        path = f"{self.url}/{session['session_id']}/draft"
        empty = self.client.get(path)
        self.assertEqual(empty.status_code, 200, empty.text)
        self.assertEqual(empty.json()["revision"], 0)
        qid = session["questions"][0]["id"]
        payload = {"revision": 0, "answers": {qid: 2}, "notes": {qid: "Minha conta"},
                   "active_question_id": qid, "flagged_question_ids": [qid],
                   "strokes": {qid: [{"id": "stroke-1", "tool": "pen", "color": "#154DB3",
                                       "width": 2, "points": [{"x": 0.25, "y": 0.75}]}]}}
        saved = self.client.put(path, json=payload)
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["revision"], 1)
        self.assertEqual(self.client.get(path).json()["strokes"], payload["strokes"])
        self.assertEqual(self.client.put(path, json=payload).status_code, 409)
        self.assertEqual(self.client.get(path).json()["revision"], 1)

    def test_study_draft_checks_session_question_choices_and_drawing_limits(self):
        session = self.client.post(self.url + "/start", json={"question_count": 6}).json()["session"]
        path = f"{self.url}/{session['session_id']}/draft"
        qid = session["questions"][0]["id"]
        self.assertEqual(self.client.get(path.replace("arithmetics", "functions")).status_code, 404)
        self.assertEqual(self.client.put(path, json={"answers": {"alien": 0}}).status_code, 400)
        self.assertEqual(self.client.put(path, json={"answers": {qid: 9}}).status_code, 400)
        self.assertEqual(self.client.put(path, json={"answers": {qid: True}}).status_code, 422)
        self.assertEqual(self.client.put(path, json={"notes": {qid: "x" * 20001}}).status_code, 400)
        self.assertEqual(self.client.put(path, json={"strokes": {qid: [{
            "id": "large", "color": "#010203", "width": 2,
            "points": [{"x": 0.2, "y": 0.3}] * 1201,
        }]}}).status_code, 422)

    def test_study_draft_is_removed_after_submission_and_manual_completion(self):
        session = self.client.post(self.url + "/start", json={"question_count": 6}).json()["session"]
        path = f"{self.url}/{session['session_id']}/draft"
        self.assertEqual(self.client.put(path, json={"notes": {session['questions'][0]['id']: "before quiz"}}).status_code, 200)
        answers = [{"question_id": question["id"], "choice_index": 1} for question in session["questions"]]
        self.assertEqual(self.client.post(self.url + "/submit", json={"session_id": session["session_id"], "answers": answers}).status_code, 200)
        self.assertEqual(self.client.get(path).status_code, 404)
        again = self.client.post(self.url + "/start", json={"question_count": 6}).json()["session"]
        new_path = f"{self.url}/{again['session_id']}/draft"
        self.assertEqual(self.client.put(new_path, json={"notes": {again['questions'][0]['id']: "before manual"}}).status_code, 200)
        self.assertEqual(self.client.post("/api/v1/graphs/mathematics-demo/topics/arithmetics/mark-finished").status_code, 200)
        self.assertEqual(self.client.get(new_path).status_code, 404)

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

    def test_unsafe_legacy_session_is_not_redisplayed_or_graded(self):
        self.repo.update_workspace_config(UpdateWorkspaceConfigRequest(quiz_question_count=6))
        previous = self.client.post(self.url + "/start", json={"question_count": 6}).json()["session"]
        legacy = self.repo.quiz_session(previous["session_id"])
        legacy.questions[0].prompt = "Quanto é 7 × 8?"
        legacy.questions[0].choices = ["54", "56", "58", "64"]
        legacy.questions[0].correct_choice_index = 0
        self.repo.save_quiz_session(legacy)

        before = self.repo.current().snapshot.id
        rejected = self.client.post(self.url + "/submit", json={
            "session_id": legacy.session_id, "answers": [],
        })
        self.assertEqual(rejected.status_code, 400, rejected.text)
        self.assertIn("math verification", rejected.json()["detail"])
        self.assertEqual(self.repo.current().snapshot.id, before)
        self.assertEqual(self.repo.graph(legacy.graph_id).quiz_attempts, [])

        replacement = self.client.post(self.url + "/start", json={"question_count": 6})
        self.assertEqual(replacement.status_code, 200, replacement.text)
        self.assertNotEqual(replacement.json()["session"]["session_id"], legacy.session_id)
        self.assertNotIn("correct_choice_index", replacement.json()["session"]["questions"][0])
        self.assertIn("verification_status", replacement.json()["session"]["questions"][0])

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

    def test_manual_completion_does_not_delete_session_created_after_commit(self):
        original = self.repo.mark_topic_finished
        created = []

        def mark_then_create_session(graph_id, topic_id):
            workspace = original(graph_id, topic_id)
            updated_graph = self.repo.graph(graph_id)
            questions = [QuizQuestion(id=f"fresh-{i}", prompt=f"Question {i}?",
                choices=["A", "B", "C", "D"], correct_choice_index=0) for i in range(6)]
            session = QuizService(Settings()).start_session(
                updated_graph, topic_id, 6,
                questions=questions,
                generator="test",
            )
            self.repo.save_quiz_session(session)
            created.append(session.session_id)
            return workspace

        with patch.object(self.repo, "mark_topic_finished", side_effect=mark_then_create_session):
            response = self.client.post("/api/v1/graphs/mathematics-demo/topics/arithmetics/mark-finished")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.repo.quiz_session(created[0]).session_id, created[0])
