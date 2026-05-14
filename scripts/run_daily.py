#!/usr/bin/env python3
"""
每日政府公告抓取 Pipeline
用法:
  python3 scripts/run_daily.py --date 2026-05-03 --phase 1   # Step 1: 脚本批量抓取
  python3 scripts/run_daily.py --date 2026-05-03 --phase 2-prep  # Step 2: 分析失败站点，生成 browser-agent 任务清单
  python3 scripts/run_daily.py --date 2026-05-03 --phase 3   # Step 3: 合并+报告+同步

输出目录:
  output/notices/{YYYY-MM}/{siteId}.json                  # 站点月度公告
  output/reports/{YYYY-MM-DD}/announcements.json          # 日报输入与 meta
  output/crawl-artifacts/{YYYY-MM-DD}/stage1_results.json # 中间产物
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

from output_paths import notices_dir, reports_dir, artifacts_dir, ensure_dirs

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
CONFIG_DIR = PROJECT_ROOT / "config"
RULES_DIR = CONFIG_DIR / "rules"

VAGUE_SELECTORS = ['ul li', 'li', 'tr', 'div li', 'div a', 'a', 'ul li a', 'div ul li', 'table tr']


def is_vague_selector(selector: str) -> bool:
    """判断 CSS 选择器是否太宽泛（无限定、无 class/id/attribute）。"""
    if not selector:
        return True
    selector = selector.strip().lower()
    if selector in VAGUE_SELECTORS:
        return True
    # 只有 tag 名，没有 class(.) 或 id(#) 或 attribute([])
    if not ('.' in selector or '#' in selector or '[' in selector):
        return True
    return False


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
    month_dir = notices_dir(month)
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
    month_dir = notices_dir(month)
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
    ensure_dirs(date_str)
    artifact_dir = artifacts_dir(date_str)

    stage1_path = artifact_dir / "stage1_results.json"
    summary_path = artifact_dir / "stage1_summary.json"
    marker_path = artifact_dir / ".phase1_done"

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
    print(f"[OK] 站点月度公告已保存到: {notices_dir(date_str[:7])}/")
    print(f"[OK] stage1 artifacts 已保存到: {artifact_dir}/")
    print(f"[OK] stage1 summary 已写入: {summary_path}")


def audit_rule_quality(date_str: str, stage1_results: list) -> list:
    """
    规则质量审计：检查 Phase 1 成功站点的 CSS 选择器规则质量。
    如果选择器太宽泛或缺少 date 选择器，将该站点加入 browser_agent_tasks。
    返回需要重新学习的站点任务列表。
    """
    urls_data = load_json(CONFIG_DIR / "urls.json")
    sites = urls_data.get("sites") if isinstance(urls_data, dict) else urls_data
    if not isinstance(sites, list):
        sites = []

    # 构建 siteId -> url 映射
    site_url_map = {}
    site_name_map = {}
    for site in sites:
        if not isinstance(site, dict):
            continue
        sid = site.get("id") or site.get("siteId") or ""
        site_url_map[sid] = site.get("url", "")
        site_name_map[sid] = site.get("name") or site.get("siteName") or sid

    # Phase 1 成功的 siteId 集合
    success_ids = set()
    for result in stage1_results:
        if not isinstance(result, dict):
            continue
        if not is_failed_for_phase2(result):
            sid = result.get("siteId") or result.get("site_id") or ""
            if sid:
                success_ids.add(sid)

    relearn_tasks = []
    for site_id in sorted(success_ids):
        rule_path = RULES_DIR / f"{site_id}.json"
        if not rule_path.exists():
            continue

        rule = load_json(rule_path)
        if not isinstance(rule, dict):
            continue

        css = rule.get("css", {})
        if not isinstance(css, dict):
            css = {}

        list_selector = css.get("list", "")
        date_selector = css.get("date", "")

        reason = None
        if is_vague_selector(list_selector):
            reason = "vague_selector"
        elif not date_selector or date_selector.strip() == "":
            reason = "missing_date"

        if reason:
            relearn_tasks.append({
                "siteId": site_id,
                "url": rule.get("url") or site_url_map.get(site_id, ""),
                "siteName": rule.get("siteName") or site_name_map.get(site_id, site_id),
                "status": "success_but_vague",
                "reason": reason,
                "css": css,
            })

    if relearn_tasks:
        print(f"[AUDIT] 规则质量审计: {len(relearn_tasks)} 个成功站点的选择器需要重新学习")
        for t in relearn_tasks:
            print(f"  - {t['siteId']}: reason={t['reason']}, css.list={t['css'].get('list', '')!r}")
    else:
        print("[AUDIT] 规则质量审计: 所有成功站点的选择器质量良好")

    return relearn_tasks


def phase2_prep(date_str: str) -> None:
    ensure_dirs(date_str)
    artifact_dir = artifacts_dir(date_str)
    stage1_path = artifact_dir / "stage1_results.json"
    output_path = artifact_dir / "browser_agent_tasks.json"

    if not stage1_path.exists():
        print(f"[ERROR] 缺失 stage1 结果: {stage1_path}")
        return

    data = load_json(stage1_path)
    results = data.get("results") if isinstance(data, dict) else []
    if not isinstance(results, list):
        results = []

    # Phase 2-prep 原有逻辑：收集 Phase 1 失败站点
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

    # 规则质量审计：检查成功站点的选择器质量，宽泛的也加入重新学习
    print("\n[AUDIT] 开始规则质量审计...")
    relearn_tasks = audit_rule_quality(date_str, results)

    # 追加审计发现的问题站点（不覆盖已有的失败站点）
    existing_ids = {t["siteId"] for t in tasks if t.get("siteId")}
    for t in relearn_tasks:
        if t["siteId"] not in existing_ids:
            tasks.append(t)
            existing_ids.add(t["siteId"])

    tasks_data = {
        "date": date_str,
        "generatedAt": now_iso(),
        "tasks": tasks,
        "summary": {
            "total": len(tasks),
            "phase1Failed": len([t for t in tasks if t.get("status") != "success_but_vague"]),
            "vagueSelector": len([t for t in tasks if t.get("reason") == "vague_selector"]),
            "missingDate": len([t for t in tasks if t.get("reason") == "missing_date"]),
        },
    }

    save_json(output_path, tasks_data)

    print(f"\n[OK] 任务清单已写入: {output_path}")
    if not tasks:
        print("[INFO] 无任务，Phase 2 可跳过")
        return

    print("[INFO] 任务列表 (供 cron-runner 派发 browser-agent):")
    for idx, item in enumerate(tasks, 1):
        reason_tag = f" | reason={item['reason']}" if item.get("reason") else ""
        print(f"  {idx:02d}. {item['siteId']} | {item['siteName']} | {item['url']}{reason_tag}")

def phase3(date_str: str) -> None:
    ensure_dirs(date_str)
    artifact_dir = artifacts_dir(date_str)
    stage1_path = artifact_dir / "stage1_results.json"
    stage2_path = artifact_dir / "stage2_results.json"
    marker_path = artifact_dir / ".phase1_done"

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
    print(f"站点月度公告目录: {notices_dir(date_str[:7])}/")
    print(f"中间产物目录: {artifact_dir}/")

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
