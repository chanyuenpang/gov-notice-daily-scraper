# v2 部署与运维指南

> 版本: 1.0 | 日期: 2026-04-28

## 1. 运行前提

| 依赖 | 说明 |
|------|------|
| **Python 3.10+** | 运行编排脚本和日报生成 |
| **browser-agent** | OpenClaw 内置的 MCP 真实浏览器 subagent，用于实际抓取 |
| **OpenClaw** | 编排调度层，通过 `sessions_spawn` 派发 browser-agent |
| **cron (可选)** | 系统定时任务，触发每日流水线 |

不需要安装 Playwright 或无头浏览器，browser-agent 通过 MCP 控制真实浏览器。

## 2. 推荐目录结构

```
gov-notice-daily-scraper/
├── config/
│   ├── urls.json              # 主配置（24 站）
│   ├── urls-test.json         # 测试配置（3 站）
│   └── urls-v2.json           # v2 配置
├── cron/
│   ├── daily-gov-notice-v2.example.sh   # 每日流水线示例脚本
│   └── crontab.example                 # crontab 示例
├── docs/
│   ├── deployment-v2.md                 # 本文档
│   ├── architecture-v2.md               # 架构说明
│   ├── browser-agent-architecture.md    # browser-agent 架构
│   ├── browser-agent-task-template.md   # 抓取任务模板
│   └── json-schema.md                   # JSON 规范
├── frontend/                            # 前端展示页
├── logs/                                # 运行日志（.gitkeep 占位）
├── output/
│   └── {YYYY-MM-DD}/
│       ├── announcements.json           # 统一公告数据
│       ├── crawl-meta.json              # 抓取元信息
│       └── crawl-tasks.json             # 抓取任务列表
├── scripts/
│   ├── browser_agent_crawl.py           # 生成 crawl-tasks
│   ├── browser_agent_pipeline.py        # 编排入口
│   ├── generate_report_v2.py            # 日报生成
│   └── incremental_analysis_v2.py       # 增量分析
└── templates/
    └── report-template.md               # 日报模板
```

## 3. 每日运行流程

```
08:00  cron 触发 daily-gov-notice-v2.example.sh
  │
  ├─ Step 1: 生成抓取任务
  │   python3 scripts/browser_agent_crawl.py --date $(date +%F)
  │   → 输出 output/{date}/crawl-tasks.json
  │
  ├─ Step 2: 派发 browser-agent 抓取
  │   由 OpenClaw sessions_spawn 逐站派发 browser-agent subagent
  │   每个 subagent 按 crawl-tasks.json 中的模板执行
  │   → 输出 output/{date}/announcements.json
  │
  ├─ Step 3: 生成日报
  │   python3 scripts/generate_report_v2.py --date $(date +%F)
  │   → 输出 output/{date}/daily-report.md
  │
  └─ Step 4: 增量分析
      python3 scripts/incremental_analysis_v2.py --date $(date +%F)
      → 输出 output/{date}/incremental-report.md
```

### 注意

Step 2（browser-agent 派发）需要 OpenClaw 运行环境。如果使用纯 cron，只能完成 Step 1/3/4；browser-agent 抓取需通过 OpenClaw skill 或对话手动/半自动触发。

推荐方案：cron 负责 Step 1/3/4，browser-agent 抓取由 OpenClaw 定时 skill 自动派发，或每天手动确认。

## 4. 失败处理建议

| 场景 | 处理方式 |
|------|----------|
| 单站抓取失败 | crawl-meta.json 记录失败站点，不影响其他站；下次运行自动重试 |
| 全站抓取失败（如网络中断） | cron 脚本退出码非 0，检查 logs/cron.log |
| 日报生成失败 | announcements.json 为空时生成空日报，标注"无新公告" |
| browser-agent 超时 | 单站设置合理超时（建议 60s），超时跳过并记录 |
| 连续 3 天同一站失败 | 人工检查该站是否改版或下线 |

## 5. 日志建议

- **cron 日志**: `logs/cron.log` — 记录每次流水线的 stdout/stderr
- **抓取元信息**: `output/{date}/crawl-meta.json` — 记录每站状态、耗时、错误信息
- **日志轮转**: 建议配合 `logrotate` 或手动定期清理，避免日志过大
- **关键日志保留**: 建议至少保留最近 30 天日志

### 日志轮转示例（/etc/logrotate.d/gov-notice）

```
/home/yankeeting/.openclaw/projects/gov-notice-daily-scraper/logs/cron.log {
    daily
    rotate 30
    compress
    missingok
    notifempty
}
```

## 6. 自动调度（OpenClaw Cron）

本项目使用 OpenClaw 内置 cron 调度，非系统 crontab。

| 配置项 | 值 |
|--------|-----|
| Job 名称 | daily-gov-notice-v2 |
| Job ID | a5efcd08-372e-4fd6-b4bd-6e69fd238da0 |
| 调度时间 | 每天 06:00 (Asia/Shanghai) |
| 执行 Agent | cron-runner |
| Session | isolated |
| Timeout | 1800s |

### 执行链路
```
cron 触发 → cron-runner → sessions_spawn(browser-agent) → 抓取公告 → 写入 announcements.json
```

### 手动操作
- 手动触发：`openclaw cron run a5efcd08-372e-4fd6-b4bd-6e69fd238da0`
- 查看记录：`openclaw cron runs --id a5efcd08-372e-4fd6-b4bd-6e69fd238da0 --limit 10`
- 查看所有 job：`openclaw cron list`
