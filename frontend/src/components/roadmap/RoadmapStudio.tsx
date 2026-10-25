import React, { useEffect, useMemo, useRef, useState } from "react";
import { API_BASE } from "../../lib/api";
import { apiFetch, readErrorMessage } from "../../lib/apiRequest";
import type { LearnerProfile, RoadmapGenerateRequest, RoadmapLanguage, RoadmapPreviewResponse, WorkspaceEnvelope } from "../../lib/types";
import { RoadmapPreview } from "./RoadmapPreview";

type Props = {
  profile: LearnerProfile;
  onClose: () => void;
  onEditProfile: () => void;
  onCreated: (workspace: WorkspaceEnvelope) => Promise<void>;
};

function suggestedTopics(profile: LearnerProfile): string[] {
  const choices = [
    ...profile.interests.map((interest) => `${interest}: do zero a um projeto prático`),
    profile.profession ? `Fundamentos essenciais de ${profile.profession}` : "Como começar na programação",
    profile.profession ? `Projetos e competências para ${profile.profession}` : "Aprender inteligência artificial do zero",
    profile.goal ? `Plano de estudos para: ${profile.goal.slice(0, 85)}` : "Métodos de estudo e aprendizagem eficaz",
  ];
  return [...new Set(choices)].slice(0, 6);
}

function socialUrl(value: string, provider: "github" | "instagram"): string | null {
  const cleaned = value.trim();
  if (!cleaned) return null;
  try {
    const isUrl = /^https?:\/\//i.test(cleaned);
    const username = isUrl ? new URL(cleaned).pathname.replace(/^\//, "").replace(/\/$/, "") : cleaned.replace(/^@/, "");
    const validName = provider === "github"
      ? /^(?!-)[A-Za-z0-9-]{1,39}(?<!-)$/.test(username)
      : /^[A-Za-z0-9._]{1,30}$/.test(username);
    if (!validName) return null;
    if (isUrl) {
      const parsed = new URL(cleaned);
      const host = provider === "github" ? "github.com" : "instagram.com";
      if (parsed.protocol !== "https:" || ![host, `www.${host}`].includes(parsed.hostname)
        || parsed.username || parsed.password || parsed.search || parsed.hash || parsed.port) return null;
    }
    return `https://${provider}.com/${username}`;
  } catch { return null; }
}

export function RoadmapStudio({ profile, onClose, onEditProfile, onCreated }: Props): React.JSX.Element {
  const [topic, setTopic] = useState("");
  const [goal, setGoal] = useState(profile.goal);
  const [language, setLanguage] = useState<RoadmapLanguage>("pt");
  const [result, setResult] = useState<RoadmapPreviewResponse | null>(null);
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const suggestions = useMemo(() => suggestedTopics(profile), [profile]);

  useEffect(() => () => { abortRef.current?.abort(); }, []);

  async function generate(event?: React.FormEvent<HTMLFormElement>): Promise<void> {
    event?.preventDefault();
    if (topic.trim().length < 2 || generating || saving) return;
    setGenerating(true);
    setError(null);
    setResult(null);
    const controller = new AbortController();
    abortRef.current = controller;
    const request: RoadmapGenerateRequest = {
      topic: topic.trim(), profession: profile.profession, level: profile.level,
      goal: goal.trim(), language,
    };
    try {
      const response = await apiFetch(`${API_BASE}/api/v1/roadmaps/preview`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request), signal: controller.signal,
      });
      if (!response.ok) throw new Error(await readErrorMessage(response, "Falha ao criar a prévia."));
      setResult((await response.json()) as RoadmapPreviewResponse);
    } catch (cause) {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "Erro ao gerar o roadmap.");
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      setGenerating(false);
    }
  }

  async function confirm(): Promise<void> {
    if (!result || saving) return;
    setSaving(true);
    setError(null);
    try {
      const response = await apiFetch(`${API_BASE}/api/v1/roadmaps/confirm`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticket: result.ticket }),
      });
      if (!response.ok) throw new Error(await readErrorMessage(response, "Não foi possível salvar o roadmap."));
      await onCreated((await response.json()) as WorkspaceEnvelope);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível confirmar o roadmap.");
    } finally { setSaving(false); }
  }

  const githubUrl = socialUrl(profile.github, "github");
  const instagramUrl = socialUrl(profile.instagram, "instagram");
  return (
    <section className="jewRoadmapStudio" aria-labelledby="jew-studio-title">
      <div className="jewStudioHero">
        <div className="jewStudioHeroText"><span className="jewEyebrow">JEW / ROADMAP STUDIO</span>
          <h1 id="jew-studio-title">Um objetivo. <em>Um caminho claro.</em></h1>
          <p>Escolha qualquer assunto. A IA local organiza etapas, pré-requisitos e uma trilha que você poderá transformar em aulas, exercícios e quizzes.</p>
          <div className="jewStudioBadges"><span>◈ Ollama local</span><span>↗ Fontes externas identificadas</span><span>◇ Progresso salvo</span></div>
        </div>
        <aside className="jewStudioIdentity">
          <span className="jewEyebrow">SEU PERFIL</span><strong>{profile.display_name || "Explorador(a)"}</strong>
          <p>{profile.profession || "Área de estudo aberta"}</p>
          <span>{profile.level === "beginner" ? "Iniciante" : profile.level === "intermediate" ? "Intermediário" : "Avançado"}</span>
          <div className="jewIdentityLinks">
            {githubUrl && <a href={githubUrl} rel="noopener noreferrer" target="_blank">↗ GitHub</a>}
            {instagramUrl && <a href={instagramUrl} rel="noopener noreferrer" target="_blank">↗ Instagram</a>}
            <button type="button" onClick={onEditProfile}>Editar perfil ↗</button>
          </div>
        </aside>
      </div>

      {!result ? <div className="jewStudioBody">
        <section className="jewSuggestions"><div className="jewFormSectionTitle"><div><span>01 / IDEIAS PARA VOCÊ</span><h2>Por onde começar?</h2></div></div>
          <p>Sugestões iniciais a partir da sua área, interesses e objetivo. Você também pode escrever qualquer tema.</p>
          <div className="jewSuggestionList">{suggestions.map((suggestion, index) => (
            <button type="button" key={suggestion} onClick={() => { setTopic(suggestion); setError(null); }} aria-pressed={topic === suggestion}
              className={topic === suggestion ? "isSelected" : ""}>
              <span className="jewSuggestionNumber">0{index + 1}</span><span>{suggestion}</span><span aria-hidden="true">↗</span>
            </button>
          ))}</div>
        </section>
        <form className="jewStudioPrompt" onSubmit={(event) => { void generate(event); }}>
          <div className="jewFormSectionTitle"><div><span>02 / SEU ROADMAP</span><h2>O que vamos aprender?</h2></div></div>
          <label className="jewField">Tema livre
            <input required minLength={2} maxLength={180} autoFocus value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="Ex.: Biologia molecular, React, Astronomia…" />
          </label>
          <label className="jewField">Resultado que você deseja alcançar
            <textarea rows={4} maxLength={400} value={goal} onChange={(event) => setGoal(event.target.value)} placeholder="Quero entender a teoria e conseguir criar um projeto." />
          </label>
          <label className="jewField">Idioma do conteúdo
            <select value={language} onChange={(event) => setLanguage(event.target.value as RoadmapLanguage)}>
              <option value="pt">Português</option><option value="en">English</option><option value="ru">Русский</option><option value="uk">Українська</option>
            </select>
          </label>
          <div className="jewEnergyNote"><span aria-hidden="true">◉</span><p><strong>Consumo consciente:</strong> o JEW ativa o Ollama apenas quando necessário, pede para descarregar o modelo ao terminar e encerra somente servidores que ele próprio iniciou.</p></div>
          {generating && <div role="status" className="jewGenerating"><span className="jewLoadingOrb" />Organizando os tópicos e consultando fontes…</div>}
          {error && <p className="jewInlineError" role="alert">{error}</p>}
          <button className="jewPrimaryButton jewGenerateButton" type="submit" disabled={generating || topic.trim().length < 2}>{generating ? "Criando sua trilha…" : "✦ Gerar meu roadmap"}</button>
        </form>
      </div> : <>
        <div className="jewPreviewToolbar"><button type="button" className="jewTextButton" onClick={() => { setResult(null); setError(null); }}>← Ajustar tema</button>
          <div><span>Confira a prévia antes de criar o grafo.</span><button type="button" className="jewPrimaryButton" disabled={saving} onClick={() => { void confirm(); }}>{saving ? "Salvando…" : "✓ Criar roadmap e começar"}</button></div>
        </div>
        {error && <p className="jewInlineError" role="alert">{error}</p>}
        <RoadmapPreview preview={result.preview} />
        <div className="jewPreviewBottom"><button type="button" className="jewPrimaryButton" disabled={saving} onClick={() => { void confirm(); }}>{saving ? "Salvando…" : "Criar este roadmap →"}</button></div>
      </>}
      <footer className="jewStudioFooter"><span>JEW · Aprendizagem conectada</span><button type="button" className="jewTextButton" onClick={() => { abortRef.current?.abort(); onClose(); }}>Voltar ao workspace ×</button></footer>
    </section>
  );
}
