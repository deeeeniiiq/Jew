import { expect, it } from "vitest";
import { computeClosureStatus } from "./graph";
import type { GraphEnvelope, QuizAttempt } from "./types";

function attempt(id: string, source: "quiz" | "manual", created_at: string): QuizAttempt {
  return { id, topic_id: "arithmetics", passed: true, score: 1, question_count: 6,
    source, created_at, closure_awarded: true, missed_questions: [], fail_count: 0 };
}

it("uses submission order to select the latest activity, including tied timestamps", () => {
  const sameTime = "2026-10-23T12:00:00Z";
  const graph = { graph_id: "g", subject: "math", title: "Math", language: "en", version: 1,
    edges: [], zones: [], topics: [{ id: "arithmetics", state: "solid" }],
    quiz_attempts: [attempt("graded", "quiz", sameTime), attempt("manual-newer", "manual", sameTime)], metadata: {},
  } as unknown as GraphEnvelope;

  expect(computeClosureStatus(graph, "arithmetics")?.latest_attempt?.id).toBe("manual-newer");
  graph.quiz_attempts.push(attempt("second-grade", "quiz", "2026-10-23T11:59:59Z"));
  expect(computeClosureStatus(graph, "arithmetics")?.latest_attempt?.id).toBe("second-grade");
});
