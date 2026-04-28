#!/bin/bash
# ============================================================
# daily-gov-notice-v2.example.sh
# 每日政府公告抓取 + 日报生成 示例脚本
# ============================================================
#
# 使用方式:
#   bash cron/daily-gov-notice-v2.example.sh
#
# 注意:
#   - Step 2 (browser-agent 抓取) 需要 OpenClaw 环境
#   - 真实 browser-agent 派发应由 OpenClaw sessions_spawn / skill 触发
#   - 本脚本中 Step 2 以 dry-run 示例，实际部署时替换为 OpenClaw 调度
# ============================================================

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DATE="${1:-$(date +%F)}"
OUTPUT_DIR="${PROJECT_DIR}/output/${DATE}"
LOG_DIR="${PROJECT_DIR}/logs"

mkdir -p "${OUTPUT_DIR}" "${LOG_DIR}"

echo "========================================"
echo "Daily gov-notice pipeline v2"
echo "Date: ${DATE}"
echo "========================================"

# --- Step 1: 生成抓取任务 ---
echo "[Step 1] Generating crawl tasks..."
python3 "${PROJECT_DIR}/scripts/browser_agent_crawl.py" --date "${DATE}"
echo "[Step 1] Done. → ${OUTPUT_DIR}/crawl-tasks.json"

# --- Step 2: Browser-Agent 抓取 ---
# 注意: 真实的 browser-agent 派发应由 OpenClaw sessions_spawn 触发
#       这里以 dry-run 作为示例，验证任务列表生成正确
echo "[Step 2] Browser-agent crawl (dry-run example)..."
python3 "${PROJECT_DIR}/scripts/browser_agent_crawl.py" --test --dry-run --date "${DATE}"
echo "[Step 2] Done. (dry-run mode, no actual crawling)"
# 实际部署时，替换上面的 dry-run 为 OpenClaw skill 调用:
#   openclaw sessions spawn --label "crawl-${DATE}" \
#     "读取 output/${DATE}/crawl-tasks.json，逐站派发 browser-agent 抓取，结果写入 announcements.json"

# --- Step 3: 生成日报 ---
echo "[Step 3] Generating daily report..."
python3 "${PROJECT_DIR}/scripts/generate_report_v2.py" --date "${DATE}"
echo "[Step 3] Done. → ${OUTPUT_DIR}/daily-report.md"

# --- Step 4: 增量分析 ---
echo "[Step 4] Running incremental analysis..."
python3 "${PROJECT_DIR}/scripts/incremental_analysis_v2.py" --date "${DATE}"
echo "[Step 4] Done. → ${OUTPUT_DIR}/incremental-report.md"

echo "========================================"
echo "Pipeline completed: ${DATE}"
echo "========================================"
