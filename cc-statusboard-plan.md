# Claude Code Statusboard 开发计划

## 1. 项目目标

开发一个本地 Web Statusboard，用于可视化 Claude Code 的 Agent 使用情况。

目标体验参考 Codex App 内置 Profile Statusboard：

- Token 使用统计
- Agent 活跃趋势
- 任务数量统计
- 工作时间统计
- 模型使用分析
- 项目维度分析
- 历史活动热力图

最终目标：

将 Claude Code 从 CLI 工具升级为具有可观测能力（Observability）的 Agent 工作台。

---

# 2. 总体技术方案

采用：

> 数据采集层 + 数据处理层 + 静态 Statusboard 前端

架构：
```

Claude Code CLI  
|  
|  
~/.claude/projects/*.jsonl  
|  
|  
Data Collector  
|  
|  
statusboard.json  
|  
|  
React Statusboard  
|  
|  
Browser  
localhost

````

---

# 3. 数据来源设计

系统使用两个数据源。

## 数据源 A：ccusage

用途：

负责 Token、Cost、Model 数据。

调用方式：

```bash
ccusage session --json
ccusage daily --json
ccusage claude daily --instances --json
````

获取：

- totalTokens
    
- inputTokens
    
- outputTokens
    
- cacheCreationTokens
    
- cacheReadTokens
    
- totalCost
    
- modelsUsed
    
- modelBreakdowns
    
- project instances
    

---

## 数据源 B：Claude Code JSONL 日志

路径：

```
~/.claude/projects/<project>/<session-id>.jsonl
```

用途：

补充 ccusage 缺失的数据：

- Task 数量
    
- Task 时间
    
- 活跃时间
    
- Average Task Duration
    

---

# 4. Statusboard 指标定义

## 4.1 Total Tokens

来源：

ccusage

字段：

```
totalTokens
```

计算：

```
Total Tokens =
sum(all sessions.totalTokens)
```

展示：

例如：

```
12.77M
```

---

## 4.2 Most Used Model

来源：

ccusage

字段：

```
modelBreakdowns
```

计算：

按照 token 数排序：

```
model_usage =
sum(model.totalTokens)
```

最大值：

```
Most Used Model
```

展示：

```
Claude Sonnet 4
78%
```

---

# 4.3 Total Tasks

来源：

JSONL

规则：

一个 Task 定义：

```
type=user
且
不包含 toolUseResult
```

即：

真实用户输入。

过滤：

```
tool response
system message
assistant message
```

计算：

```
Total Tasks =
count(valid user messages)
```

---

# 4.4 Total Time

不要使用 session wall-clock 时间。

原因：

长 session 可能跨越数天。

例如：

```
session start:
Jan 1

session end:
Jan 18
```

实际工作时间可能只有几个小时。

采用：

## Active Task Time

计算：

对于每个 user task：

```
task_start =
user message timestamp


task_end =
next user message timestamp
```

得到：

```
task_duration =
task_end - task_start
```

加入限制：

防止用户离开电脑：

```
max(task_duration, 2h)
```

超过阈值：

认为 inactive。

最终：

```
Total Time =
sum(active task duration)
```

---

# 4.5 Average Task

计算：

```
Average Task =
Total Time / Total Tasks
```

展示：

```
21m
```

如果对cc-usage的使用有疑惑，**可以（且必须）开若干个subagent**并行去获取[Introduction | ccusage](https://ccusage.com/guide/)网页内获得cc-usage如何使用的详细信息。

---

# 5. 数据处理模块设计

目录：

```
claude-statusboard/

├── collector/
│
│── ccusage_parser.py
│
│── jsonl_parser.py
│
│── aggregator.py
│
│── generate_statusboard.py
│
├── frontend/
│
├── statusboard.json
│
└── README.md
```

---

# 6. Collector 开发

## 6.1 ccusage collector

文件：

```
collector/ccusage_parser.py
```

功能：

执行：

```bash
ccusage session --json
```

解析 stdout。

输出：

```json
{
 "tokens": {
    "total": 12770000,
    "input": 5000000,
    "output":7000000
 },

 "models":{
    "claude-sonnet":80,
    "claude-opus":20
 }
}
```

---

## 6.2 JSONL parser

文件：

```
collector/jsonl_parser.py
```

功能：

扫描：

```
~/.claude/projects/
```

解析：

每条 message:

```json
{
"type":"user",
"timestamp":"",
"content":""
}
```

识别：

```
Task Event
```

输出：

```json
{
"tasks":128,

"active_time":
"45h44m"
}
```

---

# 7. 数据统一格式

生成：

```
statusboard.json
```

结构：

```json
{
 "summary":{

    "totalTokens":12770000,

    "totalTasks":128,

    "totalTime":164640,

    "averageTask":770

 },

 "models":[

 ],

 "dailyActivity":[

 ],

 "projects":[

 ]

}
```

---

# 8. Frontend Statusboard

技术：

```
React
Vite
TailwindCSS
Recharts
```

---

页面结构：

## Header Card

展示：

```
Total Tokens

Peak Tokens

Total Time

Current Streak

Longest Streak
```

---

## Activity Heatmap

参考 Github contribution graph：

数据：

```
dailyActivity
```

展示：

过去一年：

```
Jan Feb Mar Apr
□□□□■□□□□
□□■■■■□□
```

---

## Usage Analytics

图表：

Token trend:

```
daily tokens
```

Model distribution:

```
Sonnet
Opus
Haiku
```

---

## Task Analytics

展示：

```
Total Tasks

Average Task Duration

Longest Task

Most Active Day
```

---

## Project Statusboard

展示：

```
Project

tokens

tasks

time
```

例如：

```
Agent-RAG

8.2M tokens
48 tasks
20h
```

---

# 9. 自动更新机制

第一阶段：

手动刷新：

```
python generate_statusboard.py
```

生成：

```
statusboard.json
```

第二阶段：

加入 watcher：

监听：

```
~/.claude/projects/
```

发生变化：

自动更新。

---

# 10. CLI 集成

增加命令：

```bash
cc-statusboard
```

执行：

```
generate statusboard.json

open browser

localhost:3456
```

---

# 11. 开发阶段规划

## Phase 1: 数据层 MVP

目标：

生成正确 statusboard.json

完成：

- ccusage parser
    
- JSONL parser
    
- 指标计算
    
- 数据 schema
    

验收：

输出：

```
Total Tokens
Total Tasks
Total Time
Average Task
Most Used Model
```

准确。

---

## Phase 2: Web Statusboard

完成：

- React 页面
    
- 卡片
    
- 热力图
    
- 图表
    

---

## Phase 3: 实时化

增加：

- 文件监听
    
- 自动更新
    
- CLI shortcut
    

---

## Phase 4: 高级 Agent Analytics

增加：

- Agent workflow timeline
    
- Prompt 分类
    
- Tool 使用统计
    
- 项目比较
    
- 模型效率分析
    

---

# 12. 当前优先级

必须完成：

P0:

- 数据采集
    
- statusboard.json
    
- 五个核心指标
    

P1:

- Codex 风格 Statusboard UI
    

P2:

- 实时更新
    

P3:

- Agent 行为分析
    

---

# 13. 最终交付标准

用户执行：

```bash
claude statusboard
```

即可打开：

```
Claude Code Statusboard
```

看到：

- Token 使用
    
- Task 数量
    
- 工作时间
    
- 平均任务耗时
    
- 模型统计
    
- 项目统计
    
- 活动热力图
    

并且所有数据来自真实 Claude Code 使用记录。


---

补充一个架构层面的建议：你当前调研结果实际上已经证明了一点——**不要把 ccusage 当作数据库，而应该把它当作一个“官方统计引擎”**。你的 Statusboard 应该建立自己的中间数据层 `statusboard.json`（以后甚至 SQLite），ccusage 和 JSONL 都只是数据源。

这样未来扩展多 Agent（Claude Code + Codex + OpenCode + 自研 Agent）时，只需要增加 adapter：
```

Claude Adapter  
Codex Adapter  
OpenCode Adapter  
Custom Agent Adapter

```
      |
      v
```

Unified Agent Analytics Schema

```
      |
      v
```

Statusboard

```

这会比单纯复刻 Codex 页面更有长期价值。你现在设计的其实更接近一个 **Agent Observability Platform**。