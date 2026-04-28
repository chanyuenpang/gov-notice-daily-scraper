#!/usr/bin/env python3
"""
基于 announcements.json 生成增量日报。

输入:
  - output/{date}/announcements.json
  - output/{yesterday}/announcements.json
输出:
  - output/{date}/增量日报.md

新增判断逻辑:
  - 按 url 去重，url 不在昨天列表中即为新增

用法:
  python3 scripts/incremental_analysis_v2.py --date 2026-04-28
  python3 scripts/incremental_analysis_v2.py --today output/2026-04-28/announcements.json --yesterday output/2026-04-27/announcements.json
"""

import argparse
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Set, Tuple

PROJECT_DIR = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_DIR / "output"
CONFIG_PATH = PROJECT_DIR / "config" / "urls.json"
REPORT_FILE_NAME = "增量日报.md"


def load_json(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_source_config() -> Dict[str, dict]:
    config = load_json(CONFIG_PATH)
    mapping: Dict[str, dict] = {}
    for source in config.get("sources", []):
        site_id = source.get("id")
        if not site_id:
            continue
        mapping[site_id] = {
            "displayName": source.get("displayName") or source.get("name") or site_id,
            "category": source.get("category") or "未分类",
        }
    return mapping


def normalize_url(url: str) -> str:
    return (url or "").strip()


def extract_urls(announcements: List[dict]) -> Set[str]:
    urls: Set[str] = set()
    for ann in announcements:
        url = normalize_url(ann.get("url", ""))
        if url:
            urls.add(url)
    return urls


def group_by_site(announcements: List[dict], source_mapping: Dict[str, dict]) -> Dict[Tuple[str, str], List[dict]]:
    grouped: Dict[Tuple[str, str], List[dict]] = defaultdict(list)
    for ann in announcements:
        site_id = ann.get("siteId", "")
        fallback_name = ann.get("siteName") or site_id or "Unknown"
        site_name = source_mapping.get(site_id, {}).get("displayName", fallback_name)
        grouped[(site_id, site_name)].append(ann)
    return dict(sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0][1])))


def filter_new_announcements(today_announcements: List[dict], yesterday_urls: Set[str]) -> List[dict]:
    new_items: List[dict] = []
    seen_today_urls: Set[str] = set()

    for ann in today_announcements:
        url = normalize_url(ann.get("url", ""))
        if not url:
            continue
        if url in seen_today_urls:
            continue
        seen_today_urls.add(url)
        if url not in yesterday_urls:
            new_items.append(ann)

    return new_items


def generate_incremental_markdown(date_str: str, new_announcements: List[dict], source_mapping: Dict[str, dict], yesterday_exists: bool) -> str:
    grouped = group_by_site(new_announcements, source_mapping)
    total_new = len(new_announcements)
    sites_with_new = len(grouped)
    generated_at = datetime.now().isoformat(timespec="seconds")

    lines: List[str] = []
    lines.append(f"# 增量公告日报 - {date_str}")
    lines.append("")
    lines.append("## 概览")
    lines.append("")
    lines.append("| 指标 | 数值 |")
    lines.append("|------|------|")
    lines.append(f"| 对比日期 | {date_str} vs {'前一日' if yesterday_exists else '无历史数据'} |")
    lines.append(f"| 有新增公告的网站 | {sites_with_new} |")
    lines.append(f"| 新增公告总数 | {total_new} |")
    lines.append("")

    if not yesterday_exists:
        lines.append("> 昨日 announcements.json 不存在，本次将今天全部公告视为新增。")
        lines.append("")

    if not new_announcements:
        lines.append("今日无新增公告。")
        lines.append("")
    else:
        lines.append("## 新增公告")
        lines.append("")
        for (_, site_name), items in grouped.items():
            lines.append(f"### {site_name}")
            lines.append("")
            lines.append(f"**新增 {len(items)} 条**")
            lines.append("")
            lines.append("| 日期 | 公告名称 | 链接 |")
            lines.append("|------|----------|------|")
            for ann in sorted(items, key=lambda item: ((item.get('date') or ''), (item.get('title') or '')), reverse=True):
                date = ann.get("date") or "-"
                title = (ann.get("title") or "").replace("\n", " ").strip()
                if len(title) > 80:
                    title = title[:77] + "..."
                url = ann.get("url") or ""
                link = f"[查看]({url})" if url else "-"
                lines.append(f"| {date} | {title} | {link} |")
            lines.append("")

    lines.append(f"**报告生成时间**: {generated_at}")
    return "\n".join(lines)


def resolve_paths(args) -> Tuple[str, Path, Path, Path]:
    if args.date:
        today_str = args.date
        today = datetime.strptime(today_str, "%Y-%m-%d")
        yesterday_str = (today - timedelta(days=1)).strftime("%Y-%m-%d")
        today_path = OUTPUT_DIR / today_str / "announcements.json"
        yesterday_path = OUTPUT_DIR / yesterday_str / "announcements.json"
        output_path = Path(args.output) if args.output else OUTPUT_DIR / today_str / REPORT_FILE_NAME
        return today_str, today_path, yesterday_path, output_path

    if args.today:
        today_path = Path(args.today)
        today_str = today_path.parent.name
        if args.yesterday:
            yesterday_path = Path(args.yesterday)
        else:
            today = datetime.strptime(today_str, "%Y-%m-%d")
            yesterday_str = (today - timedelta(days=1)).strftime("%Y-%m-%d")
            yesterday_path = OUTPUT_DIR / yesterday_str / "announcements.json"
        output_path = Path(args.output) if args.output else today_path.parent / REPORT_FILE_NAME
        return today_str, today_path, yesterday_path, output_path

    today_str = datetime.now().strftime("%Y-%m-%d")
    today = datetime.strptime(today_str, "%Y-%m-%d")
    yesterday_str = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    today_path = OUTPUT_DIR / today_str / "announcements.json"
    yesterday_path = OUTPUT_DIR / yesterday_str / "announcements.json"
    output_path = Path(args.output) if args.output else OUTPUT_DIR / today_str / REPORT_FILE_NAME
    return today_str, today_path, yesterday_path, output_path


def main():
    parser = argparse.ArgumentParser(description="基于 announcements.json 做增量分析")
    parser.add_argument("--date", type=str, default="", help="日期，格式 YYYY-MM-DD")
    parser.add_argument("--today", type=str, default="", help="今天的 announcements.json 路径")
    parser.add_argument("--yesterday", type=str, default="", help="昨天的 announcements.json 路径")
    parser.add_argument("--output", type=str, default="", help="输出 Markdown 路径")
    args = parser.parse_args()

    today_str, today_path, yesterday_path, output_path = resolve_paths(args)

    today_announcements = load_json(today_path)
    if not isinstance(today_announcements, list):
        raise ValueError(f"today announcements.json 应为数组，实际类型: {type(today_announcements).__name__}")

    yesterday_exists = yesterday_path.exists()
    if yesterday_exists:
        yesterday_announcements = load_json(yesterday_path)
        if not isinstance(yesterday_announcements, list):
            raise ValueError(f"yesterday announcements.json 应为数组，实际类型: {type(yesterday_announcements).__name__}")
        yesterday_urls = extract_urls(yesterday_announcements)
    else:
        yesterday_urls = set()

    source_mapping = load_source_config()
    new_announcements = filter_new_announcements(today_announcements, yesterday_urls)
    markdown = generate_incremental_markdown(today_str, new_announcements, source_mapping, yesterday_exists)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(markdown)

    print(f"[INFO] 增量日报已生成: {output_path}")
    print(f"[INFO] 今天公告数: {len(today_announcements)}")
    print(f"[INFO] 新增公告数: {len(new_announcements)}")
    print(f"[INFO] 昨日文件存在: {'yes' if yesterday_exists else 'no'}")


if __name__ == "__main__":
    main()
