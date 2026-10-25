export type TopicState =
  | "not_started"
  | "learning"
  | "shaky"
  | "solid"
  | "mastered"
  | "needs_review";

export type ResourceLink = {
  id: string;
  label: string;
  url: string;
  kind: string;
};

export type Artifact = {
  id: string;
  title: string;
  kind: string;
  body: string;
  created_at: string;
};

export type Topic = {
  id: string;
  title: string;
  slug: string;
  description: string;
  difficulty: number;
  estimated_minutes: number;
  level: number;
  state: TopicState;
  zones: string[];
  resources: ResourceLink[];
  artifacts: Artifact[];
  metadata?: Record<string, unknown>;
};

export type QuizAttempt = {
  id: string;
  topic_id: string;
  passed: boolean;
  score: number;
  question_count: number;
  source?: "quiz" | "manual";
  closure_awarded: boolean;
  created_at: string;
  missed_questions: string[];
  fail_count: number;
};

export type Edge = {
  id: string;
  source_topic_id: string;
  target_topic_id: string;
  relation: string;
  rationale: string;
};

export type Zone = {
  id: string;
  title: string;
  kind: string;
  color: string;
  intensity: number;
  topic_ids: string[];
};

export type GraphEnvelope = {
  graph_id: string;
  subject: string;
  title: string;
  language: "en" | "uk" | "ru";
  version: number;
  topics: Topic[];
  edges: Edge[];
  zones: Zone[];
  quiz_attempts: QuizAttempt[];
  metadata: Record<string, unknown>;
};

export type TopicClosureStatus = {
  topic_id: string;
  prerequisite_topic_ids: string[];
  blocked_prerequisite_ids: string[];
  can_award_completion: boolean;
  latest_attempt: QuizAttempt | null;
};

export type TopicQuizSession = {
  session_id: string;
  graph_id: string;
  topic_id: string;
  created_at: string;
  question_count: number;
  generator: string;
  closure_status: TopicClosureStatus;
  questions: Array<{
    id: string;
    prompt: string;
    choices: string[];
    explanation: string;
    verification_status?: "verified" | "unverified";
  }>;
};

export type StudyPoint = { x: number; y: number };
export type StudyStroke = {
  id: string;
  tool: "pen" | "highlighter";
  color: string;
  width: number;
  points: StudyPoint[];
};
export type QuizStudyDraft = {
  format_version: 1;
  revision: number;
  answers: Record<string, number>;
  active_question_id: string | null;
  flagged_question_ids: string[];
  notes: Record<string, string>;
  strokes: Record<string, StudyStroke[]>;
  updated_at: string | null;
};

export type QuizQuestionReview = {
  question_id: string;
  prompt: string;
  selected_choice: string | null;
  correct_choice: string;
  was_correct: boolean;
  explanation: string;
};

export type QuizReportFinding = {
  question_id: string;
  outcome: "correct" | "incorrect" | "unanswered";
  observation: string;
  error_category: "not_answered" | "undetermined" | null;
  hypothesis: string | null;
  diagnosis_confidence: "not_applicable" | "insufficient";
  evidence_needed: string | null;
  next_action: string;
  verification_status: "verified" | "unverified";
};

export type QuizPedagogicalReport = {
  attempt_id: string;
  title: string;
  attempted_at: string;
  question_count: number;
  answered_count: number;
  correct_count: number;
  incorrect_count: number;
  unanswered_count: number;
  ungraded_count: number;
  score: number;
  generator: string;
  grading_method: string;
  duration_seconds: number | null;
  verified_keys_count: number;
  unverified_keys_count: number;
  strengths: string[];
  improvement_areas: string[];
  evidence_limits: string[];
  question_findings: QuizReportFinding[];
  recovery_plan: string[];
  historical_comparison: string | null;
  next_steps: string[];
};

export type QuizReportSummary = {
  attempt_id: string;
  topic_id: string;
  created_at: string;
  title: string;
  score: number;
  question_count: number;
  in_current_graph: boolean;
};

export type QuizReportHistoryPage = {
  items: QuizReportSummary[];
  total: number;
  limit: number;
  offset: number;
};

export type QuizReportRecord = {
  format_version: 1;
  graph_id: string;
  topic_id: string;
  attempt: QuizAttempt;
  report: QuizPedagogicalReport;
  reviews: QuizQuestionReview[];
  in_current_graph: boolean;
};

export type QuizStartResponse = {
  session: TopicQuizSession;
};

export type QuizSubmitResponse = {
  attempt: QuizAttempt;
  closure_status: TopicClosureStatus;
  awarded_state: TopicState | null;
  reviews: QuizQuestionReview[];
  report?: QuizPedagogicalReport | null;
  workspace: WorkspaceEnvelope;
};

export type CreateGraphRequest = {
  title: string;
  subject: string;
  language: "en" | "uk" | "ru";
  description: string;
};

export type InlineChatQuiz = {
  question: string;
  choices: string[];
  correct_index: number;
  answered_index?: number | null;
  interaction_id?: string | null;
  status?: "pending" | "answered" | "interrupted";
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  reply_id?: string | null;
  message_phase?: "commentary" | "final_answer" | null;
  content: string;
  hidden?: boolean;
  created_at: string;
  model?: string | null;
  fallback_used?: boolean;
  action?: "answer" | "propose_ingest" | "propose_expand" | null;
  planning_status?: string | null;
  planning_error?: string | null;
  proposal_applied?: boolean;
  proposal?: ProposalGenerateResponse | null;
  inline_quiz?: InlineChatQuiz | null;
  question?: AgentQuestion | null;
  closure_quiz?: TopicQuizSession | null;
  activity?: { id: string; tool: string; status: "running" | "completed" | "failed"; detail: string } | null;
  agent_status?: "streaming" | "completed" | "interrupted" | "failed" | null;
};

export type AgentQuestion = {
  interaction_id: string;
  question: string;
  choices: string[];
  answer?: string | null;
  status: "pending" | "answered" | "interrupted";
};
export type AgentStatus = "idle" | "starting" | "running" | "waiting" | "completed" | "interrupted" | "failed";

export type GraphChatThread = {
  run_id: string | null;
  agent_status: AgentStatus;
  agent_error: string | null;
  last_event_id: number;
  session_id: string;
  graph_id: string;
  topic_id?: string | null;
  title?: string | null;
  created_at: string;
  updated_at: string;
  messages: ChatMessage[];
};

export type ChatSessionSummary = {
  session_id: string;
  graph_id: string;
  topic_id?: string | null;
  title?: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
};

export type GraphChatStreamEvent = ({ event_id?: number; session_id?: string; run_id?: string } & (
  | { type: "thread_state"; thread: GraphChatThread }
  | { type: "message"; message: ChatMessage }
  | { type: "turn_status" | "turn_completed"; status: AgentStatus; error?: string | null; turn_id?: string | null }
  | { type: "heartbeat" }
));

export type TopicLearningSignal = {
  topic_id: string;
  evidence_level: "none" | "manual_only" | "quiz";
  mastery_indicator: "insufficient_evidence" | "practice_needed" | "quiz_passed";
  quiz_attempts: number;
  latest_quiz_score: number | null;
  latest_quiz_at: string | null;
  failure_count: number;
  blocked_prerequisite_ids: string[];
  next_review_at: string | null;
  review_due: boolean;
};

export type LearningRecommendation = {
  topic_id: string;
  action: "study" | "practice" | "review" | "verify" | "unblock" | "repair_graph";
  priority: number;
  reason: string;
  decision_rule: string;
  evidence: string[];
  related_topic_ids: string[];
  completion_condition: string;
};

export type LearningPlan = {
  graph_id: string;
  graph_version: number;
  evaluated_at: string;
  total_topics: number;
  completed_topics: number;
  certified_topics: number;
  manual_only_topics: number;
  due_reviews: number;
  blocked_topics: number;
  signals: TopicLearningSignal[];
  recommendations: LearningRecommendation[];
  graph_warnings: string[];
  method: string;
};

export type GraphAssessment = {
  graph_id: string;
  cards: Array<{
    label: string;
    value: string;
    tone: "neutral" | "good" | "warn";
    rationale: string;
  }>;
};

export type ProposalMode = "ingest_topics" | "expand_goal";
export type ProposalStatus = "proposed" | "reviewed" | "rejected" | "applied";

export type ProposalGenerateRequest = {
  mode: ProposalMode;
  raw_text: string;
  target_goal: string;
  instructions: string;
  source_items: Array<{
    title: string;
    description: string;
    estimated_minutes?: number | null;
    testing_notes: string;
    links: Array<{ label: string; url: string }>;
  }>;
  model?: string | null;
};

export type GraphProposal = {
  graph_id: string;
  user_prompt: string;
  summary: string;
  assistant_message: string;
  warnings: string[];
  assumptions: string[];
  operations: Array<{
    op: string;
    topic_id?: string | null;
    edge_id?: string | null;
    zone_id?: string | null;
    state?: TopicState | null;
    topic?: Topic | null;
    edge?: Edge | null;
    zone?: Zone | null;
  }>;
};

export type GraphOperation = {
  op_id: string;
  op: string;
  entity_kind: "topic" | "edge" | "zone" | "mastery";
  status: ProposalStatus;
  depends_on: string[];
  rationale: string;
  topic_id?: string | null;
  edge_id?: string | null;
  zone_id?: string | null;
  state?: TopicState | null;
  topic?: {
    id: string;
    title: string;
    slug: string;
    description: string;
    difficulty: number;
    estimated_minutes: number;
    level: number;
    state: TopicState;
    zones: string[];
    resources: Array<{ label: string; url: string; kind?: string }>;
  } | null;
  edge?: Edge | null;
  zone?: Zone | null;
};

export type GraphProposalEnvelope = {
  protocol_version: string;
  kind: "graph_proposal";
  workspace_id: string;
  graph_id: string;
  proposal_id: string;
  base_graph_version?: number | null;
  mode: ProposalMode;
  intent: {
    user_prompt: string;
    target_goal: string;
    instructions: string;
  };
  source_bundle: {
    raw_text: string;
    source_items: Array<unknown>;
    grounding_enabled: boolean;
  };
  summary: string;
  assistant_message: string;
  assumptions: string[];
  warnings: string[];
  open_questions: Array<{
    id: string;
    kind: string;
    message: string;
    impact: "low" | "medium" | "high";
    suggested_resolution: string;
  }>;
  operations: GraphOperation[];
  provenance: {
    model: string;
    grounding_used: boolean;
    generated_at: string;
    search_queries: string[];
    source_urls: string[];
  };
};

export type ApplyPlanEnvelope = {
  protocol_version: string;
  kind: "apply_plan";
  proposal_id: string;
  base_graph_version?: number | null;
  graph_id: string;
  validation: {
    ok: boolean;
    errors: string[];
    warnings: string[];
  };
  normalized_proposal: GraphProposal;
  patch_groups: Array<{
    group_id: string;
    label: string;
    operations: GraphOperation[];
  }>;
  preview: {
    topic_add_count: number;
    edge_add_count: number;
    zone_add_count: number;
    zone_update_count: number;
    mastery_update_count: number;
  };
};

export type ProposalGenerateResponse = {
  proposal_envelope: GraphProposalEnvelope;
  apply_plan: ApplyPlanEnvelope;
  trace: {
    model: string;
    mode: ProposalMode;
    used_grounding: boolean;
    raw_text_present: boolean;
    source_item_count: number;
    usage_metadata: Record<string, unknown>;
  };
  display: {
    summary: string;
    highlights: string[];
  };
};

export type ReasoningEffort = "none" | "minimal" | "low" | "medium" | "high" | "xhigh" | "max" | "ultra";
export type ChatGPTModel = {
  id: string;
  model: string;
  displayName: string;
  description: string;
  isDefault: boolean;
};
export type ChatGPTLogin = {
  loginId: string;
  authUrl: string;
  phase: "pending" | "completing";
};
export type ChatGPTAccount = {
  connected: boolean;
  authenticated: boolean;
  sharing: boolean;
  can_disconnect: boolean;
  account: { email?: string | null; name?: string | null } | null;
  login: ChatGPTLogin | null;
  error: string | null;
  models: ChatGPTModel[];
};

export type WorkspaceConfig = {
  agent_backend: "chatgpt" | "ollama" | "openai_api" | "codex_cli" | "ruflo_native";
  ruflo_enabled: boolean;
  default_model: string | null;
  reasoning_effort: ReasoningEffort | null;
  ui_language: string;
  canonical_graph_language: string;
  disable_idle_animations: boolean;
  memory_mode: "balanced" | "max" | "custom";
  assistant_nickname: string;
  persona_rules: string;
  quiz_question_count: number;
  pass_threshold: number;
  enable_closure_tests: boolean;
  debug_mode_enabled: boolean;
  memory_history_message_limit: number;
  memory_include_graph_context: boolean;
  memory_include_progress_context: boolean;
  memory_include_quiz_context: boolean;
  memory_include_frontier_context: boolean;
  memory_include_selected_topic_context: boolean;
  allow_explore_without_closure: boolean;
  require_prerequisite_closure_for_completion: boolean;
};

export type DebugLogEntry = {
  id: string;
  created_at: string;
  kind: "frontend" | "api" | "server";
  level: "info" | "error";
  title: string;
  message: string;
  method?: string | null;
  path?: string | null;
  status_code?: number | null;
  duration_ms?: number | null;
  request_excerpt?: string | null;
  response_excerpt?: string | null;
  stack?: string | null;
};

export type DebugLogSnapshot = {
  file_path: string;
  frontend: DebugLogEntry[];
  api: DebugLogEntry[];
  server: DebugLogEntry[];
};

export type SnapshotRecord = {
  id: number;
  created_at: string;
  source: string;
  reason?: string | null;
  parent_snapshot_id?: number | null;
};

export type GraphExportPackagePayload = {
  kind: string;
  version: number;
  exported_at: string;
  source_graph_id: string;
  title: string;
  include_progress: boolean;
  graph: GraphEnvelope;
};

export type GraphExportFormat = "mapmind_graph_export" | "mapmind_obsidian_export";

export type ObsidianExportOptions = {
  use_folders_as_zones: boolean;
  include_descriptions: boolean;
  include_resources: boolean;
  include_artifacts: boolean;
};

export type ObsidianExportFilePayload = {
  path: string;
  body: string;
};

export type ObsidianGraphExportPackagePayload = {
  kind: "mapmind_obsidian_export";
  version: number;
  exported_at: string;
  source_graph_id: string;
  title: string;
  include_progress: boolean;
  folder_name: string;
  file_count: number;
  files: ObsidianExportFilePayload[];
};

export type WorkspaceEnvelope = {
  snapshot: SnapshotRecord;
  workspace: {
    title: string;
    active_graph_id: string | null;
    config: WorkspaceConfig;
    graphs: GraphEnvelope[];
    learner_profile?: LearnerProfile;
  };
};

export type LearnerLevel = "beginner" | "intermediate" | "advanced";
export type RoadmapLanguage = "pt" | "en" | "ru" | "uk";
export type LearnerProfile = {
  display_name: string;
  profession: string;
  interests: string[];
  level: LearnerLevel;
  goal: string;
  github: string;
  instagram: string;
  onboarding_complete: boolean;
};

export type RoadmapGenerateRequest = {
  topic: string;
  profession: string;
  level: LearnerLevel;
  goal: string;
  language: RoadmapLanguage;
  model?: string | null;
};

export type RoadmapSource = { label: string; url: string; kind?: "encyclopedia" | "research" | "book" };
export type RoadmapTopic = {
  title: string;
  description: string;
  outcome: string;
  stage: number;
  estimated_minutes: number;
  prerequisites: number[];
  resources: RoadmapSource[];
};
export type RoadmapPreview = {
  title: string;
  subject: string;
  description: string;
  language: RoadmapLanguage;
  resource_search_status: "available" | "limited" | "unavailable";
  topics: RoadmapTopic[];
};
export type RoadmapPreviewResponse = { ticket: string; preview: RoadmapPreview };
