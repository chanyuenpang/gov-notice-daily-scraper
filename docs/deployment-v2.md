## 6. 自动调度（OpenClaw Cron）

本项目使用 OpenClaw 内置 cron 调度，非系统 crontab。

| 配置项 | 值 |
|--------|-----|
| Job 名称 | daily-gov-notice-v2 |
| Job ID | 5b8199ec-05b5-4129-829e-52a86bc3f957 |
| 调度时间 | 每天 12:00 (Asia/Shanghai) |
| 执行 Agent | cron-runner |
| Session | isolated |
| Timeout | 1800s |

### 推荐执行链路

```text
cron 触发
  → 进入项目目录
  → python3 scripts/daily_pipeline_entry.py --date {date}
  → Phase 1 生成 stage1_results.json / stage1_summary.json / .phase1_done
  → Phase 2-prep 生成 browser_agent_tasks.json
  → 如有任务，标准入口自动执行 Stage2，写入 stage2_results.json
  → Phase 3 合并可用补抓结果并执行 sync_pages_data.py
  → output/reports/{date}/run-summary.md 落盘执行摘要
```

### 重要说明

- `scripts/daily_pipeline_entry.py` 是仓库内唯一推荐的完整日跑入口。
- `scripts/run_daily.py --phase 1/2-prep/3` 只适用于分阶段调试，不应再被当成完整 cron payload。
- 所有中间产物统一以 `output/crawl-artifacts/{date}/` 为准，不再使用旧的月度任务文件命名作为阶段判断依据。

### 手动操作

- 手动触发：`openclaw cron run 5b8199ec-05b5-4129-829e-52a86bc3f957`
- 查看记录：`openclaw cron runs --id 5b8199ec-05b5-4129-829e-52a86bc3f957 --limit 10`
- 查看所有 job：`openclaw cron list`
