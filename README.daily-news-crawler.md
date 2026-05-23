# Daily News Crawler

政府网站公告抓取系统，当前以 **`scripts/daily_pipeline_entry.py`** 作为仓库内标准入口。

## 推荐执行方式

```bash
python3 scripts/daily_pipeline_entry.py --date 2026-05-23
```

该入口会串行执行：
- Phase 1: 脚本批量抓取
- Phase 2-prep: 生成失败站点任务清单
- Phase 3: 合并 + 同步

即使 Phase 1 未完全成功，也不会停在 stage1；Phase 2-prep 和 Phase 3 会继续推进，避免链路误停。

---

## 阶段执行器

如果需要单独跑某一阶段，可直接使用：

```bash
python3 scripts/run_daily.py --date 2026-05-23 --phase 1
python3 scripts/run_daily.py --date 2026-05-23 --phase 2-prep
python3 scripts/run_daily.py --date 2026-05-23 --phase 3
```

> 注意：`run_daily.py` 是阶段执行器，不是推荐的手动主入口。

---

## 真实产物路径

- `output/notices/{YYYY-MM}/{siteId}.json`
- `output/crawl-artifacts/{YYYY-MM-DD}/stage1_results.json`
- `output/crawl-artifacts/{YYYY-MM-DD}/stage1_summary.json`
- `output/crawl-artifacts/{YYYY-MM-DD}/browser_agent_tasks.json`
- `output/crawl-artifacts/{YYYY-MM-DD}/stage2_results.json`
- `output/crawl-artifacts/{YYYY-MM-DD}/日报.md`
- `output/crawl-artifacts/{YYYY-MM-DD}/增量日报.md`

---

## 旧流程纠偏

旧文档里出现的 `output/{date}/stage1_results.json`、`output/$MONTH/browser_agent_tasks_$DATE.json` 等路径，已经不再是当前标准说法。以 `scripts/run_daily.py` 与 `scripts/daily_pipeline_entry.py` 输出为准。
