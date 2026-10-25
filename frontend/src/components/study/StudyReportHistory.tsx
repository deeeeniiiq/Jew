import React, { useEffect, useRef, useState } from "react";
import { API_BASE } from "../../lib/api";
import { apiFetch, readErrorMessage } from "../../lib/apiRequest";
import type { QuizReportHistoryPage, QuizReportRecord } from "../../lib/types";
import { Modal } from "../ui/Modal";
import { StudyReport } from "./StudyReport";

const PAGE_SIZE = 10;

export function StudyReportHistory({ graphId, topicId, topicTitle, onClose }: {
  graphId: string;
  topicId: string;
  topicTitle: string;
  onClose: () => void;
}): React.JSX.Element {
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [page, setPage] = useState<QuizReportHistoryPage | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detailRevision, setDetailRevision] = useState(0);
  const [selected, setSelected] = useState<QuizReportRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const pdfController = useRef<AbortController | null>(null);
  const base = `${API_BASE}/api/v1/graphs/${encodeURIComponent(graphId)}/topics/${encodeURIComponent(topicId)}/quiz/reports`;

  useEffect(() => {
    // A new attempt or topic owns a fresh download state. Cleanup invalidates
    // the previous request; late responses must never start a stale download.
    setPdfLoading(false);
    setPdfError(null);
    return () => {
      pdfController.current?.abort();
      pdfController.current = null;
    };
  }, [base, selectedId]);

  async function downloadPDF(): Promise<void> {
    if (!selectedId || pdfLoading) return;
    const controller = new AbortController();
    pdfController.current = controller;
    setPdfError(null);
    setPdfLoading(true);
    try {
      const response = await apiFetch(`${base}/${encodeURIComponent(selectedId)}/pdf`, { signal: controller.signal });
      if (!response.ok) throw new Error(await readErrorMessage(response, "Falha ao exportar PDF."));
      if (!(response.headers.get("content-type") ?? "").includes("application/pdf")) throw new Error("O servidor não retornou um PDF válido.");
      const blob = await response.blob();
      if (!blob.size || controller.signal.aborted) throw new Error("Exportação PDF interrompida.");
      const signature = new TextDecoder().decode(await blob.slice(0, 5).arrayBuffer());
      if (signature !== "%PDF-") throw new Error("O arquivo recebido não é um PDF válido.");
      if (controller.signal.aborted) return;
      const objectUrl = URL.createObjectURL(blob);
      try {
        const link = document.createElement("a");
        link.href = objectUrl;
        link.download = "jew-relatorio-pedagogico.pdf";
        document.body.appendChild(link);
        link.click();
        link.remove();
      } finally {
        URL.revokeObjectURL(objectUrl);
      }
    } catch (error) {
      if (!controller.signal.aborted) setPdfError(error instanceof Error ? error.message : "Falha ao exportar PDF.");
    } finally {
      if (pdfController.current === controller) pdfController.current = null;
      if (!controller.signal.aborted) setPdfLoading(false);
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    apiFetch(`${base}?limit=${PAGE_SIZE}&offset=${offset}`, { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error(await readErrorMessage(response, "Não foi possível carregar o histórico."));
        return response.json() as Promise<QuizReportHistoryPage>;
      })
      .then(result => {
        if (controller.signal.aborted) return;
        if (!Array.isArray(result?.items) || !Number.isSafeInteger(result.total) || result.total < 0 ||
          result.limit !== PAGE_SIZE || result.offset !== offset || result.items.some(item =>
            item.topic_id !== topicId || typeof item.attempt_id !== "string" || !item.attempt_id ||
            !Number.isFinite(item.score) || item.score < 0 || item.score > 1 ||
            !Number.isSafeInteger(item.question_count) || item.question_count < 0 ||
            typeof item.in_current_graph !== "boolean")) {
          throw new Error("O histórico recebido contém dados inconsistentes.");
        }
        setPage(result);
      })
      .catch(reason => { if (!controller.signal.aborted) { setPage(null); setError(reason instanceof Error ? reason.message : "Falha ao consultar histórico."); } })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [base, offset, revision]);

  useEffect(() => {
    if (!selectedId) { setSelected(null); setDetailError(null); setDetailLoading(false); return; }
    const controller = new AbortController();
    setSelected(null);
    setDetailError(null);
    setDetailLoading(true);
    apiFetch(`${base}/${encodeURIComponent(selectedId)}`, { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error(await readErrorMessage(response, "Não foi possível abrir o relatório."));
        return response.json() as Promise<QuizReportRecord>;
      })
      .then(result => {
        if (controller.signal.aborted) return;
        if (result?.graph_id !== graphId || result.topic_id !== topicId || result.attempt?.id !== selectedId || result.format_version !== 1 || !result.report || !Array.isArray(result.reviews)) {
          throw new Error("O relatório recebido não corresponde à tentativa selecionada.");
        }
        setSelected(result);
      })
      .catch(reason => { if (!controller.signal.aborted) setDetailError(reason instanceof Error ? reason.message : "Falha ao abrir relatório."); })
      .finally(() => { if (!controller.signal.aborted) setDetailLoading(false); });
    return () => controller.abort();
  }, [base, graphId, topicId, selectedId, detailRevision]);

  return <Modal id="quiz-report-history" title="Histórico de relatórios" description={topicTitle}
    closeLabel="Fechar histórico" onClose={onClose} size="study">
    {selectedId ? <div className="studyHistoryDetail">
      <button type="button" className="studyLink" onClick={() => { setSelectedId(null); setPdfError(null); setPdfLoading(false); }}>← Voltar às tentativas</button>
      {detailLoading ? <p role="status">Carregando relatório…</p> : null}
      {detailError ? <div role="alert" className="studyHistoryError">{detailError} <button type="button" className="studyLink" onClick={() => setDetailRevision(value => value + 1)}>Tentar novamente</button></div> : null}
      {selected?.attempt.id === selectedId && selected.graph_id === graphId && selected.topic_id === topicId ? <>
        {!selected.in_current_graph ? <p className="studyHistoryNotice">Esta tentativa foi retirada do estado atual por uma restauração do grafo. O relatório original foi preservado para auditoria.</p> : null}
        <div className="studyHistoryExport">
          <button type="button" disabled={pdfLoading} onClick={() => { void downloadPDF(); }}>
            {pdfLoading ? "Exportando PDF…" : "Baixar relatório em PDF"}
          </button>
          {pdfError ? <p role="alert" className="studyHistoryError">{pdfError}</p> : null}
        </div>
        <StudyReport report={selected.report} reviews={selected.reviews} />
      </> : null}
    </div> : <div className="studyHistoryList">
      <p className="studyHistoryIntro">Relatórios de questionários já enviados. Tentativas concluídas ficam disponíveis mesmo após fechar o questionário.</p>
      {loading ? <p role="status">Carregando histórico…</p> : null}
      {error ? <div role="alert" className="studyHistoryError">{error} <button type="button" className="studyLink" onClick={() => setRevision(value => value + 1)}>Tentar novamente</button></div> : null}
      {!loading && !error && page?.total === 0 ? <p>Nenhuma avaliação registrada para este tópico.</p> : null}
      {!loading && !error ? <ul className="studyHistoryItems">{page?.items.map(item => <li key={item.attempt_id}>
        <button type="button" className="studyHistoryItem" onClick={() => setSelectedId(item.attempt_id)}>
          <span><strong>{Math.round(item.score * 100)}% · {new Date(item.created_at).toLocaleString("pt-BR")}</strong>
            <small>{item.question_count} questões · {item.in_current_graph ? "Tentativa registrada" : "Tentativa anterior à restauração"}</small></span>
          <span aria-hidden="true">→</span>
        </button>
      </li>)}</ul> : null}
      {!loading && !error && page && page.total > PAGE_SIZE ? <nav className="studyHistoryPager" aria-label="Páginas do histórico">
        <button type="button" disabled={offset === 0} onClick={() => setOffset(value => Math.max(0, value - PAGE_SIZE))}>Anterior</button>
        <span>{Math.floor(offset / PAGE_SIZE) + 1} de {Math.ceil(page.total / PAGE_SIZE)}</span>
        <button type="button" disabled={offset + PAGE_SIZE >= page.total} onClick={() => setOffset(value => value + PAGE_SIZE)}>Próxima</button>
      </nav> : null}
    </div>}
  </Modal>;
}
