import React from "react";
import type { ChatGPTAccountController } from "../hooks/useChatGPTAccount";
import type { SettingsDrafts, SettingsDraftSetters } from "../lib/appContracts";
import { API_BASE } from "../lib/api";
import { apiFetch, readErrorMessage } from "../lib/apiRequest";
import type { ChatGPTModel, ReasoningEffort, WorkspaceConfig } from "../lib/types";
import { SectionHead } from "./SettingsSection";
import { ChatGPTAccountPanel } from "./ChatGPTAccountPanel";

const EFFORTS: ReasoningEffort[] = ["none", "minimal", "low", "medium", "high", "xhigh"];

export function AgentProviderPanel({ chatgpt, drafts, setDrafts, savedProvider, savedRufloEnabled }: {
  chatgpt: ChatGPTAccountController;
  drafts: SettingsDrafts;
  setDrafts: SettingsDraftSetters;
  savedProvider: WorkspaceConfig["agent_backend"] | null;
  savedRufloEnabled: boolean;
}): React.JSX.Element {
  const [models, setModels] = React.useState<ChatGPTModel[]>([]);
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [key, setKey] = React.useState("");
  const [keyStatus, setKeyStatus] = React.useState<{ configured: boolean; source: string | null; editable: boolean } | null>(null);
  const [codexStatus, setCodexStatus] = React.useState<{ installed: boolean; authenticated: boolean; method: string | null } | null>(null);
  const [rufloStatus, setRufloStatus] = React.useState<{ enabled: boolean; connected: boolean; message?: string } | null>(null);
  const [refreshId, refresh] = React.useReducer((count: number) => count + 1, 0);
  const provider = drafts.agentBackend;
  const pendingSave = provider !== savedProvider;
  const pendingRufloSave = drafts.rufloEnabled !== savedRufloEnabled;
  const native = provider === "ruflo_native";
  const savedNative = savedProvider === "ruflo_native";

  React.useEffect(() => {
    if (provider === "chatgpt") void chatgpt.refresh();
  }, [provider, chatgpt.refresh]);

  React.useEffect(() => {
    if ((!savedRufloEnabled && !savedNative) || (pendingRufloSave && !savedNative)) { setRufloStatus(null); return; }
    let active = true;
    void apiFetch(`${API_BASE}/api/v1/agent/ruflo/status`)
      .then(async (response) => {
        if (!response.ok) throw new Error(await readErrorMessage(response, `HTTP ${response.status}`));
        return response.json() as Promise<{ enabled: boolean; connected: boolean; message?: string }>;
      })
      .then((status) => { if (active) setRufloStatus(status); })
      .catch(() => { if (active) setRufloStatus({ enabled: true, connected: false, message: "Ruflo status unavailable." }); });
    return () => { active = false; };
  }, [savedRufloEnabled, savedNative, pendingRufloSave, refreshId]);

  React.useEffect(() => {
    if (pendingSave || provider === "chatgpt") return;
    let active = true;
    setError(null);
    void apiFetch(`${API_BASE}/api/v1/agent/models`)
      .then(async (response) => {
        if (!response.ok) throw new Error(await readErrorMessage(response, `HTTP ${response.status}`));
        return response.json() as Promise<{ provider: string; models: ChatGPTModel[] }>;
      })
      .then((result) => { if (active && result.provider === provider) setModels(result.models); })
      .catch((caught: unknown) => { if (active) { setModels([]); setError(caught instanceof Error ? caught.message : "Model catalog unavailable"); } });
    return () => { active = false; };
  }, [provider, pendingSave, native, refreshId]);

  React.useEffect(() => {
    if (provider !== "codex_cli") return;
    let active = true;
    void apiFetch(`${API_BASE}/api/v1/agent/codex-status`)
      .then(async (res) => {
        if (!res.ok) throw new Error(`Codex status HTTP ${res.status}`);
        return res.json() as Promise<{ installed: boolean; authenticated: boolean; method: string | null }>;
      })
      .then((status) => { if (active) setCodexStatus(status); })
      .catch(() => { if (active) setCodexStatus(null); });
    return () => { active = false; };
  }, [provider, refreshId]);

  React.useEffect(() => {
    if (provider !== "openai_api") return;
    let active = true;
    void apiFetch(`${API_BASE}/api/v1/agent/openai-key`)
      .then((res) => res.json() as Promise<{ configured: boolean; source: string | null; editable: boolean }>)
      .then((status) => { if (active) setKeyStatus(status); })
      .catch(() => { if (active) setKeyStatus(null); });
    return () => { active = false; };
  }, [provider, refreshId]);

  async function saveKey(): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      const response = await apiFetch(`${API_BASE}/api/v1/agent/openai-key`, {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key }),
      });
      if (!response.ok) throw new Error(await readErrorMessage(response, `HTTP ${response.status}`));
      setKeyStatus(await response.json() as typeof keyStatus);
      setKey("");
      refresh();
      window.dispatchEvent(new Event("jew-agent-refresh"));
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Could not save API key"); }
    finally { setBusy(false); }
  }

  async function removeKey(): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      const response = await apiFetch(`${API_BASE}/api/v1/agent/openai-key`, { method: "DELETE" });
      if (!response.ok) throw new Error(await readErrorMessage(response, `HTTP ${response.status}`));
      setKeyStatus(await response.json() as typeof keyStatus);
      refresh();
      window.dispatchEvent(new Event("jew-agent-refresh"));
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Could not remove API key"); }
    finally { setBusy(false); }
  }

  return <>
    <section className="stSection">
      <SectionHead eyebrow="Execution mode" title="Jew backend" />
      <label className="uiField">
        <span className="uiLabel">Provider</span>
        <select className="uiSelect" value={provider} onChange={(event) => {
          setDrafts.agentBackend(event.target.value as WorkspaceConfig["agent_backend"]);
          setDrafts.model("");
          setDrafts.reasoningEffort("");
        }}>
          <option value="ruflo_native">Ruflo + Ollama · Free local lessons and quizzes</option>
          <option value="ollama">Ollama · Local (free)</option>
          <option value="codex_cli">ChatGPT via Codex · No API credits</option>
          <option value="openai_api">OpenAI API · Pay as you go</option>
          <option value="chatgpt">ChatGPT · Direct plan sharing</option>
        </select>
      </label>
      {pendingSave ? <p className="uiHelp" role="status">Save settings to activate the selected mode.</p> : null}
    </section>
    {native ? <section className="stSection">
      <SectionHead eyebrow="Local AI" title="Ruflo + Ollama" action={<button className="uiButton uiButtonQuiet uiButtonSmall" type="button" disabled={pendingSave} onClick={refresh}>Refresh models</button>} />
      <p className="uiHelp">Lessons, explanations and AI quizzes run on your own computer with Ollama. No ChatGPT login, API key, credits or plan quota is required. Ruflo commands still work using <code>/ruflo</code>; type <code>/help</code> to list them.</p>
      <p className="uiHelp">Install Ollama from <a href="https://ollama.com/download/windows" target="_blank" rel="noreferrer">ollama.com/download/windows</a>, then in CMD run <code>ollama pull qwen3.5:4b</code> (or download another compatible model). Keep Ollama running and refresh models. A local model uses your computer's RAM, CPU and power.</p>
      {error ? <div className="inlineNotice inlineNoticeError" role="alert">{error}</div> : models.length === 0 && !pendingSave ? <p className="uiHelp" role="status">No local models found. Start Ollama and pull a model, then refresh.</p> : null}
      <label className="uiField"><span className="uiLabel">Local model for lessons and quizzes</span>
        <select className="uiSelect" disabled={pendingSave || !models.length} value={drafts.model} onChange={(event) => setDrafts.model(event.target.value)}>
          <option value="">First available local model</option>
          {drafts.model && !models.some((item) => item.model === drafts.model) ? <option value={drafts.model}>{drafts.model} · unavailable</option> : null}
          {models.map((item) => <option key={item.id} value={item.model}>{item.displayName}</option>)}
        </select>
      </label>
      <p className="uiHelp">Optional Ruflo tools: <code>npm install -g ruflo@3.59.17</code>. No AI provider is contacted when you run a /ruflo command.</p>
    </section> : provider === "chatgpt" ? <ChatGPTAccountPanel chatgpt={chatgpt} drafts={drafts} setDrafts={setDrafts} /> :
      <section className="stSection">
        <SectionHead eyebrow="AI connection" title={provider === "ollama" ? "Local Ollama" : provider === "codex_cli" ? "ChatGPT via Codex CLI" : "OpenAI API"}
          action={<button className="uiButton uiButtonQuiet uiButtonSmall" type="button" disabled={pendingSave} onClick={refresh}>Refresh models</button>} />
        {provider === "ollama" ? <p className="uiHelp">Run Ollama locally and download a model that supports tool calls. No ChatGPT sign-in or subscription is needed.</p> : provider === "codex_cli" ? <>
          <p className="uiHelp">Uses the official Codex CLI as an intermediary and signs in to your ChatGPT plan. Does not use or charge an OpenAI API key. ChatGPT plan limits still apply.</p>
          <p className="uiHelp" role="status">{codexStatus === null ? "Checking Codex CLI status…" : codexStatus.authenticated ? "Connected via ChatGPT account" : codexStatus.installed ? "Sign in to Codex using a ChatGPT account" : "Codex CLI is not installed"}</p>
          <p className="uiHelp">{codexStatus?.installed ? "In Windows CMD, run: codex login (select Sign in with ChatGPT), then Refresh models." : "In Windows CMD, run: npm install -g @openai/codex, then codex login."}</p>
          <p className="uiHelp">Choose Automatic to use a model that your Codex login can access. A model shown in ChatGPT Web (including GPT-6 Sol Web) is not necessarily available through Codex CLI. Account limits and eligibility apply.</p>
        </> : <>
          <p className="uiHelp">API billing is separate from ChatGPT subscriptions. Keys are encrypted with Windows DPAPI and are never displayed after saving.</p>
          <p className="uiHelp" role="status">{keyStatus?.configured ? `Key configured (${keyStatus.source})` : "No API key configured"}</p>
          {keyStatus?.editable !== false ? <div className="stFieldPair">
            <label className="uiField"><span className="uiLabel">OpenAI API key</span>
              <input className="uiInput" type="password" autoComplete="off" spellCheck={false} value={key} onChange={(e) => setKey(e.currentTarget.value)} placeholder="sk-…" />
            </label>
            <div><button type="button" className="uiButton uiButtonSmall" disabled={busy || !key.trim()} onClick={() => void saveKey()}>Verify & save</button>
              {keyStatus?.source === "windows" ? <button type="button" className="uiButton uiButtonQuiet uiButtonSmall" disabled={busy} onClick={() => void removeKey()}>Remove key</button> : null}</div>
          </div> : <p className="uiHelp">Use the OPENAI_API_KEY environment variable on this system.</p>}
        </>}
        {error ? <div className="inlineNotice inlineNoticeError" role="alert">{error}</div> : null}
        <div className="stFieldPair">
          <label className="uiField"><span className="uiLabel">Model</span>
            <select className="uiSelect" disabled={pendingSave || !models.length} value={drafts.model} onChange={(event) => setDrafts.model(event.target.value)}>
              <option value="">First available model</option>
              {drafts.model && !models.some((item) => item.model === drafts.model) ? <option value={drafts.model}>{drafts.model} · unavailable</option> : null}
              {models.map((item) => <option key={item.id} value={item.model}>{item.displayName}</option>)}
            </select>
          </label>
          {provider === "openai_api" ? <label className="uiField"><span className="uiLabel">Reasoning</span>
            <select className="uiSelect" value={drafts.reasoningEffort} onChange={(event) => setDrafts.reasoningEffort(event.target.value as ReasoningEffort | "")}>
              <option value="">Model default</option>{EFFORTS.map((effort) => <option key={effort} value={effort}>{effort}</option>)}
            </select>
          </label> : null}
        </div>
      </section>}
    <section className="stSection">
      <SectionHead eyebrow="Optional orchestration" title="Ruflo MCP" action={
        <button type="button" className="uiButton uiButtonQuiet uiButtonSmall" onClick={refresh}>Check connection</button>
      } />
      {!native ? <><label className="uiField">
        <span className="uiLabel">Use Ruflo alongside your selected AI provider</span>
        <input type="checkbox" checked={drafts.rufloEnabled} onChange={(e) => setDrafts.rufloEnabled(e.target.checked)} />
      </label>
      <p className="uiHelp">Ruflo supplies optional MCP swarm and memory tools. Jew keeps the selected model provider for AI answers. Ruflo does not launch a separate Claude, Llama, or Ollama model.</p></> : null}
      {(native || drafts.rufloEnabled) ? <>
        <p className="uiHelp" role="status">{pendingSave || (pendingRufloSave && !native) ? "Save settings to activate Ruflo MCP." : rufloStatus?.connected ? "Ruflo MCP connected" : rufloStatus?.message ?? "Checking Ruflo MCP…"}</p>
        <p className="uiHelp">In Windows CMD, run <code>npm install -g ruflo@3.59.17</code>. Save settings to activate Ruflo MCP. Ruflo starts only when enabled.</p>
      </> : null}
    </section>
  </>;
}
