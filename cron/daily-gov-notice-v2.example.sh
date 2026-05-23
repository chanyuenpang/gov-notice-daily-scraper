#!/bin/bash
# 每日政府公告抓取标准入口示例
# 新流程：标准入口串行推进 phase1 -> phase2-prep -> phase3

set -euo pipefail

DATE=${1:-$(date +%F)}
PROJECT_DIR="/home/yankeeting/.openclaw/projects/gov-notice-daily-scraper"
cd "$PROJECT_DIR"

echo "===== 每日政府公告抓取 Pipeline ====="
echo "日期: $DATE"

echo "--- 标准入口：串行执行 ---"
python3 scripts/daily_pipeline_entry.py --date "$DATE"

echo "===== Pipeline 完成 ====="
