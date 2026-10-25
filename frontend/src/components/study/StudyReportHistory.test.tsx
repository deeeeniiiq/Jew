// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { StudyReportHistory } from "./StudyReportHistory";

const network = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock("../../lib/apiRequest", async (original) => ({
  ...await original<object>(), apiFetch: network.fetch,
}));
vi.mock("./StudyReport", () => ({
  StudyReport: ({ report }: { report: { title: string } }) => <p>Relatório: {report.title}</p>,
}));

const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), {
  status, headers: { "Content-Type": "application/json" },
});
const page = (ids: string[], total = ids.length, offset = 0, topicId = "algebra") => ({
  items: ids.map((attempt_id) => ({ attempt_id, topic_id: topicId,
    created_at: "2026-10-24T10:00:00Z", title: attempt_id, score: .8,
    question_count: 6, in_current_graph: true })),
  total, limit: 10, offset,
});
const record = (id: string, inCurrentGraph = true, topicId = "algebra") => ({
  format_version: 1, graph_id: "math", topic_id: topicId,
  attempt: { id }, report: { title: id }, reviews: [],
  in_current_graph: inCurrentGraph,
});
function deferred() {
  let resolve!: (value: Response) => void;
  const promise = new Promise<Response>((yes) => { resolve = yes; });
  return { promise, resolve };
}

let host: HTMLDivElement;
let root: Root;
const close = vi.fn();
beforeEach(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  network.fetch.mockReset();
  close.mockReset();
});
afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
  vi.unstubAllGlobals();
});
async function mount(graphId = "math", topicId = "algebra") {
  await act(async () => root.render(<StudyReportHistory graphId={graphId} topicId={topicId}
    topicTitle={`Tópico ${topicId}`} onClose={close} />));
}
async function click(text: string) {
  const button = [...host.querySelectorAll<HTMLButtonElement>("button")]
    .find(item => item.textContent?.includes(text));
  expect(button, `Missing button ${text}`).toBeTruthy();
  await act(async () => button!.click());
}

it("pages through completed attempts and opens a preserved rollback report", async () => {
  network.fetch.mockImplementation(async (url: string) => {
    if (url.endsWith("/reports?limit=10&offset=0")) return json(page(Array.from({ length: 10 }, (_, i) => `attempt-${i}`), 11));
    if (url.endsWith("/reports?limit=10&offset=10")) return json(page(["old-attempt"], 11, 10));
    if (url.endsWith("/reports/old-attempt")) return json(record("old-attempt", false));
    throw new Error(`Unexpected request ${url}`);
  });
  await mount();
  expect(host.querySelector('[role="dialog"]')?.getAttribute("aria-labelledby")).toBe("quiz-report-history-title");
  expect(host.textContent).toContain("1 de 2");
  await click("Próxima");
  expect(host.textContent).toContain("2 de 2");
  await click("80%");
  expect(host.textContent).toContain("Relatório: old-attempt");
  expect(host.textContent).toContain("retirada do estado atual");
  await click("Voltar às tentativas");
  expect(host.textContent).toContain("2 de 2");
  expect(network.fetch).toHaveBeenCalledTimes(3);
});

it("shows an empty history and allows retry after a listing error", async () => {
  let calls = 0;
  network.fetch.mockImplementation(async () => {
    calls += 1;
    if (calls === 1) return json({ detail: "Falha temporária" }, 503);
    return json(page([]));
  });
  await mount();
  expect(host.querySelector('[role="alert"]')?.textContent).toContain("Falha temporária");
  await click("Tentar novamente");
  expect(host.textContent).toContain("Nenhuma avaliação registrada");
  expect(host.querySelector('[role="alert"]')).toBeNull();
});

it("rejects a mismatched detail and retries only that selected attempt", async () => {
  let detailCalls = 0;
  network.fetch.mockImplementation(async (url: string) => {
    if (url.includes("/reports?")) return json(page(["attempt-a"]));
    detailCalls += 1;
    return json(record("attempt-a", true, detailCalls === 1 ? "wrong-topic" : "algebra"));
  });
  await mount();
  await click("80%");
  expect(host.querySelector('[role="alert"]')?.textContent).toContain("não corresponde");
  expect(host.textContent).not.toContain("Relatório: attempt-a");
  await click("Tentar novamente");
  expect(host.textContent).toContain("Relatório: attempt-a");
  expect(detailCalls).toBe(2);
});

it("rejects an invalid history page without crashing the modal", async () => {
  network.fetch.mockImplementation(async () => json(page(["attempt-a"], 1, 0, "foreign-topic")));
  await mount();
  expect(host.querySelector('[role="alert"]')?.textContent).toContain("dados inconsistentes");
  expect(host.querySelector('[role="dialog"]')).toBeTruthy();
});

it("aborts obsolete list requests when changing topics and ignores late responses", async () => {
  const old = deferred();
  const requests: Array<{ url: string; signal?: AbortSignal }> = [];
  network.fetch.mockImplementation(async (url: string, options?: RequestInit) => {
    requests.push({ url, signal: options?.signal as AbortSignal });
    return url.includes("/topics/algebra/") ? old.promise : json(page(["geometry-attempt"], 1, 0, "geometry"));
  });
  await mount();
  expect(host.textContent).toContain("Carregando histórico");
  await mount("math", "geometry");
  expect(requests[0].signal?.aborted).toBe(true);
  expect(host.textContent).toContain("Tópico geometry");
  await act(async () => { old.resolve(json(page(["stale-attempt"]))); });
  expect(host.textContent).not.toContain("stale-attempt");
  expect(host.querySelectorAll(".studyHistoryItem")).toHaveLength(1);
  expect(requests[1].url).toContain("/topics/geometry/");
});

it("aborts a pending detail when returning to the list and supports Escape", async () => {
  const detail = deferred();
  let detailSignal: AbortSignal | undefined;
  network.fetch.mockImplementation(async (url: string, options?: RequestInit) => {
    if (url.includes("/reports?")) return json(page(["attempt-a"]));
    detailSignal = options?.signal as AbortSignal;
    return detail.promise;
  });
  await mount();
  await click("80%");
  expect(host.textContent).toContain("Carregando relatório");
  await click("Voltar às tentativas");
  expect(detailSignal?.aborted).toBe(true);
  await act(async () => detail.resolve(json(record("attempt-a"))));
  expect(host.textContent).not.toContain("Relatório: attempt-a");
  await act(async () => document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
  expect(close).toHaveBeenCalledOnce();
});

function pdfResponse(content = "%PDF-1.7\nJEW", type = "application/pdf", status = 200) {
  return new Response(content, { status, headers: { "Content-Type": type } });
}

function setupDownload() {
  const createObjectURL = vi.fn(() => "blob:jew-report");
  const revokeObjectURL = vi.fn();
  Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectURL });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeObjectURL });
  const clickLink = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  return { createObjectURL, revokeObjectURL, clickLink };
}

afterEach(() => {
  Reflect.deleteProperty(URL, "createObjectURL");
  Reflect.deleteProperty(URL, "revokeObjectURL");
  vi.restoreAllMocks();
});

it("downloads a submitted PDF and revokes the temporary URL", async () => {
  const { createObjectURL, revokeObjectURL, clickLink } = setupDownload();
  network.fetch.mockImplementation(async (url: string) => {
    if (url.includes("/reports?")) return json(page(["attempt-a"]));
    if (url.endsWith("/reports/attempt-a")) return json(record("attempt-a"));
    if (url.endsWith("/reports/attempt-a/pdf")) return pdfResponse();
    throw new Error(`Unexpected URL ${url}`);
  });
  await mount();
  await click("80%");
  expect(host.textContent).toContain("Baixar relatório em PDF");
  await click("Baixar relatório em PDF");
  expect(createObjectURL).toHaveBeenCalledOnce();
  expect(revokeObjectURL).toHaveBeenCalledWith("blob:jew-report");
  expect(clickLink).toHaveBeenCalledOnce();
  expect(host.querySelector('[role="alert"]')).toBeNull();
  expect(host.textContent).toContain("Baixar relatório em PDF");
});

it("rejects fake PDF content and lets the learner retry", async () => {
  const { createObjectURL } = setupDownload();
  let pdfCalls = 0;
  network.fetch.mockImplementation(async (url: string) => {
    if (url.includes("/reports?")) return json(page(["attempt-a"]));
    if (url.endsWith("/reports/attempt-a")) return json(record("attempt-a"));
    pdfCalls++;
    return pdfCalls === 1 ? pdfResponse("invalid", "application/pdf") : pdfResponse();
  });
  await mount();
  await click("80%");
  await click("Baixar relatório em PDF");
  expect(host.querySelector('[role="alert"]')?.textContent).toContain("não é um PDF válido");
  expect(createObjectURL).not.toHaveBeenCalled();
  await click("Baixar relatório em PDF");
  expect(createObjectURL).toHaveBeenCalledOnce();
  expect(host.querySelector('[role="alert"]')).toBeNull();
});

it("rejects incorrect PDF content type and an empty PDF without downloading", async () => {
  const { createObjectURL } = setupDownload();
  let pdfCalls = 0;
  network.fetch.mockImplementation(async (url: string) => {
    if (url.includes("/reports?")) return json(page(["attempt-a"]));
    if (url.endsWith("/reports/attempt-a")) return json(record("attempt-a"));
    pdfCalls += 1;
    return pdfCalls === 1 ? pdfResponse("%PDF-1.7", "text/html") : pdfResponse("");
  });
  await mount();
  await click("80%");
  await click("Baixar relatório em PDF");
  expect(host.querySelector('[role="alert"]')?.textContent).toContain("não retornou um PDF válido");
  await click("Baixar relatório em PDF");
  expect(host.querySelector('[role="alert"]')?.textContent).toContain("Exportação PDF interrompida");
  expect(createObjectURL).not.toHaveBeenCalled();
});

it("shows a server-side PDF error and allows a successful retry", async () => {
  const { createObjectURL } = setupDownload();
  let pdfCalls = 0;
  network.fetch.mockImplementation(async (url: string) => {
    if (url.includes("/reports?")) return json(page(["attempt-a"]));
    if (url.endsWith("/reports/attempt-a")) return json(record("attempt-a"));
    pdfCalls += 1;
    return pdfCalls === 1 ? json({ detail: "Falha ao renderizar relatório" }, 500) : pdfResponse();
  });
  await mount();
  await click("80%");
  await click("Baixar relatório em PDF");
  expect(host.querySelector('[role="alert"]')?.textContent).toContain("Falha ao renderizar relatório");
  await click("Baixar relatório em PDF");
  expect(createObjectURL).toHaveBeenCalledOnce();
  expect(host.querySelector('[role="alert"]')).toBeNull();
});

it("aborts the PDF when navigating back and resets the next attempt's controls", async () => {
  const { createObjectURL } = setupDownload();
  const pending = deferred();
  let pdfSignal: AbortSignal | undefined;
  network.fetch.mockImplementation(async (url: string, options?: RequestInit) => {
    if (url.includes("/reports?")) return json(page(["attempt-a", "attempt-b"]));
    if (url.endsWith("/reports/attempt-a")) return json(record("attempt-a"));
    if (url.endsWith("/reports/attempt-b")) return json(record("attempt-b"));
    if (url.endsWith("/reports/attempt-a/pdf")) {
      pdfSignal = options?.signal ?? undefined;
      return pending.promise;
    }
    if (url.endsWith("/reports/attempt-b/pdf")) return pdfResponse();
    throw new Error(`Unexpected URL ${url}`);
  });
  await mount();
  await click("80%");
  await click("Baixar relatório em PDF");
  expect(host.textContent).toContain("Exportando PDF…");
  await click("Voltar às tentativas");
  expect(pdfSignal?.aborted).toBe(true);
  await act(async () => pending.resolve(pdfResponse()));
  expect(createObjectURL).not.toHaveBeenCalled();
  await click("80%");
  // The second equally-scored record appears after the first in the list.
  expect(host.textContent).toContain("Relatório: attempt-a");
  expect(host.textContent).toContain("Baixar relatório em PDF");
  expect(host.textContent).not.toContain("Exportando PDF…");
});

it("aborts a PDF request on unmount without creating a download", async () => {
  const { createObjectURL } = setupDownload();
  const pending = deferred();
  let signal: AbortSignal | undefined;
  network.fetch.mockImplementation(async (url: string, options?: RequestInit) => {
    if (url.includes("/reports?")) return json(page(["attempt-a"]));
    if (url.endsWith("/reports/attempt-a")) return json(record("attempt-a"));
    signal = options?.signal ?? undefined;
    return pending.promise;
  });
  await mount();
  await click("80%");
  await click("Baixar relatório em PDF");
  await act(async () => root.unmount());
  expect(signal?.aborted).toBe(true);
  await act(async () => pending.resolve(pdfResponse()));
  expect(createObjectURL).not.toHaveBeenCalled();
});

