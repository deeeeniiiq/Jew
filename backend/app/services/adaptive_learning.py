"""Explainable, deterministic learning suggestions from persisted graph evidence.

The labels and review intervals are product heuristics, not validated estimates
of learner knowledge or scientific claims about spaced repetition efficacy.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, Field

from app.models.domain import QuizAttempt, StudyGraph, utc_now


class TopicLearningSignal(BaseModel):
    topic_id: str
    evidence_level: Literal["none", "manual_only", "quiz"]
    mastery_indicator: Literal["insufficient_evidence", "practice_needed", "quiz_passed"]
    quiz_attempts: int
    latest_quiz_score: float | None = None
    latest_quiz_at: datetime | None = None
    failure_count: int
    blocked_prerequisite_ids: list[str] = Field(default_factory=list)
    next_review_at: datetime | None = None
    review_due: bool = False


class LearningRecommendation(BaseModel):
    topic_id: str
    action: Literal["study", "practice", "review", "verify", "unblock", "repair_graph"]
    priority: int
    reason: str
    decision_rule: str
    evidence: list[str]
    related_topic_ids: list[str] = Field(default_factory=list)
    completion_condition: str


class LearningPlan(BaseModel):
    graph_id: str
    graph_version: int
    evaluated_at: datetime
    total_topics: int
    completed_topics: int
    certified_topics: int
    manual_only_topics: int
    due_reviews: int
    blocked_topics: int
    signals: list[TopicLearningSignal]
    recommendations: list[LearningRecommendation]
    graph_warnings: list[str] = Field(default_factory=list)
    method: str = "deterministic-heuristic-v1"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _ordered(attempts: list[QuizAttempt]) -> list[QuizAttempt]:
    # The snapshot stores attempts in event order. Legacy/imported timestamps
    # can tie or predate earlier events; certification and the UI also use the
    # last appended attempt as the most recent academic action.
    return list(attempts)


class AdaptiveLearningService:
    """Pure read-only computation; no writes, model calls or inferred quiz marks."""

    def build_plan(self, graph: StudyGraph, *, now: datetime | None = None) -> LearningPlan:
        current = _as_utc(now if now is not None else utc_now())
        topics = {topic.id: topic for topic in graph.topics}
        parents: dict[str, set[str]] = {id: set() for id in topics}
        dependents: dict[str, set[str]] = {id: set() for id in topics}
        malformed: set[str] = set()
        warnings: list[str] = []
        for edge in graph.edges:
            if edge.relation != "requires":
                continue
            if edge.source_topic_id not in topics or edge.target_topic_id not in topics:
                warnings.append(f"Missing topic in requires edge {edge.id}.")
                if edge.target_topic_id in topics:
                    malformed.add(edge.target_topic_id)
                if edge.source_topic_id in topics:
                    malformed.add(edge.source_topic_id)
                continue
            parents[edge.target_topic_id].add(edge.source_topic_id)
            dependents[edge.source_topic_id].add(edge.target_topic_id)

        # Find all ancestors first, so cycles and broken links also invalidate
        # dependent study paths regardless of topic iteration order.
        ancestors_by_topic: dict[str, set[str]] = {}
        for topic_id in sorted(topics):
            ancestors: set[str] = set()
            pending = list(parents[topic_id])
            while pending:
                ancestor = pending.pop()
                if ancestor in ancestors:
                    continue
                ancestors.add(ancestor)
                pending.extend(parents.get(ancestor, ()))
            ancestors_by_topic[topic_id] = ancestors
        cycle_members = {topic_id for topic_id, ancestors in ancestors_by_topic.items() if topic_id in ancestors}
        warnings.extend(f"Cyclic prerequisite chain includes {topic_id}." for topic_id in sorted(cycle_members))

        attempts_by_topic: dict[str, list[QuizAttempt]] = defaultdict(list)
        for attempt in graph.quiz_attempts:
            if attempt.topic_id in topics:
                attempts_by_topic[attempt.topic_id].append(attempt)

        signals: list[TopicLearningSignal] = []
        recommendations: list[LearningRecommendation] = []
        certified = manual_only = due_reviews = blocked_topics = 0

        for topic_id in sorted(topics):
            topic = topics[topic_id]
            ancestors = ancestors_by_topic[topic_id]
            invalid_links = sorted((ancestors | {topic_id}) & (malformed | cycle_members))
            blockers = sorted(
                parent_id for parent_id in ancestors
                if parent_id not in topics or topics[parent_id].state not in {"solid", "mastered"}
            )
            if topic_id in cycle_members and topic_id not in blockers:
                blockers.append(topic_id)
                blockers.sort()
            if invalid_links or blockers:
                blocked_topics += 1

            ordered = _ordered(attempts_by_topic[topic_id])
            quizzes = [a for a in ordered if a.source != "manual" and not a.id.startswith("manual-")]
            manual_only_evidence = bool(ordered) and not quizzes
            if manual_only_evidence:
                manual_only += 1
            last_quiz = quizzes[-1] if quizzes else None
            if (topic.state in {"solid", "mastered"} and last_quiz
                    and last_quiz.passed and last_quiz.closure_awarded):
                certified += 1

            due_at = None
            due = False
            if last_quiz and last_quiz.passed:
                streak = 0
                for attempt in reversed(quizzes):
                    if not attempt.passed:
                        break
                    streak += 1
                interval_days = (2, 5, 12, 25)[min(streak, 4) - 1]
                due_at = _as_utc(last_quiz.created_at) + timedelta(days=interval_days)
                due = due_at <= current
            if due:
                due_reviews += 1
            signal = TopicLearningSignal(
                topic_id=topic_id,
                evidence_level="quiz" if quizzes else "manual_only" if manual_only_evidence else "none",
                mastery_indicator=(
                    "insufficient_evidence" if not last_quiz else
                    "quiz_passed" if last_quiz.passed else "practice_needed"
                ),
                quiz_attempts=len(quizzes),
                latest_quiz_score=last_quiz.score if last_quiz else None,
                latest_quiz_at=_as_utc(last_quiz.created_at) if last_quiz else None,
                failure_count=sum(not attempt.passed for attempt in quizzes),
                blocked_prerequisite_ids=blockers,
                next_review_at=due_at,
                review_due=due,
            )
            signals.append(signal)

            # Priority is a stable ranking heuristic, not a knowledge probability.
            structural_bonus = min(12, len(dependents[topic_id]) * 2)
            if invalid_links:
                recommendation = LearningRecommendation(
                    topic_id=topic_id, action="repair_graph", priority=100,
                    reason="The prerequisite graph is inconsistent for this topic.",
                    decision_rule="repair_invalid_prerequisite_graph",
                    evidence=(["missing_prerequisite"] if (ancestors | {topic_id}) & malformed else [])
                    + (["prerequisite_cycle"] if (ancestors | {topic_id}) & cycle_members else []),
                    related_topic_ids=invalid_links,
                    completion_condition="Fix the graph prerequisites before using this study path.",
                )
            elif blockers:
                recommendation = LearningRecommendation(
                    topic_id=topic_id, action="unblock", priority=50 + structural_bonus,
                    reason="Complete the prerequisite topics before attempting this topic's closure quiz.",
                    decision_rule="transitive_requires_not_closed",
                    evidence=["prerequisite_states"],
                    related_topic_ids=blockers,
                    completion_condition="All prerequisite topics become solid or mastered.",
                )
            elif last_quiz and not last_quiz.passed:
                recommendation = LearningRecommendation(
                    topic_id=topic_id, action="practice", priority=85 + structural_bonus,
                    reason=f"Latest quiz did not pass ({last_quiz.score:.0%}); practice before retrying.",
                    decision_rule="latest_quiz_failed",
                    evidence=["quiz_score", "quiz_passed", "quiz_timestamp"],
                    completion_condition="Pass a new quiz with all prerequisites satisfied.",
                )
            elif due:
                recommendation = LearningRecommendation(
                    topic_id=topic_id, action="review", priority=75 + structural_bonus,
                    reason="A review is due based on the last successful quiz and the review interval.",
                    decision_rule="spaced_review_due",
                    evidence=["quiz_passed", "quiz_timestamp", "consecutive_passes"],
                    completion_condition="Complete another successful quiz; the next interval will be recalculated.",
                )
            elif topic.state in {"shaky", "needs_review"}:
                recommendation = LearningRecommendation(
                    topic_id=topic_id, action="practice", priority=70 + structural_bonus,
                    reason="The topic is flagged as needing review.",
                    decision_rule="topic_state_needs_review",
                    evidence=["topic_state"],
                    completion_condition="Complete a successful assessment and update the topic state.",
                )
            elif manual_only_evidence:
                recommendation = LearningRecommendation(
                    topic_id=topic_id, action="verify", priority=55 + structural_bonus,
                    reason="This topic was marked complete manually; no scored quiz evidence is recorded.",
                    decision_rule="manual_completion_without_quiz",
                    evidence=["manual_completion", "absence_of_quiz"],
                    completion_condition="Pass a quiz to record assessment evidence.",
                )
            elif last_quiz is None and topic.state not in {"solid", "mastered"}:
                recommendation = LearningRecommendation(
                    topic_id=topic_id, action="study", priority=30 + structural_bonus,
                    reason="No scored quiz evidence exists for this topic yet.",
                    decision_rule="no_quiz_evidence",
                    evidence=["absence_of_quiz", "topic_state"],
                    completion_condition="Study the topic and pass its closure quiz.",
                )
            else:
                recommendation = None
            if recommendation:
                recommendations.append(recommendation)

        recommendations.sort(key=lambda rec: (-rec.priority, rec.topic_id, rec.action))
        return LearningPlan(
            graph_id=graph.graph_id, graph_version=graph.version, evaluated_at=current,
            total_topics=len(topics),
            completed_topics=sum(t.state in {"solid", "mastered"} for t in topics.values()),
            certified_topics=certified, manual_only_topics=manual_only,
            due_reviews=due_reviews, blocked_topics=blocked_topics,
            signals=signals, recommendations=recommendations,
            graph_warnings=sorted(set(warnings)),
        )
