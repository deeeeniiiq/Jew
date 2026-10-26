import React from "react";
import { ArrowLeft, BookOpenText, CaretDown, FloppyDisk, MagnifyingGlass, X } from "@phosphor-icons/react";

import type { AppCopy } from "../lib/appCopy";
import { safeExternalUrl } from "../lib/appUiHelpers";
import type { GraphEnvelope, LearningPlan, Topic } from "../lib/types";
import { AssistantMarkdown } from "./assistant/AssistantMarkdown";
import { LearningGuidance } from "./LearningGuidance";

type Props = {
  graph: GraphEnvelope;
  topic: Topic;
  onSelectTopic: (id: string) => void;
  onClose: () => void;
  onSaveNote: (id: string, markdown: string) => Promise<void>;
  onAddResource: () => void;
  onAddArtifact: () => void;
  onGenerateLesson: () => Promise<void>;
  lessonLoading: boolean;
  lessonError: string | null;
  lessonSuccess: string | null;
  onStartQuiz: () => Promise<void>;
  onMarkFinished: () => Promise<void>;
  onOpenQuizHistory: () => void;
  canComplete: boolean;
  completionEnabled: boolean;
  quizLoading: boolean;
  quizError: string | null;
  quizSuccess: string | null;
  learningPlan: LearningPlan | null;
  topicTitlesById: Map<string, string>;
  copy: AppCopy;
};

function NotePane({ topic, graph, onSaveNote, onClose }: {
  topic: Topic;
  graph: GraphEnvelope;
  onSaveNote: Props["onSaveNote"];
  onClose?: () => void;
}): React.JSX.Element {
  const [draft, setDraft] = React.useState(topic.note_markdown ?? "");
  const [preview, setPreview] = React.useState(false);
  const [status, setStatus] = React.useState<"saved" | "editing" | "saving" | "error">("saved");
  const lastSaved = React.useRef(topic.note_markdown ?? "");
  const draftRef = React.useRef(draft);
  const saving = React.useRef<Promise<void>>(Promise.resolve());
  const onSaveRef = React.useRef(onSaveNote);
  onSaveRef.current = onSaveNote;
  draftRef.current = draft;

  const save = React.useCallback((value: string) => {
    if (value === lastSaved.current) return saving.current;
    setStatus("saving");
    const next = saving.current.catch(() => undefined).then(async () => {
      await onSaveRef.current(topic.id, value);
      lastSaved.current = value;
      setStatus(draftRef.current === value ? "saved" : "editing");
    }).catch(() => { setStatus("error"); });
    saving.current = next;
    return next;
  }, [topic.id]);

  React.useEffect(() => {
    if (draft === lastSaved.current) return;
    const timer = window.setTimeout(() => { void save(draft); }, 1000);
    return () => window.clearTimeout(timer);
  }, [draft, save]);

  React.useEffect(() => () => { void save(draftRef.current); }, [save]);

  const incoming = graph.edges.filter((edge) => edge.target_topic_id === topic.id && edge.relation === "requires")
    .map((edge) => graph.topics.find((item) => item.id === edge.source_topic_id)?.title).filter(Boolean);
  const related = topic.resources.map((resource) => ({ resource, safeUrl: safeExternalUrl(resource.url) }))
    .filter((item): item is { resource: typeof topic.resources[number]; safeUrl: string } => Boolean(item.safeUrl));

  return <section className="knowledgePane" aria-label={`Nota: ${topic.title}`}>
    <div className="knowledgeTabbar">
      <span className="knowledgeTab"><BookOpenText size={14} />{topic.title}</span>
      {onClose ? <button type="button" onClick={onClose} aria-label="Fechar painel secundário"><X size={14} /></button> : null}
    </div>
    <div className="knowledgePaneToolbar">
      <span>{graph.title} <span className="knowledgeBreadcrumbSep">/</span> {topic.title}</span>
      <span className="knowledgePaneActions">
        <span role="status" className={status === "error" ? "knowledgeError" : ""}>
          {status === "saved" ? "Salvo" : status === "editing" ? "Alterações pendentes" : status === "saving" ? "Salvando…" : "Erro ao salvar"}
        </span>
        <button type="button" onClick={() => void save(draft)} title="Salvar nota" aria-label="Salvar nota"><FloppyDisk size={15} /></button>
        <button type="button" onClick={() => setPreview((value) => !value)}>{preview ? "Editar" : "Prévia"}</button>
      </span>
    </div>
    <div className="knowledgeDocument">
      <div className="knowledgeKicker">TÓPICO · {topic.state.replaceAll("_", " ")}</div>
      <h1>{topic.title}</h1>
      <div className="knowledgeProperties">
        <div><span>Objetivo</span><strong>{topic.description || "Defina o objetivo deste tópico em suas notas."}</strong></div>
        <div><span>Etapa</span><strong>{topic.level + 1}</strong></div>
        <div><span>Pré-requisitos</span><strong>{incoming.length ? incoming.join(" · ") : "Nenhum"}</strong></div>
      </div>
      <div className="knowledgeSectionLabel">MINHAS ANOTAÇÕES · MARKDOWN</div>
      {preview ? <div className="knowledgePreview">
        {draft.trim() ? <AssistantMarkdown content={draft} /> : <p>Escreva na aba de edição para ver a prévia.</p>}
      </div> : <textarea
        className="knowledgeEditor"
        aria-label={`Anotações de ${topic.title}`}
        value={draft}
        onChange={(event) => { setDraft(event.target.value); setStatus("editing"); }}
        onKeyDown={(event) => {
          if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
            event.preventDefault();
            void save(draft);
          }
        }}
        onBlur={() => void save(draft)}
        placeholder={"Comece a escrever…\n\n## O que aprendi\n\nUse Markdown para títulos, listas, código e links."}
        spellCheck
      />}
      {related.length ? <section className="knowledgeReferences"><h2>Fontes deste tópico</h2>
        {related.map(({ resource, safeUrl }) => <a key={resource.id} href={safeUrl} target="_blank" rel="noopener noreferrer">{resource.label} ↗</a>)}
      </section> : null}
      {topic.artifacts.length ? <section className="knowledgeMaterials"><h2>Materiais e aulas</h2>
        {[...topic.artifacts].reverse().map((artifact) => <details key={artifact.id}>
          <summary>{artifact.title} <small>{artifact.kind}</small></summary>
          <div className="knowledgeMaterialBody"><AssistantMarkdown content={artifact.body} /></div>
        </details>)}
      </section> : null}
    </div>
  </section>;
}

export function KnowledgeWorkspace({ graph, topic, onSelectTopic, onClose, onSaveNote, onAddResource, onAddArtifact,
  onGenerateLesson, lessonLoading, lessonError, lessonSuccess, onStartQuiz, onMarkFinished,
  onOpenQuizHistory, canComplete, completionEnabled, quizLoading, quizError, quizSuccess,
  learningPlan, topicTitlesById, copy }: Props): React.JSX.Element {
  const [query, setQuery] = React.useState("");
  const [secondId, setSecondId] = React.useState<string | null>(() =>
    graph.edges.find((edge) => edge.source_topic_id === topic.id)?.target_topic_id
      ?? graph.topics.find((item) => item.id !== topic.id)?.id
      ?? null);
  const [sidebarOpen, setSidebarOpen] = React.useState(true);
  const [inspectorOpen, setInspectorOpen] = React.useState(() => typeof window === "undefined" || window.innerWidth > 1100);
  const secondTopic = graph.topics.find((item) => item.id === secondId && item.id !== topic.id) ?? null;
  const matching = graph.topics.filter((item) => item.title.toLocaleLowerCase().includes(query.toLocaleLowerCase()));
  const backlinkTopics = graph.topics.filter((item) => item.id !== topic.id &&
    ((item.note_markdown ?? "").includes(`[[${topic.title}]]`) || (item.note_markdown ?? "").includes(`[[${topic.id}]]`)));
  const prereqs = graph.edges.filter((edge) => edge.target_topic_id === topic.id && edge.relation === "requires")
    .map((edge) => graph.topics.find((item) => item.id === edge.source_topic_id)).filter((item): item is Topic => Boolean(item));

  return <div className="knowledgeWorkspace">
    <div className="knowledgeRail" aria-label="Controles do espaço de estudo">
      <button type="button" title="Voltar ao roadmap" aria-label="Voltar ao roadmap" onClick={onClose}><ArrowLeft size={18} /></button>
      <button type="button" title="Mostrar ou ocultar biblioteca" aria-label="Mostrar ou ocultar biblioteca" onClick={() => setSidebarOpen((value) => !value)}><BookOpenText size={18} /></button>
      <button type="button" title="Mostrar ou ocultar relações" aria-label="Mostrar ou ocultar relações" onClick={() => setInspectorOpen((value) => !value)}><CaretDown size={18} /></button>
    </div>
    {sidebarOpen ? <nav className="knowledgeTree" aria-label="Tópicos do roadmap">
      <div className="knowledgeTreeHead"><span>BIBLIOTECA</span><button type="button" onClick={onClose}>Mapa ↗</button></div>
      <div className="knowledgeTreeTitle">{graph.title}</div>
      <label className="knowledgeSearch"><MagnifyingGlass size={14} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Buscar tópico" aria-label="Buscar tópico" /></label>
      <div className="knowledgeTreeList">
        {matching.map((item) => <button key={item.id} type="button" className={item.id === topic.id ? "active" : ""} onClick={() => onSelectTopic(item.id)}>
          <span className="knowledgeTreeDot" data-state={item.state} />{item.title}
        </button>)}
        {!matching.length ? <p>Nenhum tópico encontrado.</p> : null}
      </div>
      <div className="knowledgeTreeFoot">{graph.topics.length} tópicos · {graph.edges.length} conexões</div>
    </nav> : null}
    <main className="knowledgeEditors">
      <div className="knowledgeWorkspaceBar"><span>JEW <span className="knowledgeBreadcrumbSep">/</span> {graph.title}</span>
        <div><label className="knowledgeSecondSelect">Abrir ao lado <select value={secondId ?? ""} onChange={(event) => setSecondId(event.target.value || null)} aria-label="Abrir tópico ao lado">
          <option value="">Escolher tópico…</option>
          {graph.topics.filter((item) => item.id !== topic.id).map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
        </select></label><button type="button" onClick={onClose}>Ver roadmap</button></div>
      </div>
      <div className={`knowledgePaneGrid ${secondTopic ? "knowledgePaneGridSplit" : ""}`}>
        <NotePane key={`${graph.graph_id}:${topic.id}`} topic={topic} graph={graph} onSaveNote={onSaveNote} />
        {secondTopic ? <NotePane key={`${graph.graph_id}:${secondTopic.id}`} topic={secondTopic} graph={graph} onSaveNote={onSaveNote} onClose={() => setSecondId(null)} /> : null}
      </div>
    </main>
    {inspectorOpen ? <aside className="knowledgeInspector" aria-label="Relações do tópico">
      <div className="knowledgeInspectorHeader">CONTEXTO</div>
      <div className="knowledgeInspectorSection knowledgeActions"><h2>Estudar este tópico</h2>
        <button type="button" onClick={onAddResource}>+ Adicionar fonte</button>
        <button type="button" onClick={onAddArtifact}>+ Adicionar material</button>
        <button type="button" onClick={() => void onGenerateLesson()} disabled={lessonLoading}>{lessonLoading ? "Gerando aula…" : "Gerar aula com IA local"}</button>
        {lessonError ? <p role="alert" className="knowledgeError">{lessonError}</p> : null}
        {lessonSuccess ? <p role="status">{lessonSuccess}</p> : null}
      </div>
      <div className="knowledgeInspectorSection"><h2>Pré-requisitos <span>{prereqs.length}</span></h2>
        {prereqs.length ? prereqs.map((item) => <button key={item.id} type="button" onClick={() => onSelectTopic(item.id)}>{item.title}</button>) : <p>Este tópico inicia a trilha.</p>}
      </div>
      <div className="knowledgeInspectorSection"><h2>Backlinks <span>{backlinkTopics.length}</span></h2>
        {backlinkTopics.length ? backlinkTopics.map((item) => <button key={item.id} type="button" onClick={() => onSelectTopic(item.id)}>{item.title}</button>) : <p>Use [[{topic.title}]] em outra nota para criar um vínculo.</p>}
      </div>
      <div className="knowledgeInspectorSection knowledgeActions"><h2>Progresso</h2>
        <button type="button" disabled={quizLoading || !canComplete} onClick={() => void (completionEnabled ? onStartQuiz() : onMarkFinished())}>
          {quizLoading ? "Preparando…" : completionEnabled ? "Fazer avaliação" : "Marcar como estudado"}
        </button>
        {!canComplete ? <p>{completionEnabled ? "Conclua os pré-requisitos antes da avaliação." : "Tópico já concluído."}</p> : null}
        <button type="button" onClick={onOpenQuizHistory}>Ver avaliações anteriores</button>
        {quizError ? <p role="alert" className="knowledgeError">{quizError}</p> : null}
        {quizSuccess ? <p role="status">{quizSuccess}</p> : null}
      </div>
      <div className="knowledgeInspectorSection"><LearningGuidance plan={learningPlan} topicId={topic.id} titles={topicTitlesById} copy={copy} /></div>
      <div className="knowledgeInspectorGraph"><div>VISÃO DO ROADMAP</div>
        <svg viewBox="0 0 240 190" role="img" aria-label={`${graph.topics.length} tópicos e ${graph.edges.length} conexões`}>
          {(() => {
            const visible = graph.topics.slice(0, 28);
            const positions = new Map(visible.map((item, index) => [item.id, { x: 18 + (index % 5) * 49, y: 25 + Math.floor(index / 5) * 31 }]));
            return <>
              {graph.edges.filter((edge) => positions.has(edge.source_topic_id) && positions.has(edge.target_topic_id)).map((edge) => {
                const a = positions.get(edge.source_topic_id)!; const b = positions.get(edge.target_topic_id)!;
                return <line key={edge.id} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#4b4b4b" strokeWidth="1" />;
              })}
              {visible.map((item) => { const point = positions.get(item.id)!; return <circle key={item.id} cx={point.x} cy={point.y} r={item.id === topic.id ? 5 : 3} fill={item.id === topic.id ? "#d9ad45" : "#858585"} />; })}
            </>;
          })()}
        </svg>
      </div>
    </aside> : null}
  </div>;
}
