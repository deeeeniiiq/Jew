from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from app.core.config import Settings
from app.models.domain import Edge, QuizAttempt, QuizQuestion, StudyGraph, Topic
from app.services.quiz_service import QuizService
from app.services.repository import GraphRepository, RepositoryConflictError


class QuizServiceTests(unittest.TestCase):
    DEMO_GRAPH_ID = "mathematics-demo"

    def test_legacy_manual_attempt_is_distinguishable_from_a_quiz(self) -> None:
        manual = QuizAttempt.model_validate({
            "id": "manual-historical", "topic_id": "arithmetics", "passed": True,
            "score": 1.0, "question_count": 6, "closure_awarded": True,
        })
        quiz = QuizAttempt.model_validate({
            "id": "attempt-historical", "topic_id": "arithmetics", "passed": True,
            "score": 1.0, "question_count": 6, "closure_awarded": True,
        })
        self.assertEqual(manual.source, "manual")
        self.assertEqual(quiz.source, "quiz")
        self.assertEqual(QuizAttempt.model_validate(manual.model_dump(mode="json")).source, "manual")

    def setUp(self) -> None:
        settings = Settings()
        self.quiz_service = QuizService(settings)

    def questions(self):
        return [QuizQuestion(id=f"q{i}", prompt=f"Question {i}?", choices=["A", "B", "C", "D"], correct_choice_index=0) for i in range(6)]

    def test_pedagogical_report_counts_and_inference_limits(self) -> None:
        graph = self._repository().graph(self.DEMO_GRAPH_ID)
        session = self.quiz_service.start_session(graph, "arithmetics", 6,
                                                  questions=self.questions(), generator="local-test")
        cases = (
            ({f"q{i}": 0 for i in range(6)}, 6, 6, 0, 0),
            ({f"q{i}": 1 for i in range(6)}, 6, 0, 6, 0),
            ({"q0": 0, "q1": 1}, 2, 1, 1, 4),
            ({}, 0, 0, 0, 6),
        )
        for answers, answered, correct, incorrect, unanswered in cases:
            with self.subTest(answers=answers):
                attempt, _, _, reviews = self.quiz_service.grade_session(graph, session, answers)
                # Deliberately scramble the reviews to ensure question IDs,
                # rather than array position, determine report findings.
                session.questions[0].verification_status = "verified"
                report = self.quiz_service.build_pedagogical_report(
                    attempt, session, list(reversed(reviews)), "Arithmetic")
                self.assertEqual((report.question_count, report.answered_count,
                                  report.correct_count, report.incorrect_count, report.unanswered_count),
                                 (6, answered, correct, incorrect, unanswered))
                self.assertEqual(report.score, attempt.score)
                self.assertEqual((report.verified_keys_count, report.unverified_keys_count), (1, 5))
                self.assertEqual([f.question_id for f in report.question_findings],
                                 [question.id for question in session.questions])
                self.assertEqual(report.historical_comparison, None)
                for finding in report.question_findings:
                    if finding.outcome == "incorrect":
                        self.assertEqual((finding.error_category, finding.diagnosis_confidence),
                                         ("undetermined", "insufficient"))
                        self.assertIsNone(finding.hypothesis)
                    elif finding.outcome == "unanswered":
                        self.assertEqual(finding.error_category, "not_answered")

    def test_pedagogical_report_rejects_missing_or_duplicate_reviews(self) -> None:
        graph = self._repository().graph(self.DEMO_GRAPH_ID)
        session = self.quiz_service.start_session(graph, "arithmetics", 6,
                                                  questions=self.questions(), generator="test")
        attempt, _, _, reviews = self.quiz_service.grade_session(graph, session, {})
        for invalid in (reviews[:-1], reviews + [reviews[0]], [reviews[0]] * len(reviews)):
            with self.subTest(review_count=len(invalid)):
                with self.assertRaisesRegex(ValueError, "exactly one review"):
                    self.quiz_service.build_pedagogical_report(attempt, session, invalid, "Arithmetic")

    def test_closure_status_blocks_unfinished_prerequisites(self) -> None:
        repository = self._repository()
        graph = repository.graph(self.DEMO_GRAPH_ID)

        status = self.quiz_service.build_closure_status(graph, "embeddings")

        self.assertIn("linear-algebra", status.prerequisite_topic_ids)
        self.assertNotIn("vectors-geometry", status.prerequisite_topic_ids)
        self.assertNotIn("circles", status.prerequisite_topic_ids)
        self.assertFalse(status.can_award_completion)
        self.assertIn("linear-algebra", status.blocked_prerequisite_ids)

    def test_completed_cycle_blocks_its_topics_and_downstream_closure(self) -> None:
        graph = StudyGraph(graph_id="cycle", title="Cycle", subject="math",
                           topics=[Topic(id=id, slug=id, title=id, state="solid") for id in ("a", "b", "c")],
                           edges=[Edge(id=f"{a}-{b}", source_topic_id=a,
                                       target_topic_id=b, relation="requires")
                                  for a, b in (("a", "b"), ("b", "a"), ("b", "c"))])
        for topic_id in ("a", "b", "c"):
            status = self.quiz_service.build_closure_status(graph, topic_id)
            self.assertFalse(status.can_award_completion, topic_id)
            self.assertTrue(status.blocked_prerequisite_ids, topic_id)
            with self.assertRaises(ValueError):
                self.quiz_service.start_session(graph, topic_id, 6,
                                                questions=self.questions(), generator="test")

    def test_dangling_requires_edges_block_closure_without_crashing(self) -> None:
        graph = StudyGraph(graph_id="broken", title="Broken", subject="math",
                           topics=[Topic(id=id, slug=id, title=id, state="solid") for id in ("a", "b")],
                           edges=[
                               Edge(id="unknown-to-a", source_topic_id="unknown", target_topic_id="a", relation="requires"),
                               Edge(id="b-to-unknown", source_topic_id="b", target_topic_id="absent", relation="requires"),
                           ])
        self.assertIn("unknown", self.quiz_service.build_closure_status(graph, "a").blocked_prerequisite_ids)
        self.assertIn("b", self.quiz_service.build_closure_status(graph, "b").blocked_prerequisite_ids)
        for topic_id in ("a", "b"):
            with self.assertRaises(ValueError):
                self.quiz_service.start_session(graph, topic_id, 6,
                                                questions=self.questions(), generator="test")

    def test_three_node_cycle_reports_all_members_to_downstream_topics(self) -> None:
        names = ("a", "b", "c", "downstream", "independent")
        graph = StudyGraph(
            graph_id="complex-cycle", title="Complex cycle", subject="math",
            topics=[Topic(id=name, slug=name, title=name, state="solid") for name in names],
            edges=[Edge(id=f"{source}-{target}", source_topic_id=source,
                        target_topic_id=target, relation="requires") for source, target in (
                            ("a", "b"), ("b", "c"), ("c", "a"), ("c", "downstream"),
                        )],
        )
        for topic_id in ("a", "b", "c", "downstream"):
            closure = self.quiz_service.build_closure_status(graph, topic_id)
            self.assertFalse(closure.can_award_completion, topic_id)
            self.assertTrue({"a", "b", "c"}.issubset(closure.blocked_prerequisite_ids), topic_id)
        self.assertTrue(self.quiz_service.build_closure_status(graph, "independent").can_award_completion)

    def test_prerequisite_cycle_added_during_quiz_cannot_award_completion(self) -> None:
        graph = StudyGraph(graph_id="edited", title="Edited", subject="math",
                           topics=[Topic(id=name, slug=name, title=name, state="solid")
                                   for name in ("foundation", "advanced")],
                           edges=[Edge(id="foundation-advanced", source_topic_id="foundation",
                                       target_topic_id="advanced", relation="requires")])
        session = self.quiz_service.start_session(graph, "advanced", 6,
                                                  questions=self.questions(), generator="test")
        graph.edges.append(Edge(id="advanced-foundation", source_topic_id="advanced",
                                target_topic_id="foundation", relation="requires"))
        answers = {question.id: question.correct_choice_index for question in session.questions}
        attempt, closure, state, _ = self.quiz_service.grade_session(graph, session, answers)
        self.assertTrue(attempt.passed)
        self.assertFalse(attempt.closure_awarded)
        self.assertFalse(closure.can_award_completion)
        self.assertIsNone(state)

    def test_long_acyclic_prerequisite_chain_is_iterative(self) -> None:
        length = 1100
        graph = StudyGraph(graph_id="deep", title="Deep", subject="math",
                           topics=[Topic(id=f"n{i}", slug=f"n{i}", title=f"n{i}", state="solid")
                                   for i in range(length)],
                           edges=[Edge(id=f"e{i}", source_topic_id=f"n{i}",
                                       target_topic_id=f"n{i + 1}", relation="requires")
                                  for i in range(length - 1)])
        closure = self.quiz_service.build_closure_status(graph, f"n{length - 1}")
        self.assertTrue(closure.can_award_completion)
        self.assertEqual(len(closure.prerequisite_topic_ids), length - 1)

    def test_quiz_attempt_awards_state_only_when_prerequisites_closed(self) -> None:
        repository = self._repository()
        graph = repository.graph(self.DEMO_GRAPH_ID)

        for topic in graph.topics:
            if topic.id in {"arithmetics", "angles", "algebra-basics", "triangles", "functions", "circles", "vectors-geometry", "linear-algebra"}:
                topic.state = "solid"
        session = self.quiz_service.start_session(graph, "embeddings", 6, questions=self.questions(), generator="test-codex")
        answers = {question.id: question.correct_choice_index for question in session.questions}
        attempt, _, awarded_state, _ = self.quiz_service.grade_session(graph, session, answers)

        repository.save_quiz_session(session)
        repository.record_quiz_attempt(self.DEMO_GRAPH_ID, attempt, awarded_state,
                                       base_graph_version=graph.version, session_id=session.session_id)
        updated = repository.graph(self.DEMO_GRAPH_ID)
        embeddings = next(topic for topic in updated.topics if topic.id == "embeddings")

        self.assertEqual(embeddings.state, "solid")
        self.assertEqual(len(updated.quiz_attempts), 1)
        self.assertTrue(updated.quiz_attempts[0].closure_awarded)

    def test_start_session_blocks_topics_with_open_prerequisites(self) -> None:
        repository = self._repository()
        graph = repository.graph(self.DEMO_GRAPH_ID)

        with self.assertRaises(ValueError) as context:
            self.quiz_service.start_session(graph, "embeddings", 6, questions=self.questions(), generator="test-codex")

        self.assertIn("close prerequisite topics first", str(context.exception))

    def test_failed_attempt_marks_topic_for_review(self) -> None:
        repository = self._repository()
        graph = repository.graph(self.DEMO_GRAPH_ID)
        session = self.quiz_service.start_session(graph, "arithmetics", 6, questions=self.questions(), generator="test-codex")
        wrong_answers = {question.id: (question.correct_choice_index + 1) % len(question.choices) for question in session.questions}
        attempt, _, awarded_state, reviews = self.quiz_service.grade_session(graph, session, wrong_answers)

        repository.save_quiz_session(session)
        repository.record_quiz_attempt(self.DEMO_GRAPH_ID, attempt, awarded_state,
                                       base_graph_version=graph.version, session_id=session.session_id)
        updated = repository.graph(self.DEMO_GRAPH_ID)
        arithmetics = next(topic for topic in updated.topics if topic.id == "arithmetics")

        self.assertEqual(arithmetics.state, "needs_review")
        self.assertFalse(updated.quiz_attempts[0].passed)
        self.assertEqual(len(reviews), 6)
        self.assertTrue(all(review.correct_choice for review in reviews))

    def test_invalid_question_count_fails_instead_of_truncating(self):
        graph = self._repository().graph(self.DEMO_GRAPH_ID)
        with self.assertRaisesRegex(ValueError, "exactly 6"):
            self.quiz_service.start_session(graph, "arithmetics", 6, questions=self.questions()[:5], generator="test-codex")

    def test_duplicate_questions_are_rejected_without_silent_repair(self):
        graph = self._repository().graph(self.DEMO_GRAPH_ID)
        questions = self.questions()
        questions[1].prompt = questions[0].prompt
        with self.assertRaisesRegex(ValueError, "distinct"):
            self.quiz_service.start_session(graph, "arithmetics", 6, questions=questions, generator="test-codex")

    def test_failure_count_and_every_attempt_survive_repeated_quizzes(self):
        repository = self._repository()
        for expected in (1, 2, 3, 4):
            graph = repository.graph(self.DEMO_GRAPH_ID)
            session = self.quiz_service.start_session(graph, "arithmetics", 6, questions=self.questions(), generator="test")
            repository.save_quiz_session(session)
            attempt, _, awarded, _ = self.quiz_service.grade_session(graph, session, {})
            repository.record_quiz_attempt(self.DEMO_GRAPH_ID, attempt, awarded,
                                           base_graph_version=graph.version, session_id=session.session_id)
            attempts = repository.graph(self.DEMO_GRAPH_ID).quiz_attempts
            self.assertEqual(len(attempts), expected)
            self.assertEqual(attempts[-1].fail_count, expected)
            self.assertEqual([a.fail_count for a in attempts], list(range(1, expected + 1)))

    def test_grading_after_manual_completion_retains_existing_grade_history(self):
        repository = self._repository()
        graph = repository.graph(self.DEMO_GRAPH_ID)
        session = self.quiz_service.start_session(graph, "arithmetics", 6, questions=self.questions(), generator="test")
        repository.save_quiz_session(session)
        grade, _, state, _ = self.quiz_service.grade_session(graph, session, {})
        repository.record_quiz_attempt(self.DEMO_GRAPH_ID, grade, state,
                                       base_graph_version=graph.version, session_id=session.session_id)

        repository.mark_topic_finished(self.DEMO_GRAPH_ID, "arithmetics")
        graph = repository.graph(self.DEMO_GRAPH_ID)
        self.assertEqual([a.source for a in graph.quiz_attempts if a.topic_id == "arithmetics"], ["quiz", "manual"])

        session = self.quiz_service.start_session(graph, "arithmetics", 6, questions=self.questions(), generator="test")
        repository.save_quiz_session(session)
        grade2, _, state2, _ = self.quiz_service.grade_session(graph, session, {})
        repository.record_quiz_attempt(self.DEMO_GRAPH_ID, grade2, state2,
                                       base_graph_version=graph.version, session_id=session.session_id)
        history = [a for a in repository.graph(self.DEMO_GRAPH_ID).quiz_attempts if a.topic_id == "arithmetics"]
        self.assertEqual([a.source for a in history], ["quiz", "manual", "quiz"])
        self.assertEqual([a.fail_count for a in history if a.source == "quiz"], [1, 2])
        self.assertEqual(history[-1].id, grade2.id)

    def test_manual_completion_cannot_inflate_quiz_failure_count(self):
        graph = self._repository().graph(self.DEMO_GRAPH_ID)
        graph.quiz_attempts.append(QuizAttempt(
            id="manual-legacy-import", topic_id="arithmetics", source="manual",
            passed=True, score=1.0, question_count=0, closure_awarded=True,
            fail_count=99,
        ))
        session = self.quiz_service.start_session(
            graph, "arithmetics", 6, questions=self.questions(), generator="test"
        )
        failed, _, _, _ = self.quiz_service.grade_session(graph, session, {})
        self.assertEqual(failed.source, "quiz")
        self.assertEqual(failed.fail_count, 1)

    def test_interleaved_quiz_and_manual_events_survive_export_import(self):
        repository = self._repository()
        event_ids: list[str] = []
        for step in ("quiz", "manual", "quiz", "manual", "quiz"):
            if step == "manual":
                repository.mark_topic_finished(self.DEMO_GRAPH_ID, "arithmetics")
            else:
                graph = repository.graph(self.DEMO_GRAPH_ID)
                session = self.quiz_service.start_session(
                    graph, "arithmetics", 6, questions=self.questions(), generator="test"
                )
                repository.save_quiz_session(session)
                graded, _, state, _ = self.quiz_service.grade_session(graph, session, {})
                repository.record_quiz_attempt(
                    self.DEMO_GRAPH_ID, graded, state,
                    base_graph_version=graph.version, session_id=session.session_id,
                )
            history = [a for a in repository.graph(self.DEMO_GRAPH_ID).quiz_attempts
                       if a.topic_id == "arithmetics"]
            self.assertEqual(len(history), len(event_ids) + 1)
            self.assertEqual([a.id for a in history[:-1]], event_ids)
            event_ids.append(history[-1].id)

        graph = repository.graph(self.DEMO_GRAPH_ID)
        history = [a for a in graph.quiz_attempts if a.topic_id == "arithmetics"]
        self.assertEqual([a.source for a in history], ["quiz", "manual", "quiz", "manual", "quiz"])
        self.assertEqual([a.fail_count for a in history if a.source == "quiz"], [1, 2, 3])
        self.assertEqual(self.quiz_service.build_closure_status(graph, "arithmetics").latest_attempt.id,
                         event_ids[-1])
        self.assertEqual(next(t for t in graph.topics if t.id == "arithmetics").state, "needs_review")

        package = repository.export_graph_package(self.DEMO_GRAPH_ID, include_progress=True)
        # Imported legacy data may have clocks out of order. The list position
        # remains the authority on which academic event happened last.
        package.graph.quiz_attempts[0].created_at = datetime(2026, 10, 24, tzinfo=timezone.utc)
        package.graph.quiz_attempts[-1].created_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        imported = repository.import_graph_package(package, title="Audit copy", include_progress=True)
        imported_graph = next(g for g in imported.workspace.graphs if g.title == "Audit copy")
        imported_history = [a for a in imported_graph.quiz_attempts if a.topic_id == "arithmetics"]
        self.assertEqual([a.id for a in imported_history], event_ids)
        self.assertEqual([a.source for a in imported_history], [a.source for a in history])
        self.assertLess(imported_history[-1].created_at, imported_history[0].created_at)
        self.assertEqual(
            self.quiz_service.build_closure_status(imported_graph, "arithmetics").latest_attempt.id,
            event_ids[-1],
        )

    def test_quiz_consumption_and_snapshot_share_one_transaction(self):
        repository = self._repository()
        graph = repository.graph(self.DEMO_GRAPH_ID)
        session = self.quiz_service.start_session(graph, "arithmetics", 6, questions=self.questions(), generator="test")
        repository.save_quiz_session(session)
        attempt, _, awarded, _ = self.quiz_service.grade_session(graph, session, {})
        before = repository.current().snapshot.id
        with patch.object(repository, "_insert_snapshot", side_effect=RuntimeError("write failed")):
            with self.assertRaisesRegex(RuntimeError, "write failed"):
                repository.record_quiz_attempt(self.DEMO_GRAPH_ID, attempt, awarded,
                                               base_graph_version=graph.version, session_id=session.session_id)
        self.assertEqual(repository.quiz_session(session.session_id).session_id, session.session_id)
        self.assertEqual(repository.current().snapshot.id, before)

    def test_manual_completion_invalidates_all_prior_quiz_sessions_atomically(self):
        repository = self._repository()
        graph = repository.graph(self.DEMO_GRAPH_ID)
        sessions = [self.quiz_service.start_session(graph, "arithmetics", 6,
                    questions=self.questions(), generator="test") for _ in range(2)]
        for session in sessions:
            repository.save_quiz_session(session)

        before = repository.current().snapshot.id
        with patch.object(repository, "_insert_snapshot", side_effect=RuntimeError("write failed")):
            with self.assertRaisesRegex(RuntimeError, "write failed"):
                repository.mark_topic_finished(self.DEMO_GRAPH_ID, "arithmetics")
        self.assertEqual(repository.current().snapshot.id, before)
        for session in sessions:
            self.assertEqual(repository.quiz_session(session.session_id).session_id, session.session_id)

        repository.mark_topic_finished(self.DEMO_GRAPH_ID, "arithmetics")
        for session in sessions:
            with self.assertRaises(KeyError):
                repository.quiz_session(session.session_id)

    def test_consumed_quiz_cannot_award_another_snapshot(self):
        repository = self._repository()
        graph = repository.graph(self.DEMO_GRAPH_ID)
        session = self.quiz_service.start_session(graph, "arithmetics", 6, questions=self.questions(), generator="test")
        repository.save_quiz_session(session)
        attempt, _, awarded, _ = self.quiz_service.grade_session(graph, session, {})
        first = repository.record_quiz_attempt(self.DEMO_GRAPH_ID, attempt, awarded,
                                               base_graph_version=graph.version, session_id=session.session_id)
        with self.assertRaisesRegex(RepositoryConflictError, "already submitted"):
            repository.record_quiz_attempt(self.DEMO_GRAPH_ID, attempt, awarded,
                base_graph_version=repository.graph(self.DEMO_GRAPH_ID).version, session_id=session.session_id)
        self.assertEqual(repository.current().snapshot.id, first.snapshot.id)

    def _repository(self) -> GraphRepository:
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        return GraphRepository(Path(tempdir.name) / "state.sqlite3")


if __name__ == "__main__":
    unittest.main()
