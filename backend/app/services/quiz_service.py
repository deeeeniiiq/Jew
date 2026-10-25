from __future__ import annotations
from uuid import uuid4

from app.core.config import Settings
from app.services.mathematical_validation import MathAudit, VALIDATOR_VERSION, audit_math_question
from app.models.domain import (
    QuizAttempt,
    QuizQuestion,
    QuizQuestionReview,
    QuizPedagogicalReport,
    QuizReportFinding,
    StudyGraph,
    Topic,
    TopicClosureStatus,
    TopicQuizSession,
)


def is_prerequisite_relation(relation: str) -> bool:
    return relation == "requires"


class QuizService:
    def __init__(self, settings: Settings):
        self._settings = settings

    @staticmethod
    def build_pedagogical_report(
        attempt: QuizAttempt, session: TopicQuizSession,
        reviews: list[QuizQuestionReview], topic_title: str,
    ) -> QuizPedagogicalReport:
        """Report only facts supported by the submitted choices and stored answer key.

        A multiple-choice selection cannot establish a cognitive error category.
        Historical scores lack an equivalent question-set fingerprint, so we do
        not claim improvement or regression from those attempts.
        """
        question_ids = [question.id for question in session.questions]
        review_ids = [review.question_id for review in reviews]
        if (len(set(question_ids)) != len(question_ids)
                or len(set(review_ids)) != len(review_ids)
                or set(question_ids) != set(review_ids)):
            raise ValueError("The pedagogical report requires exactly one review per question.")
        reviews_by_id = {review.question_id: review for review in reviews}
        findings: list[QuizReportFinding] = []
        for question in session.questions:
            review = reviews_by_id[question.id]
            if review.selected_choice is None:
                findings.append(QuizReportFinding(
                    question_id=question.id, outcome="unanswered",
                    observation="Nenhuma alternativa foi enviada nesta questão.",
                    error_category="not_answered",
                    next_action="Leia o enunciado e tente resolver antes de consultar o gabarito.",
                    verification_status=question.verification_status,
                ))
            elif review.was_correct:
                findings.append(QuizReportFinding(
                    question_id=question.id, outcome="correct",
                    observation="A alternativa enviada coincide com o gabarito registrado.",
                    next_action="Explique o raciocínio usado para consolidar a aprendizagem.",
                    verification_status=question.verification_status,
                ))
            else:
                findings.append(QuizReportFinding(
                    question_id=question.id, outcome="incorrect",
                    observation="A alternativa enviada difere do gabarito registrado.",
                    error_category="undetermined", diagnosis_confidence="insufficient",
                    evidence_needed="Resolução passo a passo e justificativa da alternativa escolhida.",
                    next_action="Compare seu procedimento com a explicação e resolva um exercício semelhante.",
                    verification_status=question.verification_status,
                ))
        correct = sum(review.was_correct for review in reviews)
        answered = sum(review.selected_choice is not None for review in reviews)
        missed = [index for index, finding in enumerate(findings, 1) if finding.outcome != "correct"]
        verified = sum(question.verification_status == "verified" for question in session.questions)
        evidence_limits = [
            "A alternativa final não revela a causa de um erro; categorias específicas precisam de resolução justificada.",
            "As questões não têm etiquetas de conceito auditadas; não é possível afirmar domínio por conceito.",
            "Tentativas anteriores não registram equivalência entre conjuntos de questões; evolução histórica não foi comparada.",
        ]
        if verified < len(session.questions):
            evidence_limits.append(
                f"{len(session.questions) - verified} gabarito(s) não tiveram verificação matemática determinística conclusiva."
            )
        return QuizPedagogicalReport(
            attempt_id=attempt.id, title=topic_title, attempted_at=attempt.created_at,
            question_count=len(reviews), answered_count=answered, correct_count=correct,
            incorrect_count=answered - correct, unanswered_count=len(reviews) - answered,
            # All questions enter the existing score, including unanswered ones.
            ungraded_count=0, score=attempt.score, generator=session.generator,
            grading_method="Comparação determinística com o gabarito registrado",
            verified_keys_count=verified, unverified_keys_count=len(reviews) - verified,
            strengths=[f"{correct} alternativa(s) coincidiram com o gabarito."] if correct else [],
            improvement_areas=[f"Revisar as questões {', '.join(map(str, missed))}."] if missed else [],
            evidence_limits=evidence_limits, question_findings=findings,
            recovery_plan=[
                "Revise as explicações das questões sinalizadas e os pré-requisitos do tópico.",
                "Resolva um exemplo trabalhado antes de tentar novamente sem consultar a resposta.",
                "Faça um novo conjunto de exercícios e registre os passos para permitir diagnóstico posterior.",
            ] if missed else ["Explique com suas palavras as soluções para verificar a consolidação."],
            historical_comparison=None,
            next_steps=["Retome as questões sinalizadas no relatório." if missed
                        else "Continue para o próximo conteúdo do seu percurso de estudo."],
        )

    def build_closure_status(self, graph: StudyGraph, topic_id: str) -> TopicClosureStatus:
        topic_map = {topic.id: topic for topic in graph.topics}
        topic = topic_map.get(topic_id)
        if topic is None:
            raise KeyError(topic_id)

        parent_map: dict[str, list[str]] = {item.id: [] for item in graph.topics}
        malformed_sources: set[str] = set()
        for edge in graph.edges:
            if not is_prerequisite_relation(edge.relation):
                continue
            if edge.target_topic_id not in topic_map and edge.source_topic_id in topic_map:
                malformed_sources.add(edge.source_topic_id)
            parent_map.setdefault(edge.target_topic_id, []).append(edge.source_topic_id)

        prerequisite_ids: list[str] = []
        seen: set[str] = set()
        stack = list(parent_map.get(topic_id, []))
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            prerequisite_ids.append(current)
            stack.extend(parent_map.get(current, []))

        # Detect cycles in the reachable prerequisite graph. A cycle can be
        # present even when every topic is already marked solid; it must never
        # permit a new closure award. The iterative DFS handles long graphs.
        visited: set[str] = set()
        # Keep the index of every active vertex so a back edge identifies
        # the entire cycle, rather than only the vertex it points to.
        active_position: dict[str, int] = {topic_id: 0}
        cycle_nodes: set[str] = set()
        path = [(topic_id, iter(parent_map.get(topic_id, [])))]
        while path:
            current, neighbors = path[-1]
            parent = next(neighbors, None)
            if parent is None:
                path.pop()
                active_position.pop(current)
                visited.add(current)
            elif parent not in topic_map:
                continue
            elif parent in active_position:
                cycle_nodes.update(node for node, _ in path[active_position[parent]:])
            elif parent not in visited:
                active_position[parent] = len(path)
                path.append((parent, iter(parent_map.get(parent, []))))

        blocked_ids = [
            prerequisite_id for prerequisite_id in prerequisite_ids
            if prerequisite_id not in topic_map
            or topic_map[prerequisite_id].state not in {"solid", "mastered"}
            or prerequisite_id in cycle_nodes
            or prerequisite_id in malformed_sources
        ]
        if (topic_id in cycle_nodes or topic_id in malformed_sources) and topic_id not in blocked_ids:
            blocked_ids.append(topic_id)
        latest_attempt = None
        for attempt in graph.quiz_attempts:
            if attempt.topic_id == topic_id:
                latest_attempt = attempt

        return TopicClosureStatus(
            topic_id=topic.id,
            prerequisite_topic_ids=prerequisite_ids,
            blocked_prerequisite_ids=blocked_ids,
            can_award_completion=len(blocked_ids) == 0,
            latest_attempt=latest_attempt,
        )

    def start_session(self, graph: StudyGraph, topic_id: str, question_count: int, *, questions: list[QuizQuestion], generator: str) -> TopicQuizSession:
        topic_map = {topic.id: topic for topic in graph.topics}
        topic = topic_map.get(topic_id)
        if topic is None:
            raise KeyError(topic_id)
        if question_count < 6 or question_count > 12:
            raise ValueError("question_count must be between 6 and 12")

        closure = self.build_closure_status(graph, topic_id)
        if not closure.can_award_completion:
            blocked_titles = [topic_map[item_id].title for item_id in closure.blocked_prerequisite_ids if item_id in topic_map]
            detail = ", ".join(blocked_titles[:6]) or "open prerequisites"
            raise ValueError(f"close prerequisite topics first: {detail}")
        questions = self._validate_ai_questions(questions, question_count)
        return TopicQuizSession(
            session_id=f"quiz_{uuid4().hex[:12]}",
            graph_id=graph.graph_id,
            topic_id=topic_id,
            question_count=len(questions),
            questions=questions,
            closure_status=closure,
            generator=generator,
        )

    def grade_session(
        self,
        graph: StudyGraph,
        session: TopicQuizSession,
        answers: dict[str, int],
        *,
        pass_threshold: float | None = None,
    ) -> tuple[QuizAttempt, TopicClosureStatus, str | None, list[QuizQuestionReview]]:
        # Re-audit sessions saved before the verifier existed. Never penalize a
        # learner for a provably broken key, even if the session is historical.
        self.ensure_mathematical_safety(session.questions)
        question_map = {question.id: question for question in session.questions}
        if any(question_id not in question_map or type(index) is not int
               or not 0 <= index < len(question_map[question_id].choices) for question_id, index in answers.items()):
            raise ValueError("Quiz answers must reference this test's questions and valid choices.")
        correct_count = 0
        reviews: list[QuizQuestionReview] = []
        for question in session.questions:
            selected_index = answers.get(question.id)
            was_correct = selected_index == question.correct_choice_index
            if was_correct:
                correct_count += 1
            reviews.append(
                QuizQuestionReview(
                    question_id=question.id,
                    prompt=question.prompt,
                    selected_choice=question.choices[selected_index] if selected_index is not None and 0 <= selected_index < len(question.choices) else None,
                    correct_choice=question.choices[question.correct_choice_index],
                    was_correct=was_correct,
                    explanation=question.explanation,
                )
            )
        score = correct_count / max(1, len(session.questions))
        closure = self.build_closure_status(graph, session.topic_id)
        passed = score >= (pass_threshold if pass_threshold is not None else topic_pass_threshold(graph, session.topic_id))
        closure_awarded = passed and closure.can_award_completion
        awarded_state = "solid" if closure_awarded else ("needs_review" if not passed else None)
        missed = [r.prompt for r in reviews if not r.was_correct]
        previous_fails = max(
            (a.fail_count for a in graph.quiz_attempts if a.topic_id == session.topic_id and a.source == "quiz"),
            default=0,
        )
        attempt = QuizAttempt(
            id=f"attempt_{uuid4().hex[:12]}",
            topic_id=session.topic_id,
            passed=passed,
            score=score,
            question_count=len(session.questions),
            closure_awarded=closure_awarded,
            missed_questions=missed,
            fail_count=previous_fails + (0 if passed else 1),
        )
        return attempt, closure, awarded_state, reviews

    def _validate_ai_questions(self, questions: list[QuizQuestion], question_count: int) -> list[QuizQuestion]:
        if len(questions) != question_count:
            raise ValueError(f"Expected exactly {question_count} quiz questions; received {len(questions)}.")
        prompts: set[str] = set()
        ids: set[str] = set()
        for question in questions:
            prompt = question.prompt.strip().casefold()
            if not prompt or prompt in prompts or question.id in ids:
                raise ValueError("Quiz questions require distinct nonempty prompts and ids.")
            choices = [choice.strip().casefold() for choice in question.choices]
            if len(choices) != 4 or len(set(choices)) != 4 or not all(choices):
                raise ValueError("Every quiz question requires four distinct nonempty choices.")
            if not 0 <= question.correct_choice_index < 4:
                raise ValueError("Quiz correct_choice_index is out of range.")
            prompts.add(prompt)
            ids.add(question.id)
        audits = self.ensure_mathematical_safety(questions)
        return [question.model_copy(update={
            "verification_status": "verified" if audit.status == "verified" else "unverified",
            "verification_version": VALIDATOR_VERSION,
        }) for question, audit in zip(questions, audits)]

    @staticmethod
    def ensure_mathematical_safety(questions: list[QuizQuestion]) -> list[MathAudit]:
        audits: list[MathAudit] = []
        for index, question in enumerate(questions, start=1):
            audit = audit_math_question(question)
            if audit.status == "rejected":
                raise ValueError(f"Quiz question {index} rejected by math verification: {audit.reason}.")
            audits.append(audit)
        return audits


def topic_pass_threshold(graph: StudyGraph, topic_id: str) -> float:
    for topic in graph.topics:
        if topic.id == topic_id:
            return topic.quiz_policy.pass_threshold
    return 0.75
