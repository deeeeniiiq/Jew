import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import type { GraphEnvelope } from "../lib/types";
import { APP_COPY } from "../lib/appCopy";
import { KnowledgeWorkspace } from "./KnowledgeWorkspace";

const graph: GraphEnvelope = {
  graph_id: "test", subject: "computing", title: "Computação", language: "en", version: 1,
  topics: [
    { id: "first", title: "Algoritmos", slug: "algoritmos", description: "Resolver problemas", difficulty: 1,
      estimated_minutes: 60, level: 0, state: "learning", zones: [], resources: [], artifacts: [], note_markdown: "# Minha nota" },
    { id: "second", title: "Estruturas de Dados", slug: "estruturas", description: "Organizar dados", difficulty: 2,
      estimated_minutes: 90, level: 1, state: "not_started", zones: [], resources: [], artifacts: [] },
  ],
  edges: [{ id: "e1", source_topic_id: "first", target_topic_id: "second", relation: "requires", rationale: "" }],
  zones: [], quiz_attempts: [], metadata: {},
};

describe("knowledge workspace", () => {
  it("opens real topic notes and actions without the old topic popover", () => {
    const html = renderToStaticMarkup(<KnowledgeWorkspace
      graph={graph} topic={graph.topics[0]} onSelectTopic={vi.fn()} onClose={vi.fn()}
      onSaveNote={vi.fn().mockResolvedValue(undefined)} onAddResource={vi.fn()} onAddArtifact={vi.fn()}
      onGenerateLesson={vi.fn().mockResolvedValue(undefined)} lessonLoading={false} lessonError={null} lessonSuccess={null}
      onStartQuiz={vi.fn().mockResolvedValue(undefined)} onMarkFinished={vi.fn().mockResolvedValue(undefined)}
      onOpenQuizHistory={vi.fn()} canComplete completionEnabled quizLoading={false} quizError={null} quizSuccess={null}
      learningPlan={null} topicTitlesById={new Map()} copy={APP_COPY}
    />);
    expect(html).toContain('aria-label="Anotações de Algoritmos"');
    expect(html).toContain("Minha nota");
    expect(html).toContain("Estruturas de Dados");
    expect(html).toContain("Gerar aula com IA local");
    expect(html).toContain("Fazer avaliação");
    expect(html).not.toContain("topicPopover");
  });
});
