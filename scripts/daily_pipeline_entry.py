#!/usr/bin/env python3
"""每日政府公告抓取标准入口。

这是仓库内唯一推荐的手动/定时执行入口：
  python3 scripts/daily_pipeline_entry.py --date YYYY-MM-DD

默认串行推进：Phase 1 -> Phase 2-prep -> Stage2 -> Phase 3。
若 Phase 1 有失败，也会继续执行后续阶段，避免流程停在 stage1。
若存在待补抓任务，会自动执行 `scripts/run_stage2_execute.py`，尽量让日跑闭环。
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
import subprocess
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from run_daily import phase1, phase2_prep, phase3, validate_date  # noqa: E402
from output_paths import artifacts_dir, reports_dir  # noqa: E402


def load_json(path: Path):
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_run_summary(date_str: str) -> Path:
    artifact_dir = artifacts_dir(date_str)
    report_dir = reports_dir(date_str)
    report_dir.mkdir(parents=True, exist_ok=True)

    stage1_summary = load_json(artifact_dir / "stage1_summary.json")
    stage2_results = load_json(artifact_dir / "stage2_results.json")
    tasks_data = load_json(artifact_dir / "browser_agent_tasks.json")

    stage2_summary = stage2_results.get("summary", {}) if isinstance(stage2_results, dict) else {}
    task_summary = tasks_data.get("summary", {}) if isinstance(tasks_data, dict) else {}

    lines = [
        f"# 公告抓取执行摘要 - {date_str}",
        "",
        "## Phase 1",
        f"- 成功站点: {stage1_summary.get('success', 0)}",
        f"- 失败站点: {stage1_summary.get('failed', 0)}",
        f"- 公告总数: {stage1_summary.get('totalAnnouncements', 0)}",
        f"- 今日新增: {stage1_summary.get('newToday', 0)}",
        "",
        "## Phase 2 / Stage2",
        f"- 待补抓任务数: {task_summary.get('total', 0)}",
        f"- Stage2 成功: {stage2_summary.get('success', 0)}",
        f"- Stage2 失败: {stage2_summary.get('failed', 0)}",
        f"- Stage2 公告数: {stage2_summary.get('totalAnnouncements', 0)}",
        "",
    ]

    pending_reason = None
    if task_summary.get('total', 0) > 0 and not stage2_summary:
        pending_reason = "存在待补抓任务，但没有生成 stage2_results.json"
    elif stage2_summary.get('failed', 0) > 0:
        pending_reason = "Stage2 已执行，但仍有失败站点，需要继续排查站点可达性或规则问题"

    if pending_reason:
        lines.extend([
            "## 状态",
            f"- 未完全收口: {pending_reason}",
            "",
        ])
    else:
        lines.extend([
            "## 状态",
            "- 已完成当日标准闭环执行",
            "",
        ])

    failed_sites = stage1_summary.get('failedSites', []) if isinstance(stage1_summary, dict) else []
    if failed_sites:
        lines.append("## Phase 1 失败站点")
        for item in failed_sites:
            lines.append(f"- {item.get('siteId', '')}: {item.get('error', '')}".rstrip())
        lines.append("")

    stage2_items = stage2_results.get('results', []) if isinstance(stage2_results, dict) else []
    failed_stage2 = [x for x in stage2_items if isinstance(x, dict) and x.get('status') != 'success']
    if failed_stage2:
        lines.append("## Stage2 失败站点")
        for item in failed_stage2:
            lines.append(f"- {item.get('siteId', '')}: {item.get('error', '')}".rstrip())
        lines.append("")

    out = report_dir / "run-summary.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] 执行摘要已写入: {out}")
    return out


def maybe_run_stage2(date_str: str) -> None:
    artifact_dir = artifacts_dir(date_str)
    tasks_path = artifact_dir / "browser_agent_tasks.json"
    stage2_path = artifact_dir / "stage2_results.json"

    if not tasks_path.exists():
        print("[INFO] 未检测到 browser_agent_tasks.json，跳过 Stage2")
        return

    tasks_data = load_json(tasks_path)
    tasks = tasks_data.get("tasks") if isinstance(tasks_data, dict) else []
    if not isinstance(tasks, list) or not tasks:
        print("[INFO] 无待补抓任务，跳过 Stage2")
        if stage2_path.exists():
            stage2_path.unlink()
            print(f"[INFO] 已清理陈旧 Stage2 结果: {stage2_path}")
        return

    if stage2_path.exists():
        stage2_path.unlink()
        print(f"[INFO] 已清理旧的 Stage2 结果，准备按最新任务重跑: {stage2_path}")

    cmd = [sys.executable, "scripts/run_stage2_execute.py", "--date", date_str]
    print(f"[ENTRY] 检测到 {len(tasks)} 个待补抓任务，自动执行 Stage2")
    result = subprocess.run(cmd, cwd=PROJECT_ROOT, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"Stage2 执行失败，退出码 {result.returncode}")


def main() -> int:
    parser = argparse.ArgumentParser(description="每日政府公告抓取标准入口")
    parser.add_argument("--date", type=str, default=datetime.now().strftime("%Y-%m-%d"), help="日期（YYYY-MM-DD）")
    parser.add_argument("--skip-phase2", action="store_true", help="跳过 Phase 2-prep")
    parser.add_argument("--skip-stage2", action="store_true", help="跳过 Stage2 自动补抓")
    args = parser.parse_args()

    try:
        date_str = validate_date(args.date)
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        return 1

    print("[ENTRY] 标准入口已启动: scripts/daily_pipeline_entry.py")
    print(f"[ENTRY] 日期: {date_str}")
    print("[ENTRY] 执行顺序: Phase 1 -> Phase 2-prep -> Stage2 -> Phase 3")

    try:
        phase1(date_str)
    except Exception as exc:
        print(f"[ERROR] Phase 1 异常: {exc}")

    if not args.skip_phase2:
        try:
            phase2_prep(date_str)
        except Exception as exc:
            print(f"[ERROR] Phase 2-prep 异常: {exc}")
            print("[WARN] 继续进入后续阶段，避免链路停在 stage1")

    if not args.skip_stage2:
        try:
            maybe_run_stage2(date_str)
        except Exception as exc:
            print(f"[ERROR] Stage2 异常: {exc}")

    try:
        phase3(date_str)
        write_run_summary(date_str)
    except Exception as exc:
        print(f"[ERROR] Phase 3 异常: {exc}")
        return 1

    print("[ENTRY] 标准入口执行完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
