// @vitest-environment jsdom
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { QuizPedagogicalReport, QuizQuestionReview } from "../../lib/types";
import { StudyReport } from "./StudyReport";

const reviews: QuizQuestionReview[] = [
  { question_id: "q1", prompt: "Resolva $x^2$", selected_choice: "4",
    correct_choice: "4", was_correct: true, explanation: "Pois $2^2 = 4$." },
  { question_id: "q2", prompt: "Calcule a segunda expressão", selected_choice: "9",
    correct_choice: "8", was_correct: false, explanation: "Reveja a multiplicação." },
  { question_id: "q3", prompt: "Complete o terceiro problema", selected_choice: null,
    correct_choice: "10", was_correct: false, explanation: "Revise o conceito." },
];

const report: QuizPedagogicalReport = {
  attempt_id: "attempt-42", title: "Álgebra", attempted_at: "2026-10-24T10:00:00Z",
  question_count: 3, answered_count: 2, correct_count: 1, incorrect_count: 1,
  unanswered_count: 1, ungraded_count: 0, score: 1 / 3,
  generator: "ollama", grading_method: "Gabarito registrado", duration_seconds: null,
  verified_keys_count: 1, unverified_keys_count: 2,
  strengths: ["Um acerto observado"], improvement_areas: ["Revisar as questões 2 e 3"],
  evidence_limits: ["Sem evidências suficientes para diagnosticar a causa do erro."],
  question_findings: [
    { question_id: "q1", outcome: "correct", observation: "Coincide com o gabarito.",
      error_category: null, hypothesis: null, diagnosis_confidence: "not_applicable",
      evidence_needed: null, next_action: "Explique o cálculo.", verification_status: "verified" },
    { question_id: "q2", outcome: "incorrect", observation: "Difere do gabarito.",
      error_category: "undetermined", hypothesis: null, diagnosis_confidence: "insufficient",
      evidence_needed: "Apresente os passos da solução.", next_action: "Resolva outro exemplo.",
      verification_status: "unverified" },
    { question_id: "q3", outcome: "unanswered", observation: "Nenhuma alternativa enviada.",
      error_category: "not_answered", hypothesis: null, diagnosis_confidence: "not_applicable",
      evidence_needed: null, next_action: "Tente antes do gabarito.",
      verification_status: "unverified" },
  ],
  recovery_plan: ["Refaça uma questão semelhante."], historical_comparison: null,
  next_steps: ["Reveja as resoluções."],
};

function render(currentReport: QuizPedagogicalReport | null, currentReviews = reviews) {
  const element = document.createElement("div");
  element.innerHTML = renderToStaticMarkup(<StudyReport report={currentReport} reviews={currentReviews} />);
  return element;
}

describe("StudyReport", () => {
  it("shows verified attempt counts, evidence limits, recovery actions and honest historical context", () => {
    const result = render(report);
    expect(result.querySelector(".studyReportHero strong")?.textContent).toBe("33%");
    expect(result.getAttribute("aria-label")).toBeNull();
    expect(result.querySelector('[aria-label="Resumo da tentativa"]')?.textContent)
      .toContain("2Respondidas1Corretas1Incorretas1Sem resposta");
    expect(result.textContent).toContain("attempt-42");
    expect(result.textContent).toContain("Tempo: não medido");
    expect(result.textContent).toContain("Sem evidências suficientes para diagnosticar");
    expect(result.textContent).toContain("Refaça uma questão semelhante.");
    expect(result.textContent).toContain("Sem comparação confiável");
    expect(result.textContent).toContain("Reveja as resoluções.");
  });

  it("orders shuffled reviews by report question IDs and associates every finding with its own question", () => {
    const items = [...render(report, [reviews[2], reviews[0], reviews[1]])
      .querySelectorAll<HTMLElement>(".studyReviewItem")];
    expect(items).toHaveLength(3);
    expect(items[0].textContent).toContain("Questão 1 · Correta");
    expect(items[0].textContent).toContain("Coincide com o gabarito.");
    expect(items[1].textContent).toContain("Questão 2 · Revisar");
    expect(items[1].textContent).toContain("Difere do gabarito.");
    expect(items[1].textContent).toContain("indeterminada com os dados disponíveis");
    expect(items[1].textContent).toContain("Confiança do diagnóstico: insuficiente");
    expect(items[1].textContent).toContain("Apresente os passos da solução.");
    expect(items[2].textContent).toContain("Questão 3 · Não respondida");
    expect(items[2].textContent).toContain("Sua resposta: Não respondida");
    expect(items[2].textContent).toContain("Nenhuma alternativa enviada.");
  });

  it("labels unverified keys individually without warning for the verified question", () => {
    const items = [...render(report).querySelectorAll<HTMLElement>(".studyReviewItem")];
    expect(items[0].textContent).not.toContain("Gabarito sem verificação matemática conclusiva");
    expect(items[1].textContent).toContain("Gabarito sem verificação matemática conclusiva");
    expect(items[2].textContent).toContain("Gabarito sem verificação matemática conclusiva");
    expect(render(report).textContent).toContain("2 gabaritos sem verificação matemática conclusiva");
  });

  it("renders mathematical expressions through KaTeX and labels report sections accessibly", () => {
    const result = render(report);
    expect(result.querySelectorAll(".katex").length).toBeGreaterThan(0);
    for (const section of result.querySelectorAll(".studyReportSection")) {
      const label = section.getAttribute("aria-labelledby");
      expect(label).toBeTruthy();
      expect(section.querySelector(`#${label}`)).not.toBeNull();
    }
  });

  it("keeps usable question feedback when the structured report is unavailable", () => {
    const result = render(null, [reviews[0], reviews[1]]);
    expect(result.querySelector(".studyReportHero strong")?.textContent).toBe("50%");
    expect(result.textContent).toContain("Confira as justificativas por questão");
    expect(result.textContent).toContain("Gabarito registrado: 8");
    expect(result.querySelector(".studyReportFacts")).toBeNull();
    expect(result.textContent).not.toContain("Plano de recuperação");
  });
});
