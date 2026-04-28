# 架构说明 v2 — Browser-Agent 抓取方案

## 旧流程（v1 — Playwright 4阶段）

```
crawl_batch.py (Playwright)
  → stage2 (SKILL + Subagent 修规则)
  → merge_results.py
  → generate_daily_report.py
  → incremental_analysis.py
  → feishu_sender.py
```

特点：Python Playwright 无头浏览器直跑，stage2 依赖 skill 编排修复失败站点。

## 新流程（v2 — Browser-Agent 编排）

```
browser_agent_crawl.py (生成任务列表)
  → browser-agent subagent (真实浏览器抓取，逐站)
  → 结果收集 → announcements.json + crawl-meta.json
  → 日报生成（复用旧脚本）
  → 前端展示
```

特点：通过 MCP 控制真实浏览器（非无头），由 subagent 编排调度。

## 阶段划分

| 阶段 | 职责 | 工具 |
|------|------|------|
| 任务生成 | 读取配置，生成抓取任务 | browser_agent_crawl.py |
| 页面抓取 | 打开网页，提取公告列表 | browser-agent (MCP) |
| 数据存储 | 写入统一 JSON | announcements.json |
| 日报生成 | 从 JSON 生成日报 | generate_daily_report.py |
| 前端展示 | 展示 JSON 数据 | HTML + JS |

## 试跑步骤

1. 先用测试配置验证：
   `python3 scripts/browser_agent_crawl.py --test --dry-run`
2. 对少量站点实际抓取：
   通过 sessions_spawn 派发 browser-agent 执行 crawl-tasks.json 中的任务
3. 检查 output/{date}/announcements.json 是否符合 json-schema.md
4. 全量跑 24 个站点

## 文件结构

```
gov-notice-daily-scraper/
├── config/
│   ├── urls.json          # 主配置（24站）
│   ├── urls-test.json     # 测试配置（3站）
│   └── rules/             # 旧版规则（保留参考）
├── docs/
│   ├── json-schema.md     # 统一 JSON 规范
│   ├── browser-agent-task-template.md  # 抓取任务模板
│   └── architecture-v2.md # 本文档
├── scripts/
│   ├── browser_agent_crawl.py  # v2 入口
│   ├── crawl_batch.py          # v1 旧脚本（保留）
│   └── ...                     # 其他旧脚本保留
├── output/
│   └── {YYYY-MM-DD}/
│       ├── announcements.json   # 统一公告数据
│       ├── crawl-meta.json      # 抓取元信息
│       └── crawl-tasks.json     # 抓取任务列表
└── frontend/                    # 前端页面（待建）
```
