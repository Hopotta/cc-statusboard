"""
contracts.py
============

TypedDict boundaries for the collector data flowing between modules
(legacy-plan item A3, closed 2026-08-31): the shapes of the JSONL summary
(`summarize` output), the native usage rollups (`native_usage` output) and
the pricing info the reconciler hands to the build are declared once here
and used in the module signatures.

The `Statusboard*` block below is the public contract: `statusboard.json`
itself.  It mirrors `frontend/src/types.ts` one-to-one — when these shapes
drift apart, one of the two is wrong.  Static-only — nothing here runs.
"""

from __future__ import annotations

from typing import Dict, List, Literal, NotRequired, Optional, TypedDict


class TokenUsage(TypedDict):
    inputTokens: int
    outputTokens: int
    cacheCreationTokens: int
    cacheReadTokens: int


class UsageTotals(TokenUsage):
    totalTokens: int
    totalCost: float


class ModelUsageRow(UsageTotals):
    modelName: str
    cost: float


class DailyUsageSlot(UsageTotals):
    date: str


class FilterStats(TypedDict):
    userEntries: int
    toolResult: int
    isMeta: int
    injected: int
    tasks: int


class ProjectSummaryRow(TypedDict):
    project: str
    projectPath: Optional[str]
    files: int
    tasks: int
    activeSeconds: int
    tokens: int
    modelUsage: Dict[str, TokenUsage]


class SessionSummaryRow(ProjectSummaryRow):
    sessionId: str
    firstTs: Optional[str]
    lastTs: Optional[str]


class JsonlSummary(TypedDict):
    totalTasks: int
    totalActiveSeconds: int
    projects: List[ProjectSummaryRow]
    sessions: List[SessionSummaryRow]
    filesScanned: int
    dailyTasks: List[Dict[str, object]]
    dailyActive: List[Dict[str, object]]
    hourlyTasks: List[int]
    filterStats: FilterStats


class UsageRollups(TypedDict):
    totals: UsageTotals
    models: List[ModelUsageRow]
    daily: List[DailyUsageSlot]


class PricingInfo(TypedDict):
    prices: Dict[str, float]
    asOf: Optional[str]
    modelTokens: Dict[str, int]


# --------------------------------------------------------------------------
# The public artifact contract: statusboard.json (mirrors types.ts).
# --------------------------------------------------------------------------


class MostUsedModel(TypedDict):
    modelName: str
    totalTokens: int
    sharePct: float


class StatusboardSummary(TypedDict):
    totalTokens: int
    totalTasks: int
    totalTime: int
    totalTimeHuman: str
    averageTask: int
    averageTaskHuman: str
    mostUsedModel: Optional[MostUsedModel]
    totalCost: float


class TokenTotals(TypedDict):
    total: int
    input: int
    output: int
    cacheCreation: int
    cacheRead: int
    cost: float


class ModelStat(TypedDict):
    modelName: str
    totalTokens: int
    inputTokens: int
    outputTokens: int
    cacheCreationTokens: int
    cacheReadTokens: int
    cost: float
    sharePct: float


class BusiestDay(TypedDict):
    date: str
    tokens: int
    tasks: int
    activeSeconds: int
    cost: float


class TaskStats(TypedDict):
    total: int
    activeSeconds: int
    activeHuman: str
    averageSeconds: int
    averageHuman: str
    longestSeconds: int
    longestAverageSeconds: int
    busiestDay: Optional[BusiestDay]
    hourlyTasks: List[int]
    filterStats: NotRequired[Optional[FilterStats]]


class ProjectStat(TypedDict):
    project: str
    projectPath: Optional[str]
    tasks: int
    activeSeconds: int
    activeHuman: str
    tokens: int
    cost: float
    files: int
    averageSeconds: int


class SessionStat(ProjectStat):
    sessionId: str
    firstTs: Optional[str]
    lastTs: Optional[str]


class DailyActivity(TypedDict):
    date: str
    tokens: int
    inputTokens: int
    outputTokens: int
    cacheCreationTokens: int
    cacheReadTokens: int
    cost: float
    tasks: int
    activeSeconds: int


class ToolCount(TypedDict):
    name: str
    count: int


class ToolUsage(TypedDict):
    tools: List[ToolCount]
    byProject: Dict[str, List[ToolCount]]
    total: int
    uniqueTools: int


class TimelineEvent(TypedDict):
    t: str
    kind: str  # "user" | "assistant" | "tool"
    label: str


class TimelineSession(TypedDict):
    sessionId: str
    events: List[TimelineEvent]
    firstEvent: str
    lastEvent: str


class WorkflowTimeline(TypedDict):
    sessions: List[TimelineSession]
    count: int


class PromptCategory(TypedDict):
    slug: str
    label: str
    count: int
    sharePct: float


class PromptCategories(TypedDict):
    classifierVersion: NotRequired[str]
    categories: List[PromptCategory]
    total: int


class TaskDurations(TypedDict):
    longest: int
    count: int
    p50: int
    p90: int


class ModelEfficiency(TypedDict):
    tokensPerTask: int
    costPerTask: float
    outputRatio: float
    cacheShare: float
    cacheReadTokens: int
    cacheCreationTokens: int
    inputTokens: int
    totalTokens: int
    totalCost: float


class Advanced(TypedDict):
    toolUsage: ToolUsage
    workflowTimeline: WorkflowTimeline
    promptCategories: PromptCategories
    taskDurations: TaskDurations
    modelEfficiency: Optional[ModelEfficiency]


class StatusboardMeta(TypedDict):
    pricingSource: Literal["ccusage", "none"]
    pricingAsOf: Optional[str]
    pricingCoverage: NotRequired[Optional[float]]
    ccusageReconciledAt: Optional[str]
    ccusageTotalTokens: Optional[int]
    ccusageOtherAgentsTokens: NotRequired[Optional[int]]
    totalTokensDiffPct: Optional[float]


class StatusboardArtifact(TypedDict):
    """The whole of statusboard.json — the stable public API."""
    summary: StatusboardSummary
    tokens: TokenTotals
    models: List[ModelStat]
    tasks: TaskStats
    projects: List[ProjectStat]
    sessions: List[SessionStat]
    dailyActivity: List[DailyActivity]
    advanced: Advanced
    generatedAt: str
    meta: NotRequired[StatusboardMeta]
