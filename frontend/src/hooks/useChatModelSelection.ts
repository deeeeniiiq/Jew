import { useCallback, useMemo, useState, type Dispatch, type SetStateAction } from "react";
import type { ChatGPTModel, WorkspaceConfig } from "../lib/types";

export function resolveChatGPTModel(explicit: string | null, defaultModel: string | null | undefined, models: ChatGPTModel[]): string | null {
  return explicit ?? defaultModel ?? models.find((item) => item.isDefault)?.model ?? null;
}
type Provider = WorkspaceConfig["agent_backend"];
const storageKey = (provider: Provider, graphId: string) => `jew_agent_model_v1:${provider}:${graphId}`;
const legacyKey = (graphId: string) => `clew_chatgpt_model_v1:${graphId}`;
function storedModel(provider: Provider, graphId: string): string | null {
  if (!graphId) return null;
  try {
    const existing = localStorage.getItem(storageKey(provider, graphId));
    if (existing !== null) return existing;
    if (provider !== "chatgpt") return null;
    const legacy = localStorage.getItem(legacyKey(graphId));
    if (legacy !== null) localStorage.setItem(storageKey(provider, graphId), legacy);
    return legacy;
  } catch { return null; }
}
export function useChatModelSelection(config: WorkspaceConfig | null, graphId: string | null, models: ChatGPTModel[], provider: Provider = config?.agent_backend ?? "ruflo_native"): {
  chatModelOptions: string[]; selectedChatModel: string | null; setSelectedChatModel: Dispatch<SetStateAction<string | null>>;
} {
  const [selections, setSelections] = useState<Record<string, string | null>>({});
  const key = graphId ? `${provider}:${graphId}` : "";
  const explicit = Object.prototype.hasOwnProperty.call(selections, key) ? selections[key] : storedModel(provider, graphId ?? "");
  // Ruflo commands are deterministic, but ordinary lessons/quizzes in this
  // combined mode select a locally installed Ollama model.
  const selectedChatModel = resolveChatGPTModel(explicit, config?.default_model, models);
  const chatModelOptions = useMemo(() => Array.from(new Set([...(selectedChatModel ? [selectedChatModel] : []), ...models.map((item) => item.model)])), [models, selectedChatModel]);
  const setSelectedChatModel: Dispatch<SetStateAction<string | null>> = useCallback((value) => {
    if (!key || !graphId) return;
    setSelections((current) => {
      const previous = Object.prototype.hasOwnProperty.call(current, key) ? current[key] : storedModel(provider, graphId);
      const next = typeof value === "function" ? value(resolveChatGPTModel(previous, config?.default_model, models)) : value;
      try {
        if (next) localStorage.setItem(storageKey(provider, graphId), next);
        else {
          localStorage.removeItem(storageKey(provider, graphId));
          // Clearing a migrated preference must not resurrect it from legacy storage.
          if (provider === "chatgpt") localStorage.removeItem(legacyKey(graphId));
        }
      } catch { /* Optional UI preference. */ }
      return { ...current, [key]: next };
    });
  }, [key, graphId, provider, config?.default_model, models]);
  // Model choices persist per provider and graph, including legacy ChatGPT choices.
  // An unavailable explicit choice remains visible and is rejected by the server.
  return { chatModelOptions, selectedChatModel, setSelectedChatModel };
}
