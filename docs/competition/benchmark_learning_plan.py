"""Reproducible, isolated benchmark for the read-only adaptive learning engine.

Run from the repository root with PYTHONPATH=backend:
    python -m docs.competition.benchmark_learning_plan --topics 100 --runs 20

Timing results characterize only the current machine and synthetic workload.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import statistics
import sys
from datetime import datetime, timezone
from time import perf_counter

from app.models.domain import Edge, QuizAttempt, StudyGraph, Topic
from app.services.adaptive_learning import AdaptiveLearningService


EVALUATED_AT = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)


def build_graph(count: int, scenario: str) -> StudyGraph:
    if not 1 <= count <= 2000:
        raise ValueError("topics must be between 1 and 2000")
    if scenario not in {"chain", "independent"}:
        raise ValueError("scenario must be chain or independent")
    topics = [
        Topic(id=f"topic-{index:04d}", slug=f"topic-{index:04d}",
              title=f"Synthetic topic {index}",
              state="solid" if index % 3 == 0 else "learning")
        for index in range(count)
    ]
    edges = [
        Edge(id=f"edge-{index:04d}", source_topic_id=topics[index - 1].id,
             target_topic_id=topics[index].id, relation="requires")
        for index in range(1, count)
    ] if scenario == "chain" else []
    attempts = [
        QuizAttempt(id=f"quiz-{index:04d}", topic_id=topic.id, passed=True,
                    score=0.85, question_count=6, source="quiz", closure_awarded=True,
                    created_at=datetime(2026, 10, 20, tzinfo=timezone.utc))
        for index, topic in enumerate(topics) if index % 3 == 0
    ]
    return StudyGraph(graph_id="synthetic-benchmark", subject="benchmark",
                      title="Synthetic adaptive benchmark", version=1,
                      generated_at=EVALUATED_AT,
                      topics=topics, edges=edges, quiz_attempts=attempts)


def nearest_rank(values: list[float], percentile: float) -> float:
    if not values:
        raise ValueError("at least one observation is required")
    if not 0 < percentile <= 1:
        raise ValueError("percentile must be between 0 and 1")
    ordered = sorted(values)
    return ordered[math.ceil(len(ordered) * percentile) - 1]


def run_benchmark(*, topics: int, scenario: str, runs: int, warmups: int) -> dict:
    if not 1 <= runs <= 1000 or not 0 <= warmups <= 100:
        raise ValueError("runs must be 1..1000 and warmups 0..100")
    graph = build_graph(topics, scenario)
    service = AdaptiveLearningService()
    canonical = graph.model_dump_json()
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    for _ in range(warmups):
        service.build_plan(graph, now=EVALUATED_AT)

    measurements = []
    for _ in range(runs):
        started = perf_counter()
        plan = service.build_plan(graph, now=EVALUATED_AT)
        measurements.append((perf_counter() - started) * 1000)
        if plan.total_topics != topics or len(plan.signals) != topics:
            raise RuntimeError("benchmark plan does not match the generated input")
    if graph.model_dump_json() != canonical:
        raise RuntimeError("adaptive engine mutated the benchmark input")
    return {
        "benchmark": "adaptive-learning-plan",
        "synthetic": True,
        "evaluated_at": EVALUATED_AT.isoformat(),
        "input_sha256": fingerprint,
        "environment": {"os": platform.platform(), "python": sys.version.split()[0],
                        "processor": platform.processor() or "unknown"},
        "workload": {"scenario": scenario, "topics": topics, "edges": len(graph.edges),
                     "quiz_attempts": len(graph.quiz_attempts), "warmups": warmups, "runs": runs},
        "latency_ms": {"min": min(measurements), "mean": statistics.mean(measurements),
                       "p50_nearest_rank": nearest_rank(measurements, .50),
                       "p95_nearest_rank": nearest_rank(measurements, .95),
                       "max": max(measurements)},
        "limitation": "Synthetic graph and current device only; no claims about real learners or AI inference.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topics", type=int, default=100)
    parser.add_argument("--scenario", choices=["chain", "independent"], default="chain")
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--warmups", type=int, default=3)
    args = parser.parse_args()
    print(json.dumps(run_benchmark(topics=args.topics, scenario=args.scenario,
                                   runs=args.runs, warmups=args.warmups), indent=2))


if __name__ == "__main__":
    main()
