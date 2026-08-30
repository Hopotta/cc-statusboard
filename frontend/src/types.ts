export interface StatusboardSummary {
  totalTokens: number;
  totalTasks: number;
  totalTime: number; // seconds
  totalTimeHuman: string;
  averageTask: number; // seconds
  averageTaskHuman: string;
  totalCost: number;
  mostUsedModel: { modelName: string; totalTokens: number; sharePct: number } | null;
}

export interface ModelStat {
  modelName: string;
  totalTokens: number;
  inputTokens: number;
  outputTokens: number;
  cacheCreationTokens?: number;
  cacheReadTokens?: number;
  cost: number;
  sharePct: number;
}

export interface TokenTotals {
  total: number;
  input: number;
  output: number;
  cacheCreation: number;
  cacheRead: number;
  cost: number;
}

export interface TaskStats {
  total: number;
  activeSeconds: number;
  activeHuman: string;
  averageSeconds: number;
  averageHuman: string;
  longestSeconds: number;
  longestAverageSeconds: number;
  busiestDay: { date: string; tasks: number; activeSeconds: number } | null;
  hourlyTasks: number[];
}

export interface ProjectStat {
  project: string;
  projectPath: string | null;
  tasks: number;
  activeSeconds: number;
  activeHuman: string;
  tokens: number;
  cost: number;
  files: number;
  averageSeconds: number;
}

export interface DailyActivity {
  date: string;
  tokens: number;
  inputTokens: number;
  outputTokens: number;
  cacheCreationTokens: number;
  cacheReadTokens: number;
  cost: number;
  tasks: number;
  activeSeconds: number;
}

export interface Statusboard {
  summary: StatusboardSummary;
  tokens: TokenTotals;
  models: ModelStat[];
  tasks: TaskStats;
  projects: ProjectStat[];
  sessions: SessionStat[];
  dailyActivity: DailyActivity[];
  advanced: {
    toolUsage: ToolUsage;
    workflowTimeline: WorkflowTimelinePayload;
    promptCategories: PromptCategoriesPayload;
    taskDurations: TaskDurations;
    modelEfficiency: ModelEfficiency | null;
  };
  generatedAt: string;
}

export interface ToolUsage {
  tools: Array<{ name: string; count: number }>;
  total: number;
  uniqueTools: number;
  byProject: Record<string, Array<{ name: string; count: number }>>;
}

export interface TimelineEvent {
  t: string;
  kind: "user" | "assistant" | "tool";
  label: string;
}

export interface TimelineSession {
  sessionId: string;
  file: string;
  events: TimelineEvent[];
  firstEvent: string;
  lastEvent: string;
}

export interface WorkflowTimelinePayload {
  sessions: TimelineSession[];
  count: number;
}

export interface PromptCategory {
  slug: string;
  label: string;
  count: number;
  sharePct: number;
}

export interface PromptCategoriesPayload {
  categories: PromptCategory[];
  total: number;
  examples: Record<string, string[]>;
}

export interface ModelEfficiency {
  tokensPerTask: number;
  costPerTask: number;
  outputRatio: number;
  /** cache_read / (cache_read + cache_creation + plain input) */
  cacheShare: number;
  cacheReadTokens: number;
  cacheCreationTokens: number;
  inputTokens: number;
  totalTokens: number;
  totalCost: number;
}

export interface TaskDurations {
  longest: number;
  count: number;
  p50: number;
  p90: number;
}

export interface SessionStat {
  sessionId: string;
  project: string;
  projectPath: string | null;
  files: number;
  tasks: number;
  activeSeconds: number;
  activeHuman: string;
  tokens: number;
  cost: number;
  averageSeconds: number;
  firstTs: string | null;
  lastTs: string | null;
}

export type Accent = "signal" | "mint" | "sun" | "fg";

export const ACCENT_CLASS: Record<Accent, string> = {
  signal: "text-signal",
  mint: "text-mint",
  sun: "text-sun",
  fg: "text-fg",
};