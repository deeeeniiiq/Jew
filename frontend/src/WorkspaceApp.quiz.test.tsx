// @vitest-environment jsdom
import { act, type ComponentProps } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import WorkspaceApp from "./WorkspaceApp";
import type { WorkspaceShell } from "./components/WorkspaceShell";
import type { AppDialogs } from "./components/AppDialogs";
import type { StudyReportHistory } from "./components/study/StudyReportHistory";
import type { ChatGPTAccountController } from "./hooks/useChatGPTAccount";
import type { GraphEnvelope, LearningPlan, TopicQuizSession, WorkspaceConfig, WorkspaceEnvelope } from "./lib/types";

let shell: ComponentProps<typeof WorkspaceShell>;
let dialogs: ComponentProps<typeof AppDialogs>;
let settings: { rollbackSnapshot: (snapshotId: number) => Promise<void> };
let historyProps: ComponentProps<typeof StudyReportHistory> | null = null;
const network = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock("./lib/apiRequest", async (original) => ({ ...await original<object>(), apiFetch: network.fetch }));
// Exercise WorkspaceApp's real handlers and selection state without mounting WebGL or dialogs.
vi.mock("./components/WorkspaceShell", () => ({ WorkspaceShell: (props: typeof shell) => { shell = props; return null; } }));
vi.mock("./components/AppDialogs", () => ({ AppDialogs: (props: typeof dialogs) => { dialogs = props; return null; } }));
vi.mock("./components/SettingsModal", () => ({ SettingsModal: (props: typeof settings) => { settings = props; return null; } }));
vi.mock("./components/DebugLogsModal", () => ({ DebugLogsModal: () => null }));
vi.mock("./components/study/StudyReportHistory", () => ({
  StudyReportHistory: (props: ComponentProps<typeof StudyReportHistory>) => { historyProps = props; return null; },
}));
vi.mock("./hooks/useGraphChatController", () => ({ useGraphChatController: () => ({
  chatSessions: [], currentChatState: { input: "", messages: [] },
}) }));

const config: WorkspaceConfig = { agent_backend: "chatgpt", ruflo_enabled: false, default_model: "chosen", reasoning_effort: null,
  ui_language: "en", canonical_graph_language: "en", disable_idle_animations: false, memory_mode: "balanced",
  assistant_nickname: "", persona_rules: "", quiz_question_count: 6, pass_threshold: 1, enable_closure_tests: true,
  debug_mode_enabled: false, memory_history_message_limit: 32, memory_include_graph_context: true,
  memory_include_progress_context: true, memory_include_quiz_context: true, memory_include_frontier_context: true,
  memory_include_selected_topic_context: true, allow_explore_without_closure: true,
  require_prerequisite_closure_for_completion: true };
function graph(graph_id: string): GraphEnvelope {
  return { graph_id, title: graph_id, subject: "math", language: "en", version: 1, edges: [], zones: [],
    quiz_attempts: [], metadata: {}, topics: ["arithmetics", "functions"].map(id => ({ id, slug: id, title: id,
      description: "", difficulty: 1, level: 0, estimated_minutes: 10, state: "not_started", zones: [], resources: [], artifacts: [] })) };
}
const workspace = { workspace: { graphs: [graph("first"), graph("second")], active_graph_id: "first", config },
  snapshot: { id: 1 } } as WorkspaceEnvelope;
function plan(graph_id: string, graph_version = 1): LearningPlan {
  return { graph_id, graph_version, evaluated_at: "2026-10-24T00:00:00Z", method: "deterministic-heuristic-v1",
    total_topics: 2, completed_topics: 0, certified_topics: 0, manual_only_topics: 0,
    due_reviews: 0, blocked_topics: 0, graph_warnings: [],
    signals: [{ topic_id: "arithmetics", evidence_level: "none", mastery_indicator: "insufficient_evidence",
      quiz_attempts: 0, latest_quiz_score: null, latest_quiz_at: null, failure_count: 0,
      blocked_prerequisite_ids: [], next_review_at: null, review_due: false }],
    recommendations: [{ topic_id: "arithmetics", action: "study", priority: 30,
      reason: "No quiz evidence", decision_rule: "no_quiz_evidence", evidence: ["absence_of_quiz"],
      related_topic_ids: [], completion_condition: "Pass a quiz" }],
  };
}
function quiz(topic_id = "arithmetics", session_id = "test"): TopicQuizSession {
  return { graph_id: "first", topic_id, session_id, created_at: "2026-10-17T00:00:00Z", question_count: 6,
    generator: "chosen", closure_status: { topic_id, prerequisite_topic_ids: [], blocked_prerequisite_ids: [],
      can_award_completion: true, latest_attempt: null }, questions: [{ id: "q1", prompt: "Question?", choices: ["A", "B", "C", "D"], explanation: "" }] };
}
function deferred() {
  let resolve!: (value: Response) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<Response>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const json = (value: unknown) => new Response(JSON.stringify(value), { headers: { "Content-Type": "application/json" } });
let root: Root;
beforeEach(async () => {
  historyProps = null;
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
  vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
  localStorage.clear();
  network.fetch.mockReset().mockImplementation(async (url: string) => {
    if (url.endsWith("/workspace/current")) return json(workspace);
    if (url.endsWith("/auth/session")) return json({ workspace_surface: { onboarding_state: "active_workspace" } });
    if (url.endsWith("/graph/snapshots")) return json({ items: [] });
    if (url.endsWith("/assessment")) return json({ cards: [] });
    if (url.endsWith("/learning-plan")) return json(plan(url.includes("/graphs/second/") ? "second" : "first"));
    throw new Error(`Unexpected request: ${url}`);
  });
  root = createRoot(document.createElement("div"));
  await act(async () => root.render(<WorkspaceApp chatgpt={{ account: null, refresh: vi.fn() } as unknown as ChatGPTAccountController} />));
  await select("arithmetics");
});
afterEach(async () => { await act(async () => root.unmount()); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
async function select(topicId: string) { await act(async () => shell.navigation.setSelectedTopicId(topicId)); }
async function start() {
  let request!: Promise<void>;
  await act(async () => { request = shell.topicDetails.startQuiz(); });
  return { request };
}

it("opens report history for the current topic and closes it on selection changes", async () => {
  await act(async () => shell.topicDetails.openQuizReportHistory());
  expect(historyProps).toMatchObject({ graphId: "first", topicId: "arithmetics", topicTitle: "arithmetics" });
  historyProps = null;
  await select("functions");
  expect(historyProps).toBeNull();
  await act(async () => shell.topicDetails.openQuizReportHistory());
  expect(historyProps).toMatchObject({ graphId: "first", topicId: "functions" });
  historyProps = null;
  await act(async () => shell.navigation.setActiveGraphId("second"));
  expect(historyProps).toBeNull();
  await select("arithmetics");
  await act(async () => shell.topicDetails.openQuizReportHistory());
  expect(historyProps).toMatchObject({ graphId: "second", topicId: "arithmetics" });
  await act(async () => historyProps?.onClose());
  historyProps = null;
  await select("functions");
  expect(historyProps).toBeNull();
});

it("does not disturb an active quiz when viewing the history", async () => {
  const baseFetch = network.fetch.getMockImplementation()!;
  network.fetch.mockImplementation(async (url: string) => url.endsWith("/quiz/start")
    ? json({ session: quiz() }) : baseFetch(url));
  const { request } = await start();
  await act(async () => request);
  expect(dialogs.quizSession?.session_id).toBe("test");
  await act(async () => shell.topicDetails.openQuizReportHistory());
  expect(historyProps).toMatchObject({ graphId: "first", topicId: "arithmetics" });
  expect(dialogs.quizSession?.session_id).toBe("test");
  await act(async () => historyProps?.onClose());
  expect(dialogs.quizSession?.session_id).toBe("test");
});

it("loads the active graph's explainable learning guidance", () => {
  expect(shell.topicDetails.learningPlan?.graph_id).toBe("first");
  expect(shell.topicDetails.learningPlan?.recommendations[0].decision_rule).toBe("no_quiz_evidence");
});

it("ignores delayed adaptive guidance from an inactive graph", async () => {
  const old = deferred();
  const current = deferred();
  const baseFetch = network.fetch.getMockImplementation()!;
  network.fetch.mockImplementation((url: string) => url.endsWith("/learning-plan")
    ? (url.includes("/graphs/second/") ? old.promise : current.promise) : baseFetch(url));
  await act(async () => shell.navigation.setActiveGraphId("second"));
  expect(shell.topicDetails.learningPlan).toBeNull();
  await act(async () => shell.navigation.setActiveGraphId("first"));
  await act(async () => current.resolve(json(plan("first"))));
  expect(shell.topicDetails.learningPlan?.graph_id).toBe("first");
  await act(async () => old.resolve(json(plan("second"))));
  expect(shell.topicDetails.learningPlan?.graph_id).toBe("first");
});

it("rejects adaptive payloads with a stale graph version or wrong graph ID", async () => {
  const baseFetch = network.fetch.getMockImplementation()!;
  network.fetch.mockImplementation((url: string) => url.endsWith("/learning-plan")
    ? json(plan("second", 999)) : baseFetch(url));
  await act(async () => shell.navigation.setActiveGraphId("second"));
  expect(shell.topicDetails.learningPlan).toBeNull();
  network.fetch.mockImplementation((url: string) => url.endsWith("/learning-plan")
    ? json(plan("second", 1)) : baseFetch(url));
  await act(async () => shell.navigation.setActiveGraphId("first"));
  await act(async () => shell.navigation.setActiveGraphId("second"));
  expect(shell.topicDetails.learningPlan?.graph_id).toBe("second");
});

it("clears guidance after a failed adaptive request without interrupting navigation", async () => {
  const baseFetch = network.fetch.getMockImplementation()!;
  network.fetch.mockImplementation((url: string) => url.endsWith("/learning-plan")
    ? Promise.reject(new Error("offline")) : baseFetch(url));
  await act(async () => shell.navigation.setActiveGraphId("second"));
  expect(shell.topicDetails.learningPlan).toBeNull();
  expect(shell.navigation.activeGraph?.graph_id).toBe("second");
});

it("refreshes guidance when a successful academic action changes the graph", async () => {
  const updated = structuredClone(workspace);
  updated.snapshot.id = 2;
  updated.workspace.graphs[0].version = 2;
  const baseFetch = network.fetch.getMockImplementation()!;
  network.fetch.mockImplementation((url: string) => {
    if (url.endsWith("/mark-finished")) return json({ workspace: updated, reviews: [], attempt: { passed: true } });
    if (url.endsWith("/graphs/first/learning-plan")) return json(plan("first", 2));
    return baseFetch(url);
  });
  await act(async () => shell.topicDetails.markTopicFinished());
  expect(shell.navigation.activeGraph?.version).toBe(2);
  expect(shell.topicDetails.learningPlan?.graph_version).toBe(2);
  expect(network.fetch.mock.calls.some(([url]) => String(url).endsWith("/graphs/first/learning-plan"))).toBe(true);
});

it("does not open a delayed quiz after selecting another topic", async () => {
  const pending = deferred();
  network.fetch.mockImplementationOnce(() => pending.promise);
  const { request } = await start();
  await select("functions");
  await act(async () => { pending.resolve(json({ session: quiz() })); await request; });
  expect(dialogs.quizSession).toBeNull();
  expect(shell.topicDetails.quizLoading).toBe(false);
  expect(shell.topicDetails.quizError).toBeNull();
});

it("ignores an old response after leaving and returning to the original topic", async () => {
  const pending = deferred();
  network.fetch.mockImplementationOnce(() => pending.promise);
  const { request } = await start();
  await select("functions");
  await select("arithmetics");
  await act(async () => { pending.resolve(json({ session: quiz() })); await request; });
  expect(dialogs.quizSession).toBeNull();
});

it("does not open a quiz from a previous graph with the same topic id", async () => {
  const pending = deferred();
  network.fetch.mockImplementationOnce(() => pending.promise);
  const { request } = await start();
  await act(async () => shell.navigation.setActiveGraphId("second"));
  await select("arithmetics");
  await act(async () => { pending.resolve(json({ session: quiz() })); await request; });
  expect(dialogs.quizSession).toBeNull();
  expect(shell.navigation.activeGraph?.graph_id).toBe("second");
});

it("an older response cannot replace a new quiz or stop its loading indicator", async () => {
  const old = deferred();
  network.fetch.mockImplementationOnce(() => old.promise);
  const first = await start();
  await select("functions");
  const next = deferred();
  network.fetch.mockImplementationOnce(() => next.promise);
  const second = await start();
  await act(async () => { old.resolve(json({ session: quiz() })); await first.request; });
  expect(shell.topicDetails.quizLoading).toBe(true);
  expect(dialogs.quizSession).toBeNull();
  await act(async () => { next.resolve(json({ session: quiz("functions", "new") })); await second.request; });
  expect(dialogs.quizSession?.session_id).toBe("new");
});

it("does not show an error from a previous topic's request", async () => {
  const pending = deferred();
  network.fetch.mockImplementationOnce(() => pending.promise);
  const { request } = await start();
  await select("functions");
  await act(async () => { pending.reject(new Error("old failure")); await request; });
  expect(shell.topicDetails.quizError).toBeNull();
});

it("opening a saved test from chat invalidates pending generation for that topic", async () => {
  const pending = deferred();
  network.fetch.mockImplementationOnce(() => pending.promise);
  const { request } = await start();
  await act(async () => shell.assistant.agentControls!.openQuiz(quiz("arithmetics", "saved")));
  await act(async () => { pending.resolve(json({ session: quiz() })); await request; });
  expect(dialogs.quizSession?.session_id).toBe("saved");
  expect(shell.topicDetails.quizLoading).toBe(false);
});

it("submits the quiz session's graph, topic, session id and answers", async () => {
  network.fetch.mockResolvedValueOnce(json({ session: quiz() }));
  await act(async () => shell.topicDetails.startQuiz());
  await act(async () => dialogs.setQuizAnswers({ q1: 2 }));
  network.fetch.mockResolvedValueOnce(json({ workspace, reviews: [], attempt: { passed: false } }));
  await act(async () => dialogs.submitQuiz());
  const [url, options] = network.fetch.mock.calls.find(([url]) => String(url).endsWith("/quiz/submit"))!;
  expect(url).toMatch(/\/graphs\/first\/topics\/arithmetics\/quiz\/submit$/);
  expect(JSON.parse(options.body)).toEqual({ session_id: "test", answers: [{ question_id: "q1", choice_index: 2 }] });
});

it("uses the graph's selected local model to generate quizzes", async () => {
  await act(async () => shell.assistant.setSelectedChatModel("qwen3:4b"));
  network.fetch.mockResolvedValueOnce(json({ session: quiz() }));
  await act(async () => shell.topicDetails.startQuiz());
  const [, options] = network.fetch.mock.calls.find(([url]) => String(url).endsWith("/quiz/start"))!;
  expect(JSON.parse(options.body)).toEqual({ model: "qwen3:4b" });
});

it("closing a quiz while submission is pending does not restore its error or reviews", async () => {
  network.fetch.mockResolvedValueOnce(json({ session: quiz() }));
  await act(async () => shell.topicDetails.startQuiz());
  const pending = deferred();
  network.fetch.mockImplementationOnce(() => pending.promise);
  let request!: Promise<void>;
  await act(async () => { request = dialogs.submitQuiz(); });
  await act(async () => dialogs.closeQuizModal());
  await act(async () => { pending.reject(new Error("late submission failure")); await request; });
  expect(dialogs.quizSession).toBeNull();
  expect(dialogs.quizError).toBeNull();
});

it("keeps awarded progress after navigation without reopening the old quiz", async () => {
  network.fetch.mockResolvedValueOnce(json({ session: quiz() }));
  await act(async () => shell.topicDetails.startQuiz());
  const pending = deferred();
  network.fetch.mockImplementationOnce(() => pending.promise);
  let request!: Promise<void>;
  await act(async () => { request = dialogs.submitQuiz(); });
  await select("functions");
  const awarded = structuredClone(workspace);
  awarded.snapshot.id = 2;
  awarded.workspace.graphs[0].topics[0].state = "solid";
  await act(async () => { pending.resolve(json({ workspace: awarded, reviews: [], attempt: { passed: true } })); await request; });
  expect(dialogs.quizSession).toBeNull();
  expect(shell.topicDetails.selectedTopic?.id).toBe("functions");
  expect(shell.navigation.activeGraph?.topics[0].state).toBe("solid");
  expect(shell.topicDetails.quizSuccess).toBeNull();
});

it("keeps a newer rollback visible when an older quiz submission returns afterwards", async () => {
  network.fetch.mockResolvedValueOnce(json({ session: quiz() }));
  await act(async () => shell.topicDetails.startQuiz());
  const submitted = deferred();
  network.fetch.mockImplementationOnce(() => submitted.promise);
  let pendingSubmit!: Promise<void>;
  await act(async () => { pendingSubmit = dialogs.submitQuiz(); });
  expect(shell.topicDetails.quizLoading).toBe(true);

  const rolledBack = structuredClone(workspace);
  rolledBack.snapshot.id = 3;
  rolledBack.workspace.graphs[0].version = 3;
  rolledBack.workspace.graphs[0].topics[0].state = "learning";
  network.fetch.mockResolvedValueOnce(json(rolledBack));
  await act(async () => settings.rollbackSnapshot(1));
  expect(shell.topicDetails.quizLoading).toBe(false);
  expect(dialogs.quizSession).toBeNull();
  expect(dialogs.quizReviews).toBeNull();

  const olderSubmission = structuredClone(workspace);
  olderSubmission.snapshot.id = 2;
  olderSubmission.workspace.graphs[0].topics[0].state = "solid";
  await act(async () => {
    submitted.resolve(json({ workspace: olderSubmission, reviews: [], attempt: { passed: true } }));
    await pendingSubmit;
  });
  expect(shell.navigation.activeGraph?.topics[0].state).toBe("learning");
  expect(dialogs.quizSession).toBeNull();
  expect(dialogs.quizReviews).toBeNull();
  expect(shell.topicDetails.quizSuccess).toBeNull();
  expect(shell.topicDetails.quizLoading).toBe(false);
});

it("preserves manual completion after navigating to another topic without stale success", async () => {
  const pending = deferred();
  network.fetch.mockImplementationOnce(() => pending.promise);
  let request!: Promise<void>;
  await act(async () => { request = shell.topicDetails.markTopicFinished(); });
  await select("functions");
  const completed = structuredClone(workspace);
  completed.snapshot.id = 2;
  completed.workspace.graphs[0].topics[0].state = "solid";
  await act(async () => {
    pending.resolve(json({ workspace: completed, reviews: [], attempt: { source: "manual" } }));
    await request;
  });
  expect(shell.topicDetails.selectedTopic?.id).toBe("functions");
  expect(shell.navigation.activeGraph?.topics[0].state).toBe("solid");
  expect(shell.topicDetails.quizSuccess).toBeNull();
  expect(dialogs.quizSession).toBeNull();
});
