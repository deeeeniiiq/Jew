"""Independent reference calculations for deterministic quiz verification."""
from __future__ import annotations

import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

from app.core.config import Settings
from app.models.domain import QuizQuestion
from app.services.mathematical_validation import VALIDATOR_VERSION, audit_math_question
from app.services.quiz_service import QuizService
from app.services.repository import GraphRepository


def question(prompt: str, choices: list[str], answer: int = 1, explanation: str = "") -> QuizQuestion:
    return QuizQuestion(id="check", prompt=prompt, choices=choices,
                        correct_choice_index=answer, explanation=explanation)


class MathematicalValidationTests(unittest.TestCase):
    def test_reference_cases(self):
        cases = [
            ("Quanto é 7 × 8?", ["54", "56", "58", "64"], "verified"),
            ("What is 7 * 8?", ["54", "56", "58", "64"], "verified"),
            ("Calcule (8 + 4)/3", ["3", "4", "5", "6"], "verified"),
            ("Quanto é 1/2 + 1/4?", ["1/2", "3/4", "1/4", "1"], "verified"),
            ("Simplifique 2/4", ["1", "0,5", "2", "3"], "verified"),
            ("Quanto é 20% de 150?", ["25", "30", "35", "40"], "verified"),
            ("Se x/9 = 2/3, qual é o valor de x?", ["4", "6", "8", "10"], "verified"),
            ("Resolva 2x + 3 = 11", ["3", "4", "5", "6"], "verified"),
            ("Quanto é 7 × 8?", ["54", "55", "58", "64"], "rejected"),
            ("Quanto é 7 × 8?", ["54", "56", "58", "64"], "rejected"),
            ("Quanto é 1/2 + 1/4?", ["0,75", "3/4", "1/4", "1"], "rejected"),
            ("Quanto é 1/0?", ["0", "1", "2", "3"], "rejected"),
            ("Resolva x = x + 1", ["0", "1", "2", "3"], "rejected"),
            ("Qual é a definição de fotossíntese?", ["A", "B", "C", "D"], "unverified"),
            ("Resolva x^2 = 4", ["0", "2", "4", "5"], "unverified"),
            ("Quanto é __import__('os').system('exit')?", ["0", "1", "2", "3"], "unverified"),
        ]
        for index, (prompt, choices, expected) in enumerate(cases):
            with self.subTest(index=index, prompt=prompt):
                actual = audit_math_question(question(prompt, choices, answer=0 if index == 9 else 1))
                self.assertEqual(actual.status, expected, actual.reason)

    def test_explanation_cannot_override_independent_arithmetic(self):
        original = question("Quanto é 7 × 8?", ["54", "56", "58", "64"],
                            explanation="7 × 8 = 54")
        self.assertEqual(audit_math_question(original).status, "rejected")

    def test_explanation_equation_conflicts_with_correct_key(self):
        original = question("Se x/9 = 2/3, qual é o valor de x?", ["4", "6", "8", "10"],
                            explanation="Obtemos x = 4")
        self.assertEqual(audit_math_question(original).status, "rejected")

    def test_correct_symbolic_and_percentage_explanations_are_not_rejected(self):
        linear = question("Resolva 2x + 3 = 11", ["3", "4", "5", "6"],
                          explanation="A equação 2x + 3 = 11; portanto x = 4.")
        percent = question("Quanto é 20% de 150?", ["25", "30", "35", "40"],
                           explanation="20% de 150 = 30.")
        for item in (linear, percent):
            with self.subTest(explanation=item.explanation):
                self.assertEqual(audit_math_question(item).status, "verified")

    def test_incorrect_percentage_explanation_is_rejected(self):
        original = question("Quanto é 20% de 150?", ["25", "30", "35", "40"],
                            explanation="20% de 150 = 35.")
        self.assertEqual(audit_math_question(original).status, "rejected")

    def test_zero_result_and_numeric_equivalence(self):
        original = question("Calcule 2 - 2", ["1", "0", "0/2", "3"])
        self.assertEqual(audit_math_question(original).status, "rejected")

    def test_150_reference_cases_generated_from_independent_integer_arithmetic(self):
        # The expected answer is produced by Python integer operations, not by
        # the verifier or an AI provider; all 150 cases have one unique key.
        for a in range(1, 31):
            operations = [
                (f"Quanto é {a} + 13?", a + 13),
                (f"Quanto é {a} - 13?", a - 13),
                (f"Quanto é {a} × 7?", a * 7),
                (f"Quanto é {a * 6} / 6?", a),
                (f"Quanto é ({a} + 4) × 2?", (a + 4) * 2),
            ]
            for prompt, expected in operations:
                with self.subTest(prompt=prompt):
                    choices = [str(expected - 1), str(expected), str(expected + 1), str(expected + 2)]
                    self.assertEqual(audit_math_question(question(prompt, choices)).status, "verified")

    def test_reject_before_save_and_revalidate_historical_session(self):
        with tempfile.TemporaryDirectory() as folder:
            repository = GraphRepository(Path(folder) / "quiz.sqlite3")
            service = QuizService(Settings())
            graph = repository.graph("mathematics-demo")
            good = [QuizQuestion(id=f"q{i}", prompt=f"Quanto é {i} + 2?",
                                 choices=[str(i + 1), str(i + 2), str(i + 3), str(i + 4)],
                                 correct_choice_index=1) for i in range(6)]
            bad = [item.model_copy(deep=True) for item in good]
            bad[0].correct_choice_index = 0
            with self.assertRaisesRegex(ValueError, "math verification"):
                service.start_session(graph, "arithmetics", 6, questions=bad, generator="mock")
            self.assertIsNone(repository.latest_quiz_session_for_topic(graph.graph_id, "arithmetics"))

            session = service.start_session(graph, "arithmetics", 6, questions=good, generator="mock")
            self.assertEqual(session.questions[0].verification_status, "verified")
            self.assertEqual(session.questions[0].verification_version, VALIDATOR_VERSION)
            repository.save_quiz_session(session)
            saved = repository.quiz_session(session.session_id)
            saved.questions[0].correct_choice_index = 0
            saved.questions[0].verification_status = "verified"  # forged or stale metadata
            repository.save_quiz_session(saved)
            before = repository.current().snapshot.id
            with self.assertRaisesRegex(ValueError, "math verification"):
                service.grade_session(graph, saved, {q.id: 1 for q in saved.questions})
            self.assertEqual(repository.current().snapshot.id, before)
            self.assertEqual(graph.quiz_attempts, [])
            self.assertEqual(repository.quiz_session(session.session_id).session_id, session.session_id)

    def test_legacy_question_metadata_defaults_to_unverified(self):
        old = QuizQuestion.model_validate({
            "id": "legacy", "prompt": "O que é história?", "choices": ["A", "B", "C", "D"],
            "correct_choice_index": 0,
        })
        self.assertEqual(old.verification_status, "unverified")
        self.assertIsNone(old.verification_version)


if __name__ == "__main__":
    unittest.main()
