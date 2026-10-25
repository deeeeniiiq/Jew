import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { APP_COPY } from "../lib/appCopy";
import type { LearningPlan } from "../lib/types";
import { LearningGuidance } from "./LearningGuidance";

const plan: LearningPlan = {
  graph_id: "math", graph_version: 2, evaluated_at: "2026-10-24T00:00:00Z",
  total_topics: 2, completed_topics: 1, certified_topics: 0, manual_only_topics: 1,
  due_reviews: 0, blocked_topics: 1, graph_warnings: [], method: "deterministic-heuristic-v1",
  signals: [{ topic_id: "algebra", evidence_level: "none", mastery_indicator: "insufficient_evidence",
    quiz_attempts: 0, latest_quiz_score: null, latest_quiz_at: null, failure_count: 0,
    blocked_prerequisite_ids: ["fractions"], next_review_at: null, review_due: false }],
  recommendations: [{ topic_id: "algebra", action: "unblock", priority: 50,
    reason: "Prerequisite closure is pending.", decision_rule: "transitive_requires_not_closed",
    evidence: ["prerequisite_states"], related_topic_ids: ["fractions"],
    completion_condition: "Close the prerequisite." }],
};

describe("LearningGuidance", () => {
  it("renders evidence, a clear recommended action and prerequisite names", () => {
    const html = renderToStaticMarkup(<LearningGuidance plan={plan} topicId="algebra"
      titles={new Map([["fractions", "Fractions"]])} copy={APP_COPY} />);
    expect(html).toContain('aria-label="Learning guidance"');
    expect(html).toContain("Complete prerequisites");
    expect(html).toContain("Fractions");
    expect(html).toContain("Prerequisites still open");
    expect(html).toContain("Completion states of prerequisite topics");
    expect(html).toContain("Complete all prerequisite topics.");
    expect(html).toContain('title="transitive_requires_not_closed"');
    expect(html).toContain('title="prerequisite_states"');
    expect(html).toContain("product heuristics");
  });

  it("provides readable descriptions for every current backend rule and evidence code", () => {
    const backendRules = [
      "repair_invalid_prerequisite_graph", "transitive_requires_not_closed", "latest_quiz_failed",
      "spaced_review_due", "topic_state_needs_review", "manual_completion_without_quiz",
      "no_quiz_evidence",
    ];
    const backendEvidence = [
      "missing_prerequisite", "prerequisite_cycle", "prerequisite_states", "quiz_score",
      "quiz_passed", "quiz_timestamp", "consecutive_passes", "topic_state",
      "manual_completion", "absence_of_quiz",
    ];
    for (const rule of backendRules) {
      const description = APP_COPY.adaptive.decisions[rule as keyof typeof APP_COPY.adaptive.decisions];
      expect(description?.label).toBeTruthy();
      expect(description?.reason).toBeTruthy();
      expect(description?.completion).toBeTruthy();
    }
    for (const code of backendEvidence) {
      expect(APP_COPY.adaptive.evidenceItems[code as keyof typeof APP_COPY.adaptive.evidenceItems]).toBeTruthy();
    }
  });

  it("shows the actual latest failed quiz score without losing the audit codes", () => {
    const failed: LearningPlan = {
      ...plan,
      signals: [{ ...plan.signals[0], latest_quiz_score: 0.35 }],
      recommendations: [{ ...plan.recommendations[0], action: "practice",
        decision_rule: "latest_quiz_failed", evidence: ["quiz_score", "quiz_timestamp"] }],
    };
    const html = renderToStaticMarkup(<LearningGuidance plan={failed} topicId="algebra"
      titles={new Map()} copy={APP_COPY} />);
    expect(html).toContain("Latest quiz score: 35%");
    expect(html).toContain("Latest quiz was not passed");
    expect(html).toContain("Recorded quiz score");
    expect(html).toContain('title="latest_quiz_failed"');
  });

  it("falls back safely to backend explanations for future unknown rule codes", () => {
    const future: LearningPlan = {
      ...plan,
      recommendations: [{ ...plan.recommendations[0], decision_rule: "future_rule_2",
        evidence: ["future_evidence_1"], reason: "Server-provided explanation.",
        completion_condition: "Server-provided completion." }],
    };
    const html = renderToStaticMarkup(<LearningGuidance plan={future} topicId="algebra"
      titles={new Map()} copy={APP_COPY} />);
    expect(html).toContain("Server-provided explanation.");
    expect(html).toContain("Server-provided completion.");
    expect(html).toContain("future_rule_2");
    expect(html).toContain("future_evidence_1");
  });

  it("does not show guidance for a different topic or failed request", () => {
    expect(renderToStaticMarkup(<LearningGuidance plan={plan} topicId="unknown"
      titles={new Map()} copy={APP_COPY} />)).toBe("");
    expect(renderToStaticMarkup(<LearningGuidance plan={null} topicId="algebra"
      titles={new Map()} copy={APP_COPY} />)).toBe("");
  });
});
