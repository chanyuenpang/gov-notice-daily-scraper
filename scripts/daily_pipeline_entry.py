#!/usr/bin/env python3
"""每日政府公告抓取标准入口。

这是仓库内唯一推荐的手动/定时执行入口：
  python3 scripts/daily_pipeline_entry.py --date YYYY-MM-DD

默认串行推进：Phase 1 -> Phase 2-prep -> Phase 3。
若 Phase 1 有失败，也会继续执行后续阶段，避免流程停在 stage1。

说明：
- Phase 2 的实际补抓仍由仓库外的调度层 / subagent 执行。
- 本入口会明确输出下一步需要补抓的站点任务文件，避免误以为流程已结束。
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from run_daily import phase1, phase2_prep, phase3, validate_date  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="每日政府公告抓取标准入口")
    parser.add_argument("--date", type=str, default=datetime.now().strftime("%Y-%m-%d"), help="日期（YYYY-MM-DD）")
    parser.add_argument("--skip-phase2", action="store_true", help="跳过 Phase 2-prep")
    args = parser.parse_args()

    try:
        date_str = validate_date(args.date)
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        return 1

    print("[ENTRY] 标准入口已启动: scripts/daily_pipeline_entry.py")
    print(f"[ENTRY] 日期: {date_str}")
    print("[ENTRY] 执行顺序: Phase 1 -> Phase 2-prep -> Phase 3")

    try:
        phase1(date_str)
    except Exception as exc:
        print(f"[ERROR] Phase 1 异常: {exc}")

    if not args.skip_phase2:
        try:
            phase2_prep(date_str)
        except Exception as exc:
            print(f"[ERROR] Phase 2-prep 异常: {exc}")
            print("[WARN] 继续进入 Phase 3，避免链路停在 stage1")

    try:
        phase3(date_str)
    except Exception as exc:
        print(f"[ERROR] Phase 3 异常: {exc}")
        return 1

    print("[ENTRY] 标准入口执行完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
