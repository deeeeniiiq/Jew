"""HTTP contract for editable, persistent topic notes."""
import unittest

from agent_test_support import install_client
from app.services.repository import GraphRepository


class TopicNotesRouteTests(unittest.TestCase):
    def setUp(self):
        self.client, self.repo, _ = install_client(self)
        self.url = "/api/v1/workspace/graphs/mathematics-demo/topics/arithmetics/note"

    def test_note_is_saved_and_available_after_restart(self):
        markdown = "# Frações\n\nAnotar [[algebra-basics]] aqui."
        response = self.client.put(self.url, json={"note_markdown": markdown})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["note_markdown"], markdown)
        graph = GraphRepository(self.repo._db_path).graph("mathematics-demo")
        self.assertEqual(next(item.note_markdown for item in graph.topics if item.id == "arithmetics"), markdown)

    def test_invalid_input_and_missing_topic_do_not_create_snapshot(self):
        before = self.repo.current().snapshot.id
        self.assertEqual(self.client.put(self.url, json={"note_markdown": "x" * 200001}).status_code, 422)
        self.assertEqual(self.client.put(self.url.replace("arithmetics", "missing"), json={"note_markdown": "x"}).status_code, 404)
        self.assertEqual(self.repo.current().snapshot.id, before)
