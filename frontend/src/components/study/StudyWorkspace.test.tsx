// @vitest-environment jsdom
import { act, createRef } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { APP_COPY } from "../../lib/appCopy";
import type { QuizStudyDraft, TopicQuizSession } from "../../lib/types";
import { StudyWorkspace } from "./StudyWorkspace";

const network = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock("../../lib/apiRequest", async (original) => ({
  ...await original<object>(), apiFetch: network.fetch,
}));

const session: TopicQuizSession = {
  session_id: "study-1", graph_id: "math", topic_id: "algebra", question_count: 1,
  generator: "local", created_at: "2026-10-24T00:00:00Z",
  closure_status: { topic_id: "algebra", prerequisite_topic_ids: [],
    blocked_prerequisite_ids: [], can_award_completion: true, latest_attempt: null },
  questions: [{ id: "q1", prompt: "Resolva a expressão", choices: ["Um", "Dois", "Três"], explanation: "" }],
};
const empty: QuizStudyDraft = {
  format_version: 1, revision: 0, answers: {}, active_question_id: null,
  flagged_question_ids: [], notes: {}, strokes: {}, updated_at: null,
};
const copy = APP_COPY;

const json = (value: unknown) => new Response(JSON.stringify(value), {
  headers: { "Content-Type": "application/json" },
});
function deferred() {
  let resolve!: (response: Response) => void;
  const promise = new Promise<Response>((yes) => { resolve = yes; });
  return { promise, resolve };
}

let root: Root;
let host: HTMLDivElement;
const submit = vi.fn< (answers?: Record<string, number>) => Promise<void> >();
const close = vi.fn();
const setAnswers = vi.fn();
beforeEach(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  submit.mockReset().mockResolvedValue(undefined);
  close.mockReset();
  setAnswers.mockReset();
  network.fetch.mockReset().mockImplementation((url: string, options?: RequestInit) => {
    if (!url.endsWith("/draft")) throw new Error(`Unexpected request ${url}`);
    if (options?.method === "PUT") {
      const value = JSON.parse(String(options.body)) as QuizStudyDraft;
      return Promise.resolve(json({ ...value, revision: value.revision + 1, updated_at: "2026-10-24T00:01:00Z" }));
    }
    return Promise.resolve(json(empty));
  });
});
afterEach(async () => {
  vi.useRealTimers();
  await act(async () => root.unmount());
  host.remove();
  vi.unstubAllGlobals();
});

async function mount() {
  await act(async () => root.render(<StudyWorkspace session={session}
    modalRef={createRef<HTMLDivElement>()} closeButtonRef={createRef<HTMLButtonElement>()}
    selectedTopic={null} closeModal={close} error={null} reviews={null}
    setAnswers={setAnswers} loading={false} submitQuiz={submit} copy={copy} />));
}
async function choose(index: number) {
  const button = host.querySelectorAll<HTMLButtonElement>(".studyChoice")[index];
  expect(button).toBeTruthy();
  await act(async () => { button.click(); });
}
async function pressSubmit() {
  const button = [...host.querySelectorAll<HTMLButtonElement>("button")]
    .find((item) => item.textContent === copy.quiz.submit);
  expect(button).toBeTruthy();
  await act(async () => { button!.click(); });
}
function saves(): QuizStudyDraft[] {
  return network.fetch.mock.calls.filter(([, options]) => options?.method === "PUT")
    .map(([, options]) => JSON.parse(String(options.body)) as QuizStudyDraft);
}

it("restores saved answers and submits precisely the current draft snapshot", async () => {
  network.fetch.mockImplementation((url: string, options?: RequestInit) => {
    if (options?.method === "PUT") {
      const value = JSON.parse(String(options.body)) as QuizStudyDraft;
      return Promise.resolve(json({ ...value, revision: value.revision + 1 }));
    }
    expect(url).toContain("study-1/draft");
    return Promise.resolve(json({ ...empty, revision: 3, answers: { q1: 1 }, notes: { q1: "Continuar daqui" } }));
  });
  await mount();
  expect(host.querySelectorAll(".studyChoice")[1].getAttribute("aria-pressed")).toBe("true");
  expect(host.querySelector<HTMLTextAreaElement>(".studyNotes")?.value).toBe("Continuar daqui");
  await choose(2);
  await pressSubmit();
  expect(saves()).toMatchObject([{ revision: 3, answers: { q1: 2 } }]);
  expect(submit).toHaveBeenCalledWith({ q1: 2 });
});

it("serializes edits arriving during a pending save using successive revisions", async () => {
  const pending = deferred();
  network.fetch.mockImplementation((url: string, options?: RequestInit) => {
    if (options?.method === "PUT") {
      const value = JSON.parse(String(options.body)) as QuizStudyDraft;
      return value.revision === 0 ? pending.promise : Promise.resolve(json({ ...value, revision: value.revision + 1 }));
    }
    expect(url).toContain("/draft");
    return Promise.resolve(json(empty));
  });
  await mount();
  vi.useFakeTimers();
  await choose(0);
  await act(async () => { await vi.advanceTimersByTimeAsync(700); });
  expect(saves()).toHaveLength(1);
  await choose(2);
  await act(async () => { pending.resolve(json({ ...saves()[0], revision: 1 })); });
  expect(saves()).toMatchObject([
    { revision: 0, answers: { q1: 0 } },
    { revision: 1, answers: { q1: 2 } },
  ]);
  expect(host.textContent).toContain("Salvo");
});

it("blocks submission after a revision conflict and offers a local backup", async () => {
  network.fetch.mockImplementation((_url: string, options?: RequestInit) => options?.method === "PUT"
    ? Promise.resolve(new Response(JSON.stringify({ detail: "Revision conflict" }), { status: 409 }))
    : Promise.resolve(json(empty)));
  await mount();
  await choose(1);
  await pressSubmit();
  expect(submit).not.toHaveBeenCalled();
  expect(host.textContent).toContain("Conflito de edição");
  expect(host.textContent).toContain("Exportar cópia local");
});

it("never writes or submits when draft recovery fails, and permits an explicit retry", async () => {
  let reads = 0;
  network.fetch.mockImplementation((_url: string, options?: RequestInit) => {
    if (options?.method === "PUT") {
      const value = JSON.parse(String(options.body)) as QuizStudyDraft;
      return Promise.resolve(json({ ...value, revision: value.revision + 1 }));
    }
    reads += 1;
    return Promise.resolve(reads === 1
      ? new Response(JSON.stringify({ detail: "indisponível" }), { status: 503 })
      : json({ ...empty, revision: 7, answers: { q1: 0 } }));
  });
  await mount();
  expect(host.textContent).toContain("Falha na recuperação");
  expect(host.querySelectorAll(".studyChoice")).toHaveLength(0);
  expect(saves()).toHaveLength(0);
  expect(submit).not.toHaveBeenCalled();
  const retry = [...host.querySelectorAll<HTMLButtonElement>("button")]
    .find((button) => button.textContent === "Tentar novamente");
  expect(retry).toBeTruthy();
  await act(async () => { retry!.click(); });
  expect(host.querySelectorAll(".studyChoice")).toHaveLength(3);
  await choose(1);
  await pressSubmit();
  expect(saves()).toMatchObject([{ revision: 7, answers: { q1: 1 } }]);
  expect(submit).toHaveBeenCalledWith({ q1: 1 });
});

it("keeps unsaved edits after a network failure and retries without discarding them", async () => {
  let writeCount = 0;
  network.fetch.mockImplementation((_url: string, options?: RequestInit) => {
    if (options?.method !== "PUT") return Promise.resolve(json(empty));
    writeCount += 1;
    const value = JSON.parse(String(options.body)) as QuizStudyDraft;
    return writeCount === 1 ? Promise.reject(new Error("Rede indisponível"))
      : Promise.resolve(json({ ...value, revision: value.revision + 1 }));
  });
  await mount();
  await choose(2);
  await pressSubmit();
  expect(submit).not.toHaveBeenCalled();
  expect(host.textContent).toContain("Rede indisponível");
  const retry = [...host.querySelectorAll<HTMLButtonElement>("button")]
    .find((button) => button.textContent === "Tentar novamente");
  expect(retry).toBeTruthy();
  await act(async () => { retry!.click(); });
  expect(host.textContent).toContain("Salvo");
  expect(saves()).toMatchObject([
    { revision: 0, answers: { q1: 2 } },
    { revision: 0, answers: { q1: 2 } },
  ]);
  await pressSubmit();
  expect(submit).toHaveBeenCalledOnce();
  expect(submit).toHaveBeenCalledWith({ q1: 2 });
});
