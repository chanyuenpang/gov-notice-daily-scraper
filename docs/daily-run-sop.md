# Daily Run SOP — 政府公告抓取 + 日报生成 + 飞书推送

> 本文档与仓库内真实入口同步：**优先使用 `scripts/daily_pipeline_entry.py`**。`scripts/run_daily.py` 仅作为阶段执行器，不再作为手动首选入口。

## 工作目录

```
/home/yankeeting/.openclaw/projects/gov-notice-daily-scraper
```

## 标准入口

```bash
python3 scripts/daily_pipeline_entry.py --date $(date +%F)
```

该入口会按顺序执行：
1. Phase 1：`scripts/run_daily.py --phase 1`
2. Phase 2-prep：`scripts/run_daily.py --phase 2-prep`
3. Stage2：如有待补抓任务，自动执行 `scripts/run_stage2_execute.py --date $DATE`
4. Phase 3：`scripts/run_daily.py --phase 3`
5. 落盘执行摘要：`output/reports/{DATE}/run-summary.md`

即使 Phase 1 失败，也会继续执行后续阶段，避免链路停在 stage1。

---

## 如果只想单独跑某一阶段

### Phase 1
```bash
python3 scripts/run_daily.py --date $DATE --phase 1
```

### Phase 2-prep
```bash
python3 scripts/run_daily.py --date $DATE --phase 2-prep
```

### Phase 3
```bash
python3 scripts/run_daily.py --date $DATE --phase 3
```

---

## 产物与路径真实约定

### Stage 1 / Phase 1
- 结果文件：`output/crawl-artifacts/{DATE}/stage1_results.json`
- 汇总文件：`output/crawl-artifacts/{DATE}/stage1_summary.json`
- 完成标记：`output/crawl-artifacts/{DATE}/.phase1_done`

### Phase 2-prep
- 任务文件：`output/crawl-artifacts/{DATE}/browser_agent_tasks.json`

### Phase 3
- 若存在补抓结果：读取 `output/crawl-artifacts/{DATE}/stage2_results.json`
- 执行摘要：`output/reports/{DATE}/run-summary.md`
- 月度站点文件：`output/notices/{YYYY-MM}/{siteId}.json`
- GitHub Pages 同步：`docs/data/`

---

## 标准执行建议

### 完整闭环执行
```bash
python3 scripts/daily_pipeline_entry.py --date $DATE
```

### 仅做阶段级检查
```bash
python3 scripts/run_daily.py --date $DATE --phase 1
python3 scripts/run_daily.py --date $DATE --phase 2-prep
python3 scripts/run_daily.py --date $DATE --phase 3
```

---

## 失败处理原则

- 如果 Phase 1 有失败站点，Phase 2-prep 会生成 `browser_agent_tasks.json`，标准入口会继续尝试执行 Stage2。
- 如果 Stage2 仍未成功产出 `output/crawl-artifacts/{DATE}/stage2_results.json`，执行摘要会明确标记当日未完全收口，便于告警与排查。
- 不再使用 `output/$MONTH/browser_agent_tasks_$DATE.json`、`output/$DATE/stage1_results.json` 等旧路径表述。

---

## 调度说明

仓库内可控入口已经收口为：
- **推荐手动/cron 入口**：`scripts/daily_pipeline_entry.py`
- **阶段执行器**：`scripts/run_daily.py`

如果外部 cron / 上层调度仍在使用旧命名，请替换为上述标准入口。
