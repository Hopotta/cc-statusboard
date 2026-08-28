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
  busiestDay: { date: string; tasks: number; activeSeconds: number } | null;
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
  dailyActivity: DailyActivity[];
  generatedAt: string;
}