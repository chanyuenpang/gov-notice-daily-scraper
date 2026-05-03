#!/usr/bin/env python3
"""
每日政府公告抓取 Pipeline
用法:
  python3 scripts/run_daily.py --date 2026-05-03 --phase 1   # Step 1: 脚本批量抓取
  python3 scripts/run_daily.py --date 2026-05-03 --phase 2-prep  # Step 2: 分析失败站点，生成 browser-agent 任务清单
  python3 scripts/run_daily.py --date 2026-05-03 --phase 3   # Step 3: 合并+报告+同步
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
CONFIG_DIR = PROJECT_ROOT / "config"


def run_command(cmd: List[str], label: str, timeout: int = 600) -> Tuple[int, str, str]:
    """运行子进程，返回 (returncode, stdout, stderr)，并输出日志。"""
    printable = " ".join(shlex.quote(str(part)) for part in cmd)
    print(f"[RUN:{label}] {printable}")
    try:
        result = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        if result.stdout:
            print(result.stdout.rstrip())
        if result.stderr:
            print(result.stderr.rstrip())
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError as exc:
        msg = f"[ERROR] 命令不存在: {cmd[0]} ({exc})"
        print(msg)
        return 1, "", msg
    except subprocess.TimeoutExpired:
        msg = "[ERROR] 命令执行超时"
        print(msg)
        return 1, "", msg
    except Exception as exc:
        msg = f"[ERROR] 执行命令异常: {exc}"
        print(msg)
        return 1, "", msg


def load_json(path: Path):
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def save_json(path: Path, data: object):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def validate_date(date_str: str) -> str:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        raise ValueError(f"日期格式错误：{date_str}，请用 YYYY-MM-DD")


def normalize_site_result(result: dict) -> dict:
    """把不同来源的单站结果标准化为 stage1/merge 兼容格式。"""
    if not isinstance(result, dict):
        return {}

    site_id = result.get("siteId") or result.get("site_id") or result.get("id") or ""
    site_name = result.get("siteName") or result.get("name") or result.get("site_name") or result.get("displayName") or ""
    url = result.get("url") or result.get("siteUrl") or result.get("targetUrl") or ""
    status = result.get("status")

    # stage2 旧格式：success: bool
    if status is None and "success" in result:
        status = "success" if result.get("success") else "failed"

    if status is None:
        status = "failed"

    raw_announcements = result.get("announcements")
    if raw_announcements is None:
        raw_announcements = result.get("articles", [])

    if not isinstance(raw_announcements, list):
        raw_announcements = []

    announcements: List[dict] = []
    for ann in raw_announcements:
        if not isinstance(ann, dict):
            continue
        ann = dict(ann)
        if ann.get("siteId", "") == "" and site_id:
            ann["siteId"] = site_id
        if ann.get("siteName", "") == "" and site_name:
            ann["siteName"] = site_name
        if ann.get("siteUrl", "") == "" and url:
            ann["siteUrl"] = url
        announcements.append(ann)

    return {
        "siteId": site_id,
        "siteName": site_name,
        "url": url,
        "status": str(status).lower(),
        "strategyUsed": result.get("strategyUsed") or result.get("strategy") or "script_or_agent",
        "announcements": announcements,
        "error": result.get("error") or result.get("message") or None,
        "durationMs": result.get("durationMs", 0),
        "source": result.get("source", "stage2") if result.get("site_id") else result.get("source", "stage1"),
    }


def is_success(result: dict) -> bool:
    return str(result.get("status", "")).lower() == "success"


def result_announcements(result: dict) -> List[dict]:
    announcements = result.get("announcements", [])
    if not isinstance(announcements, list):
        return []
    return announcements


def is_failed_for_phase2(result: dict) -> bool:
    status = str(result.get("status", "")).lower()
    announcements = result_announcements(result)
    return status != "success" or len(announcements) == 0


def flatten_announcements_for_output(results: List[dict]) -> List[dict]:
    all_announcements: List[dict] = []
    seen_keys = set()

    for result in results:
        if not isinstance(result, dict):
            continue
        site_id = result.get("siteId", "")
        site_name = result.get("siteName", "") or site_id
        for ann in result.get("announcements", []) or []:
            if not isinstance(ann, dict):
                continue
            item = dict(ann)
            item.setdefault("siteId", site_id)
            item.setdefault("siteName", site_name)
            # 保持兼容字段
            item["siteId"] = item.get("siteId") or site_id
            item["siteName"] = item.get("siteName") or site_name

            # 去重 key：优先按 URL，缺省时按(站点+标题+日期)
            url = (item.get("url") or "").strip()
            if url:
                dedup_key = f"url::{url}"
            else:
                dedup_key = f"no-url::{site_id}::{item.get('title', '')}::{item.get('date', '')}"

            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)
            all_announcements.append(item)

    return all_announcements


def save_site_monthly(date_str: str, results: List[dict]) -> dict:
    """按月+站点保存结果，URL去重。返回统计信息。"""
    month = date_str[:7]
    month_dir = OUTPUT_DIR / month
    month_dir.mkdir(parents=True, exist_ok=True)

    stats = {"total_new": 0, "total_existing": 0, "sites": {}}

    for result in results:
        site_id = result.get("siteId", "") or result.get("site_id", "") or "unknown"
        site_file = month_dir / f"{site_id}.json"

        existing = load_json(site_file)
        existing_urls = {a.get("url", "") for a in existing.get("announcements", []) if a.get("url")}
        existing_announcements = existing.get("announcements", [])

        new_announcements = []
        for ann in result.get("announcements", []):
            if not isinstance(ann, dict):
                continue
            url = ann.get("url", "")
            if url and url in existing_urls:
                continue
            if url:
                existing_urls.add(url)
            ann.setdefault("siteId", site_id)
            ann.setdefault("siteName", result.get("siteName", site_id))
            new_announcements.append(ann)

        all_announcements = existing_announcements + new_announcements
        data = {
            "siteId": site_id,
            "siteName": result.get("siteName", site_id),
            "month": month,
            "updatedAt": now_iso(),
            "announcements": all_announcements,
        }
        save_json(site_file, data)

        stats["total_new"] += len(new_announcements)
        stats["total_existing"] += len(existing_announcements)
        stats["sites"][site_id] = {
            "new": len(new_announcements),
            "existing": len(existing_announcements),
            "total": len(all_announcements),
        }

    return stats


def get_today_announcements(date_str: str) -> List[dict]:
    """从月份目录各站点文件中，筛选出指定日期新增的公告。"""
    month = date_str[:7]
    month_dir = OUTPUT_DIR / month
    if not month_dir.exists():
        return []

    today_announcements = []
    for site_file in sorted(month_dir.glob("*.json")):
        if site_file.name.startswith("stage") or site_file.name.startswith("browser") or site_file.name.startswith("combined"):
            continue
        data = load_json(site_file)
        if not isinstance(data, dict) or "announcements" not in data:
            continue
        for ann in data.get("announcements", []):
            if not isinstance(ann, dict):
                continue
            ann_date = ann.get("date", "")
            if ann_date == date_str:
                today_announcements.append(ann)

    return today_announcements


def normalize_stage2_data(raw: object, date_str: str) -> dict:
    """将不稳定的 stage2 文件格式标准化为 {date, results:[...]}。"""
    if not raw:
        return {"date": date_str, "results": []}

    if isinstance(raw, dict):
        if "results" in raw and isinstance(raw.get("results"), list):
            return {
                "date": raw.get("date", date_str),
                "results": [normalize_site_result(r) for r in raw.get("results", []) if isinstance(r, dict)],
            }

        # 简化格式：{"siteId": [announcements]}
        if raw and all(isinstance(k, str) and isinstance(v, list) for k, v in raw.items()):
            results = []
            for site_id, anns in raw.items():
                rec = {
                    "siteId": site_id,
                    "siteName": site_id,
                    "url": "",
                    "status": "success" if anns else "failed",
                    "strategyUsed": "stage2",
                    "announcements": anns,
                    "durationMs": 0,
                    "error": None,
                    "source": "stage2",
                }
                results.append(normalize_site_result(rec))
            return {"date": date_str, "results": results}

        # 兼容其它字段包裹
        if "data" in raw and isinstance(raw["data"], list):
            return normalize_stage2_data(raw.get("data"), date_str)

        if any(
            isinstance(raw.get(k), (list, dict)) and k.endswith("_results")
            for k in raw.keys()
        ):
            for value in raw.values():
                if isinstance(value, list):
                    nested = normalize_stage2_data(value, date_str)
                    if nested.get("results"):
                        return nested

        return {"date": date_str, "results": []}

    if isinstance(raw, list):
        results = []
        for item in raw:
            if isinstance(item, dict):
                results.append(normalize_site_result(item))
        return {"date": date_str, "results": results}

    return {"date": date_str, "results": []}


def merge_stage1_stage2(stage1: dict, stage2: dict, date_str: str) -> dict:
    """本地合并逻辑（与 merge_results.py 语义保持一致）。"""
    stage1_results = [normalize_site_result(r) for r in stage1.get("results", []) if isinstance(r, dict)]
    stage2_results = [normalize_site_result(r) for r in stage2.get("results", []) if isinstance(r, dict)]

    stage1_map = OrderedDict((r.get("siteId", ""), r) for r in stage1_results if r.get("siteId", "") != "")
    stage2_map = OrderedDict((r.get("siteId", ""), r) for r in stage2_results if r.get("siteId", "") != "")

    merged_results: List[dict] = []

    for site_id, result1 in stage1_map.items():
        result2 = stage2_map.get(site_id)

        if is_success(result1):
            merged_results.append(result1)
            continue

        if result2 and is_success(result2):
            merged_results.append(result2)
            continue

        if result2 and result_announcements(result2):
            merged = dict(result1)
            merged["announcements"] = result_announcements(result2)
            merged["status"] = "success"
            merged["agentRecovered"] = True
            merged_results.append(merged)
            continue

        merged = dict(result1)
        if result2 and result2.get("error"):
            merged["stage2Error"] = result2.get("error")
        merged_results.append(merged)

    # 补齐 stage2 新站点
    for site_id, result2 in stage2_map.items():
        if site_id not in stage1_map:
            merged_results.append(result2)

    success_count = len([r for r in merged_results if is_success(r)])
    failed_count = len(merged_results) - success_count
    total_announcements = sum(len(r.get("announcements", [])) for r in merged_results)

    return {
        "date": date_str,
        "generatedAt": now_iso(),
        "stage": "combined",
        "results": merged_results,
        "summary": {
            "total": len(merged_results),
            "success": success_count,
            "failed": failed_count,
            "totalAnnouncements": total_announcements,
            "agentRecovered": len([r for r in merged_results if r.get("agentRecovered")]),
        },
    }


def write_meta(output_dir: Path, date_str: str, announcements: List[dict], merged_results: List[dict]):
    success_sites = len([r for r in merged_results if is_success(r)])
    total_sites = len(merged_results)
    meta = {
        "date": date_str,
        "crawledAt": now_iso(),
        "totalSites": total_sites,
        "successSites": success_sites,
        "failedSites": total_sites - success_sites,
        "totalAnnouncements": len(announcements),
        "newAnnouncements": 0,
        "source": "run_daily",
    }
    save_json(output_dir / "crawl-meta.json", meta)


def phase1(date_str: str) -> None:
    month = date_str[:7]
    month_dir = OUTPUT_DIR / month
    month_dir.mkdir(parents=True, exist_ok=True)

    stage1_path = month_dir / f"stage1_results_{date_str}.json"
    summary_path = month_dir / f"stage1_summary_{date_str}.json"
    marker_path = month_dir / f".phase1_done_{date_str}"

    rc, _, _ = run_command(
        [
            sys.executable,
            "scripts/crawl_batch.py",
            "--urls",
            str(CONFIG_DIR / "urls.json"),
            "--output",
            str(stage1_path),
        ],
        label="phase1.crawl_batch",
        timeout=3600,
    )

    if rc != 0:
        print(f"[WARN] phase1 crawl_batch 执行失败(代码 {rc})，尝试继续读取输出文件")

    stage1_data = load_json(stage1_path)
    results = stage1_data.get("results") if isinstance(stage1_data, dict) else []
    if not isinstance(results, list):
        results = []

    # 按月+站点保存，URL去重
    save_stats = save_site_monthly(date_str, results)

    success_sites: List[dict] = []
    failed_sites: List[dict] = []
    total_announcements = 0

    for result in results:
        if not isinstance(result, dict):
            continue
        status = str(result.get("status", "")).lower()
        announcements = result_announcements(result)
        count = len(announcements)
        total_announcements += count

        payload = {
            "siteId": result.get("siteId") or result.get("site_id") or "",
            "siteName": result.get("siteName") or result.get("name") or result.get("site_name") or "",
            "url": result.get("url") or "",
            "status": status or "failed",
            "announcements": count,
            "error": result.get("error") or result.get("message"),
        }

        if is_failed_for_phase2(result):
            failed_sites.append(payload)
        else:
            success_sites.append(payload)

    summary = {
        "date": date_str,
        "generatedAt": now_iso(),
        "total": len(results),
        "success": len(success_sites),
        "failed": len(failed_sites),
        "totalAnnouncements": total_announcements,
        "newToday": save_stats["total_new"],
        "existingInMonth": save_stats["total_existing"],
        "failedSites": failed_sites,
    }

    save_json(summary_path, summary)
    marker_data = {
        "done": True,
        "date": date_str,
        "generatedAt": now_iso(),
        "summary": {
            "success": summary["success"],
            "failed": summary["failed"],
            "totalAnnouncements": summary["totalAnnouncements"],
            "newToday": summary["newToday"],
        },
    }
    save_json(marker_path, marker_data)

    print(f"[OK] phase1 完成: 成功 {summary['success']} 站, 失败 {summary['failed']} 站")
    print(f"[OK] 总公告数: {summary['totalAnnouncements']}, 今日新增: {summary['newToday']}")
    print(f"[OK] 数据已保存到: {month_dir}/")
    print(f"[OK] stage1 summary 已写入: {summary_path}")


def phase2_prep(date_str: str) -> None:
    month = date_str[:7]
    month_dir = OUTPUT_DIR / month
    stage1_path = month_dir / f"stage1_results_{date_str}.json"
    output_path = month_dir / f"browser_agent_tasks_{date_str}.json"

    if not stage1_path.exists():
        print(f"[ERROR] 缺失 stage1 结果: {stage1_path}")
        return

    data = load_json(stage1_path)
    results = data.get("results") if isinstance(data, dict) else []
    if not isinstance(results, list):
        results = []

    tasks = []
    for result in results:
        if not isinstance(result, dict):
            continue
        if not is_failed_for_phase2(result):
            continue

        tasks.append(
            {
                "siteId": result.get("siteId") or result.get("site_id") or "",
                "url": result.get("url") or "",
                "siteName": result.get("siteName") or result.get("name") or result.get("site_name") or "",
                "status": str(result.get("status", "")).lower() or "failed",
                "error": result.get("error") or result.get("message"),
            }
        )

    tasks_data = {
        "date": date_str,
        "generatedAt": now_iso(),
        "tasks": tasks,
        "summary": {
            "total": len(tasks),
        },
    }

    save_json(output_path, tasks_data)

    print(f"[OK] 失败站点任务清单已写入: {output_path}")
    if not tasks:
        print("[INFO] 无失败站点，Phase 2 可跳过")
        return

    print("[INFO] 失败站点列表 (供 cron-runner 派发 browser-agent):")
    for idx, item in enumerate(tasks, 1):
        print(f"  {idx:02d}. {item['siteId']} | {item['siteName']} | {item['url']}")

def phase3(date_str: str) -> None:
    month = date_str[:7]
    month_dir = OUTPUT_DIR / month
    stage1_path = month_dir / f"stage1_results_{date_str}.json"
    stage2_path = month_dir / f"stage2_results_{date_str}.json"
    marker_path = month_dir / f".phase1_done_{date_str}"

    if not stage1_path.exists():
        print(f"[ERROR] 缺失 stage1 结果: {stage1_path}")
        return

    if not marker_path.exists():
        print(f"[WARN] 未检测到 phase1 标记文件，继续执行但请确认已跑完 Phase 1")

    stage1_data = load_json(stage1_path)
    stage1_data.setdefault("date", date_str)

    # 如果有 stage2 补抓结果，追加到月份站点文件
    if stage2_path.exists():
        print(f"[INFO] 检测到 stage2 补抓结果: {stage2_path}")
        stage2_data = normalize_stage2_data(load_json(stage2_path), date_str)
        stage2_results = stage2_data.get("results", [])
        save_stats = save_site_monthly(date_str, stage2_results)
        print(f"[OK] stage2 补抓结果已追加: 新增 {save_stats['total_new']} 条")
    else:
        print("[INFO] 未检测到 stage2 补抓结果，跳过合并")

    # 从月份站点文件中提取今天的公告
    today_announcements = get_today_announcements(date_str)
    
    # 生成日报（兼容旧路径）
    date_dir = OUTPUT_DIR / date_str
    date_dir.mkdir(parents=True, exist_ok=True)
    announcements_path = date_dir / "announcements.json"
    save_json(announcements_path, today_announcements)

    # 写 crawl-meta
    sites_with_data = set()
    for ann in today_announcements:
        sid = ann.get("siteId", "")
        if sid:
            sites_with_data.add(sid)
    meta = {
        "date": date_str,
        "crawledAt": now_iso(),
        "totalSites": len(sites_with_data),
        "totalAnnouncements": len(today_announcements),
        "source": "run_daily_monthly",
        "storageStructure": "monthly",
        "monthDir": str(month_dir),
    }
    save_json(date_dir / "crawl-meta.json", meta)

    # 生成日报
    run_command(
        [
            sys.executable,
            "scripts/generate_report_v2.py",
            "--date",
            date_str,
            "--input",
            str(announcements_path),
        ],
        label="phase3.generate_report_v2",
        timeout=120,
    )

    # 增量分析
    run_command(
        [
            sys.executable,
            "scripts/incremental_analysis_v2.py",
            "--date",
            date_str,
        ],
        label="phase3.incremental_analysis_v2",
        timeout=120,
    )

    # pandoc 转 docx
    for md_name, docx_name in [("日报.md", "日报.docx"), ("增量日报.md", "增量日报.docx")]:
        md_file = date_dir / md_name
        docx_file = date_dir / docx_name
        if md_file.exists():
            run_command(
                ["pandoc", str(md_file), "-o", str(docx_file)],
                label=f"phase3.pandoc.{md_name}",
                timeout=60,
            )

    # 同步 GitHub Pages
    rc, _, _ = run_command(
        [sys.executable, "scripts/sync_pages_data.py"],
        label="phase3.sync_pages_data",
        timeout=120,
    )
    if rc != 0:
        print("[WARN] sync_pages_data 执行失败，已忽略")

    # 最终汇报
    print("\n===== 执行汇总 =====")
    print(f"日期: {date_str}")
    print(f"今日新增公告: {len(today_announcements)}")
    print(f"数据目录: {month_dir}/")
    print(f"日报文件: {date_dir / '日报.md'}")
    print(f"增量日报文件: {date_dir / '增量日报.md'}")

def main():
    parser = argparse.ArgumentParser(description="每日政府公告抓取 Pipeline")
    parser.add_argument("--date", type=str, default=datetime.now().strftime("%Y-%m-%d"), help="日期（YYYY-MM-DD）")
    parser.add_argument(
        "--phase",
        type=str,
        required=True,
        choices=["1", "2-prep", "3"],
        help="执行阶段：1 / 2-prep / 3",
    )

    args = parser.parse_args()

    try:
        date_str = validate_date(args.date)
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.phase == "1":
        phase1(date_str)
    elif args.phase == "2-prep":
        phase2_prep(date_str)
    elif args.phase == "3":
        phase3(date_str)


if __name__ == "__main__":
    main()
