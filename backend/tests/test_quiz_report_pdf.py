"""Submitted pedagogical PDF export: real records, scope, pagination and safety."""

from io import BytesIO
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from pypdf import PdfReader
from reportlab.platypus.doctemplate import LayoutError

from agent_test_support import install_client
from app.models.domain import QuizReportRecord
from app.services.pdf_export import MAX_REPORT_CHARS, PDFExportError, WATERMARK, render_quiz_report_pdf


class QuizReportPDFTests(unittest.TestCase):
    def setUp(self):
        self.client, self.repo, self.runtime = install_client(self, "closure")
        self.base = "/api/v1/graphs/mathematics-demo/topics/arithmetics/quiz"

    def submit(self):
        session = self.client.post(self.base + "/start", json={}).json()["session"]
        answers = [{"question_id": q["id"], "choice_index": 1} for q in session["questions"]]
        result = self.client.post(self.base + "/submit", json={
            "session_id": session["session_id"], "answers": answers,
        })
        self.assertEqual(result.status_code, 200, result.text)
        attempt_id = result.json()["attempt"]["id"]
        return attempt_id, self.base + "/reports/" + attempt_id + "/pdf"

    def read_pdf(self, content):
        self.assertTrue(content.startswith(b"%PDF-"))
        reader = PdfReader(BytesIO(content))
        self.assertGreaterEqual(len(reader.pages), 1)
        texts = [page.extract_text() for page in reader.pages]
        for text in texts:
            self.assertIn(WATERMARK, text)
        return reader, "\n".join(texts)

    def test_export_submitted_attempt_with_selectable_text_and_headers(self):
        attempt_id, url = self.submit()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, response.text[:200])
        self.assertEqual(response.headers["content-type"], "application/pdf")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertIn("attachment;", response.headers["content-disposition"])
        reader, text = self.read_pdf(response.content)
        self.assertIn("RELATÓRIO PEDAGÓGICO", text)
        self.assertIn("Nota:", text)
        self.assertIn("Questão 1", text)
        self.assertIn(attempt_id, text)
        self.assertEqual(reader.metadata.title, "Relatório pedagógico - JEW")

    def test_export_after_rollback_marks_historical_record(self):
        original_snapshot = self.repo.current().snapshot.id
        _, url = self.submit()
        self.repo.rollback_to(original_snapshot)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        _, text = self.read_pdf(response.content)
        self.assertIn("não integra o grafo atual", text)
        self.assertIn("registro histórico", text)

    def test_missing_attempt_wrong_topic_and_wrong_graph_return_404(self):
        _, url = self.submit()
        for path in (
            self.base + "/reports/unknown/pdf",
            url.replace("arithmetics", "functions"),
            url.replace("mathematics-demo", "another-graph"),
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_incompatible_version_and_corrupted_payload_are_safe(self):
        _, url = self.submit()
        with self.repo._connect() as conn:
            conn.execute("UPDATE quiz_pedagogical_reports SET format_version=2")
        self.assertEqual(self.client.get(url).status_code, 409)
        with self.repo._connect() as conn:
            conn.execute("UPDATE quiz_pedagogical_reports SET format_version=1, payload_json=?",
                         ("{secret private payload",))
        response = self.client.get(url)
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("secret", response.text)
        self.assertNotIn("private", response.text)

    def test_large_unicode_report_paginates_without_leaking_markup(self):
        attempt_id, _ = self.submit()
        payload = self.repo.get_quiz_report("mathematics-demo", "arithmetics", attempt_id)
        payload["report"]["title"] = 'Álgebra, funções e raízes: α + β = π; <script>alert("x")</script>'
        payload["report"]["strengths"] = [
            f"Revisão matemática número {i}: ângulo θ, inequação x² ≥ 0, ação didática <b>sem HTML</b>."
            for i in range(170)
        ]
        record = QuizReportRecord.model_validate(payload)
        reader, text = self.read_pdf(render_quiz_report_pdf(record, in_current_graph=True))
        self.assertGreater(len(reader.pages), 2)
        self.assertIn("Álgebra", text)
        self.assertIn("<script>", text)
        self.assertIn("<b>sem HTML</b>", text)
        self.assertIn("x²", text)
        self.assertIn("π", text)
        self.assertIn("Página 1", reader.pages[0].extract_text())
        self.assertIn(f"Página {len(reader.pages)}", reader.pages[-1].extract_text())

    def test_short_question_analyses_do_not_split_between_pages(self):
        attempt_id, _ = self.submit()
        payload = self.repo.get_quiz_report("mathematics-demo", "arithmetics", attempt_id)
        payload["report"]["strengths"] = ["Conteúdo sintético de paginação."] * 70
        record = QuizReportRecord.model_validate(payload)
        reader, _ = self.read_pdf(render_quiz_report_pdf(record, in_current_graph=True))
        self.assertGreater(len(reader.pages), 2)
        headings = actions = 0
        for page in reader.pages:
            text = page.extract_text()
            page_headings = len(re.findall(r"Questão \d+ - (?:Correta|Revisar|Não respondida)", text))
            page_actions = text.count("Próxima ação:")
            self.assertEqual(page_headings, page_actions, "Question analysis crossed a page boundary")
            headings += page_headings
            actions += page_actions
        self.assertEqual(headings, len(record.reviews))
        self.assertEqual(actions, len(record.reviews))

    def test_pdf_uses_bundled_font_when_system_fonts_are_unavailable(self):
        attempt_id, _ = self.submit()
        payload = self.repo.get_quiz_report("mathematics-demo", "arithmetics", attempt_id)
        payload["report"]["title"] = "Revisão de álgebra: x² ≥ 0 e π"
        record = QuizReportRecord.model_validate(payload)
        is_file = Path.is_file
        # Simulate a minimal installation that only has ReportLab's own font.
        with patch.object(Path, "is_file", autospec=True,
                          side_effect=lambda path: path.name == "Vera.ttf" and is_file(path)):
            content = render_quiz_report_pdf(record, in_current_graph=True)
        _, text = self.read_pdf(content)
        self.assertIn("Revisão de álgebra", text)
        self.assertIn("π", text)

    def test_reject_excessively_large_report(self):
        attempt_id, _ = self.submit()
        payload = self.repo.get_quiz_report("mathematics-demo", "arithmetics", attempt_id)
        payload["report"]["strengths"] = ["A" * MAX_REPORT_CHARS]
        with self.assertRaises(PDFExportError):
            render_quiz_report_pdf(QuizReportRecord.model_validate(payload), in_current_graph=True)

    def test_pdf_endpoint_requires_private_desktop_session_when_configured(self):
        _, url = self.submit()
        self.runtime.settings.desktop_token = "private-desktop-session"
        for headers in ({}, {"x-clew-session": "invalid"}):
            with self.subTest(headers=headers):
                response = self.client.get(url, headers=headers)
                self.assertEqual(response.status_code, 403)
                self.assertNotEqual(response.headers["content-type"], "application/pdf")
        response = self.client.get(url, headers={"x-clew-session": "private-desktop-session"})
        self.assertEqual(response.status_code, 200)
        self.read_pdf(response.content)

    def test_renderer_failure_returns_generic_error_without_private_data(self):
        _, url = self.submit()
        with patch("app.api.routes.render_quiz_report_pdf", side_effect=PDFExportError("private diagnostic")):
            response = self.client.get(url)
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("private diagnostic", response.text)
        self.assertEqual(response.json()["detail"], "Pedagogical PDF could not be generated")

    def test_reportlab_layout_failure_is_wrapped_safely(self):
        attempt_id, _ = self.submit()
        record = QuizReportRecord.model_validate(
            self.repo.get_quiz_report("mathematics-demo", "arithmetics", attempt_id))
        with patch("app.services.pdf_export.SimpleDocTemplate") as renderer:
            renderer.return_value.build.side_effect = LayoutError("internal content")
            with self.assertRaises(PDFExportError) as error:
                render_quiz_report_pdf(record, in_current_graph=True)
        self.assertNotIn("internal content", str(error.exception))


if __name__ == "__main__":
    unittest.main()
