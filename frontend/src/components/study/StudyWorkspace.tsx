import React, { useCallback, useEffect, useRef, useState } from "react";

import { Modal } from "../ui/Modal";
import { AssistantMarkdown } from "../assistant/AssistantMarkdown";
import { StudyReport } from "./StudyReport";
import { StudyScratchpad } from "./StudyScratchpad";
import { API_BASE } from "../../lib/api";
import { apiFetch, readErrorMessage } from "../../lib/apiRequest";
import type { AppCopy } from "../../lib/appCopy";
import type { QuizPedagogicalReport, QuizQuestionReview, QuizStudyDraft, StudyStroke, Topic, TopicQuizSession } from "../../lib/types";

type SaveState = "loading" | "saved" | "pending" | "saving" | "error" | "conflict";

function emptyDraft(): QuizStudyDraft {
  return { format_version: 1, revision: 0, answers: {}, active_question_id: null,
    flagged_question_ids: [], notes: {}, strokes: {}, updated_at: null };
}

export function StudyWorkspace({ session, modalRef, closeButtonRef, selectedTopic, closeModal, error,
  reviews, report, setAnswers, loading, submitQuiz, copy }: {
  session: TopicQuizSession;
  modalRef: React.RefObject<HTMLDivElement | null>;
  closeButtonRef: React.RefObject<HTMLButtonElement | null>;
  selectedTopic: Topic | null;
  closeModal: () => void;
  error: string | null;
  reviews: QuizQuestionReview[] | null;
  report?: QuizPedagogicalReport | null;
  setAnswers: React.Dispatch<React.SetStateAction<Record<string, number>>>;
  loading: boolean;
  submitQuiz: (answersOverride?: Record<string, number>) => Promise<void>;
  copy: AppCopy;
}): React.JSX.Element {
  const [draft, setDraft] = useState<QuizStudyDraft>(emptyDraft);
  const [saveState, setSaveState] = useState<SaveState>("loading");
  const [saveError, setSaveError] = useState<string | null>(null);
  const latest = useRef<QuizStudyDraft>(emptyDraft());
  const revision = useRef(0);
  const changeNumber = useRef(0);
  const savedNumber = useRef(0);
  const ready = useRef(false);
  const alive = useRef(true);
  const conflicted = useRef(false);
  const inFlight = useRef<Promise<boolean> | null>(null);
  const submitting = useRef(false);
  const finished = useRef(false);
  const restoreId = useRef(0);
  const [submissionActive, setSubmissionActive] = useState(false);
  const questions = session.questions;
  const draftUrl = `${API_BASE}/api/v1/graphs/${encodeURIComponent(session.graph_id)}/topics/${encodeURIComponent(session.topic_id)}/quiz/${encodeURIComponent(session.session_id)}/draft`;

  const flush = useCallback(async (): Promise<boolean> => {
    if (!ready.current || conflicted.current || finished.current) return false;
    // One serial writer owns all revisions, including edits made during a PUT.
    if (inFlight.current) return inFlight.current;
    const writer = async (): Promise<boolean> => {
      while (savedNumber.current < changeNumber.current) {
        const savingChange = changeNumber.current;
        const snapshot = { ...latest.current, revision: revision.current };
        try {
          if (alive.current) setSaveState("saving");
          const response = await apiFetch(draftUrl, { method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(snapshot) });
          if (!response.ok) {
            if (response.status === 409) conflicted.current = true;
            throw new Error(await readErrorMessage(response, "Não foi possível salvar o caderno."));
          }
          const saved = await response.json() as QuizStudyDraft;
          revision.current = saved.revision;
          savedNumber.current = savingChange;
          latest.current = { ...latest.current, revision: saved.revision, updated_at: saved.updated_at };
          if (alive.current) {
            setDraft(value => ({ ...value, revision: saved.revision, updated_at: saved.updated_at }));
            setSaveState(changeNumber.current > savingChange ? "pending" : "saved");
            setSaveError(null);
          }
        } catch (cause) {
          if (alive.current) {
            setSaveState(conflicted.current ? "conflict" : "error");
            setSaveError(cause instanceof Error ? cause.message : "Falha ao salvar o caderno.");
          }
          return false;
        }
      }
      return true;
    };
    const request = writer();
    inFlight.current = request;
    try { return await request; }
    finally { if (inFlight.current === request) inFlight.current = null; }
  }, [draftUrl]);

  const restore = useCallback(async (): Promise<void> => {
    const requestId = ++restoreId.current;
    ready.current = false;
    if (alive.current) { setSaveState("loading"); setSaveError(null); }
    try {
      const response = await apiFetch(draftUrl);
      if (!response.ok) throw new Error(await readErrorMessage(response, "Não foi possível recuperar o caderno."));
      const stored = await response.json() as QuizStudyDraft;
      if (!alive.current || requestId !== restoreId.current) return;
      const available = new Set(questions.map(question => question.id));
      const restored = { ...stored,
        active_question_id: stored.active_question_id && available.has(stored.active_question_id)
          ? stored.active_question_id : questions[0]?.id ?? null };
      latest.current = restored;
      revision.current = restored.revision;
      changeNumber.current = 0;
      savedNumber.current = 0;
      conflicted.current = false;
      setDraft(restored);
      setAnswers(restored.answers);
      ready.current = true;
      setSaveState("saved");
    } catch (cause) {
      if (alive.current && requestId === restoreId.current) {
        setSaveState("error");
        setSaveError(cause instanceof Error ? cause.message : "Falha ao recuperar o caderno.");
      }
    }
  }, [draftUrl, questions, setAnswers]);

  useEffect(() => {
    alive.current = true;
    void restore();
    return () => {
      // Navigating away must still attempt the latest pending snapshot.
      alive.current = false;
      restoreId.current += 1;
      if (ready.current && savedNumber.current < changeNumber.current && !conflicted.current) void flush();
    };
  }, [restore, flush]);

  function edit(update: (previous: QuizStudyDraft) => QuizStudyDraft): void {
    if (!ready.current || conflicted.current || submitting.current || finished.current || reviews) return;
    const next = update(latest.current);
    latest.current = next;
    changeNumber.current += 1;
    setDraft(next);
    setSaveState("pending");
  }

  useEffect(() => {
    if (saveState !== "pending" || reviews) return;
    const timer = window.setTimeout(() => void flush(), 650);
    return () => window.clearTimeout(timer);
  }, [draft, saveState, reviews, flush]);

  async function finish(): Promise<void> {
    if (submitting.current || loading || !ready.current || conflicted.current) return;
    submitting.current = true;
    setSubmissionActive(true);
    try {
      if (await flush()) await submitQuiz({ ...latest.current.answers });
    } finally {
      submitting.current = false;
      if (alive.current) setSubmissionActive(false);
    }
  }

  async function close(): Promise<void> {
    if (submitting.current || loading) return;
    if (conflicted.current || (ready.current && saveState === "error")) {
      if (!window.confirm("Existem alterações locais que podem não estar salvas. Deseja fechar mesmo assim?")) return;
      closeModal();
      return;
    }
    if (!reviews && ready.current && !(await flush())) return;
    closeModal();
  }

  function exportDraft(): void {
    const blob = new Blob([JSON.stringify(latest.current, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `jew-caderno-${session.session_id}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  useEffect(() => { if (reviews) finished.current = true; }, [reviews]);

  const activeId = draft.active_question_id ?? questions[0]?.id ?? null;
  const active = questions.find(question => question.id === activeId) ?? questions[0];
  const activeIndex = active ? questions.findIndex(question => question.id === active.id) : 0;
  const answered = questions.filter(question => Number.isInteger(draft.answers[question.id])).length;
  const editable = ready.current && saveState !== "loading" && saveState !== "conflict" && !submissionActive && !loading && !reviews;
  const correctCount = reviews?.filter(review => review.was_correct).length ?? 0;

  return <Modal id="quiz-dialog" modalRef={modalRef} closeButtonRef={closeButtonRef}
    title={reviews ? "Relatório do questionário" : "Área Estudar"}
    description={selectedTopic?.title ?? copy.quiz.selectedTopic}
    closeLabel={copy.quiz.closeQuiz} onClose={() => void close()} size="study"
    footer={<>
      <span className="uiModalFooterStart studySaveStatus" role="status" aria-live="polite">
        {reviews ? `${correctCount} de ${reviews.length} corretas` :
          saveState === "loading" ? "Recuperando sessão…" :
          saveState === "saving" ? "Salvando…" :
          saveState === "pending" ? "Alterações pendentes…" :
          saveState === "conflict" ? "Conflito de edição" :
          saveState === "error" ? "Erro ao salvar" :
          `Salvo · ${answered}/${questions.length} respondidas`}
      </span>
      {saveState === "error" && !reviews
        ? <button type="button" className="uiButton" onClick={() => void (ready.current ? flush() : restore())}>
          Tentar novamente
        </button> : null}
      {(saveState === "error" || saveState === "conflict") && ready.current && !reviews
        ? <button type="button" className="uiButton" onClick={exportDraft}>Exportar cópia local</button> : null}
      {reviews
        ? <button type="button" className="uiButton uiButtonPrimary" onClick={() => void close()}>Fechar relatório</button>
        : <button type="button" className="uiButton uiButtonPrimary"
          disabled={!editable || saveState === "error" || submitting.current}
          onClick={() => void finish()}>{loading ? copy.quiz.submitting : copy.quiz.submit}</button>}
    </>}>
    {error ? <div className="inlineNotice inlineNoticeError" role="alert">{error}</div> : null}
    {saveError ? <div className="inlineNotice inlineNoticeError" role="alert">{saveError}
      {saveState === "conflict" ? " Seu rascunho local está preservado nesta janela; reabra a sessão após conferir a outra janela." : null}
    </div> : null}
    {!reviews && questions.some(question => question.verification_status !== "verified")
      ? <div className="inlineNotice" role="status">{copy.quiz.unverifiedNotice}</div> : null}
    {reviews ? <StudyReport report={report ?? null} reviews={reviews} /> : !ready.current
      ? <div className="studyLoading" role="status">{saveState === "error"
        ? "Falha na recuperação. Use ‘Tentar novamente’ para carregar a sessão."
        : "Recuperando anotações e respostas desta sessão…"}</div>
      : <div className="studyLayout">
        <nav className="studyNavigation" aria-label="Navegação entre questões">
          <span className="studyEyebrow">QUESTIONÁRIO</span>
          <strong>{answered} / {questions.length}</strong>
          <div className="studyProgress"><span style={{ width: `${answered / Math.max(questions.length, 1) * 100}%` }} /></div>
          <div className="studyQuestionGrid">{questions.map((question, index) =>
            <button type="button" key={question.id} disabled={!editable}
              aria-current={question.id === active?.id ? "step" : undefined}
              aria-label={`Questão ${index + 1}${draft.answers[question.id] !== undefined ? ", respondida" : ""}`}
              className={`studyQuestionNumber${question.id === active?.id ? " isCurrent" : ""}${draft.answers[question.id] !== undefined ? " isAnswered" : ""}`}
              onClick={() => edit(value => ({ ...value, active_question_id: question.id }))}>
              {index + 1}{draft.flagged_question_ids.includes(question.id) ? " •" : ""}
            </button>)}</div>
          <p className="studySidebarHint">O progresso e os rabiscos ficam salvos por questão.</p>
        </nav>
        {active ? <article className="studyQuestion" aria-labelledby="study-question-title">
          <div className="studyQuestionTop"><span className="studyEyebrow">QUESTÃO {activeIndex + 1} DE {questions.length}</span>
            <button type="button" className="studyLink" disabled={!editable} aria-pressed={draft.flagged_question_ids.includes(active.id)}
              onClick={() => edit(value => ({ ...value, flagged_question_ids: value.flagged_question_ids.includes(active.id)
                ? value.flagged_question_ids.filter(id => id !== active.id) : [...value.flagged_question_ids, active.id] }))}>
              {draft.flagged_question_ids.includes(active.id) ? "Marcada para revisão" : "Marcar para revisão"}
            </button></div>
          <h3 id="study-question-title" className="studyPrompt"><AssistantMarkdown content={active.prompt} /></h3>
          <span className="studyEyebrow">SELECIONE UMA ALTERNATIVA</span>
          <div className="studyChoices">{active.choices.map((choice, index) =>
            <button key={index} type="button" disabled={!editable}
              className={`studyChoice${draft.answers[active.id] === index ? " isSelected" : ""}`}
              aria-pressed={draft.answers[active.id] === index}
              onClick={() => {
                edit(value => ({ ...value, answers: { ...value.answers, [active.id]: index } }));
                setAnswers(previous => ({ ...previous, [active.id]: index }));
              }}>
              <span className="studyChoiceLetter">{String.fromCharCode(65 + index)}</span><AssistantMarkdown content={choice} />
            </button>)}</div>
          <div className="studyQuestionActions">
            <button type="button" className="uiButton" disabled={!editable || activeIndex <= 0}
              onClick={() => edit(value => ({ ...value, active_question_id: questions[activeIndex - 1].id }))}>Anterior</button>
            <button type="button" className="uiButton" disabled={!editable || activeIndex >= questions.length - 1}
              onClick={() => edit(value => ({ ...value, active_question_id: questions[activeIndex + 1].id }))}>Próxima</button>
          </div>
        </article> : null}
        {active ? <aside className="studyNotebook" aria-label="Caderno da questão">
          <div className="studyNotebookHeader"><span className="studyEyebrow">CADERNO DIGITAL</span>
            <span>Questão {activeIndex + 1}</span></div>
          <label className="studyNotesLabel" htmlFor="study-notes">Anotações</label>
          <textarea id="study-notes" className="studyNotes" placeholder="Escreva suas contas, dúvidas ou lembretes…"
            value={draft.notes[active.id] ?? ""} maxLength={20000} disabled={!editable}
            onChange={event => edit(value => ({ ...value, notes: { ...value.notes, [active.id]: event.target.value } }))} />
          <StudyScratchpad key={active.id} questionId={active.id} strokes={draft.strokes[active.id] ?? []}
            disabled={!editable} onChange={(strokes: StudyStroke[]) =>
              edit(value => ({ ...value, strokes: { ...value.strokes, [active.id]: strokes } }))} />
        </aside> : null}
      </div>}
  </Modal>;
}
