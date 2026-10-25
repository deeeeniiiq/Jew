from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

from app.models.domain import (
    CreateGraphRequest,
    QuizAttempt,
    TopicClosureStatus,
    TopicQuizSession,
)
from app.services.repository import GraphRepository, RepositoryConflictError
from app.services import repository_storage


class RepositoryConcurrencyTests(unittest.TestCase):
    """Exercise independent SQLite connections with reads staged at the same revision."""

    def setUp(self) -> None:
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        self.database = Path(tempdir.name) / "concurrent.sqlite3"
        self.first = GraphRepository(self.database)
        self.second = GraphRepository(self.database)

    def _race(self, left, right):
        gate = Barrier(2, timeout=10)
        first_current = self.first.current
        second_current = self.second.current

        def staged_read(read):
            envelope = read()
            gate.wait()
            return envelope

        def result(operation):
            try:
                return operation()
            except Exception as exc:
                return exc

        with (
            patch.object(self.first, "current", side_effect=lambda: staged_read(first_current)),
            patch.object(self.second, "current", side_effect=lambda: staged_read(second_current)),
            ThreadPoolExecutor(max_workers=2) as executor,
        ):
            pending = (executor.submit(result, left), executor.submit(result, right))
            return tuple(item.result(timeout=20) for item in pending)

    def _one_winner_one_conflict(self, outcomes):
        winners = [outcome for outcome in outcomes if not isinstance(outcome, Exception)]
        conflicts = [outcome for outcome in outcomes if isinstance(outcome, RepositoryConflictError)]
        self.assertEqual(len(winners), 1, outcomes)
        self.assertEqual(len(conflicts), 1, outcomes)
        return 0 if not isinstance(outcomes[0], Exception) else 1

    def _assert_linear_snapshots(self):
        snapshots = list(reversed(self.first.list_snapshots(limit=100)))
        self.assertEqual(snapshots[0].parent_snapshot_id, None)
        for previous, subsequent in zip(snapshots, snapshots[1:]):
            self.assertEqual(subsequent.parent_snapshot_id, previous.id)
        self.assertEqual(self.first.current().snapshot.id, snapshots[-1].id)
        return len(snapshots)

    def test_independent_graph_writes_report_conflict_and_can_retry(self):
        self.first.create_graph(CreateGraphRequest(title="Physics", subject="physics"))
        initial = self._assert_linear_snapshots()
        outcomes = self._race(
            lambda: self.first.rename_graph("mathematics-demo", "Revised Mathematics"),
            lambda: self.second.rename_graph("physics", "Revised Physics"),
        )
        winner = self._one_winner_one_conflict(outcomes)
        self.assertEqual(self._assert_linear_snapshots(), initial + 1)
        if winner == 0:
            self.second.rename_graph("physics", "Revised Physics")
        else:
            self.first.rename_graph("mathematics-demo", "Revised Mathematics")
        graphs = {graph.graph_id: graph for graph in self.first.current().workspace.graphs}
        self.assertEqual(graphs["mathematics-demo"].title, "Revised Mathematics")
        self.assertEqual(graphs["physics"].title, "Revised Physics")
        self.assertEqual(self._assert_linear_snapshots(), initial + 2)

    def test_simultaneous_changes_to_same_graph_do_not_overwrite(self):
        initial = self._assert_linear_snapshots()
        outcomes = self._race(
            lambda: self.first.rename_graph("mathematics-demo", "First title"),
            lambda: self.second.rename_graph("mathematics-demo", "Second title"),
        )
        winner = self._one_winner_one_conflict(outcomes)
        self.assertEqual(self.first.graph("mathematics-demo").title, "First title" if winner == 0 else "Second title")
        self.assertEqual(self._assert_linear_snapshots(), initial + 1)

    def test_quiz_conflict_rolls_back_session_consumption(self):
        session = TopicQuizSession(
            session_id="race-quiz", graph_id="mathematics-demo", topic_id="arithmetics",
            question_count=6, closure_status=TopicClosureStatus(topic_id="arithmetics"),
        )
        attempt = QuizAttempt(
            id="race-attempt", topic_id="arithmetics", passed=False,
            score=0.0, question_count=6,
        )
        self.first.save_quiz_session(session)
        base_version = self.first.graph("mathematics-demo").version
        initial = self._assert_linear_snapshots()
        outcomes = self._race(
            lambda: self.first.record_quiz_attempt(
                "mathematics-demo", attempt, None,
                base_graph_version=base_version, session_id=session.session_id,
            ),
            lambda: self.second.rename_graph("mathematics-demo", "Updated Mathematics"),
        )
        winner = self._one_winner_one_conflict(outcomes)
        self.assertEqual(self._assert_linear_snapshots(), initial + 1)
        if winner == 0:
            with self.assertRaises(KeyError):
                self.first.quiz_session(session.session_id)
            self.second.rename_graph("mathematics-demo", "Updated Mathematics")
        else:
            self.assertEqual(self.first.quiz_session(session.session_id).session_id, session.session_id)
            self.first.record_quiz_attempt(
                "mathematics-demo", attempt, None,
                base_graph_version=self.first.graph("mathematics-demo").version,
                session_id=session.session_id,
            )
        graph = self.first.graph("mathematics-demo")
        self.assertEqual(graph.title, "Updated Mathematics")
        self.assertEqual([item.id for item in graph.quiz_attempts if item.id == attempt.id], [attempt.id])
        with self.assertRaises(KeyError):
            self.first.quiz_session(session.session_id)
        self.assertEqual(self._assert_linear_snapshots(), initial + 2)

    def test_simultaneous_submissions_of_same_session_have_single_winner(self):
        session = TopicQuizSession(
            session_id="same-session-race",
            graph_id="mathematics-demo",
            topic_id="arithmetics",
            question_count=6,
            closure_status=TopicClosureStatus(topic_id="arithmetics"),
        )
        attempt = QuizAttempt(
            id="same-session-attempt", topic_id="arithmetics",
            passed=False, score=0.0, question_count=6,
        )
        self.first.save_quiz_session(session)
        base_version = self.first.graph("mathematics-demo").version
        initial_snapshots = self._assert_linear_snapshots()

        # Both independent repositories read the same revision before either
        # obtains SQLite's writer lock and tries to consume the same session.
        outcomes = self._race(
            lambda: self.first.record_quiz_attempt(
                "mathematics-demo", attempt, None,
                base_graph_version=base_version, session_id=session.session_id,
            ),
            lambda: self.second.record_quiz_attempt(
                "mathematics-demo", attempt, None,
                base_graph_version=base_version, session_id=session.session_id,
            ),
        )
        self._one_winner_one_conflict(outcomes)

        graph = self.first.graph("mathematics-demo")
        self.assertEqual([a.id for a in graph.quiz_attempts], [attempt.id])
        self.assertEqual(self._assert_linear_snapshots(), initial_snapshots + 1)
        with self.assertRaises(KeyError):
            self.second.quiz_session(session.session_id)

    def test_rollback_and_update_preserve_snapshot_ancestry(self):
        target_id = self.first.current().snapshot.id
        self.first.rename_graph("mathematics-demo", "Temporary title")
        initial = self._assert_linear_snapshots()
        outcomes = self._race(
            lambda: self.first.rollback_to(target_id),
            lambda: self.second.rename_graph("mathematics-demo", "Concurrent title"),
        )
        winner = self._one_winner_one_conflict(outcomes)
        self.assertEqual(self._assert_linear_snapshots(), initial + 1)
        if winner == 1:
            self.first.rollback_to(target_id)
        self.assertEqual(self.first.graph("mathematics-demo").title, "Mathematics demo")
        self.assertEqual(self._assert_linear_snapshots(), initial + (2 if winner == 1 else 1))

    def test_import_and_create_cannot_reuse_same_id_silently(self):
        package = self.first.export_graph_package("mathematics-demo", title="Race copy")
        initial = self._assert_linear_snapshots()
        outcomes = self._race(
            lambda: self.first.import_graph_package(package, title="Race copy"),
            lambda: self.second.create_graph(CreateGraphRequest(title="Race copy", subject="math")),
        )
        winner = self._one_winner_one_conflict(outcomes)
        self.assertEqual(self._assert_linear_snapshots(), initial + 1)
        if winner == 0:
            self.second.create_graph(CreateGraphRequest(title="Race copy", subject="math"))
        else:
            self.first.import_graph_package(package, title="Race copy")
        ids = {graph.graph_id for graph in self.first.current().workspace.graphs}
        self.assertTrue({"mathematics-demo", "race-copy", "race-copy-2"} <= ids)
        self.assertEqual(self._assert_linear_snapshots(), initial + 2)

    def test_concurrent_seed_check_creates_one_initial_snapshot(self):
        # Use only the disposable fixture database to exercise first-run bootstrap.
        with self.first._connect() as conn:
            conn.execute("DELETE FROM graph_snapshots")

        original_insert = repository_storage.insert_snapshot
        insert_gate = Barrier(2, timeout=5)

        def coordinated_insert(conn, *args, **kwargs):
            # Before the fix, both reads occur outside a transaction, allowing
            # both contenders to reach this point and insert two seed rows.
            if not conn.in_transaction:
                insert_gate.wait()
            return original_insert(conn, *args, **kwargs)

        start_gate = Barrier(2, timeout=10)

        def bootstrap(repository):
            start_gate.wait()
            repository._ensure_seed()

        with (
            patch.object(repository_storage, "insert_snapshot", side_effect=coordinated_insert),
            ThreadPoolExecutor(max_workers=2) as executor,
        ):
            first = executor.submit(bootstrap, self.first)
            second = executor.submit(bootstrap, self.second)
            first.result(timeout=20)
            second.result(timeout=20)

        self.assertEqual(self._assert_linear_snapshots(), 1)

    def test_concurrent_fresh_repository_construction_has_single_seed(self):
        other_database = self.database.with_name("fresh.sqlite3")
        start_gate = Barrier(2, timeout=10)

        def construct():
            start_gate.wait()
            return GraphRepository(other_database)

        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(construct)
            second = executor.submit(construct)
            repositories = (first.result(timeout=20), second.result(timeout=20))
        self.assertEqual(len(repositories[0].list_snapshots()), 1)
        self.assertEqual(repositories[0].current().snapshot.id, repositories[1].current().snapshot.id)


if __name__ == "__main__":
    unittest.main()
