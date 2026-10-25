import React, { useLayoutEffect, useRef, useState } from "react";
import type { RoadmapPreview as RoadmapPreviewData, RoadmapTopic } from "../../lib/types";

const PHASES = ["Fundamentos", "Primeiros passos", "Construindo a base", "Aplicação", "Prática avançada", "Projeto final"];

function duration(minutes: number): string {
  return minutes >= 60 ? `${Math.round(minutes / 60 * 10) / 10} h` : `${minutes} min`;
}

function safeSource(url: string): boolean {
  try { return new URL(url).protocol === "https:"; } catch { return false; }
}

const SOURCE_KIND = { encyclopedia: "Enciclopédia", research: "Pesquisa acadêmica", book: "Catálogo de livros" };

type Connection = { key: string; path: string };

function usePrerequisiteConnections(topics: RoadmapTopic[]) {
  const flowRef = useRef<HTMLDivElement>(null);
  const [layout, setLayout] = useState<{ width: number; height: number; edges: Connection[] }>({
    width: 0, height: 0, edges: [],
  });

  useLayoutEffect(() => {
    const flow = flowRef.current;
    if (!flow) return;
    let frame = 0;
    const measure = () => {
      const bounds = flow.getBoundingClientRect();
      const nodes = new Map<number, DOMRect>();
      flow.querySelectorAll<HTMLElement>(".jewMapNode[data-topic-index]").forEach((node) => {
        nodes.set(Number(node.dataset.topicIndex), node.getBoundingClientRect());
      });
      const edges: Connection[] = [];
      topics.forEach((topic, index) => {
        const target = nodes.get(index);
        if (!target) return;
        topic.prerequisites.forEach((prerequisite) => {
          const source = nodes.get(prerequisite);
          if (!source || prerequisite >= index) return;
          const sideBySide = Math.abs(source.top - target.top) < 18 && source.right < target.left;
          const x1 = (sideBySide ? source.right : source.left + source.width / 2) - bounds.left;
          const y1 = (sideBySide ? source.top + source.height / 2 : source.bottom) - bounds.top;
          const x2 = (sideBySide ? target.left : target.left + target.width / 2) - bounds.left;
          const y2 = (sideBySide ? target.top + target.height / 2 : target.top) - bounds.top;
          const midpoint = sideBySide ? (x1 + x2) / 2 : (y1 + y2) / 2;
          const path = sideBySide
            ? `M ${x1} ${y1} C ${midpoint} ${y1}, ${midpoint} ${y2}, ${x2} ${y2}`
            : `M ${x1} ${y1} C ${x1} ${midpoint}, ${x2} ${midpoint}, ${x2} ${y2}`;
          edges.push({ key: `${prerequisite}-${index}`, path });
        });
      });
      setLayout({ width: flow.clientWidth, height: flow.scrollHeight, edges });
    };
    const schedule = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(measure);
    };
    const observer = new ResizeObserver(schedule);
    observer.observe(flow);
    flow.querySelectorAll(".jewMapNode").forEach((node) => observer.observe(node));
    window.addEventListener("resize", schedule);
    schedule();
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("resize", schedule);
    };
  }, [topics]);
  return { flowRef, layout };
}

function TopicCard({ topic, index, topics }: { topic: RoadmapTopic; index: number; topics: RoadmapTopic[] }): React.JSX.Element {
  return (
    <article className="jewMapNode" id={`jew-roadmap-topic-${index}`} data-topic-index={index}>
      <div className="jewMapNodeHead"><span className="jewMapIndex">{String(index + 1).padStart(2, "0")}</span>
        <span className="jewMapDuration">◷ {duration(topic.estimated_minutes)}</span></div>
      <h4>{topic.title}</h4>
      <p>{topic.description}</p>
      <div className="jewMapOutcome"><span>↗ Você vai conseguir</span>{topic.outcome}</div>
      {topic.prerequisites.length > 0 && <div className="jewMapPrereqs">↳ Antes: {topic.prerequisites.map((id) => (
        <a key={id} href={`#jew-roadmap-topic-${id}`} title={`Ir para o pré-requisito ${topics[id]?.title ?? id}`}>
          {String(id + 1).padStart(2, "0")} · {topics[id]?.title ?? "Tópico anterior"}
        </a>
      ))}</div>}
      {topic.resources.length > 0 && <div className="jewMapResources">
        {topic.resources.filter((source) => safeSource(source.url)).map((source) => (
          <a key={source.url} target="_blank" rel="noopener noreferrer" href={source.url} title={source.url}>
            <small>{SOURCE_KIND[source.kind ?? "encyclopedia"]}</small>↗ {source.label}
          </a>
        ))}
      </div>}
    </article>
  );
}

export function RoadmapPreview({ preview }: { preview: RoadmapPreviewData }): React.JSX.Element {
  const { flowRef, layout } = usePrerequisiteConnections(preview.topics);
  const stages = Array.from(new Set(preview.topics.map((topic) => topic.stage))).sort((a, b) => a - b);
  const totalMinutes = preview.topics.reduce((sum, topic) => sum + topic.estimated_minutes, 0);
  const sourceCount = preview.topics.reduce((sum, topic) => sum + topic.resources.length, 0);
  return (
    <section aria-labelledby="jew-map-title" className="jewRoadmapResult">
      <div className="jewResultHeading">
        <div><span className="jewEyebrow">MAPA DE APRENDIZAGEM · PRÉVIA</span>
          <h2 id="jew-map-title">{preview.title}</h2><p>{preview.description}</p></div>
        <div className="jewResultStats"><span><b>{preview.topics.length}</b> tópicos</span><span><b>{duration(totalMinutes)}</b> estimadas</span><span><b>{sourceCount}</b> fontes</span></div>
      </div>
      {preview.resource_search_status !== "available" && (
        <p className="jewSourceNotice">{preview.resource_search_status === "limited"
          ? "Algumas fontes não puderam ser consultadas. Confira os links disponíveis antes de estudar."
          : "A pesquisa externa está indisponível neste momento. Os tópicos foram gerados localmente, sem fontes verificadas."}</p>
      )}
      <div className="jewMapFlow" ref={flowRef}>
        {layout.edges.length > 0 && <svg className="jewMapConnectionLayer" aria-hidden="true"
          width={layout.width} height={layout.height} viewBox={`0 0 ${layout.width} ${layout.height}`}>
          <defs><marker id="jew-roadmap-arrow" viewBox="0 0 10 10" refX="8" refY="5"
            markerWidth="5" markerHeight="5" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--jew-green)" />
          </marker></defs>
          {layout.edges.map((edge) => <path key={edge.key} d={edge.path}
            fill="none" stroke="var(--jew-green)" strokeWidth="2" strokeOpacity=".66"
            markerEnd="url(#jew-roadmap-arrow)" />)}
        </svg>}
        {stages.map((stage) => (
          <div className="jewMapStage" key={stage}>
            <div className="jewMapStageLabel"><span className="jewStageDot" /><small>ETAPA {String(stage + 1).padStart(2, "0")}</small>
              <h3>{PHASES[stage] ?? `Etapa ${stage + 1}`}</h3></div>
            <div className="jewMapStageNodes">{preview.topics.map((topic, index) => topic.stage === stage ? (
              <TopicCard topic={topic} index={index} topics={preview.topics} key={`${index}-${topic.title}`} />
            ) : null)}</div>
          </div>
        ))}
      </div>
      <p className="jewPreviewFootnote">As ligações indicam a sequência de aprendizagem. Ao criar o roadmap, os tópicos, as dependências e os materiais serão salvos em um grafo editável no JEW.</p>
    </section>
  );
}
