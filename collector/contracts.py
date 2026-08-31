"""
types.py
========

TypedDict boundaries for the collector data flowing between modules
(legacy-plan item A3, closed 2026-08-31): the shapes of the JSONL summary
(`summarize` output), the native usage rollups (`native_usage` output) and
the pricing info the reconciler hands to the build are declared once here
and used in the module signatures.  Static-only — nothing here runs.
"""

from __future__ import annotations

from typing import Dict, List, Optional, TypedDict


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
