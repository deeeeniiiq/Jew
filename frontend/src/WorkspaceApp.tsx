import type { ChatGPTAccountController } from "./hooks/useChatGPTAccount";
import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { AppDialogs } from "./components/AppDialogs";
import { DebugLogsModal } from "./components/DebugLogsModal";
import { SettingsModal } from "./components/SettingsModal";
import { WorkspaceShell } from "./components/WorkspaceShell";
import { LearnerOnboarding, EMPTY_LEARNER_PROFILE, needsLearnerOnboarding } from "./components/roadmap/LearnerOnboarding";
import { RoadmapStudio } from "./components/roadmap/RoadmapStudio";
import { StudyReportHistory } from "./components/study/StudyReportHistory";
import { ClewLoader } from "./components/ClewLoader";
import { API_BASE } from "./lib/api";
import { APP_COPY } from "./lib/appCopy";
import { setDebugModeEnabled } from "./lib/debugLogs";
import {
  ASSISTANT_COLLAPSE_THRESHOLD,
  ASSISTANT_MAX_WIDTH,
  ASSISTANT_MIN_WIDTH,
  type AuthSessionPayload,
  type WorkspaceSurfacePayload,
} from "./lib/appContracts";
import { COMPACT_TOP_OVERLAY_THRESHOLD } from "./lib/appStatePersistence";
import { apiFetch, readErrorMessage } from "./lib/apiRequest";
import { type ManualLayoutPositions, readManualLayoutPositions } from "./lib/appUiHelpers";
import {
  buildFallbackAssessment,
  computeClosureStatus,
  computeFocusData,
  computeGraphSummary,
  firstProposedTopicId,
  templatePrompt,
} from "./lib/graph";
import { supportsObsidianDirectoryExport, writeObsidianExportPackageToDirectory } from "./lib/obsidianExport";
import {
  buildObsidianImportPreview,
  type ObsidianImportOptions,
  type ObsidianVaultEntry,
} from "./lib/obsidianImport";
import { useChatModelSelection } from "./hooks/useChatModelSelection";
import { useGraphChatController } from "./hooks/useGraphChatController";
import { useWorkspaceSettings } from "./hooks/useWorkspaceSettings";
import { useWorkspaceChromeState } from "./hooks/useWorkspaceChromeState";
import { useTopicPopover } from "./hooks/useTopicPopover";
import { useModalAccessibility } from "./lib/useModalAccessibility";
import type {
  Artifact,
  CreateGraphRequest,
  GraphEnvelope,
  GraphAssessment,
  LearningPlan,
  GraphExportFormat,
  GraphExportPackagePayload,
  ObsidianExportOptions,
  ObsidianGraphExportPackagePayload,
  ProposalGenerateResponse,
  QuizQuestionReview,
  QuizPedagogicalReport,
  QuizStartResponse,
  QuizSubmitResponse,
  DebugLogSnapshot,
  ChatGPTModel,
  SnapshotRecord,
  LearnerProfile,
  TopicQuizSession,
  WorkspaceEnvelope,
} from "./lib/types";

const ACTIVE_GRAPH_STORAGE_KEY = "knowledge_graph_active_graph_v1";

function defaultObsidianExportOptions(): ObsidianExportOptions {
  return {
    use_folders_as_zones: true,
    include_descriptions: true,
    include_resources: true,
    include_artifacts: true,
  };
}

export default function WorkspaceApp({ chatgpt }: { chatgpt: ChatGPTAccountController }): React.JSX.Element {
  const copy = APP_COPY;
  const [data, setData] = useState<WorkspaceEnvelope | null>(null);
  const [learnerProfile, setLearnerProfile] = useState<LearnerProfile>(EMPTY_LEARNER_PROFILE);
  const [onboardingOpen, setOnboardingOpen] = useState(false);
  const [roadmapStudioOpen, setRoadmapStudioOpen] = useState(false);
  const [providerCatalog, setProviderCatalog] = useState<{ provider: string; models: ChatGPTModel[] } | null>(null);
  const [providerRefresh, setProviderRefresh] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [projectsExpanded, setProjectsExpanded] = useState(true);
  const [snapshots, setSnapshots] = useState<SnapshotRecord[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [assessment, setAssessment] = useState<GraphAssessment | null>(null);
  const [assessmentError, setAssessmentError] = useState<string | null>(null);
  const [createGraphDraft, setCreateGraphDraft] = useState<CreateGraphRequest>({
    title: "",
    subject: "",
    language: "en",
    description: "",
  });
  const [createGraphOpen, setCreateGraphOpen] = useState(false);
  const [createGraphLoading, setCreateGraphLoading] = useState(false);
  const [createGraphError, setCreateGraphError] = useState<string | null>(null);
  const [importGraphOpen, setImportGraphOpen] = useState(false);
  const [importGraphLoading, setImportGraphLoading] = useState(false);
  const [importGraphError, setImportGraphError] = useState<string | null>(null);
  const [importGraphFileName, setImportGraphFileName] = useState<string | null>(null);
  const [importGraphPayload, setImportGraphPayload] = useState<GraphExportPackagePayload | null>(null);
  const [importGraphTitleDraft, setImportGraphTitleDraft] = useState("");
  const [importGraphIncludeProgressDraft, setImportGraphIncludeProgressDraft] = useState(true);
  const [importObsidianOpen, setImportObsidianOpen] = useState(false);
  const [importObsidianLoading, setImportObsidianLoading] = useState(false);
  const [importObsidianError, setImportObsidianError] = useState<string | null>(null);
  const [obsidianVaultName, setObsidianVaultName] = useState<string | null>(null);
  const [obsidianVaultEntries, setObsidianVaultEntries] = useState<ObsidianVaultEntry[] | null>(null);
  const [obsidianImportDraft, setObsidianImportDraft] = useState<Omit<ObsidianImportOptions, "vaultName">>({
    graphTitle: "",
    subject: "",
    language: "en",
    relation: "bridges",
    useFoldersAsZones: true,
    autofillDescriptions: true,
    createArtifactsFromNotes: false,
    createPlaceholderTopics: false,
  });
  const [exportGraphTarget, setExportGraphTarget] = useState<GraphEnvelope | null>(null);
  const [exportGraphLoading, setExportGraphLoading] = useState(false);
  const [exportGraphError, setExportGraphError] = useState<string | null>(null);
  const [exportGraphTitleDraft, setExportGraphTitleDraft] = useState("");
  const [exportGraphIncludeProgressDraft, setExportGraphIncludeProgressDraft] = useState(true);
  const [exportGraphFormatDraft, setExportGraphFormatDraft] = useState<GraphExportFormat>("mapmind_graph_export");
  const [exportGraphObsidianOptionsDraft, setExportGraphObsidianOptionsDraft] = useState<ObsidianExportOptions>(defaultObsidianExportOptions);
  const [deleteConfirm, setDeleteConfirm] = useState<{ graphId: string; title: string } | null>(null);
  const [sessionDeleteConfirm, setSessionDeleteConfirm] = useState<{ sessionId: string; title: string } | null>(null);
  const [graphLayoutEditing, setGraphLayoutEditing] = useState(false);
  const [graphLayoutDraft, setGraphLayoutDraft] = useState<ManualLayoutPositions | null>(null);
  const [graphLayoutSaving, setGraphLayoutSaving] = useState(false);
  const [renamingGraphId, setRenamingGraphId] = useState<string | null>(null);
  const [renameGraphDraft, setRenameGraphDraft] = useState("");
  const [renameGraphSaving, setRenameGraphSaving] = useState(false);
  const [activeGraphId, setActiveGraphId] = useState<string | null>(() => {
    try {
      const raw = localStorage.getItem(ACTIVE_GRAPH_STORAGE_KEY);
      return raw && raw.trim() ? raw : null;
    } catch {
      return null;
    }
  });
  const [applyLoadingMessageId, setApplyLoadingMessageId] = useState<string | null>(null);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [assistantResizing, setAssistantResizing] = useState(false);
  const [configSaving, setConfigSaving] = useState(false);
  const [learningPlan, setLearningPlan] = useState<LearningPlan | null>(null);
  const [quizSession, setQuizSession] = useState<TopicQuizSession | null>(null);
  const [quizAnswers, setQuizAnswers] = useState<Record<string, number>>({});
  const [quizLoading, setQuizLoading] = useState(false);
  const [quizError, setQuizError] = useState<string | null>(null);
  const [quizSuccess, setQuizSuccess] = useState<string | null>(null);
  const [quizReviews, setQuizReviews] = useState<QuizQuestionReview[] | null>(null);
  const [quizReport, setQuizReport] = useState<QuizPedagogicalReport | null>(null);
  const [reportHistoryTarget, setReportHistoryTarget] = useState<{
    graphId: string;
    topicId: string;
    topicTitle: string;
  } | null>(null);
  const [lessonLoading, setLessonLoading] = useState(false);
  const [lessonError, setLessonError] = useState<string | null>(null);
  const [lessonSuccess, setLessonSuccess] = useState<string | null>(null);
  const [workspaceSurface, setWorkspaceSurface] = useState<WorkspaceSurfacePayload | null>(null);
  const [debugLogs, setDebugLogs] = useState<DebugLogSnapshot | null>(null);
  const [debugLogsLoading, setDebugLogsLoading] = useState(false);
  const [debugLogsError, setDebugLogsError] = useState<string | null>(null);
  const {
    assistantWidth,
    setAssistantWidth,
    isMobileViewport,
    viewportWidth,
    leftSidebarOpen,
    setLeftSidebarOpen,
    leftSidebarClosing,
    setLeftSidebarClosing,
    mobileMenuOpen,
    setMobileMenuOpen,
    isSettingsOpen,
    setSettingsOpen,
    isLogsOpen,
    setLogsOpen,
    viewportCenteredZoom,
    setViewportCenteredZoom,
    straightEdgeLinesEnabled,
    setStraightEdgeLinesEnabled,
    initialThemeMode,
    themeModeDraft,
    setThemeModeDraft,
  } = useWorkspaceChromeState();
  const graphShellRef = useRef<HTMLDivElement | null>(null);
  const deleteGraphModalRef = useRef<HTMLDivElement | null>(null);
  const deleteGraphCancelButtonRef = useRef<HTMLButtonElement | null>(null);
  const sessionDeleteModalRef = useRef<HTMLDivElement | null>(null);
  const sessionDeleteCancelButtonRef = useRef<HTMLButtonElement | null>(null);
  const createGraphModalRef = useRef<HTMLDivElement | null>(null);
  const createGraphTitleInputRef = useRef<HTMLInputElement | null>(null);
  const importGraphModalRef = useRef<HTMLDivElement | null>(null);
  const importGraphFileButtonRef = useRef<HTMLButtonElement | null>(null);
  const importObsidianModalRef = useRef<HTMLDivElement | null>(null);
  const importObsidianFolderButtonRef = useRef<HTMLButtonElement | null>(null);
  const exportGraphModalRef = useRef<HTMLDivElement | null>(null);
  const exportGraphTitleInputRef = useRef<HTMLInputElement | null>(null);
  const importGraphFileInputRef = useRef<HTMLInputElement | null>(null);
  const importObsidianFolderInputRef = useRef<HTMLInputElement | null>(null);
  const quizModalRef = useRef<HTMLDivElement | null>(null);
  const quizCloseButtonRef = useRef<HTMLButtonElement | null>(null);
  const quizRequestRef = useRef(0);
  const lessonRequestRef = useRef(0);
  const chatViewportRef = useRef<HTMLDivElement | null>(null);
  const chatComposerRef = useRef<HTMLTextAreaElement | null>(null);
  const sessionListRef = useRef<HTMLDivElement | null>(null);
  const sessionListWrapRef = useRef<HTMLDivElement | null>(null);
  const floatingStatsRef = useRef<HTMLDivElement | null>(null);
  const sessionDragRef = useRef<{ startX: number; scrollLeft: number } | null>(null);
  const bootstrapStartedRef = useRef(false);
  const [bootstrapRevision, setBootstrapRevision] = useState(0);
  const debugLogsInFlightRef = useRef(false);
  const sidebarCloseTimerRef = useRef<number | null>(null);
  const closeDeleteGraphModal = useCallback(() => setDeleteConfirm(null), []);
  const closeSessionDeleteModal = useCallback(() => setSessionDeleteConfirm(null), []);
  const closeCreateGraphModal = useCallback(() => {
    setCreateGraphOpen(false);
    setCreateGraphError(null);
  }, []);
  const closeImportGraphModal = useCallback(() => {
    setImportGraphOpen(false);
    setImportGraphError(null);
    setImportGraphPayload(null);
    setImportGraphFileName(null);
    setImportGraphTitleDraft("");
    setImportGraphIncludeProgressDraft(true);
  }, []);
  const closeImportObsidianModal = useCallback(() => {
    setImportObsidianOpen(false);
    setImportObsidianError(null);
    setImportObsidianLoading(false);
    setObsidianVaultName(null);
    setObsidianVaultEntries(null);
    setObsidianImportDraft({
      graphTitle: "",
      subject: "",
      language: "en",
      relation: "bridges",
      useFoldersAsZones: true,
      autofillDescriptions: true,
      createArtifactsFromNotes: false,
      createPlaceholderTopics: false,
    });
  }, []);
  const closeExportGraphModal = useCallback(() => {
    setExportGraphTarget(null);
    setExportGraphError(null);
    setExportGraphLoading(false);
    setExportGraphTitleDraft("");
    setExportGraphIncludeProgressDraft(true);
    setExportGraphFormatDraft("mapmind_graph_export");
    setExportGraphObsidianOptionsDraft(defaultObsidianExportOptions());
  }, []);
  const openImportGraphModal = useCallback(() => {
    setCreateGraphOpen(false);
    setImportGraphOpen(true);
    setImportGraphError(null);
  }, []);
  const openImportObsidianModal = useCallback(() => {
    setCreateGraphOpen(false);
    setImportObsidianOpen(true);
    setImportObsidianError(null);
  }, []);
  const openExportGraphModal = useCallback((graph: GraphEnvelope) => {
    setExportGraphTarget(graph);
    setExportGraphTitleDraft(graph.title);
    setExportGraphIncludeProgressDraft(true);
    setExportGraphFormatDraft("mapmind_graph_export");
    setExportGraphObsidianOptionsDraft(defaultObsidianExportOptions());
    setExportGraphError(null);
  }, []);
  const closeQuizModal = useCallback(() => {
    quizRequestRef.current += 1;
    setQuizLoading(false);
    setQuizSession(null);
    setQuizReport(null);
    setQuizError(null);
  }, []);

  useModalAccessibility({
    isOpen: Boolean(deleteConfirm),
    modalRef: deleteGraphModalRef,
    onClose: closeDeleteGraphModal,
    initialFocusRef: deleteGraphCancelButtonRef,
  });
  useModalAccessibility({
    isOpen: Boolean(sessionDeleteConfirm),
    modalRef: sessionDeleteModalRef,
    onClose: closeSessionDeleteModal,
    initialFocusRef: sessionDeleteCancelButtonRef,
  });
  useModalAccessibility({
    isOpen: createGraphOpen,
    modalRef: createGraphModalRef,
    onClose: closeCreateGraphModal,
    initialFocusRef: createGraphTitleInputRef,
  });
  useModalAccessibility({
    isOpen: importGraphOpen,
    modalRef: importGraphModalRef,
    onClose: closeImportGraphModal,
    initialFocusRef: importGraphFileButtonRef,
  });
  useModalAccessibility({
    isOpen: importObsidianOpen,
    modalRef: importObsidianModalRef,
    onClose: closeImportObsidianModal,
    initialFocusRef: importObsidianFolderButtonRef,
  });
  useModalAccessibility({
    isOpen: Boolean(exportGraphTarget),
    modalRef: exportGraphModalRef,
    onClose: closeExportGraphModal,
    initialFocusRef: exportGraphTitleInputRef,
  });
  useModalAccessibility({
    isOpen: Boolean(quizSession),
    modalRef: quizModalRef,
    // Escape follows the StudyWorkspace close button's save-before-exit path.
    onClose: () => { if (quizCloseButtonRef.current) quizCloseButtonRef.current.click(); else closeQuizModal(); },
    initialFocusRef: quizCloseButtonRef,
  });

  useEffect(() => {
    try {
      if (activeGraphId) {
        localStorage.setItem(ACTIVE_GRAPH_STORAGE_KEY, activeGraphId);
      } else {
        localStorage.removeItem(ACTIVE_GRAPH_STORAGE_KEY);
      }
    } catch {
      // Ignore localStorage write failures.
    }
  }, [activeGraphId]);

  useEffect(() => {
    const input = importObsidianFolderInputRef.current;
    if (!input) return;
    input.setAttribute("webkitdirectory", "");
    input.setAttribute("directory", "");
    input.multiple = true;
  }, [importObsidianOpen]);

  useEffect(() => {
    if (bootstrapStartedRef.current) return;
    bootstrapStartedRef.current = true;
    async function load(): Promise<void> {
      setLoading(true);
      setError(null);
      try {
        const payload = await fetchWorkspace();
        setData(payload);
        const profile = payload.workspace.learner_profile ?? EMPTY_LEARNER_PROFILE;
        setLearnerProfile(profile);
        setOnboardingOpen(needsLearnerOnboarding(profile, payload.snapshot.id));
        const fallbackGraphId = payload.workspace.active_graph_id ?? payload.workspace.graphs[0]?.graph_id ?? null;
        setActiveGraphId((previous) => previous ?? fallbackGraphId);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : copy.errors.loadWorkspace);
      } finally {
        setLoading(false);
      }
    }
    void load();
    void loadSnapshots();
  }, [bootstrapRevision]);

  const obsidianImportPreview = useMemo(() => {
    if (!obsidianVaultEntries || !obsidianVaultName) return null;
    return buildObsidianImportPreview(obsidianVaultEntries, {
      vaultName: obsidianVaultName,
      ...obsidianImportDraft,
    });
  }, [obsidianImportDraft, obsidianVaultEntries, obsidianVaultName]);

  useEffect(() => {
    return () => {
      if (sidebarCloseTimerRef.current) {
        window.clearTimeout(sidebarCloseTimerRef.current);
      }
    };
  }, []);

  const availableGraphs = useMemo(() => data?.workspace.graphs ?? [], [data]);
  const activeGraph = useMemo(
    () => availableGraphs.find((graph) => graph.graph_id === activeGraphId) ?? availableGraphs[0] ?? null,
    [activeGraphId, availableGraphs],
  );
  const activeGraphManualLayout = useMemo(() => readManualLayoutPositions(activeGraph), [activeGraph]);
  const {
    selectedTopicId,
    setSelectedTopicId,
    selectedTopicAnchor,
    setSelectedTopicAnchor,
    selectedTopic,
    popoverPosition,
    topicPopoverRef,
    popoverDragRef,
    handleSelectedTopicAnchorChange,
    handleSelectTopic,
  } = useTopicPopover({ activeGraph, isMobileViewport, graphShellRef });
  const openQuizReportHistory = () => {
    if (!activeGraph || !selectedTopic) return;
    setReportHistoryTarget({ graphId: activeGraph.graph_id, topicId: selectedTopic.id, topicTitle: selectedTopic.title });
  };
  useLayoutEffect(() => {
    setReportHistoryTarget(null);
    quizRequestRef.current += 1;
    lessonRequestRef.current += 1;
    setLessonLoading(false);
    setLessonError(null);
    setLessonSuccess(null);
    setQuizLoading(false);
    setQuizSession((session) => session && session.graph_id === activeGraph?.graph_id && session.topic_id === selectedTopicId ? session : null);
    setQuizAnswers({});
    setQuizReviews(null);
    setQuizReport(null);
    setQuizError(null);
    setQuizSuccess(null);
    return () => { quizRequestRef.current += 1; lessonRequestRef.current += 1; };
  }, [activeGraph?.graph_id, selectedTopicId]);

  useEffect(() => {
    setApplyError(null);
    setQuizSession(null);
    setQuizAnswers({});
    setQuizError(null);
    setQuizSuccess(null);
    setQuizReviews(null);
    setQuizReport(null);
    setGraphLayoutEditing(false);
    setGraphLayoutDraft(null);
  }, [activeGraph?.graph_id]);

  const currentConfig = data?.workspace.config ?? null;
  const settingsState = useWorkspaceSettings({
    config: currentConfig,
    updateWorkspaceConfig: async (patch) => {
      setConfigSaving(true);
      setError(null);
      try {
        const response = await apiFetch(`${API_BASE}/api/v1/workspace/config`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(patch),
        });
        if (!response.ok) {
          const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
          throw new Error(payload?.detail ?? `config update failed with ${response.status}`);
        }
        const payload = (await response.json()) as WorkspaceEnvelope;
        setData(payload);
        void loadSnapshots();
        void loadWorkspaceSurface();
      } catch (updateError) {
        setError(updateError instanceof Error ? updateError.message : copy.errors.updateConfig);
      } finally {
        setConfigSaving(false);
      }
    },
    straightEdgeLinesEnabled,
    setStraightEdgeLinesEnabled,
    initialThemeMode,
  });
  const { disableIdleAnimations: disableIdleAnimationsDraft } = settingsState.drafts;

  const provider = currentConfig?.agent_backend ?? "ruflo_native";
  useEffect(() => {
    if (provider !== "chatgpt") return;
    const refresh = () => void chatgpt.refresh();
    refresh();
    window.addEventListener("clew-sign-in-required", refresh);
    window.addEventListener("focus", refresh);
    return () => {
      window.removeEventListener("clew-sign-in-required", refresh);
      window.removeEventListener("focus", refresh);
    };
  }, [provider, chatgpt.refresh]);
  useEffect(() => {
    const refresh = () => setProviderRefresh((value) => value + 1);
    window.addEventListener("jew-agent-refresh", refresh);
    return () => window.removeEventListener("jew-agent-refresh", refresh);
  }, []);
  useEffect(() => {
    if (provider === "chatgpt") return;
    const controller = new AbortController();
    void apiFetch(`${API_BASE}/api/v1/agent/models`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(await readErrorMessage(response, `HTTP ${response.status}`));
        return response.json() as Promise<{ provider: string; models: ChatGPTModel[] }>;
      })
      .then((result) => {
        if (!controller.signal.aborted && result.provider === provider) setProviderCatalog(result);
      })
      .catch(() => {
        if (!controller.signal.aborted) setProviderCatalog({ provider, models: [] });
      });
    return () => controller.abort();
  }, [provider, providerRefresh]);
  const availableModels = provider === "chatgpt" ? chatgpt.account?.models ?? []
    : providerCatalog?.provider === provider ? providerCatalog.models : [];
  const { chatModelOptions, selectedChatModel, setSelectedChatModel } = useChatModelSelection(
    currentConfig,
    activeGraph?.graph_id ?? null,
    availableModels,
    provider,
  );
  const {
    activeSessionId,
    setActiveSessionId,
    chatSessions,
    currentChatState,
    chatLoading,
    chatThreadLoading,
    chatError,
    chatSessionsError,
    updateCurrentChatState,
    clearChatStateForGraph,
    loadSessions,
    sendChat,
    answerInteraction, stopChat, reconnectChat,
  } = useGraphChatController({
    activeGraph,
    selectedTopicId,
    selectedChatModel,
    defaultModel: currentConfig?.default_model ?? null,
    loadChatError: copy.errors.loadChat,
    loadChatSessionsError: copy.errors.loadChatSessions,
  });

  useEffect(() => {
    if (!isSettingsOpen) return;
    settingsState.setDrafts.straightEdgeLines(straightEdgeLinesEnabled);
  }, [isSettingsOpen, straightEdgeLinesEnabled]);

  useEffect(() => {
    if (!isMobileViewport) return;
    setLeftSidebarOpen(false);
    setLeftSidebarClosing(false);
    setAssistantWidth(0);
  }, [isMobileViewport]);

  useEffect(() => {
    if (!isMobileViewport || activeGraph) return;
    setAssistantWidth(0);
  }, [activeGraph, isMobileViewport]);

  useEffect(() => {
    if (!isMobileViewport) {
      setMobileMenuOpen(false);
      return;
    }
    if (isSettingsOpen) {
      setMobileMenuOpen(false);
    }
  }, [isMobileViewport, isSettingsOpen]);


  const focusData = useMemo(() => computeFocusData(activeGraph, selectedTopicId), [activeGraph, selectedTopicId]);
  const graphSummary = useMemo(() => computeGraphSummary(activeGraph), [activeGraph]);
  const fallbackAssessment = useMemo(() => buildFallbackAssessment(activeGraph, copy), [activeGraph, copy]);
  const zoneTitlesById = useMemo(() => new Map((activeGraph?.zones ?? []).map((zone) => [zone.id, zone.title])), [activeGraph]);
  const topicTitlesById = useMemo(() => new Map((activeGraph?.topics ?? []).map((topic) => [topic.id, topic.title])), [activeGraph]);
  const selectedZoneTitles = useMemo(
    () => (selectedTopic?.zones ?? []).map((zoneId) => zoneTitlesById.get(zoneId) ?? zoneId),
    [selectedTopic, zoneTitlesById],
  );
  const selectedZoneLabel = selectedZoneTitles.join(" · ");
  const selectedResourceLinks = useMemo(() => selectedTopic?.resources ?? [], [selectedTopic]);
  const selectedArtifacts = useMemo(() => selectedTopic?.artifacts ?? [], [selectedTopic]);
  const selectedClosureStatus = useMemo(() => computeClosureStatus(activeGraph, selectedTopicId), [activeGraph, selectedTopicId]);
  const activeAssessmentCards = useMemo(
    () => (assessment?.cards.length ? assessment.cards : fallbackAssessment.cards).filter((card) => !["Roadmap", "Closure"].includes(card.label)),
    [assessment?.cards, fallbackAssessment.cards],
  );
  const onboardingNeedsFirstGraph = !activeGraph && workspaceSurface?.onboarding_state === "needs_first_graph";
  const liveDisableIdleAnimations =
    isSettingsOpen
      ? disableIdleAnimationsDraft
      : Boolean(currentConfig?.disable_idle_animations);
  const closureTestsEnabled = currentConfig?.enable_closure_tests ?? true;
  const debugModeEnabled = currentConfig?.debug_mode_enabled ?? false;
  useEffect(() => {
    setDebugModeEnabled(debugModeEnabled);
    if (!debugModeEnabled) {
      setLogsOpen(false);
    }
    return () => setDebugModeEnabled(false);
  }, [debugModeEnabled]);
  const activeMemoryOption = settingsState.activeMemoryOption;
  const activeMemoryValues = settingsState.activeMemoryValues;
  const settingsDirty = settingsState.settingsDirty;
  const showGraphLoadingState = loading && !activeGraph;
  const showGraphEmptyState = !loading && !activeGraph;

  useEffect(() => {
    let cancelled = false;
    async function loadAssessment(): Promise<void> {
      if (!activeGraph) {
        setAssessment(null);
        setAssessmentError(null);
        return;
      }
      try {
        const response = await apiFetch(`${API_BASE}/api/v1/graphs/${activeGraph.graph_id}/assessment`);
        if (!response.ok) throw new Error(`assessment failed with ${response.status}`);
        const payload = (await response.json()) as GraphAssessment;
        if (cancelled) return;
        setAssessment(payload);
        setAssessmentError(null);
      } catch (loadError) {
        if (cancelled) return;
        setAssessment(null);
        setAssessmentError(loadError instanceof Error ? loadError.message : copy.errors.loadAssessment);
      }
    }
    void loadAssessment();
    return () => {
      cancelled = true;
    };
  }, [activeGraph?.graph_id, data?.snapshot.id]);

  useEffect(() => {
    let cancelled = false;
    setLearningPlan(null);
    if (activeGraph) {
      const graphId = activeGraph.graph_id;
      const graphVersion = activeGraph.version;
      void (async () => {
        try {
          const response = await apiFetch(API_BASE + "/api/v1/graphs/" + graphId + "/learning-plan");
          if (!response.ok) throw new Error("learning plan failed with " + response.status);
          const payload = (await response.json()) as LearningPlan;
          if (!cancelled && payload.graph_id === graphId && payload.graph_version === graphVersion) {
            setLearningPlan(payload);
          }
        } catch {
          if (!cancelled) setLearningPlan(null);
        }
      })();
    }
    return () => { cancelled = true; };
  }, [activeGraph?.graph_id, activeGraph?.version, data?.snapshot.id]);

  // Auto-scroll only for new messages or active assistant loading.
  const lastMessagesLengthRef = useRef(0);
  useEffect(() => {
    const viewport = chatViewportRef.current;
    if (!viewport) return;
    const nextLength = currentChatState.messages.length;
    const grew = nextLength > lastMessagesLengthRef.current;
    lastMessagesLengthRef.current = nextLength;
    if (grew || chatLoading) {
      viewport.scrollTop = viewport.scrollHeight;
    }
  }, [currentChatState.messages, chatLoading]);

  function handleAssistantResize(startX: number): void {
    setAssistantResizing(true);
    const startWidth = assistantWidth;
    let latestWidth = assistantWidth;

    function onMouseMove(event: MouseEvent): void {
      const delta = startX - event.clientX;
      const nextWidth = Math.min(Math.max(0, startWidth + delta), ASSISTANT_MAX_WIDTH);
      latestWidth = nextWidth;
      setAssistantWidth(nextWidth);
    }

    function onMouseUp(): void {
      setAssistantResizing(false);
      setAssistantWidth((current) => {
        const resolved = latestWidth || current;
        if (resolved < ASSISTANT_COLLAPSE_THRESHOLD) return 0;
        return Math.min(ASSISTANT_MAX_WIDTH, Math.max(ASSISTANT_MIN_WIDTH, resolved));
      });
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
    }

    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
  }

  async function fetchWorkspace(): Promise<WorkspaceEnvelope> {
    const response = await apiFetch(`${API_BASE}/api/v1/workspace/current`);
    if (!response.ok) throw new Error(await readErrorMessage(response, copy.errors.loadWorkspace));
    return (await response.json()) as WorkspaceEnvelope;
  }
  const loadWorkspaceSurface = useCallback(async (): Promise<WorkspaceSurfacePayload | null> => {
    try {
      const response = await apiFetch(`${API_BASE}/api/v1/workspace/surface`);
      if (!response.ok) return null;
      const payload = (await response.json()) as WorkspaceSurfacePayload;
      setWorkspaceSurface(payload);
      return payload;
    } catch {
      return null;
    }
  }, []);

  const loadSessionInfo = useCallback(async (): Promise<AuthSessionPayload | null> => {
    try {
      const response = await apiFetch(`${API_BASE}/api/v1/auth/session`);
      if (!response.ok) throw new Error(await readErrorMessage(response, copy.errors.loadWorkspace));
      const payload = (await response.json()) as AuthSessionPayload;
      if (payload.workspace_surface) {
        setWorkspaceSurface(payload.workspace_surface);
      }
      return payload;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : copy.errors.loadWorkspace);
      return null;
    }
  }, []);

  useEffect(() => {
    void loadSessionInfo();
  }, [loadSessionInfo, bootstrapRevision]);

  async function loadSnapshots(): Promise<void> {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const response = await apiFetch(`${API_BASE}/api/v1/graph/snapshots`);
      if (!response.ok) throw new Error(`snapshot list failed with ${response.status}`);
      const payload = (await response.json()) as { items: SnapshotRecord[] };
      setSnapshots(payload.items);
    } catch (loadError) {
      setHistoryError(loadError instanceof Error ? loadError.message : copy.errors.loadHistory);
    } finally {
      setHistoryLoading(false);
    }
  }

  async function saveLearnerProfile(profile: LearnerProfile): Promise<void> {
    const launchStudio = needsLearnerOnboarding(learnerProfile, data?.snapshot.id ?? 0);
    const response = await apiFetch(`${API_BASE}/api/v1/learner/profile`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(profile),
    });
    if (!response.ok) throw new Error(await readErrorMessage(response, "Não foi possível salvar o perfil."));
    const payload = (await response.json()) as WorkspaceEnvelope;
    setData(payload);
    setLearnerProfile(payload.workspace.learner_profile ?? profile);
    setOnboardingOpen(false);
    if (launchStudio) setRoadmapStudioOpen(true);
  }

  async function openConfirmedRoadmap(payload: WorkspaceEnvelope): Promise<void> {
    const graphId = payload.workspace.active_graph_id ?? payload.workspace.graphs[0]?.graph_id ?? null;
    setData(payload);
    clearChatStateForGraph(graphId);
    setActiveGraphId(graphId);
    setSelectedTopicId(null);
    setSelectedTopicAnchor(null);
    await Promise.all([loadSnapshots(), loadSessionInfo()]);
    setRoadmapStudioOpen(false);
  }

  async function createGraph(): Promise<void> {
    setCreateGraphLoading(true);
    setCreateGraphError(null);
    try {
      const response = await apiFetch(`${API_BASE}/api/v1/workspace/graphs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(createGraphDraft),
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(payload?.detail ?? `graph create failed with ${response.status}`);
      }
      const payload = (await response.json()) as WorkspaceEnvelope;
      setData(payload);
      clearChatStateForGraph(payload.workspace.active_graph_id ?? payload.workspace.graphs[0]?.graph_id ?? null);
      await loadSnapshots();
      setActiveGraphId(payload.workspace.active_graph_id ?? payload.workspace.graphs[0]?.graph_id ?? null);
      setSelectedTopicId(null);
      setSelectedTopicAnchor(null);
      setCreateGraphOpen(false);
      setCreateGraphDraft({ title: "", subject: "", language: "en", description: "" });
      await loadSessionInfo();
    } catch (createError) {
      setCreateGraphError(createError instanceof Error ? createError.message : copy.errors.createGraph);
    } finally {
      setCreateGraphLoading(false);
    }
  }

  async function importGraphFromPackage(): Promise<void> {
    if (!importGraphPayload) {
      setImportGraphError(copy.dialogs.noFileChosen);
      return;
    }
    setImportGraphLoading(true);
    setImportGraphError(null);
    try {
      const response = await apiFetch(`${API_BASE}/api/v1/workspace/graphs/import`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          package: importGraphPayload,
          title: importGraphTitleDraft.trim() || undefined,
          include_progress: importGraphIncludeProgressDraft,
        }),
      });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, copy.errors.importGraph));
      }
      const payload = (await response.json()) as WorkspaceEnvelope;
      setData(payload);
      clearChatStateForGraph(payload.workspace.active_graph_id ?? payload.workspace.graphs[0]?.graph_id ?? null);
      setActiveGraphId(payload.workspace.active_graph_id ?? payload.workspace.graphs[0]?.graph_id ?? null);
      setSelectedTopicId(null);
      setSelectedTopicAnchor(null);
      closeImportGraphModal();
      setCreateGraphOpen(false);
      await Promise.all([loadSnapshots(), loadSessionInfo()]);
    } catch (importError) {
      setImportGraphError(importError instanceof Error ? importError.message : copy.errors.importGraph);
    } finally {
      setImportGraphLoading(false);
    }
  }

  async function handleImportGraphFile(file: File): Promise<void> {
    try {
      const raw = await file.text();
      const parsed = JSON.parse(raw) as GraphExportPackagePayload;
      if (!parsed || parsed.kind !== "mapmind_graph_export" || !parsed.graph) {
        throw new Error("unsupported graph package");
      }
      setImportGraphPayload(parsed);
      setImportGraphFileName(file.name);
      setImportGraphTitleDraft(parsed.title ?? parsed.graph.title ?? "");
      setImportGraphIncludeProgressDraft(Boolean(parsed.include_progress));
      setImportGraphError(null);
    } catch (parseError) {
      setImportGraphPayload(null);
      setImportGraphFileName(file.name);
      setImportGraphError(parseError instanceof Error ? parseError.message : copy.errors.importGraph);
    }
  }

  async function handleObsidianVaultFiles(files: FileList | null): Promise<void> {
    const fileList = files ? Array.from(files) : [];
    if (fileList.length === 0) return;
    setImportObsidianLoading(true);
    setImportObsidianError(null);
    try {
      const relativePaths = fileList
        .map((file) => file.webkitRelativePath || file.name)
        .filter(Boolean);
      const vaultRoot = relativePaths[0]?.split("/")[0] ?? "Obsidian Vault";
      const markdownFiles = fileList.filter((file) => {
        const relativePath = file.webkitRelativePath || file.name;
        return relativePath.toLowerCase().endsWith(".md");
      });
      const entries = await Promise.all(
        markdownFiles.map(async (file) => {
          const relativePath = file.webkitRelativePath || file.name;
          const [, ...segments] = relativePath.split("/");
          return {
            path: segments.join("/") || file.name,
            content: await file.text(),
          } satisfies ObsidianVaultEntry;
        }),
      );
      if (entries.length === 0) {
        throw new Error(copy.dialogs.obsidianNoMarkdown);
      }
      setObsidianVaultName(vaultRoot);
      setObsidianVaultEntries(entries);
      setObsidianImportDraft((current) => ({
        ...current,
        graphTitle: vaultRoot,
        subject: vaultRoot,
      }));
    } catch (loadError) {
      setObsidianVaultName(null);
      setObsidianVaultEntries(null);
      setImportObsidianError(loadError instanceof Error ? loadError.message : copy.errors.importGraph);
    } finally {
      setImportObsidianLoading(false);
    }
  }

  async function importGraphFromObsidian(): Promise<void> {
    if (!obsidianImportPreview?.package) {
      setImportObsidianError(copy.dialogs.obsidianImportBlocked);
      return;
    }
    setImportObsidianLoading(true);
    setImportObsidianError(null);
    try {
      const response = await apiFetch(`${API_BASE}/api/v1/workspace/graphs/import`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          package: obsidianImportPreview.package,
          title: obsidianImportDraft.graphTitle.trim() || undefined,
          include_progress: false,
        }),
      });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, copy.errors.importGraph));
      }
      const payload = (await response.json()) as WorkspaceEnvelope;
      setData(payload);
      clearChatStateForGraph(payload.workspace.active_graph_id ?? payload.workspace.graphs[0]?.graph_id ?? null);
      setActiveGraphId(payload.workspace.active_graph_id ?? payload.workspace.graphs[0]?.graph_id ?? null);
      setSelectedTopicId(null);
      setSelectedTopicAnchor(null);
      closeImportObsidianModal();
      setCreateGraphOpen(false);
      await Promise.all([loadSnapshots(), loadSessionInfo()]);
    } catch (importError) {
      setImportObsidianError(importError instanceof Error ? importError.message : copy.errors.importGraph);
    } finally {
      setImportObsidianLoading(false);
    }
  }

  async function exportGraph(graph: GraphEnvelope): Promise<void> {
    setExportGraphLoading(true);
    setExportGraphError(null);
    try {
      if (exportGraphFormatDraft === "mapmind_obsidian_export" && !supportsObsidianDirectoryExport()) {
        throw new Error(copy.errors.exportGraphObsidianUnsupported);
      }
      const response = await apiFetch(`${API_BASE}/api/v1/workspace/graphs/${graph.graph_id}/export`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: exportGraphTitleDraft.trim() || graph.title,
          include_progress: exportGraphIncludeProgressDraft,
          format: exportGraphFormatDraft,
          obsidian: exportGraphFormatDraft === "mapmind_obsidian_export" ? exportGraphObsidianOptionsDraft : undefined,
        }),
      });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, copy.errors.exportGraph));
      }
      if (exportGraphFormatDraft === "mapmind_obsidian_export") {
        const payload = (await response.json()) as ObsidianGraphExportPackagePayload;
        if (!await writeObsidianExportPackageToDirectory(payload)) return;
      } else {
        const payload = (await response.json()) as GraphExportPackagePayload;
        const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
        const objectUrl = URL.createObjectURL(blob);
        const link = document.createElement("a");
        const safeBase = (exportGraphTitleDraft.trim() || graph.title).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "graph";
        link.href = objectUrl;
        link.download = `${safeBase}.mapmind-graph.json`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(objectUrl);
      }
      closeExportGraphModal();
    } catch (exportError) {
      setExportGraphError(exportError instanceof Error ? exportError.message : copy.errors.exportGraph);
    } finally {
      setExportGraphLoading(false);
    }
  }

  async function renameGraph(graphId: string): Promise<void> {
    const nextTitle = renameGraphDraft.trim();
    if (!nextTitle) {
      setError("graph title is required");
      return;
    }
    setRenameGraphSaving(true);
    setError(null);
    try {
      const response = await apiFetch(`${API_BASE}/api/v1/workspace/graphs/${graphId}/rename`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: nextTitle }),
      });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, copy.errors.renameGraph));
      }
      const payload = (await response.json()) as WorkspaceEnvelope;
      setData(payload);
      setActiveGraphId(payload.workspace.active_graph_id ?? graphId);
      setRenamingGraphId(null);
      setRenameGraphDraft("");
      await Promise.all([loadSnapshots(), loadSessionInfo()]);
    } catch (renameError) {
      setError(renameError instanceof Error ? renameError.message : copy.errors.renameGraph);
    } finally {
      setRenameGraphSaving(false);
    }
  }

  async function saveGraphLayout(): Promise<void> {
    if (!activeGraph) return;
    if (!graphLayoutDraft || Object.keys(graphLayoutDraft).length === 0) {
      setGraphLayoutEditing(false);
      return;
    }
    setGraphLayoutSaving(true);
    setError(null);
    try {
      const response = await apiFetch(`${API_BASE}/api/v1/workspace/graphs/${activeGraph.graph_id}/layout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ positions: graphLayoutDraft }),
      });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, copy.errors.saveGraphLayout));
      }
      const payload = (await response.json()) as WorkspaceEnvelope;
      setData(payload);
      setGraphLayoutEditing(false);
      setGraphLayoutDraft(null);
      void loadSnapshots();
    } catch (layoutError) {
      setError(layoutError instanceof Error ? layoutError.message : copy.errors.saveGraphLayout);
    } finally {
      setGraphLayoutSaving(false);
    }
  }

  function startGraphLayoutEdit(): void {
    setError(null);
    setGraphLayoutDraft(activeGraphManualLayout);
    setGraphLayoutEditing(true);
  }

  async function applyProposalFromMessage(messageId: string, proposal: ProposalGenerateResponse): Promise<void> {
    if (!activeGraph) return;
    setApplyLoadingMessageId(messageId);
    setApplyError(null);
    try {
      const response = await apiFetch(`${API_BASE}/api/v1/graphs/${activeGraph.graph_id}/apply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(proposal.proposal_envelope),
      });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, copy.errors.applyProposal));
      }
      const payload = (await response.json()) as WorkspaceEnvelope;
      const proposedTopicId = firstProposedTopicId(proposal);
      // Commit the graph transition in one synchronous block to avoid visible intermediate states.
      setData(payload);
      setActiveGraphId(proposal.proposal_envelope.graph_id);
      if (proposedTopicId) {
        setSelectedTopicId(proposedTopicId);
        setSelectedTopicAnchor(null);
      }
      // Snapshot refresh should not block the main graph transition.
      void loadSnapshots();
      updateCurrentChatState((current) => ({ ...current,
        messages: current.messages.map((message) => message.id === messageId ? { ...message, proposal_applied: true } : message),
      }));
    } catch (applyLoadError) {
      setApplyError(applyLoadError instanceof Error ? applyLoadError.message : copy.errors.applyProposal);
    } finally {
      setApplyLoadingMessageId(null);
    }
  }

  async function startQuiz(): Promise<void> {
    if (!activeGraph || !selectedTopic) return;
    const requestId = ++quizRequestRef.current;
    setQuizLoading(true);
    setQuizError(null);
    setQuizSuccess(null);
    setQuizReviews(null);
    setQuizReport(null);
    try {
      const response = await apiFetch(`${API_BASE}/api/v1/graphs/${activeGraph.graph_id}/topics/${selectedTopic.id}/quiz/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: selectedChatModel ?? null }),
      });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, copy.errors.startQuiz));
      }
      const payload = (await response.json()) as QuizStartResponse;
      if (requestId !== quizRequestRef.current) return;
      setQuizSession(payload.session);
      setQuizAnswers({});
    } catch (quizLoadError) {
      if (requestId !== quizRequestRef.current) return;
      setQuizError(quizLoadError instanceof Error ? quizLoadError.message : copy.errors.startQuiz);
    } finally {
      if (requestId === quizRequestRef.current) setQuizLoading(false);
    }
  }

  async function generateLesson(): Promise<void> {
    if (!activeGraph || !selectedTopic) return;
    const requestId = ++lessonRequestRef.current;
    setLessonLoading(true);
    setLessonError(null);
    setLessonSuccess(null);
    try {
      const response = await apiFetch(`${API_BASE}/api/v1/graphs/${activeGraph.graph_id}/topics/${selectedTopic.id}/lessons/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: provider === "ollama" || provider === "ruflo_native" ? selectedChatModel ?? null : null }),
      });
      if (!response.ok) throw new Error(await readErrorMessage(response, copy.errors.generateLesson));
      const payload = (await response.json()) as { artifact: Artifact; workspace: WorkspaceEnvelope };
      if (requestId !== lessonRequestRef.current) return;
      setData((current) => !current || payload.workspace.snapshot.id >= current.snapshot.id ? payload.workspace : current);
      void loadSnapshots();
      setLessonSuccess(copy.topic.lessonSaved);
    } catch (lessonFailure) {
      if (requestId === lessonRequestRef.current) {
        setLessonError(lessonFailure instanceof Error ? lessonFailure.message : copy.errors.generateLesson);
      }
    } finally {
      if (requestId === lessonRequestRef.current) setLessonLoading(false);
    }
  }

  async function markTopicFinished(): Promise<void> {
    if (!activeGraph || !selectedTopic) return;
    const requestId = ++quizRequestRef.current;
    setQuizLoading(true);
    setQuizError(null);
    setQuizSuccess(null);
    setQuizReviews(null);
    setQuizReport(null);
    try {
      const response = await apiFetch(`${API_BASE}/api/v1/graphs/${activeGraph.graph_id}/topics/${selectedTopic.id}/mark-finished`, {
        method: "POST",
      });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, copy.errors.submitQuiz));
      }
      const payload = (await response.json()) as QuizSubmitResponse;
      setData((current) => !current || payload.workspace.snapshot.id >= current.snapshot.id ? payload.workspace : current);
      void loadSnapshots();
      if (requestId !== quizRequestRef.current) return;
      setQuizSession(null);
      setQuizAnswers({});
      setQuizSuccess(copy.closure.markAsFinished);
    } catch (markError) {
      if (requestId === quizRequestRef.current) {
        setQuizError(markError instanceof Error ? markError.message : copy.errors.submitQuiz);
      }
    } finally {
      if (requestId === quizRequestRef.current) setQuizLoading(false);
    }
  }

  async function addTopicResource(topicId: string, url: string): Promise<void> {
    if (!activeGraph) return;
    const response = await apiFetch(`${API_BASE}/api/v1/workspace/graphs/${activeGraph.graph_id}/topics/${topicId}/resources`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: url.trim() }),
    });
    if (!response.ok) {
      throw new Error(await readErrorMessage(response, copy.dialogs.addResourceTitle));
    }
    const payload = (await response.json()) as WorkspaceEnvelope;
    setData(payload);
    await loadSnapshots();
  }

  async function addTopicArtifact(topicId: string, title: string, body: string): Promise<void> {
    if (!activeGraph) return;
    const response = await apiFetch(`${API_BASE}/api/v1/workspace/graphs/${activeGraph.graph_id}/topics/${topicId}/artifacts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: title.trim(), body: body.trim() }),
    });
    if (!response.ok) {
      throw new Error(await readErrorMessage(response, copy.dialogs.addArtifactTitle));
    }
    const payload = (await response.json()) as WorkspaceEnvelope;
    setData(payload);
    await loadSnapshots();
  }

  async function saveTopicNote(topicId: string, noteMarkdown: string): Promise<void> {
    if (!activeGraph) return;
    const graphId = activeGraph.graph_id;
    const response = await apiFetch(`${API_BASE}/api/v1/workspace/graphs/${graphId}/topics/${topicId}/note`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ note_markdown: noteMarkdown }),
    });
    if (!response.ok) throw new Error(await readErrorMessage(response, "Não foi possível salvar a nota."));
    setData((current) => current ? {
      ...current,
      workspace: {
        ...current.workspace,
        graphs: current.workspace.graphs.map((graph) => graph.graph_id === graphId ? {
          ...graph,
          topics: graph.topics.map((topic) => topic.id === topicId ? { ...topic, note_markdown: noteMarkdown } : topic),
        } : graph),
      },
    } : current);
  }

  async function submitQuiz(answersOverride?: Record<string, number>): Promise<void> {
    if (!quizSession) return;
    const requestId = ++quizRequestRef.current;
    setQuizLoading(true);
    setQuizError(null);
    setQuizSuccess(null);
    try {
      const response = await apiFetch(`${API_BASE}/api/v1/graphs/${quizSession.graph_id}/topics/${quizSession.topic_id}/quiz/submit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: quizSession.session_id,
          answers: quizSession.questions
            .filter((question) => Number.isInteger((answersOverride ?? quizAnswers)[question.id])
              && (answersOverride ?? quizAnswers)[question.id] >= 0
              && (answersOverride ?? quizAnswers)[question.id] < question.choices.length)
            .map((question) => ({
              question_id: question.id,
              choice_index: (answersOverride ?? quizAnswers)[question.id],
            })),
        }),
      });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, copy.errors.submitQuiz));
      }
      const payload = (await response.json()) as QuizSubmitResponse;
      // A completed submission is a durable mutation even if navigation or
      // closing the dialog invalidated its transient UI response.
      setData((current) => !current || payload.workspace.snapshot.id >= current.snapshot.id ? payload.workspace : current);
      void loadSnapshots();
      if (requestId !== quizRequestRef.current) return;
      setQuizAnswers({});
      setQuizReviews(payload.reviews);
      setQuizReport(payload.report ?? null);
      if (payload.attempt.passed) {
        setQuizSuccess(copy.quiz.correct);
      }
    } catch (quizSubmitError) {
      if (requestId !== quizRequestRef.current) return;
      setQuizError(quizSubmitError instanceof Error ? quizSubmitError.message : copy.errors.submitQuiz);
    } finally {
      if (requestId === quizRequestRef.current) setQuizLoading(false);
    }
  }

  async function rollbackSnapshot(snapshotId: number): Promise<void> {
    quizRequestRef.current += 1;
    setQuizLoading(false);
    setQuizError(null);
    setQuizSuccess(null);
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const response = await apiFetch(`${API_BASE}/api/v1/graph/rollback/${snapshotId}`, {
        method: "POST",
      });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, copy.errors.rollbackSnapshot));
      }
      const payload = (await response.json()) as WorkspaceEnvelope;
      setData(payload);
      setActiveGraphId(payload.workspace.active_graph_id ?? payload.workspace.graphs[0]?.graph_id ?? null);
      setSelectedTopicId(null);
      setSelectedTopicAnchor(null);
      setQuizSession(null);
      setQuizAnswers({});
      setQuizReviews(null);
      setQuizReport(null);
      await loadSnapshots();
    } catch (rollbackError) {
      setHistoryError(rollbackError instanceof Error ? rollbackError.message : copy.errors.rollbackSnapshot);
    } finally {
      setHistoryLoading(false);
    }
  }

  const assistantTemplates = [
    { id: "expand", label: copy.graphText.expandGraphAction, value: templatePrompt("expand", copy) },
    { id: "ingest", label: copy.graphText.ingestTopicsAction, value: templatePrompt("ingest", copy) },
  ];
  const suspendedSurfaceStateRef = useRef<{ leftSidebarOpen: boolean; assistantWidth: number } | null>(null);
  const overlayWasOpenRef = useRef(false);
  const [overlayRestoreEpoch, setOverlayRestoreEpoch] = useState(0);
  const assistantOpen = assistantWidth >= ASSISTANT_MIN_WIDTH;
  const hasInlinePlanningWidget = currentChatState.messages.some((message) => Boolean(message.planning_status));
  const overlayLeftOffset = leftSidebarOpen ? 280 : 68;
  const overlayRightOffset = assistantOpen ? assistantWidth + 20 : 56;
  // Desktop windows float over the canvas and reserve no width; only the dock (left) and edge gutter count.
  const topOverlayCompact =
    !isMobileViewport
    && viewportWidth - 104 - 24 < COMPACT_TOP_OVERLAY_THRESHOLD;

  const openSidebar = useCallback(() => {
    if (sidebarCloseTimerRef.current) {
      window.clearTimeout(sidebarCloseTimerRef.current);
      sidebarCloseTimerRef.current = null;
    }
    setLeftSidebarClosing(false);
    setLeftSidebarOpen(true);
  }, []);

  const closeSidebar = useCallback(() => {
    if (!leftSidebarOpen || leftSidebarClosing) return;
    setLeftSidebarClosing(true);
    sidebarCloseTimerRef.current = window.setTimeout(() => {
      setLeftSidebarOpen(false);
      setLeftSidebarClosing(false);
      sidebarCloseTimerRef.current = null;
    }, 220);
  }, [leftSidebarClosing, leftSidebarOpen]);

  const openConfigurationSettings = useCallback(() => {
    setSettingsOpen((prev) => {
      const next = !prev;
      if (next) setLogsOpen(false);
      return next;
    });
    setMobileMenuOpen(false);
  }, []);

  const toggleDebugLogs = useCallback(() => {
    setLogsOpen((prev) => {
      const next = !prev;
      if (next) setSettingsOpen(false);
      return next;
    });
    setMobileMenuOpen(false);
  }, []);

  const closeOverlaySurfaces = useCallback(() => {
    suspendedSurfaceStateRef.current = null;
    setSettingsOpen(false);
    setLogsOpen(false);
    setMobileMenuOpen(false);
  }, []);

  useEffect(() => {
    const overlayOpen = isSettingsOpen || isLogsOpen;
    if (overlayOpen && !overlayWasOpenRef.current) {
      suspendedSurfaceStateRef.current = {
        leftSidebarOpen,
        assistantWidth,
      };
      if (sidebarCloseTimerRef.current) {
        window.clearTimeout(sidebarCloseTimerRef.current);
        sidebarCloseTimerRef.current = null;
      }
      setLeftSidebarClosing(false);
      setLeftSidebarOpen(false);
      setAssistantWidth(0);
    } else if (!overlayOpen && overlayWasOpenRef.current && suspendedSurfaceStateRef.current) {
      const suspendedState = suspendedSurfaceStateRef.current;
      setLeftSidebarClosing(false);
      setLeftSidebarOpen(suspendedState.leftSidebarOpen);
      setAssistantWidth(suspendedState.assistantWidth);
      suspendedSurfaceStateRef.current = null;
      setOverlayRestoreEpoch((current) => current + 1);
    }
    overlayWasOpenRef.current = overlayOpen;
  }, [assistantWidth, isLogsOpen, isSettingsOpen, leftSidebarOpen]);

  const loadDebugLogs = useCallback(async () => {
    if (debugLogsInFlightRef.current) return;
    debugLogsInFlightRef.current = true;
    setDebugLogsLoading(true);
    try {
      const response = await apiFetch(`${API_BASE}/api/v1/debug/logs`);
      if (!response.ok) {
        throw new Error(`debug logs failed with ${response.status}`);
      }
      const payload = (await response.json()) as DebugLogSnapshot;
      setDebugLogs(payload);
      setDebugLogsError(null);
    } catch (loadError) {
      setDebugLogsError(loadError instanceof Error ? loadError.message : "Failed to load debug logs");
    } finally {
      debugLogsInFlightRef.current = false;
      setDebugLogsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!isLogsOpen || !debugModeEnabled) return;
    void loadDebugLogs();
    const interval = window.setInterval(() => {
      void loadDebugLogs();
    }, 1200);
    return () => window.clearInterval(interval);
  }, [debugModeEnabled, isLogsOpen, loadDebugLogs]);

  const sidebarVisible = leftSidebarOpen || leftSidebarClosing;

  if (!data || !workspaceSurface) {
    if (error) return <main className="launchLoading"><div className="launchError">
      <p role="alert">{error}</p>
      <button className="uiButton" type="button" onClick={() => { bootstrapStartedRef.current = false; setError(null); setBootstrapRevision((value) => value + 1); }}>Try again</button>
    </div></main>;
    return (
      <div className="clewLaunchInline" role="status" aria-label="Loading Jew">
        <ClewLoader size={56} />
      </div>
    );
  }

  return (
    <div className="app" data-theme={themeModeDraft}>
      <div className="ambient-glow" />
      <WorkspaceShell
        copy={copy}
        navigation={{
          sidebarVisible,
          leftSidebarClosing,
          closeSidebar,
          projectsExpanded,
          setProjectsExpanded,
          availableGraphs,
          activeGraph,
          renamingGraphId,
          renameGraphDraft,
          setRenameGraphDraft,
          renameGraphSaving,
          renameGraph,
          setError,
          setRenamingGraphId,
          setActiveGraphId,
          setSelectedTopicId,
          setSelectedTopicAnchor,
          openExportGraphModal,
          setDeleteConfirm,
          setCreateGraphOpen,
          setCreateGraphError,
          openRoadmapStudio: () => { setOnboardingOpen(false); setRoadmapStudioOpen(true); },
          mobileMenuOpen,
          setMobileMenuOpen,
        }}
        chrome={{
          openConfigurationSettings,
          openDebugLogs: toggleDebugLogs,
          closeOverlaySurfaces,
          isLogsOpen,
          modalSurfaceLocked: isSettingsOpen || isLogsOpen,
          isMobileViewport,
          leftSidebarOpen,
          openSidebar,
          assistantOpen,
          setAssistantWidth,
          assistantWidth,
          viewportCenteredZoom,
          setViewportCenteredZoom,
          straightEdgeLinesEnabled,
          topOverlayCompact,
          overlayLeftOffset,
          overlayRightOffset,
          floatingStatsRef,
          isSettingsOpen,
          debugModeEnabled,
          themeMode: themeModeDraft,
          setThemeMode: setThemeModeDraft,
          overlayRestoreEpoch,
        }}
        workspaceStatus={{
          data,
          assessmentError,
          configSaving,
          error,
          workspaceSurface,
        }}
        graphWorkspace={{
          graphSummary,
          activeAssessmentCards,
          graphLayoutEditing,
          graphLayoutSaving,
          saveGraphLayout,
          startGraphLayoutEdit,
          setGraphLayoutEditing,
          setGraphLayoutDraft,
          graphShellRef,
          focusData,
          handleSelectTopic,
          handleSelectedTopicAnchorChange,
          selectedTopicId,
          graphLayoutDraft,
          activeGraphManualLayout,
          liveDisableIdleAnimations,
          showGraphLoadingState,
          showGraphEmptyState,
          onboardingNeedsFirstGraph,
        }}
        topicDetails={{
          addTopicResource,
          addTopicArtifact,
          saveTopicNote,
          generateLesson,
          lessonLoading,
          lessonError,
          lessonSuccess,
          selectedTopic,
          selectedTopicAnchor,
          popoverPosition,
          topicPopoverRef,
          popoverDragRef,
          selectedZoneLabel,
          selectedResourceLinks,
          selectedArtifacts,
          selectedClosureStatus,
          learningPlan: learningPlan?.graph_id === activeGraph?.graph_id && learningPlan?.graph_version === activeGraph?.version ? learningPlan : null,
          topicTitlesById,
          quizError,
          quizSuccess,
          closureTestsEnabled,
          quizLoading,
          startQuiz,
          openQuizReportHistory,
          markTopicFinished,
        }}
        assistant={{
          agentControls: {
            answer: answerInteraction, stop: stopChat, reconnect: reconnectChat,
            authenticated: provider === "ruflo_native" ? true : provider === "chatgpt"
              ? !!chatgpt.account?.authenticated && !!chatgpt.account?.sharing
              : availableModels.length > 0,
            localAIWarning: provider === "ruflo_native"
              ? availableModels.length === 0
                ? "IA local indisponível. Inicie o Ollama e instale um modelo com: ollama pull qwen3.5:4b (ou outro modelo compatível). Depois atualize os modelos."
                : selectedChatModel && !availableModels.some((item) => item.model === selectedChatModel)
                  ? `O modelo local ${selectedChatModel} não está instalado. Selecione um modelo disponível nas configurações.`
                  : null
              : null,
            connect: () => setSettingsOpen(true),
            openQuiz: (session) => {
              quizRequestRef.current += 1;
              setQuizLoading(false);
              setSelectedTopicId(session.topic_id);
              setQuizSession(session);
              setQuizAnswers({});
              setQuizReviews(null);
              setQuizError(null);
            },
          },
          assistantResizing,
          handleAssistantResize,
          chatSessions,
          activeSessionId,
          setActiveSessionId,
          sessionListWrapRef,
          sessionListRef,
          sessionDragRef,
          apiFetch,
          loadSessions,
          currentChatState,
          chatViewportRef,
          chatThreadLoading,
          hasInlinePlanningWidget,
          chatLoading,
          chatError,
          chatSessionsError,
          updateCurrentChatState,
          sendChat,
          applyLoadingMessageId,
          applyProposalFromMessage,
          setSessionDeleteConfirm,
          applyError,
          assistantTemplates,
          chatModelOptions,
          selectedChatModel,
          setSelectedChatModel,
          chatComposerRef,
        }}
      />

      {(onboardingOpen || roadmapStudioOpen) && (
        <div className="jewLearningOverlay" role="presentation">
          <div className="jewLearningPanel" role="dialog" aria-modal="true" aria-label={onboardingOpen ? "Seu perfil de aprendizagem" : "Criar roadmap"}>
            {(!onboardingOpen || !needsLearnerOnboarding(learnerProfile, data?.snapshot.id ?? 0)) &&
              <button className="jewLearningClose" type="button" aria-label="Voltar ao JEW"
                onClick={() => { setOnboardingOpen(false); setRoadmapStudioOpen(false); }}>✕</button>}
            {onboardingOpen ? (
              <LearnerOnboarding key={`${learnerProfile.profession}:${learnerProfile.onboarding_complete}`} profile={learnerProfile}
                onSave={saveLearnerProfile} onClose={!needsLearnerOnboarding(learnerProfile, data?.snapshot.id ?? 0) ? () => setOnboardingOpen(false) : undefined} />
            ) : (
              <RoadmapStudio profile={learnerProfile} onClose={() => setRoadmapStudioOpen(false)}
                onCreated={openConfirmedRoadmap} />
            )}
          </div>
        </div>
      )}

      {reportHistoryTarget && reportHistoryTarget.graphId === activeGraph?.graph_id &&
        reportHistoryTarget.topicId === selectedTopicId ? (
        <StudyReportHistory
          key={`${reportHistoryTarget.graphId}:${reportHistoryTarget.topicId}`}
          graphId={reportHistoryTarget.graphId}
          topicId={reportHistoryTarget.topicId}
          topicTitle={reportHistoryTarget.topicTitle}
          onClose={() => setReportHistoryTarget(null)}
        />
      ) : null}

      <SettingsModal
        isSettingsOpen={isSettingsOpen}
        copy={copy}
        setSettingsOpen={setSettingsOpen}
        onEditLearnerProfile={() => { setSettingsOpen(false); setRoadmapStudioOpen(false); setOnboardingOpen(true); }}
        currentConfig={currentConfig}
        drafts={{ ...settingsState.drafts, themeMode: themeModeDraft }}
        setDrafts={{ ...settingsState.setDrafts, themeMode: setThemeModeDraft }}
        chatgpt={chatgpt}
        activeMemoryOption={activeMemoryOption}
        activeMemoryValues={activeMemoryValues}
        activeGraph={activeGraph}
        loadSnapshots={loadSnapshots}
        historyLoading={historyLoading}
        historyError={historyError}
        snapshots={snapshots}
        data={data}
        rollbackSnapshot={rollbackSnapshot}
        configSaving={configSaving}
        settingsDirty={settingsDirty}
        saveSettings={settingsState.saveSettings}
      />

      <DebugLogsModal
        copy={copy}
        open={isLogsOpen}
        onClose={() => setLogsOpen(false)}
        logs={debugLogs}
        loading={debugLogsLoading}
        error={debugLogsError}
      />

      <AppDialogs
        copy={copy}
        deleteConfirm={deleteConfirm}
        deleteGraphModalRef={deleteGraphModalRef}
        closeDeleteGraphModal={closeDeleteGraphModal}
        deleteGraphCancelButtonRef={deleteGraphCancelButtonRef}
        apiFetch={apiFetch}
        readErrorMessage={readErrorMessage}
        setDeleteConfirm={setDeleteConfirm}
        setData={setData}
        setActiveGraphId={setActiveGraphId}
        clearChatStateForGraph={clearChatStateForGraph}
        loadSnapshots={loadSnapshots}
        loadSessionInfo={loadSessionInfo}
        setError={setError}
        sessionDeleteConfirm={sessionDeleteConfirm}
        sessionDeleteModalRef={sessionDeleteModalRef}
        closeSessionDeleteModal={closeSessionDeleteModal}
        sessionDeleteCancelButtonRef={sessionDeleteCancelButtonRef}
        setSessionDeleteConfirm={setSessionDeleteConfirm}
        activeGraph={activeGraph}
        activeSessionId={activeSessionId}
        setActiveSessionId={setActiveSessionId}
        loadSessions={loadSessions}
        createGraphOpen={createGraphOpen}
        createGraphModalRef={createGraphModalRef}
        closeCreateGraphModal={closeCreateGraphModal}
        createGraphTitleInputRef={createGraphTitleInputRef}
        createGraphDraft={createGraphDraft}
        setCreateGraphDraft={setCreateGraphDraft}
        createGraphError={createGraphError}
        openImportGraphModal={openImportGraphModal}
        openImportObsidianModal={openImportObsidianModal}
        createGraphLoading={createGraphLoading}
        createGraph={createGraph}
        importGraphOpen={importGraphOpen}
        importGraphModalRef={importGraphModalRef}
        closeImportGraphModal={closeImportGraphModal}
        importGraphFileInputRef={importGraphFileInputRef}
        importGraphFileButtonRef={importGraphFileButtonRef}
        handleImportGraphFile={handleImportGraphFile}
        importGraphFileName={importGraphFileName}
        importGraphPayload={importGraphPayload}
        importGraphTitleDraft={importGraphTitleDraft}
        setImportGraphTitleDraft={setImportGraphTitleDraft}
        importGraphIncludeProgressDraft={importGraphIncludeProgressDraft}
        setImportGraphIncludeProgressDraft={setImportGraphIncludeProgressDraft}
        importGraphError={importGraphError}
        importGraphLoading={importGraphLoading}
        importGraphFromPackage={importGraphFromPackage}
        importObsidianOpen={importObsidianOpen}
        importObsidianModalRef={importObsidianModalRef}
        closeImportObsidianModal={closeImportObsidianModal}
        importObsidianFolderInputRef={importObsidianFolderInputRef}
        importObsidianFolderButtonRef={importObsidianFolderButtonRef}
        handleObsidianVaultFiles={handleObsidianVaultFiles}
        obsidianVaultName={obsidianVaultName}
        obsidianImportDraft={obsidianImportDraft}
        setObsidianImportDraft={setObsidianImportDraft}
        obsidianImportPreview={obsidianImportPreview}
        importObsidianError={importObsidianError}
        importObsidianLoading={importObsidianLoading}
        importGraphFromObsidian={importGraphFromObsidian}
        exportGraphTarget={exportGraphTarget}
        exportGraphModalRef={exportGraphModalRef}
        closeExportGraphModal={closeExportGraphModal}
        exportGraphTitleInputRef={exportGraphTitleInputRef}
        exportGraphTitleDraft={exportGraphTitleDraft}
        setExportGraphTitleDraft={setExportGraphTitleDraft}
        exportGraphIncludeProgressDraft={exportGraphIncludeProgressDraft}
        setExportGraphIncludeProgressDraft={setExportGraphIncludeProgressDraft}
        exportGraphFormatDraft={exportGraphFormatDraft}
        setExportGraphFormatDraft={setExportGraphFormatDraft}
        exportGraphObsidianOptionsDraft={exportGraphObsidianOptionsDraft}
        setExportGraphObsidianOptionsDraft={setExportGraphObsidianOptionsDraft}
        exportGraphError={exportGraphError}
        exportGraphLoading={exportGraphLoading}
        exportGraph={exportGraph}
        quizSession={quizSession}
        quizModalRef={quizModalRef}
        quizCloseButtonRef={quizCloseButtonRef}
        selectedTopic={selectedTopic}
        closeQuizModal={closeQuizModal}
        quizError={quizError}
        quizReviews={quizReviews}
        quizReport={quizReport}
        quizAnswers={quizAnswers}
        setQuizAnswers={setQuizAnswers}
        quizLoading={quizLoading}
        submitQuiz={submitQuiz}
      />
    </div>
  );
}
