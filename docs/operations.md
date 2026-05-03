# 运维手册 - 每日政府公告抓取

## Pipeline 流程

```
Step 1: 脚本批量抓取 (crawl_batch.py + CSS 选择器)
  ↓
Step 2: 失败站点分析 → browser-agent 补抓 + 自动生成新 CSS 规则
  ↓
Step 3: 合并结果 → 日报 → 增量分析 → GitHub Page 同步 → 飞书通知
```

**核心原则：脚本优先，browser-agent 兜底。**

## 日常运维命令

### 手动运行完整 Pipeline

```bash
cd /home/yankeeting/.openclaw/projects/gov-notice-daily-scraper
DATE=$(date +%F)

# Step 1: 脚本抓取
python3 scripts/run_daily.py --date $DATE --phase 1

# Step 2: 分析失败站点
python3 scripts/run_daily.py --date $DATE --phase 2-prep

# （browser-agent 补抓由 OpenClaw 编排，或手动 spawn）

# Step 3: 合并+报告+同步
python3 scripts/run_daily.py --date $DATE --phase 3
```

### 指定日期运行

```bash
python3 scripts/run_daily.py --date 2026-05-03 --phase 1
```

### 仅运行单个站点测试

```bash
python3 scripts/crawl_batch.py --urls config/urls-test.json --output output/test_results.json
```

## 故障排查

### Phase 1 失败（crawl_batch.py 报错）

**症状**：stage1_results.json 中某些站点 status != success
**排查**：
1. 检查 `config/rules/{siteId}.json` 中 CSS 选择器是否过期
2. 手动访问目标网站，确认页面结构是否变化
3. 如果规则过期，等待 Phase 2 browser-agent 自动生成新规则

### Phase 2 browser-agent 补抓失败

**症状**：stage2_results.json 不存在或部分站点仍失败
**排查**：
1. 检查 browser-agent subagent 日志
2. 手动 spawn browser-agent 测试单个站点
3. 检查网络连接（部分政府网站需要代理）

### Phase 3 报告生成失败

**症状**：日报.md 或 增量日报.md 未生成
**排查**：
1. 检查 `output/{date}/announcements.json` 是否存在且格式正确
2. 手动运行：`python3 scripts/generate_report_v2.py --date {date}`
3. 手动运行：`python3 scripts/incremental_analysis_v2.py --date {date}`

### GitHub Page 同步失败

**症状**：docs/data/ 未更新
**排查**：
1. 检查 git 权限：`cd project_dir && git remote -v`
2. 手动运行：`python3 scripts/sync_pages_data.py`
3. 检查是否有未提交的改动阻塞 push

### 增量分析显示全部为新增

**原因**：昨天没有运行或 output/{昨天}/announcements.json 不存在
**解决**：正常现象，脚本会自动将全部视为新增

## 输出文件说明

每天 `output/{YYYY-MM-DD}/` 目录下：

| 文件 | 说明 |
|------|------|
| `stage1_results.json` | Step 1 脚本抓取原始结果 |
| `stage1_summary.json` | Step 1 统计摘要 |
| `browser_agent_tasks.json` | Step 2 失败站点任务清单 |
| `stage2_results.json` | Step 2 browser-agent 补抓结果 |
| `combined_results.json` | Step1+Step2 合并结果 |
| `announcements.json` | 最终公告列表（扁平化） |
| `crawl-meta.json` | 抓取元数据 |
| `日报.md` | 全量日报 |
| `增量日报.md` | 增量日报（按站点分组） |
| `日报.docx` | 日报 Word 版 |
| `增量日报.docx` | 增量日报 Word 版 |
| `.phase1_done` | Phase 1 完成标记 |

## 调度配置

- **Cron Job**: `daily-gov-notice-v2`
- **执行时间**: 每天 06:30 CST
- **配置文件**: `~/.openclaw/cron/jobs.json`
- **飞书群**: `oc_00c2c690e5a60b6803a38b121568e4c1`
