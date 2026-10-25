"""Export a deterministic, synthetic JEW teaching scenario without opening SQLite.

Run from the repository root with PYTHONPATH=backend. The JSON is an audit aid;
it is not evidence of actual student performance or an imported user profile.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from app.models.domain import QuizAttempt
from app.services.adaptive_learning import AdaptiveLearningService
from app.services.bootstrap import build_seed_workspace


EVALUATED_AT = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)


def build_fixture() -> dict:
    workspace = build_seed_workspace().model_copy(deep=True)
    graph = next(g for g in workspace.graphs if g.graph_id == "mathematics-demo")
    # The seed graph otherwise receives the wall-clock time at construction.
    # Both the data and the evaluation timestamp must be reproducible.
    graph.generated_at = EVALUATED_AT
    by_id = {topic.id: topic for topic in graph.topics}
    by_id["arithmetics"].state = "solid"
    by_id["angles"].state = "solid"
    by_id["algebra-basics"].state = "needs_review"
    graph.quiz_attempts = [
        QuizAttempt(
            id="synthetic-quiz-arithmetic", topic_id="arithmetics", source="quiz",
            passed=True, score=0.9, question_count=10, closure_awarded=True,
            created_at=datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc),
        ),
        QuizAttempt(
            id="synthetic-manual-angles", topic_id="angles", source="manual",
            passed=True, score=1.0, question_count=0, closure_awarded=False,
            created_at=datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc),
        ),
        QuizAttempt(
            id="synthetic-quiz-algebra", topic_id="algebra-basics", source="quiz",
            passed=False, score=0.4, question_count=10, closure_awarded=False,
            created_at=datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc),
        ),
    ]
    plan = AdaptiveLearningService().build_plan(graph, now=EVALUATED_AT)
    return {
        "synthetic": True,
        "disclaimer": "Synthetic demonstration only; no measured learner outcomes.",
        "evaluated_at": EVALUATED_AT.isoformat(),
        "graph": graph.model_dump(mode="json"),
        "learning_plan": plan.model_dump(mode="json"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write JSON to this path instead of stdout")
    args = parser.parse_args()
    content = json.dumps(build_fixture(), ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
        print(f"Synthetic demo fixture written to {args.output}")
    else:
        print(content, end="")


if __name__ == "__main__":
    main()
