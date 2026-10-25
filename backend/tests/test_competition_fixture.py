"""The public competition demonstration must be reproducible and synthetic."""

import json
import unittest
from pathlib import Path

from docs.competition.generate_demo_fixture import EVALUATED_AT, build_fixture


FIXTURE_PATH = Path(__file__).resolve().parents[2] / "docs" / "competition" / "demo_fixture.synthetic.json"


class CompetitionFixtureTests(unittest.TestCase):
    def test_fixture_matches_generated_data_byte_for_byte(self):
        expected = json.dumps(build_fixture(), ensure_ascii=False, indent=2) + "\n"
        self.assertEqual(FIXTURE_PATH.read_text(encoding="utf-8"), expected)

    def test_fixture_is_explicitly_synthetic_and_has_expected_invariants(self):
        payload = build_fixture()
        plan = payload["learning_plan"]
        graph = payload["graph"]

        self.assertIs(payload["synthetic"], True)
        self.assertIn("Synthetic", payload["disclaimer"])
        self.assertEqual(graph["generated_at"], EVALUATED_AT.isoformat().replace("+00:00", "Z"))
        self.assertEqual((plan["total_topics"], plan["completed_topics"]), (9, 2))
        self.assertEqual((plan["certified_topics"], plan["manual_only_topics"]), (1, 1))
        self.assertEqual((plan["due_reviews"], plan["blocked_topics"]), (1, 3))
        self.assertEqual(len(graph["quiz_attempts"]), 3)


if __name__ == "__main__":
    unittest.main()
