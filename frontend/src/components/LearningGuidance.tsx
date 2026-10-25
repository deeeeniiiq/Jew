import type { AppCopy } from "../lib/appCopy";
import type { LearningPlan } from "../lib/types";

type Props = {
  plan: LearningPlan | null;
  topicId: string;
  titles: Map<string, string>;
  copy: AppCopy;
};

/** Read-only evidence explanation within the graph topic popover. */
export function LearningGuidance({ plan, topicId, titles, copy }: Props) {
  const signal = plan?.signals.find((item) => item.topic_id === topicId);
  if (!signal) return null;
  const recommendation = plan?.recommendations.find((item) => item.topic_id === topicId);
  const decisions: Record<string, { label: string; reason: string; completion: string }> = copy.adaptive.decisions;
  const evidenceLabels: Record<string, string> = copy.adaptive.evidenceItems;
  const decision = recommendation && decisions[recommendation.decision_rule];
  return (
    <section className="topicPopoverAdaptive" aria-label={copy.adaptive.title}>
      <div className="topicPopoverAdaptiveTitle">{copy.adaptive.title}</div>
      <p className="topicPopoverCopy">{copy.adaptive.indicators[signal.mastery_indicator]}</p>
      {recommendation ? (
        <>
          <div className="topicPopoverAdaptiveAction">{copy.adaptive.actions[recommendation.action]}</div>
          <p className="topicPopoverCopy">{decision?.reason ?? recommendation.reason}</p>
          {recommendation.decision_rule === "latest_quiz_failed" && signal.latest_quiz_score != null
            && Number.isFinite(signal.latest_quiz_score) ? (
            <p className="topicPopoverCopy">{copy.adaptive.quizScore(signal.latest_quiz_score)}</p>
          ) : null}
          {recommendation.related_topic_ids.length > 0 ? (
            <p className="topicPopoverCopy">
              {copy.adaptive.related}: {recommendation.related_topic_ids.map((id) => titles.get(id) ?? id).join(" · ")}
            </p>
          ) : null}
          <p className="topicPopoverAdaptiveRule">{copy.adaptive.rule}: <span title={recommendation.decision_rule}>{decision?.label ?? recommendation.decision_rule}</span></p>
          <p className="topicPopoverAdaptiveRule">{copy.adaptive.evidence}: {recommendation.evidence.map((item, index) => (
            <span key={`${item}-${index}`} title={item}>{index > 0 ? ", " : ""}{evidenceLabels[item] ?? item}</span>
          ))}</p>
          <p className="topicPopoverAdaptiveRule">{copy.adaptive.until}: {decision?.completion ?? recommendation.completion_condition}</p>
        </>
      ) : null}
      {signal.next_review_at ? (
        <p className="topicPopoverAdaptiveRule">
          {copy.adaptive.nextReview}: {new Date(signal.next_review_at).toLocaleDateString("en-US")}
        </p>
      ) : null}
      <div className="topicPopoverAdaptiveFootnote">{copy.adaptive.heuristic}</div>
    </section>
  );
}
