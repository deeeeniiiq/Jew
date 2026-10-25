import React from "react";
import { AssistantMarkdown } from "../assistant/AssistantMarkdown";
import type { QuizPedagogicalReport, QuizQuestionReview } from "../../lib/types";

export function StudyReport({ report, reviews }: {
  report: QuizPedagogicalReport | null;
  reviews: QuizQuestionReview[];
}): React.JSX.Element {
  const correct = reviews.filter(review => review.was_correct).length;
  const findings = new Map(report?.question_findings.map(item => [item.question_id, item]));
  // The report uses the original question order. A caller may supply reviews
  // in a different order, so number them from the report when it is available.
  const questionOrder = new Map(report?.question_findings.map((item, index) => [item.question_id, index]));
  const orderedReviews = report ? [...reviews].sort((a, b) =>
    (questionOrder.get(a.question_id) ?? Number.MAX_SAFE_INTEGER)
    - (questionOrder.get(b.question_id) ?? Number.MAX_SAFE_INTEGER)) : reviews;
  const stats = report ? [
    ["Respondidas", report.answered_count], ["Corretas", report.correct_count],
    ["Incorretas", report.incorrect_count], ["Sem resposta", report.unanswered_count],
  ] as const : [];

  return <div className="studyReport">
    <div className="studyReportHero">
      <strong>{Math.round((report?.score ?? correct / Math.max(reviews.length, 1)) * 100)}%</strong>
      <div><span className="studyEyebrow">RELATÓRIO PEDAGÓGICO</span>
        <h3>{report?.title ?? "Resultado do questionário"}</h3>
        <p>{correct} de {reviews.length} respostas conforme o gabarito registrado</p>
      </div>
    </div>
    {report ? <>
      <div className="studyReportFacts" aria-label="Resumo da tentativa">
        {stats.map(([label, value]) => <div className="studyReportStat" key={label}>
          <strong>{value}</strong><span>{label}</span>
        </div>)}
      </div>
      <p className="studyReportMeta">Tentativa {report.attempt_id} · {new Date(report.attempted_at).toLocaleString("pt-BR")}</p>
      <p className="studyReportMeta">Gerador: {report.generator} · {report.grading_method} · Tempo: {report.duration_seconds == null ? "não medido" : `${report.duration_seconds}s`}</p>
      <p className="studyReportMeta">{report.ungraded_count} não avaliadas · {report.unverified_keys_count} gabaritos sem verificação matemática conclusiva</p>
      <section className="studyReportSection" aria-labelledby="study-overview-title">
        <h3 id="study-overview-title">Visão geral</h3>
        {report.strengths.map((item, i) => <p key={`strength-${i}`}>{item}</p>)}
        {report.improvement_areas.map((item, i) => <p key={`improve-${i}`} className="studyReportSignal">{item}</p>)}
        {report.evidence_limits.map((item, i) => <p key={`evidence-${i}`} className="studyReportMeta">{item}</p>)}
      </section>
    </> : <p>Confira as justificativas por questão. A pontuação considera as alternativas enviadas; anotações e desenhos não são corrigidos automaticamente.</p>}
    <section className="studyReportSection" aria-labelledby="study-review-title">
      <h3 id="study-review-title">Análise por questão</h3>
      <ol className="studyReviewList">{orderedReviews.map((review, index) => {
        const finding = findings.get(review.question_id);
        return <li key={review.question_id} className="studyReviewItem">
          <span className={review.was_correct ? "quizVerdictGood" : "quizVerdictBad"}>
            Questão {index + 1} · {finding?.outcome === "unanswered" ? "Não respondida" : review.was_correct ? "Correta" : "Revisar"}
          </span>
          <AssistantMarkdown content={review.prompt} />
          <p>Sua resposta: {review.selected_choice ?? "Não respondida"}</p>
          <p>Gabarito registrado: {review.correct_choice}</p>
          {review.explanation ? <AssistantMarkdown content={review.explanation} /> : null}
          {finding ? <div className="studyReportDetails">
            <p><strong>Observação:</strong> {finding.observation}</p>
            {finding.error_category === "undetermined" ? <p><strong>Natureza do erro:</strong> indeterminada com os dados disponíveis.</p> : null}
            {finding.hypothesis ? <p><strong>Hipótese:</strong> {finding.hypothesis}</p> : null}
            {finding.outcome === "incorrect" ? <p><strong>Confiança do diagnóstico:</strong> {finding.diagnosis_confidence === "insufficient" ? "insuficiente para identificar a causa" : "não aplicável"}.</p> : null}
            {finding.evidence_needed ? <p><strong>Para investigar:</strong> {finding.evidence_needed}</p> : null}
            <p><strong>Próxima ação:</strong> {finding.next_action}</p>
            {finding.verification_status !== "verified" ? <p className="studyReportSignal">Gabarito sem verificação matemática conclusiva; solicite revisão se houver dúvida.</p> : null}
          </div> : null}
        </li>;
      })}</ol>
    </section>
    {report ? <>
      <section className="studyReportSection" aria-labelledby="study-recovery-title">
        <h3 id="study-recovery-title">Plano de recuperação</h3>
        <ol className="studyReportActions">{report.recovery_plan.map((item, i) => <li key={i}>{item}</li>)}</ol>
      </section>
      <section className="studyReportSection" aria-labelledby="study-history-title">
        <h3 id="study-history-title">Evolução histórica</h3>
        <p>{report.historical_comparison ?? "Sem comparação confiável: as tentativas anteriores não registram equivalência entre conjuntos de questões."}</p>
      </section>
      <section className="studyReportSection" aria-labelledby="study-next-title">
        <h3 id="study-next-title">Próximos passos</h3>
        {report.next_steps.map((item, i) => <p key={i}>{item}</p>)}
      </section>
    </> : null}
  </div>;
}
