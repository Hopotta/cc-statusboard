import type {
  DailyActivity,
  ModelStat,
  ProjectStat,
  Statusboard,
  StatusboardPayload,
  ToolUsage,
} from "../types";

const DAILY_TOKEN_KEYS = [
  "tokens",
  "inputTokens",
  "outputTokens",
  "cacheCreationTokens",
  "cacheReadTokens",
] as const;

/** Connected sources in a legacy artifact still behave as one Claude feed. */
export function connectedAgentIds(data: Statusboard): string[] {
  if (data.agents) {
    return data.agents
      .filter((agent) => agent.state === "connected")
      .map((agent) => agent.id);
  }
  return ["claude-code"];
}

export function selectAgentData(
  data: Statusboard,
  selected: Set<string>,
): StatusboardPayload | null {
  const connected = connectedAgentIds(data);
  const selectedConnected = connected.filter((id) => selected.has(id));
  if (!selectedConnected.length) return null;
  if (selectedConnected.length === connected.length) return data;
  const bodies = selectedConnected
    .map((id) => data.agentData?.[id])
    .filter((body): body is StatusboardPayload => Boolean(body));
  if (!bodies.length) return null;
  return mergePayloads(bodies);
}

function mergePayloads(bodies: StatusboardPayload[]): StatusboardPayload {
  const totalTokens = bodies.reduce((sum, body) => sum + body.summary.totalTokens, 0);
  const totalTasks = bodies.reduce((sum, body) => sum + body.summary.totalTasks, 0);
  const totalTime = bodies.reduce((sum, body) => sum + body.summary.totalTime, 0);
  const totalCost = bodies.reduce((sum, body) => sum + body.tokens.cost, 0);
  const models = mergeModels(bodies.flatMap((body) => body.models), totalTokens);
  const dailyActivity = mergeDaily(bodies.flatMap((body) => body.dailyActivity));
  const projects = mergeProjects(bodies.flatMap((body) => body.projects));
  const sessions = bodies.flatMap((body) => body.sessions);
  const toolUsage = mergeToolUsage(bodies.map((body) => body.advanced.toolUsage));
  const promptCategories = mergePromptCategories(bodies);
  const durations = bodies.reduce(
    (acc, body) => ({
      longest: Math.max(acc.longest, body.advanced.taskDurations.longest),
      count: acc.count + body.advanced.taskDurations.count,
      // Per-agent percentiles are intentionally not re-labelled as an exact
      // pooled percentile. The detailed duration panel uses longest/count.
      p50: Math.max(acc.p50, body.advanced.taskDurations.p50),
      p90: Math.max(acc.p90, body.advanced.taskDurations.p90),
    }),
    { longest: 0, count: 0, p50: 0, p90: 0 },
  );
  const tokens = {
    total: totalTokens,
    input: bodies.reduce((sum, body) => sum + body.tokens.input, 0),
    output: bodies.reduce((sum, body) => sum + body.tokens.output, 0),
    cacheCreation: bodies.reduce((sum, body) => sum + body.tokens.cacheCreation, 0),
    cacheRead: bodies.reduce((sum, body) => sum + body.tokens.cacheRead, 0),
    cost: totalCost,
  };
  const promptTotal = tokens.input + tokens.cacheCreation + tokens.cacheRead;
  const latest = bodies.reduce((latestValue, body) =>
    body.generatedAt > latestValue ? body.generatedAt : latestValue,
  bodies[0].generatedAt);
  // A selection can combine independently priced adapters (Claude's ccusage
  // estimate and Codex's API-equivalent rates).  The old ccusage-only check
  // incorrectly downgraded that valid mixed selection to "none", which made
  // the Spend tile claim that no pricing data was available.
  const pricedBodies = bodies.filter(
    (body) => body.meta?.pricingSource && body.meta.pricingSource !== "none",
  );
  const pricingSources = new Set(pricedBodies.map((body) => body.meta!.pricingSource));
  const pricingSource = pricingSources.size > 1
    ? "mixed"
    : pricingSources.values().next().value ?? "none";
  const coveredTokens = pricedBodies.reduce(
    (sum, body) => sum + body.summary.totalTokens * (body.meta?.pricingCoverage ?? 0),
    0,
  );
  const priceDates = pricedBodies
    .map((body) => body.meta?.pricingAsOf)
    .filter((date): date is string => Boolean(date));
  const ccusageMetas = bodies.map((body) => body.meta)
    .filter((meta): meta is NonNullable<StatusboardPayload["meta"]> => meta?.pricingSource === "ccusage");

  return {
    summary: {
      totalTokens,
      totalTasks,
      totalTime,
      totalTimeHuman: formatSecondsCompact(totalTime),
      averageTask: totalTasks ? Math.floor(totalTime / totalTasks) : 0,
      averageTaskHuman: formatSecondsCompact(totalTasks ? Math.floor(totalTime / totalTasks) : 0),
      mostUsedModel: models[0]
        ? { modelName: models[0].modelName, totalTokens: models[0].totalTokens, sharePct: models[0].sharePct }
        : null,
      totalCost,
    },
    tokens,
    models,
    tasks: {
      total: totalTasks,
      activeSeconds: totalTime,
      activeHuman: formatSecondsCompact(totalTime),
      averageSeconds: totalTasks ? Math.floor(totalTime / totalTasks) : 0,
      averageHuman: formatSecondsCompact(totalTasks ? Math.floor(totalTime / totalTasks) : 0),
      longestSeconds: durations.longest,
      longestAverageSeconds: Math.max(...projects.map((project) => project.averageSeconds), 0),
      busiestDay: [...dailyActivity].sort((a, b) => b.tasks - a.tasks)[0] ?? null,
      hourlyTasks: bodies[0].tasks.hourlyTasks.map((_, index) =>
        bodies.reduce((sum, body) => sum + (body.tasks.hourlyTasks[index] ?? 0), 0),
      ),
    },
    projects,
    sessions,
    dailyActivity,
    advanced: {
      toolUsage,
      workflowTimeline: {
        sessions: bodies.flatMap((body) => body.advanced.workflowTimeline.sessions)
          .sort((a, b) => b.lastEvent.localeCompare(a.lastEvent))
          .slice(0, 10),
        count: bodies.reduce((sum, body) => sum + body.advanced.workflowTimeline.count, 0),
      },
      promptCategories,
      taskDurations: durations,
      modelEfficiency: {
        tokensPerTask: totalTasks ? Math.floor(totalTokens / totalTasks) : 0,
        costPerTask: totalTasks ? totalCost / totalTasks : 0,
        outputRatio: totalTokens ? tokens.output / totalTokens : 0,
        cacheShare: promptTotal ? tokens.cacheRead / promptTotal : 0,
        cacheReadTokens: tokens.cacheRead,
        cacheCreationTokens: tokens.cacheCreation,
        inputTokens: tokens.input,
        totalTokens,
        totalCost,
      },
    },
    generatedAt: latest,
    meta: {
      pricingSource,
      pricingAsOf: priceDates.sort().at(-1) ?? null,
      pricingCoverage: totalTokens && pricedBodies.length
        ? coveredTokens / totalTokens
        : null,
      ccusageReconciledAt: ccusageMetas.map((meta) => meta.ccusageReconciledAt)
        .filter((date): date is string => Boolean(date)).sort().at(-1) ?? null,
      ccusageTotalTokens: ccusageMetas.reduce(
        (sum, meta) => sum + (meta.ccusageTotalTokens ?? 0), 0,
      ) || null,
      ccusageOtherAgentsTokens: ccusageMetas.reduce(
        (sum, meta) => sum + (meta.ccusageOtherAgentsTokens ?? 0), 0,
      ) || null,
      totalTokensDiffPct: ccusageMetas.length === 1
        ? ccusageMetas[0].totalTokensDiffPct
        : null,
    },
  };
}

function mergeModels(models: ModelStat[], totalTokens: number): ModelStat[] {
  const result = new Map<string, ModelStat>();
  for (const model of models) {
    const current = result.get(model.modelName) ?? {
      ...model, totalTokens: 0, inputTokens: 0, outputTokens: 0,
      cacheCreationTokens: 0, cacheReadTokens: 0, cost: 0, sharePct: 0,
    };
    current.totalTokens += model.totalTokens;
    current.inputTokens += model.inputTokens;
    current.outputTokens += model.outputTokens;
    current.cacheCreationTokens = (current.cacheCreationTokens ?? 0) + (model.cacheCreationTokens ?? 0);
    current.cacheReadTokens = (current.cacheReadTokens ?? 0) + (model.cacheReadTokens ?? 0);
    current.cost += model.cost;
    result.set(model.modelName, current);
  }
  return [...result.values()]
    .map((model) => ({ ...model, sharePct: totalTokens ? (model.totalTokens / totalTokens) * 100 : 0 }))
    .sort((a, b) => b.totalTokens - a.totalTokens);
}

function mergeDaily(days: DailyActivity[]): DailyActivity[] {
  const result = new Map<string, DailyActivity>();
  for (const day of days) {
    const current = result.get(day.date) ?? {
      date: day.date, tokens: 0, inputTokens: 0, outputTokens: 0,
      cacheCreationTokens: 0, cacheReadTokens: 0, cost: 0, tasks: 0, activeSeconds: 0,
    };
    for (const key of DAILY_TOKEN_KEYS) current[key] += day[key];
    current.cost += day.cost;
    current.tasks += day.tasks;
    current.activeSeconds += day.activeSeconds;
    result.set(day.date, current);
  }
  return [...result.values()].sort((a, b) => a.date.localeCompare(b.date));
}

function mergeProjects(projects: ProjectStat[]): ProjectStat[] {
  const result = new Map<string, ProjectStat>();
  for (const project of projects) {
    const key = project.projectPath ?? project.project;
    const current = result.get(key) ?? { ...project, tokens: 0, tasks: 0, activeSeconds: 0, cost: 0, files: 0, averageSeconds: 0 };
    current.tokens += project.tokens;
    current.tasks += project.tasks;
    current.activeSeconds += project.activeSeconds;
    current.cost += project.cost;
    current.files += project.files;
    current.averageSeconds = current.tasks ? Math.floor(current.activeSeconds / current.tasks) : 0;
    current.activeHuman = formatSecondsCompact(current.activeSeconds);
    result.set(key, current);
  }
  return [...result.values()].sort((a, b) => b.tokens - a.tokens);
}

function mergeToolUsage(usages: ToolUsage[]): ToolUsage {
  const tools = new Map<string, number>();
  const byProject = new Map<string, Map<string, number>>();
  for (const usage of usages) {
    for (const tool of usage.tools) tools.set(tool.name, (tools.get(tool.name) ?? 0) + tool.count);
    for (const [project, entries] of Object.entries(usage.byProject)) {
      const projectTools = byProject.get(project) ?? new Map<string, number>();
      for (const tool of entries) projectTools.set(tool.name, (projectTools.get(tool.name) ?? 0) + tool.count);
      byProject.set(project, projectTools);
    }
  }
  const sortedTools = [...tools.entries()].map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count);
  return {
    tools: sortedTools,
    byProject: Object.fromEntries([...byProject.entries()].map(([project, entries]) => [
      project,
      [...entries.entries()].map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count),
    ])),
    total: sortedTools.reduce((sum, tool) => sum + tool.count, 0),
    uniqueTools: sortedTools.length,
  };
}

function mergePromptCategories(bodies: StatusboardPayload[]) {
  const categories = new Map<string, { slug: string; label: string; count: number }>();
  for (const body of bodies) {
    for (const category of body.advanced.promptCategories.categories) {
      const current = categories.get(category.slug) ?? { ...category, count: 0 };
      current.count += category.count;
      categories.set(category.slug, current);
    }
  }
  const total = [...categories.values()].reduce((sum, category) => sum + category.count, 0);
  return {
    classifierVersion: bodies.map((body) => body.advanced.promptCategories.classifierVersion).filter(Boolean).join(" + ") || undefined,
    categories: [...categories.values()].map((category) => ({
      ...category,
      sharePct: total ? (category.count / total) * 100 : 0,
    })),
    total,
  };
}

function formatSecondsCompact(value: number): string {
  if (!value) return "0m";
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  return hours ? (minutes ? `${hours}h ${minutes}m` : `${hours}h`) : `${minutes}m`;
}
