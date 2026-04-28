# Browser-Agent 抓取架构说明

> 版本: 1.0 | 日期: 2026-04-28

## 1. 旧 Playwright 流程 vs 新 Browser-Agent 流程

### 旧流程（Python Playwright）

```
config/urls.json
    ↓
scripts/orchestrator.py / scripts/run_pipeline.py
    ↓
scripts/crawl_batch.py (Python Playwright 并发抓取)
    ↓
CSS 选择器解析 / 语义解析
    ↓
output/{date}/stage1_results.json
    ↓
scripts/stage2_*.py (详情页二次抓取)
    ↓
output/{date}/combined_results.json / incremental_results.json
```

**痛点：**
- Playwright 脚本需为每个站点维护 CSS 选择器规则（`config/rules/*.json`）
- 站点改版导致选择器失效，维护成本高
- 需要本地安装浏览器二进制文件
- 并发控制和错误处理逻辑复杂

### 新流程（Browser-Agent Subagent）

```
config/urls.json / urls-test.json
    ↓
scripts/browser_agent_pipeline.py (编排入口，生成计划)
    ↓
output/{date}/crawl-plan.json (任务模板列表)
    ↓
OpenClaw browser-agent subagent (逐站执行)
    ↓ 每站产出 task_{siteId}.json
scripts/browser_agent_pipeline.py (或后续合并脚本)
    ↓
output/{date}/announcements.json + crawl-meta.json
```

**优势：**
- browser-agent 是 MCP 驱动的真实浏览器，自动处理 JS 渲染
- 提取逻辑由 LLM 语义理解驱动，不依赖硬编码 CSS 选择器
- 编排逻辑与抓取执行解耦，便于独立调试
- 任务粒度为单站，失败可单独重试

## 2. 新流程的阶段划分

### Phase 1: 编排准备

- 运行 `scripts/browser_agent_pipeline.py`
- 读取站点配置，生成 `crawl-plan.json`（含所有任务模板）
- 初始化 `announcements.json`（空数组）和 `crawl-meta.json`（骨架）

### Phase 2: Browser-Agent 执行

- OpenClaw 主 agent 读取 `crawl-plan.json`
- 为每个任务 spawn browser-agent subagent
- 每个 subagent 按照任务模板中的 prompt 访问目标 URL 并提取数据
- 产出 `task_{siteId}.json`，包含提取到的公告列表

### Phase 3: 合并归档

- 读取所有 `task_{siteId}.json`
- 合并公告到 `announcements.json`（扁平数组，遵循 `docs/json-schema.md`）
- 更新 `crawl-meta.json` 的统计信息（成功/失败数、公告总数等）

### Phase 4: 后处理（可选，暂不实现）

- 去重（与历史数据比对）
- 详情页深度抓取（如需 `content` 字段）
- 日报生成 / 飞书通知

## 3. 试跑指南

### 步骤 1: 使用 urls-test.json 小范围试跑

```bash
cd /home/yankeeting/.openclaw/projects/gov-notice-daily-scraper

# 生成试跑计划（默认使用 urls-test.json，仅 3 个站点）
python scripts/browser_agent_pipeline.py --config config/urls-test.json

# 或指定日期
python scripts/browser_agent_pipeline.py --config config/urls-test.json --date 2026-04-28

# 仅预览不写文件
python scripts/browser_agent_pipeline.py --dry-run
```

### 步骤 2: 查看生成的抓取计划

```bash
cat output/2026-04-28/crawl-plan.json | python -m json.tool | head -50
```

### 步骤 3: 逐站试跑 browser-agent

通过 OpenClaw 对话，让主 agent 读取 `crawl-plan.json` 中的任务，逐个 spawn browser-agent subagent 执行。

### 步骤 4: 检查结果

```bash
# 查看单站产出
cat output/2026-04-28/task_xm_hrss.json | python -m json.tool

# 合并后检查
cat output/2026-04-28/announcements.json | python -m json.tool
cat output/2026-04-28/crawl-meta.json | python -m json.tool
```

### 全量运行

验证试跑成功后，改用完整配置：

```bash
python scripts/browser_agent_pipeline.py --config config/urls.json
```

## 4. 文件清单

| 文件 | 说明 |
|---|---|
| `scripts/browser_agent_pipeline.py` | 编排入口，生成计划与初始化输出文件 |
| `docs/browser-agent-task-template.md` | browser-agent 单站任务的 prompt 模板与返回格式 |
| `docs/browser-agent-architecture.md` | 本文档，架构说明 |
| `docs/json-schema.md` | 统一公告 JSON 输出规范（已有） |

## 5. 与旧脚本的兼容

旧脚本（`scripts/orchestrator.py`、`scripts/crawl_batch.py`、`scripts/stage2_*.py` 等）**全部保留**，不做删除或修改。
新流程是独立的新入口，两者互不干扰。
