import React, { useState } from "react";
import type { LearnerLevel, LearnerProfile } from "../../lib/types";

const PROFESSIONS = [
  "Engenharia de Software", "Desenvolvimento Front-end", "Desenvolvimento Back-end",
  "Desenvolvimento Full Stack", "Engenharia de Dados", "Inteligência Artificial",
  "Ciência de Dados", "Cibersegurança", "DevOps", "Design de Produto",
  "UX / UI Design", "Biologia", "Medicina e Saúde", "Engenharia Civil",
  "Engenharia Elétrica", "Engenharia Mecânica", "Química", "Física",
  "Matemática", "Administração", "Marketing", "Finanças",
  "Direito", "Educação", "Psicologia", "Arquitetura",
  "Produção de Conteúdo", "Empreendedorismo", "Estudante", "Outra área",
];
const INTERESTS = [
  "Programação", "Pesquisa científica", "Automação", "IA e aprendizado de máquina",
  "Dados", "Projetos práticos", "Design", "Redes e infraestrutura",
  "Empreendedorismo", "Idiomas", "Saúde", "Sustentabilidade",
];
const LEARNING_PREFERENCES = ["Exemplos práticos", "Leitura guiada", "Vídeos", "Exercícios", "Projetos", "Revisões curtas"];

export const EMPTY_LEARNER_PROFILE: LearnerProfile = {
  display_name: "", profession: "", interests: [], level: "beginner",
  goal: "", study_hours_per_week: 0, learning_preferences: [],
  github: "", instagram: "", onboarding_complete: false,
};

// The original workspace starts with a demo graph. Snapshot 1 still represents a new profile.
export function needsLearnerOnboarding(profile: LearnerProfile, snapshotId: number): boolean {
  return !profile.onboarding_complete && snapshotId === 1;
}

type Props = {
  profile: LearnerProfile;
  onSave: (profile: LearnerProfile) => Promise<void>;
  onClose?: () => void;
};

export function LearnerOnboarding({ profile, onSave, onClose }: Props): React.JSX.Element {
  const [draft, setDraft] = useState<LearnerProfile>(profile);
  const [customProfession, setCustomProfession] = useState(
    profile.profession && !PROFESSIONS.includes(profile.profession) ? profile.profession : "",
  );
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isCustom = draft.profession === "Outra área" || Boolean(customProfession);

  async function submit(event: React.FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const profession = (isCustom ? customProfession : draft.profession).trim();
    if (!profession) { setError("Escolha sua área ou descreva sua profissão."); return; }
    setError(null);
    setPending(true);
    try {
      await onSave({ ...draft, profession, onboarding_complete: true });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível salvar seu perfil.");
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="jewOnboarding" aria-labelledby="jew-onboard-title">
      <div className="jewOnboardingIntro">
        <span className="jewEyebrow">JEW / SEU PONTO DE PARTIDA</span>
        <h1 id="jew-onboard-title">Toda jornada começa <em>em algum lugar.</em></h1>
        <p>Conte um pouco sobre sua área. O JEW usará suas escolhas para sugerir caminhos de estudo e adaptar cada roadmap.</p>
        <div className="jewStepTrack"><span className="isActive">01 · Você</span><span>02 · Seu tema</span><span>03 · Seu caminho</span></div>
      </div>
      <form className="jewOnboardingForm" onSubmit={(event) => { void submit(event); }}>
        <div className="jewFormSectionTitle"><div><span>01 / ÁREA</span><h2>O que você faz ou quer aprender?</h2></div><small>Escolha uma opção</small></div>
        <div className="jewProfessionGrid" role="group" aria-label="Áreas e profissões">
          {PROFESSIONS.map((profession) => (
            <button key={profession} type="button" className={`jewProfession ${draft.profession === profession ? "isSelected" : ""}`}
              aria-pressed={draft.profession === profession}
              onClick={() => { setDraft((value) => ({ ...value, profession })); if (profession !== "Outra área") setCustomProfession(""); }}>
              <span>{profession}</span><span aria-hidden="true">{draft.profession === profession ? "●" : "○"}</span>
            </button>
          ))}
        </div>
        {isCustom && <label className="jewField jewFullField">Sua área / profissão
          <input maxLength={120} value={customProfession} onChange={(event) => setCustomProfession(event.target.value)} placeholder="Ex.: Oceanografia" />
        </label>}

        <div className="jewFormSectionTitle jewSectionGap"><div><span>02 / CONTEXTO</span><h2>Personalize sua jornada</h2></div><small>Você poderá editar depois</small></div>
        <div className="jewFormGrid">
          <label className="jewField">Seu nome (opcional)
            <input maxLength={100} value={draft.display_name} onChange={(event) => setDraft((value) => ({ ...value, display_name: event.target.value }))} placeholder="Como podemos chamar você?" />
          </label>
          <label className="jewField">Seu nível atual
            <select value={draft.level} onChange={(event) => setDraft((value) => ({ ...value, level: event.target.value as LearnerLevel }))}>
              <option value="beginner">Iniciante · começando agora</option>
              <option value="intermediate">Intermediário · já tenho base</option>
              <option value="advanced">Avançado · quero me aprofundar</option>
            </select>
          </label>
          <label className="jewField jewFullField">Qual é seu objetivo?
            <textarea rows={2} maxLength={400} value={draft.goal} onChange={(event) => setDraft((value) => ({ ...value, goal: event.target.value }))} placeholder="Ex.: quero trabalhar com IA, criar um projeto ou me preparar para uma prova" />
          </label>
          <label className="jewField">Horas de estudo por semana (estimativa)
            <input type="number" min={0} max={80} step={1} value={draft.study_hours_per_week ?? 0}
              onChange={(event) => setDraft((value) => ({ ...value, study_hours_per_week: Number(event.target.value) }))} />
          </label>
          <div className="jewField jewFullField"><span>Como você prefere aprender?</span>
            <div className="jewInterestChips" role="group" aria-label="Preferências de aprendizagem">
              {LEARNING_PREFERENCES.map((preference) => {
                const selected = (draft.learning_preferences ?? []).includes(preference);
                return <button key={preference} type="button" aria-pressed={selected} className={selected ? "isSelected" : ""}
                  onClick={() => setDraft((value) => ({ ...value, learning_preferences: selected
                    ? (value.learning_preferences ?? []).filter((item) => item !== preference)
                    : [...(value.learning_preferences ?? []), preference] }))}>
                  {selected ? "✓ " : "+ "}{preference}
                </button>;
              })}
            </div>
          </div>
          <div className="jewFullField jewField"><span>Assuntos de interesse (até 12)</span>
            <div className="jewInterestChips" role="group" aria-label="Interesses">
              {INTERESTS.map((interest) => {
                const selected = draft.interests.includes(interest);
                return <button key={interest} type="button" aria-pressed={selected} className={selected ? "isSelected" : ""}
                  onClick={() => setDraft((value) => ({ ...value, interests: selected ? value.interests.filter((item) => item !== interest) : [...value.interests, interest].slice(0, 12) }))}>
                  {selected ? "✓ " : "+ "}{interest}
                </button>;
              })}
            </div>
          </div>
          <label className="jewField">GitHub (opcional)
            <input maxLength={240} value={draft.github} onChange={(event) => setDraft((value) => ({ ...value, github: event.target.value }))} placeholder="Seu usuário do GitHub" autoComplete="off" />
          </label>
          <label className="jewField">Instagram (opcional)
            <input maxLength={240} value={draft.instagram} onChange={(event) => setDraft((value) => ({ ...value, instagram: event.target.value }))} placeholder="Seu @ do Instagram" autoComplete="off" />
          </label>
        </div>
        {error && <p className="jewInlineError" role="alert">{error}</p>}
        <div className="jewFormActions">{onClose && <button type="button" className="jewTextButton" onClick={onClose}>Cancelar</button>}
          <button type="submit" className="jewPrimaryButton" disabled={pending}>{pending ? "Salvando perfil…" : "Salvar e continuar →"}</button>
        </div>
      </form>
    </section>
  );
}
