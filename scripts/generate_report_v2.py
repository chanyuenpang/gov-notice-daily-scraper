#!/usr/bin/env python3
"""
基于 announcements.json 生成日报。

输入:
  - output/{date}/announcements.json
输出:
  - output/{date}/日报.md

用法:
  python3 scripts/generate_report_v2.py --date 2026-04-28
  python3 scripts/generate_report_v2.py --input output/2026-04-28/announcements.json
"""

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

PROJECT_DIR = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_DIR / "output"
CONFIG_PATH = PROJECT_DIR / "config" / "urls.json"
META_FILE_NAME = "crawl-meta.json"
REPORT_FILE_NAME = "日报.md"


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
            "url": source.get("url") or source.get("baseUrl") or "",
        }
    return mapping


def infer_date_from_path(input_path: Path) -> str:
    parent_name = input_path.parent.name
    try:
        datetime.strptime(parent_name, "%Y-%m-%d")
        return parent_name
    except ValueError:
        return datetime.now().strftime("%Y-%m-%d")


def group_announcements_by_site(announcements: List[dict], source_mapping: Dict[str, dict]) -> Dict[Tuple[str, str], List[dict]]:
    grouped: Dict[Tuple[str, str], List[dict]] = defaultdict(list)
    for ann in announcements:
        site_id = ann.get("siteId", "")
        fallback_name = ann.get("siteName") or site_id or "Unknown"
        site_name = source_mapping.get(site_id, {}).get("displayName", fallback_name)
        grouped[(site_id, site_name)].append(ann)

    def sort_key(item: Tuple[Tuple[str, str], List[dict]]):
        (_, site_name), records = item
        return (-len(records), site_name)

    return dict(sorted(grouped.items(), key=sort_key))


def load_crawl_meta(meta_path: Path) -> dict:
    if not meta_path.exists():
        return {}
    try:
        return load_json(meta_path)
    except Exception:
        return {}


def generate_report_markdown(date_str: str, announcements: List[dict], crawl_meta: dict, source_mapping: Dict[str, dict]) -> str:
    grouped = group_announcements_by_site(announcements, source_mapping)
    total_sites = crawl_meta.get("totalSites")
    success_sites = crawl_meta.get("successSites")
    failed_sites = crawl_meta.get("failedSites")
    total_announcements = crawl_meta.get("totalAnnouncements", len(announcements))
    generated_at = crawl_meta.get("crawledAt") or datetime.now().isoformat(timespec="seconds")

    if total_sites is None:
        site_ids = {ann.get("siteId", "") for ann in announcements if ann.get("siteId")}
        total_sites = len(site_ids)
    if success_sites is None:
        success_sites = len(grouped)
    if failed_sites is None:
        failed_sites = max(total_sites - success_sites, 0)

    lines: List[str] = []
    lines.append("---")
    lines.append('title: "政府网站新闻政策日报"')
    lines.append(f'date: "{date_str}"')
    lines.append(f'source_count: "{total_sites}"')
    lines.append('generated_by: "OpenClaw Daily News Crawler"')
    lines.append("---")
    lines.append("")
    lines.append("# 政府网站新闻政策日报")
    lines.append("")
    lines.append(f"**报告日期**: {date_str}")
    lines.append(f"**数据来源**: {total_sites}个政府网站")
    lines.append(f"**生成时间**: {generated_at}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 概览")
    lines.append("")
    lines.append("| 统计项 | 数量 |")
    lines.append("|--------|------|")
    lines.append(f"| 监控网站数 | {total_sites} |")
    lines.append(f"| 成功抓取网站数 | {success_sites} |")
    lines.append(f"| 失败网站数 | {failed_sites} |")
    lines.append(f"| 新增新闻/政策 | {total_announcements} |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 分站点公告明细")
    lines.append("")

    if not announcements:
        lines.append("今日暂无公告。")
        lines.append("")
    else:
        for (_, site_name), items in grouped.items():
            lines.append(f"### {site_name}")
            lines.append("")
            lines.append(f"**共 {len(items)} 条**")
            lines.append("")
            lines.append("| 日期 | 公告名称 | 链接 |")
            lines.append("|------|----------|------|")

            def ann_sort_key(ann: dict):
                return (ann.get("date") or "", ann.get("title") or "")

            for ann in sorted(items, key=ann_sort_key, reverse=True)[:50]:
                date = ann.get("date") or "-"
                title = (ann.get("title") or "").replace("\n", " ").strip()
                if len(title) > 80:
                    title = title[:77] + "..."
                url = ann.get("url") or ""
                link = f"[查看]({url})" if url else "-"
                lines.append(f"| {date} | {title} | {link} |")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 附：监控网站列表")
    lines.append("")
    for site_id, info in sorted(source_mapping.items(), key=lambda item: item[1]["displayName"]):
        lines.append(f"- {info['displayName']}（{info['category']}）")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"**报告生成时间**: {generated_at}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="基于 announcements.json 生成日报")
    parser.add_argument("--date", type=str, default="", help="日期，格式 YYYY-MM-DD")
    parser.add_argument("--input", type=str, default="", help="announcements.json 路径")
    parser.add_argument("--output", type=str, default="", help="输出 Markdown 路径")
    args = parser.parse_args()

    if args.input:
        input_path = Path(args.input)
        date_str = args.date or infer_date_from_path(input_path)
    elif args.date:
        date_str = args.date
        input_path = OUTPUT_DIR / date_str / "announcements.json"
    else:
        date_str = datetime.now().strftime("%Y-%m-%d")
        input_path = OUTPUT_DIR / date_str / "announcements.json"

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.parent / REPORT_FILE_NAME

    announcements = load_json(input_path)
    if not isinstance(announcements, list):
        raise ValueError(f"announcements.json 应为数组，实际类型: {type(announcements).__name__}")

    source_mapping = load_source_config()
    crawl_meta = load_crawl_meta(input_path.parent / META_FILE_NAME)
    markdown = generate_report_markdown(date_str, announcements, crawl_meta, source_mapping)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(markdown)

    print(f"[INFO] 日报已生成: {output_path}")
    print(f"[INFO] 公告数: {len(announcements)}")


if __name__ == "__main__":
    main()
