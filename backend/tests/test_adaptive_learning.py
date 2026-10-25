"""Regression coverage for deterministic, read-only learning guidance."""
import unittest
from random import Random
from datetime import datetime, timezone

from app.core.config import Settings
from app.models.domain import Edge, QuizAttempt, StudyGraph, Topic
from app.services.adaptive_learning import AdaptiveLearningService
from app.services.quiz_service import QuizService
from agent_test_support import install_client


NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)


def topic(topic_id: str, state: str = "not_started") -> Topic:
    return Topic(id=topic_id, slug=topic_id, title=topic_id, state=state)


def requires(source: str, target: str) -> Edge:
    return Edge(id=f"{source}->{target}", source_topic_id=source, target_topic_id=target, relation="requires")


def attempt(topic_id: str, date: str, *, passed: bool = True, manual: bool = False,
            awarded: bool = True, score: float = 0.9) -> QuizAttempt:
    return QuizAttempt(id=f"{'manual-' if manual else 'quiz-'}{topic_id}-{date}",
                       topic_id=topic_id, source="manual" if manual else "quiz",
                       passed=passed, score=score, question_count=0 if manual else 6,
                       closure_awarded=awarded,
                       created_at=datetime.fromisoformat(date))


def graph(*, topics=None, edges=None, attempts=None) -> StudyGraph:
    return StudyGraph(graph_id="test", subject="math", title="Math", version=7,
                      topics=topics or [], edges=edges or [], quiz_attempts=attempts or [])


class AdaptiveLearningTests(unittest.TestCase):
    def setUp(self):
        self.service = AdaptiveLearningService()

    def plan(self, item: StudyGraph):
        return self.service.build_plan(item, now=NOW)

    def test_empty_graph_produces_empty_read_only_plan(self):
        item = graph()
        before = item.model_dump(mode="json")
        result = self.plan(item)
        self.assertEqual((result.total_topics, result.blocked_topics), (0, 0))
        self.assertEqual(result.recommendations, [])
        self.assertEqual(item.model_dump(mode="json"), before)

    def test_topic_without_quiz_has_insufficient_evidence(self):
        result = self.plan(graph(topics=[topic("a")]))
        self.assertEqual(result.signals[0].evidence_level, "none")
        self.assertEqual(result.signals[0].mastery_indicator, "insufficient_evidence")
        self.assertEqual(result.recommendations[0].action, "study")

    def test_recent_pass_schedules_review_without_marking_due(self):
        item = graph(topics=[topic("a", "solid")], attempts=[attempt("a", "2026-10-23T00:00:00+00:00")])
        result = self.plan(item)
        self.assertEqual(result.certified_topics, 1)
        self.assertEqual(result.due_reviews, 0)
        self.assertEqual(result.signals[0].next_review_at.isoformat(), "2026-10-25T00:00:00+00:00")
        self.assertFalse(result.recommendations)

    def test_old_success_is_due_and_consecutive_successes_extend_interval(self):
        item = graph(topics=[topic("a", "solid")], attempts=[
            attempt("a", "2026-10-01T00:00:00+00:00"),
            attempt("a", "2026-10-16T00:00:00+00:00"),
        ])
        result = self.plan(item)
        self.assertEqual(result.signals[0].next_review_at.isoformat(), "2026-10-21T00:00:00+00:00")
        self.assertTrue(result.signals[0].review_due)
        self.assertEqual(result.recommendations[0].decision_rule, "spaced_review_due")

    def test_manual_completion_is_distinct_from_certified(self):
        item = graph(topics=[topic("a", "solid")], attempts=[
            attempt("a", "2026-10-23T00:00:00+00:00", manual=True),
        ])
        result = self.plan(item)
        self.assertEqual((result.completed_topics, result.certified_topics, result.manual_only_topics), (1, 0, 1))
        self.assertEqual(result.recommendations[0].action, "verify")

    def test_failed_quiz_takes_precedence_over_old_pass(self):
        item = graph(topics=[topic("a", "needs_review")], attempts=[
            attempt("a", "2026-10-01T00:00:00+00:00"),
            attempt("a", "2026-10-18T00:00:00+00:00", passed=False, awarded=False, score=0.3),
            attempt("a", "2026-10-23T00:00:00+00:00", passed=False, awarded=False, score=0.4),
        ])
        result = self.plan(item)
        self.assertEqual(result.signals[0].failure_count, 2)
        self.assertEqual(result.signals[0].mastery_indicator, "practice_needed")
        self.assertEqual(result.recommendations[0].decision_rule, "latest_quiz_failed")

    def test_transitive_prerequisites_block_uncertified_path(self):
        item = graph(topics=[topic("a"), topic("b", "solid"), topic("c")],
                     edges=[requires("a", "b"), requires("b", "c")])
        result = self.plan(item)
        signal = next(s for s in result.signals if s.topic_id == "c")
        self.assertEqual(signal.blocked_prerequisite_ids, ["a"])
        rec = next(r for r in result.recommendations if r.topic_id == "c")
        self.assertEqual((rec.action, rec.related_topic_ids), ("unblock", ["a"]))

    def test_cycle_repairs_are_recommended_to_downstream_dependents(self):
        item = graph(topics=[topic("a", "solid"), topic("b", "solid"), topic("c", "solid")],
                     edges=[requires("a", "b"), requires("b", "a"), requires("b", "c")])
        result = self.plan(item)
        self.assertEqual(result.blocked_topics, 3)
        self.assertEqual([r.action for r in result.recommendations], ["repair_graph"] * 3)
        self.assertTrue(result.graph_warnings)

    def test_overlapping_cycles_self_loop_and_unrelated_topics(self):
        names = ("a", "b", "c", "d", "downstream", "self", "independent")
        item = graph(
            topics=[topic(name, "solid") for name in names],
            edges=[requires(a, b) for a, b in (
                ("a", "b"), ("b", "c"), ("c", "a"),
                ("c", "d"), ("d", "b"), ("d", "downstream"),
                ("self", "self"),
            )],
        )
        plan = self.plan(item)
        recommendations = {rec.topic_id: rec for rec in plan.recommendations}
        for name in ("a", "b", "c", "d", "downstream", "self"):
            self.assertEqual(recommendations[name].action, "repair_graph", name)
            self.assertIn("prerequisite_cycle", recommendations[name].evidence)
        self.assertNotIn("independent", recommendations)
        self.assertEqual(plan.blocked_topics, 6)

    def test_missing_prerequisite_edge_endpoints_are_reported(self):
        item = graph(topics=[topic("a"), topic("b")], edges=[requires("missing", "a"), requires("b", "missing2")])
        result = self.plan(item)
        self.assertEqual(result.blocked_topics, 2)
        self.assertEqual([r.action for r in result.recommendations], ["repair_graph", "repair_graph"])
        self.assertEqual(len(result.graph_warnings), 2)

    def test_naive_legacy_timestamp_and_stable_tie_breaking(self):
        item = graph(topics=[topic("z"), topic("a")], attempts=[
            attempt("a", "2026-10-01T00:00:00"),
        ])
        first = self.plan(item)
        second = self.plan(item)
        self.assertEqual(first.model_dump(mode="json"), second.model_dump(mode="json"))
        self.assertEqual(first.signals[0].latest_quiz_at.tzinfo, timezone.utc)
        self.assertEqual([r.topic_id for r in first.recommendations], ["a", "z"])

    def test_latest_quiz_follows_recorded_event_order_even_with_legacy_timestamps(self):
        previous_pass = attempt("a", "2026-10-23T00:00:00+00:00", score=1.0)
        for timestamp in ("2026-10-23T00:00:00+00:00", "2026-10-01T00:00:00+00:00"):
            with self.subTest(timestamp=timestamp):
                latest_failure = attempt("a", timestamp, passed=False, awarded=False, score=0.25)
                latest_failure.id = "a-later-failure"
                item = graph(topics=[topic("a", "needs_review")], attempts=[previous_pass, latest_failure])
                closure = QuizService(Settings()).build_closure_status(item, "a")
                plan = self.plan(item)
                self.assertEqual(closure.latest_attempt.id, latest_failure.id)
                self.assertEqual(plan.signals[0].latest_quiz_score, 0.25)
                self.assertEqual(plan.signals[0].mastery_indicator, "practice_needed")
                self.assertEqual(plan.recommendations[0].decision_rule, "latest_quiz_failed")

    def test_adaptive_blocking_matches_quiz_certification_on_seeded_graphs(self):
        """Keep study guidance and certification in agreement on graph defects.

        The seed and bounded sample make this a reproducible regression suite,
        not a proof that every possible graph is handled correctly.
        """
        random = Random(42)
        quiz_service = QuizService(Settings())
        for case in range(200):
            size = random.randint(2, 11)
            names = [f"n{i}" for i in range(size)]
            topics = [topic(name, random.choice(("solid", "mastered", "learning")))
                      for name in names]
            edges = []
            for index in range(random.randint(0, size * 3)):
                source = random.choice(names + ["missing"])
                target = random.choice(names + ["missing"])
                edges.append(Edge(id=f"edge-{index}", source_topic_id=source,
                                  target_topic_id=target, relation="requires"))
            item = graph(topics=topics, edges=edges)
            before = item.model_dump(mode="json")
            plan = self.plan(item)
            recommendations = {rec.topic_id: rec for rec in plan.recommendations}
            for name in names:
                closure = quiz_service.build_closure_status(item, name)
                guidance_blocks = (name in recommendations and
                                   recommendations[name].action in {"repair_graph", "unblock"})
                self.assertEqual(guidance_blocks, not closure.can_award_completion,
                                 f"case={case}, topic={name}, edges={[(e.source_topic_id, e.target_topic_id) for e in edges]}")
            self.assertEqual(item.model_dump(mode="json"), before, f"case={case}")


class AdaptiveLearningRouteTests(unittest.TestCase):
    def setUp(self):
        self.client, self.repo, _ = install_client(self)

    def test_plan_endpoint_matches_persisted_graph(self):
        item = self.repo.graph("mathematics-demo")
        response = self.client.get("/api/v1/graphs/mathematics-demo/learning-plan")
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual((result["graph_id"], result["graph_version"]), (item.graph_id, item.version))
        self.assertEqual(len(result["signals"]), len(item.topics))
        self.assertEqual(result["method"], "deterministic-heuristic-v1")

    def test_unknown_graph_returns_404(self):
        response = self.client.get("/api/v1/graphs/nonexistent/learning-plan")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
