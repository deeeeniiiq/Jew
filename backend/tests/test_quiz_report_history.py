"""Durable quiz evidence, isolation and transaction boundary regressions."""

import sqlite3
import unittest

from agent_test_support import install_client
from app.services.repository import GraphRepository


class QuizReportHistoryTests(unittest.TestCase):
    def setUp(self):
        self.client, self.repo, _ = install_client(self, "closure")
        self.base = "/api/v1/graphs/mathematics-demo/topics/arithmetics/quiz"

    def submit(self):
        session = self.client.post(self.base + "/start", json={}).json()["session"]
        answers = [{"question_id": q["id"], "choice_index": 1} for q in session["questions"]]
        result = self.client.post(self.base + "/submit", json={
            "session_id": session["session_id"], "answers": answers,
        })
        self.assertEqual(result.status_code, 200, result.text)
        return session, result.json()

    def test_save_fetch_and_reopen_repository(self):
        session, submitted = self.submit()
        attempt_id = submitted["attempt"]["id"]
        history = self.client.get(self.base + "/reports")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()["total"], 1)
        self.assertEqual(history.json()["items"][0]["attempt_id"], attempt_id)
        self.assertTrue(history.json()["items"][0]["in_current_graph"])
        details = self.client.get(self.base + "/reports/" + attempt_id).json()
        self.assertEqual(details["format_version"], 1)
        self.assertEqual(details["report"], submitted["report"])
        self.assertEqual(details["reviews"], submitted["reviews"])
        self.assertEqual([q["question_id"] for q in details["reviews"]],
                         [q["id"] for q in session["questions"]])
        reopened = GraphRepository(self.repo._db_path)
        self.assertEqual(reopened.get_quiz_report("mathematics-demo", "arithmetics", attempt_id)["report"],
                         submitted["report"])
        self.assertEqual(self.client.get(self.base + "/reports/unknown").status_code, 404)
        self.assertEqual(self.client.get(self.base.replace("arithmetics", "functions") +
                                         "/reports/" + attempt_id).status_code, 404)

    def test_multiple_attempts_pagination_and_legacy_manual_entry(self):
        _, first = self.submit()
        self.client.post("/api/v1/graphs/mathematics-demo/topics/arithmetics/mark-finished")
        _, second = self.submit()
        result = self.client.get(self.base + "/reports?limit=1&offset=0").json()
        self.assertEqual(result["total"], 2)
        self.assertEqual(len(result["items"]), 1)
        next_page = self.client.get(self.base + "/reports?limit=1&offset=1").json()
        self.assertEqual(len(next_page["items"]), 1)
        self.assertEqual({result["items"][0]["attempt_id"], next_page["items"][0]["attempt_id"]},
                         {first["attempt"]["id"], second["attempt"]["id"]})
        self.assertEqual(self.client.get(self.base + "/reports?limit=101").status_code, 422)
        self.assertEqual(self.client.get(self.base + "/reports?offset=-1").status_code, 422)

    def test_rollback_preserves_audit_but_marks_attempt_as_reverted(self):
        before = self.repo.current().snapshot.id
        _, submitted = self.submit()
        attempt_id = submitted["attempt"]["id"]
        self.repo.rollback_to(before)
        history = self.client.get(self.base + "/reports").json()
        self.assertEqual(history["total"], 1)
        self.assertFalse(history["items"][0]["in_current_graph"])
        self.assertFalse(self.client.get(self.base + "/reports/" + attempt_id).json()["in_current_graph"])

    def test_deleting_graph_erases_educational_records(self):
        self.submit()
        self.repo.delete_graph("mathematics-demo")
        with self.repo._connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM quiz_pedagogical_reports").fetchone()[0], 0)
        self.assertEqual(self.client.get(self.base + "/reports").status_code, 404)

    def test_failed_report_insert_rolls_back_session_draft_and_snapshot(self):
        session = self.client.post(self.base + "/start", json={}).json()["session"]
        sid = session["session_id"]
        draft_url = f"{self.base}/{sid}/draft"
        self.assertEqual(self.client.put(draft_url, json={"notes": {
            session["questions"][0]["id"]: "retain my note",
        }}).status_code, 200)
        original_snapshot = self.repo.current().snapshot.id
        with self.repo._connect() as conn:
            conn.execute("""CREATE TRIGGER reject_report BEFORE INSERT ON quiz_pedagogical_reports
                            BEGIN SELECT RAISE(ABORT, 'report insert blocked'); END""")
        answers = [{"question_id": q["id"], "choice_index": 1} for q in session["questions"]]
        with self.assertRaises(sqlite3.IntegrityError):
            self.client.post(self.base + "/submit", json={"session_id": sid, "answers": answers})
        self.assertEqual(self.repo.current().snapshot.id, original_snapshot)
        self.assertEqual(self.client.get(draft_url).json()["notes"], {
            session["questions"][0]["id"]: "retain my note",
        })
        with self.repo._connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM quiz_pedagogical_reports").fetchone()[0], 0)
            conn.execute("DROP TRIGGER reject_report")
        submitted = self.client.post(self.base + "/submit", json={"session_id": sid, "answers": answers})
        self.assertEqual(submitted.status_code, 200, submitted.text)
        self.assertEqual(self.client.get(draft_url).status_code, 404)
        self.assertEqual(self.client.post(self.base + "/submit", json={
            "session_id": sid, "answers": answers,
        }).status_code, 404)

    def test_invalid_version_is_rejected_instead_of_falling_back(self):
        _, submitted = self.submit()
        with self.repo._connect() as conn:
            conn.execute("UPDATE quiz_pedagogical_reports SET format_version=2")
        with self.assertRaisesRegex(ValueError, "Unsupported pedagogical report"):
            self.repo.get_quiz_report("mathematics-demo", "arithmetics", submitted["attempt"]["id"])
        for path in (self.base + "/reports", self.base + "/reports/" + submitted["attempt"]["id"]):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()["detail"], "Stored report uses an unsupported format version")

    def test_corrupted_payload_returns_safe_error_without_leaking_data(self):
        _, submitted = self.submit()
        with self.repo._connect() as conn:
            conn.execute("UPDATE quiz_pedagogical_reports SET payload_json=?", ("{private malformed payload",))
        for path in (self.base + "/reports", self.base + "/reports/" + submitted["attempt"]["id"]):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 500)
            self.assertEqual(response.json()["detail"], "Stored pedagogical report failed integrity checks")
            self.assertNotIn("private", response.text)

    def test_report_metadata_mismatch_is_rejected(self):
        _, submitted = self.submit()
        with self.repo._connect() as conn:
            conn.execute("UPDATE quiz_pedagogical_reports SET created_at=?", ("2000-01-01T00:00:00+00:00",))
        response = self.client.get(self.base + "/reports/" + submitted["attempt"]["id"])
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"], "Stored pedagogical report failed integrity checks")


if __name__ == "__main__":
    unittest.main()
