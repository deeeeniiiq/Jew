// @vitest-environment jsdom
import { act, type ComponentProps } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import WorkspaceApp from "./WorkspaceApp";
import type { WorkspaceShell } from "./components/WorkspaceShell";
import type { ChatGPTAccountController } from "./hooks/useChatGPTAccount";
import type { WorkspaceConfig, WorkspaceEnvelope } from "./lib/types";

let shell: ComponentProps<typeof WorkspaceShell>;
const network = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock("./lib/apiRequest", async original => ({ ...await original<object>(), apiFetch: network.fetch }));
vi.mock("./components/WorkspaceShell", () => ({ WorkspaceShell: (props: typeof shell) => { shell = props; return null; } }));
vi.mock("./components/AppDialogs", () => ({ AppDialogs: () => null }));
vi.mock("./components/SettingsModal", () => ({ SettingsModal: () => null }));
vi.mock("./components/DebugLogsModal", () => ({ DebugLogsModal: () => null }));
vi.mock("./hooks/useGraphChatController", () => ({ useGraphChatController: () => ({
  chatSessions: [], currentChatState: { input: "", messages: [] },
}) }));

const config: WorkspaceConfig = { agent_backend: "ollama", ruflo_enabled: false, default_model: "qwen3.5:4b", reasoning_effort: null,
  ui_language: "en", canonical_graph_language: "en", disable_idle_animations: false, memory_mode: "balanced",
  assistant_nickname: "", persona_rules: "", quiz_question_count: 6, pass_threshold: 1, enable_closure_tests: true,
  debug_mode_enabled: false, memory_history_message_limit: 32, memory_include_graph_context: true,
  memory_include_progress_context: true, memory_include_quiz_context: true, memory_include_frontier_context: true,
  memory_include_selected_topic_context: true, allow_explore_without_closure: true,
  require_prerequisite_closure_for_completion: true };
const base = { workspace: { title: "Test workspace", graphs: ["first", "second"].map(graph_id => ({ graph_id, title: graph_id, subject: "math", language: "en", version: 1,
  edges: [], zones: [], quiz_attempts: [], metadata: {}, topics: ["arithmetics", "functions"].map(id => ({
    id, slug: id, title: id, description: "", difficulty: 1, level: 0, estimated_minutes: 10, state: "not_started", zones: [], resources: [], artifacts: [],
  })) })), active_graph_id: "first", config }, snapshot: { id: 1, source: "test", created_at: "2026-10-23T00:00:00Z" } } as WorkspaceEnvelope;
const json = (body: unknown) => new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } });
function deferred() {
  let resolve!: (response: Response) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<Response>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function generated(title: string, snapshotId: number): { artifact: unknown; workspace: WorkspaceEnvelope } {
  const workspace = structuredClone(base);
  workspace.snapshot.id = snapshotId;
  const artifact = { id: `lesson-${title}`, title, kind: "lesson", body: "## A complete lesson", created_at: "2026-10-23T00:00:00Z" };
  workspace.workspace.graphs[0].topics[0].artifacts.push(artifact);
  return { artifact, workspace };
}
let root: Root;
beforeEach(async () => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
  vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
  localStorage.clear();
  network.fetch.mockReset().mockImplementation(async (url: string) => {
    if (url.endsWith("/workspace/current")) return json(base);
    if (url.endsWith("/auth/session")) return json({ workspace_surface: { onboarding_state: "active_workspace" } });
    if (url.endsWith("/graph/snapshots")) return json({ items: [] });
    if (url.endsWith("/assessment")) return json({ cards: [] });
    throw new Error(`Unexpected request: ${url}`);
  });
  root = createRoot(document.createElement("div"));
  await act(async () => root.render(<WorkspaceApp chatgpt={{ account: null, refresh: vi.fn() } as unknown as ChatGPTAccountController} />));
  await act(async () => shell.navigation.setSelectedTopicId("arithmetics"));
});
afterEach(async () => { await act(async () => root.unmount()); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("sends the chosen Ollama model and displays a persisted lesson", async () => {
  network.fetch.mockResolvedValueOnce(json(generated("First lesson", 2)));
  await act(async () => shell.topicDetails.generateLesson());
  const [url, options] = network.fetch.mock.calls.find(([url]) => String(url).endsWith("/lessons/generate"))!;
  expect(url).toMatch(/\/graphs\/first\/topics\/arithmetics\/lessons\/generate$/);
  expect(JSON.parse(options.body)).toEqual({ model: "qwen3.5:4b" });
  expect(shell.topicDetails.selectedTopic?.artifacts.map(item => item.title)).toContain("First lesson");
  expect(shell.topicDetails.lessonSuccess).toBeTruthy();
});

it("ignores a delayed response after changing topics and returning", async () => {
  const old = deferred();
  network.fetch.mockImplementationOnce(() => old.promise);
  let request!: Promise<void>;
  await act(async () => { request = shell.topicDetails.generateLesson(); });
  await act(async () => shell.navigation.setSelectedTopicId("functions"));
  await act(async () => shell.navigation.setSelectedTopicId("arithmetics"));
  await act(async () => { old.resolve(json(generated("Stale lesson", 7))); await request; });
  expect(shell.topicDetails.selectedTopic?.artifacts).toEqual([]);
  expect(shell.topicDetails.lessonSuccess).toBeNull();
  expect(shell.topicDetails.lessonLoading).toBe(false);
});

it("keeps the current graph while an older graph's request finishes", async () => {
  const old = deferred();
  network.fetch.mockImplementationOnce(() => old.promise);
  let request!: Promise<void>;
  await act(async () => { request = shell.topicDetails.generateLesson(); });
  await act(async () => shell.navigation.setActiveGraphId("second"));
  await act(async () => shell.navigation.setSelectedTopicId("arithmetics"));
  await act(async () => { old.resolve(json(generated("Wrong graph", 9))); await request; });
  expect(shell.navigation.activeGraph?.graph_id).toBe("second");
  expect(shell.topicDetails.selectedTopic?.artifacts).toEqual([]);
});

it("does not surface a failure after the topic changes", async () => {
  const pending = deferred();
  network.fetch.mockImplementationOnce(() => pending.promise);
  let request!: Promise<void>;
  await act(async () => { request = shell.topicDetails.generateLesson(); });
  await act(async () => shell.navigation.setSelectedTopicId("functions"));
  await act(async () => { pending.reject(new Error("Old error")); await request; });
  expect(shell.topicDetails.lessonError).toBeNull();
});
