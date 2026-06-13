# 给彦庭抓取每日政府公告功能

本仓库的**标准入口**是：

```bash
python3 scripts/daily_pipeline_entry.py --date $(date +%F)
```

如果只需要单步执行，再使用 `scripts/run_daily.py` 的 `--phase` 参数。

## 真实执行顺序

1. Phase 1：脚本批量抓取
2. Phase 2-prep：分析失败站点并产出任务清单
3. Stage2 执行：标准入口在有任务时自动逐站补抓并写回 `stage2_results.json`
4. Phase 3：合并、同步与收口，并落盘 `output/reports/{date}/run-summary.md`

即使 Phase 1 不完整，标准入口也会继续推进到后续阶段，避免"停在 stage1"。

## 真实产物路径

- `output/notices/{YYYY-MM}/{siteId}.json`
- `output/crawl-artifacts/{YYYY-MM-DD}/stage1_results.json`
- `output/crawl-artifacts/{YYYY-MM-DD}/stage1_summary.json`
- `output/crawl-artifacts/{YYYY-MM-DD}/browser_agent_tasks.json`
- `output/crawl-artifacts/{YYYY-MM-DD}/stage2_results.json`

## Stage2 闭环执行（仓库外调度层 / subagent）

如需单独重跑 Stage2，可执行：

```bash
python3 scripts/run_stage2_execute.py --date $DATE
```

该脚本会逐站执行补抓，并将结果写入：
`output/crawl-artifacts/{DATE}/stage2_results.json`

`stage2_results.json` 采用如下兼容格式（可被 `run_daily.py` 的 `normalize_stage2_data()` 消费）：

```json
{
  "date": "YYYY-MM-DD",
  "results": [
    {
      "siteId": "...",
      "status": "success|failed",
      "announcements": [],
      "error": "..."
    }
  ]
}
```

## 说明

旧文档中若出现 `output/{date}/stage1_results.json` 之类路径，请以 `scripts/run_daily.py` 和 `scripts/daily_pipeline_entry.py` 的实际输出为准。
