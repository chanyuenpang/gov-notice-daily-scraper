#!/bin/bash
# 每日政府公告抓取 Pipeline 示例
# 新流程：脚本优先 → browser-agent 兜底 → 报告+同步

set -euo pipefail

DATE=${1:-$(date +%F)}
PROJECT_DIR="/home/yankeeting/.openclaw/projects/gov-notice-daily-scraper"
cd "$PROJECT_DIR"

echo "===== 每日政府公告抓取 Pipeline ====="
echo "日期: $DATE"

# Step 1: 脚本批量抓取（CSS 选择器）
echo "--- Step 1: 脚本批量抓取 ---"
python3 scripts/run_daily.py --date "$DATE" --phase 1

# Step 2: 分析失败站点 + browser-agent 补抓
echo "--- Step 2: 失败站点分析 ---"
python3 scripts/run_daily.py --date "$DATE" --phase 2-prep

# 如果有失败站点，需要通过 OpenClaw sessions_spawn browser-agent 补抓
# 这一步由 cron job 编排，不在 shell 脚本中执行
# 补抓完成后结果写入 output/$DATE/stage2_results.json

# Step 3: 合并 + 日报 + 增量 + GitHub Page 同步
echo "--- Step 3: 报告与同步 ---"
python3 scripts/run_daily.py --date "$DATE" --phase 3

echo "===== Pipeline 完成 ====="
