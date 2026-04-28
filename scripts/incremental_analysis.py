#!/usr/bin/env python3
"""
增量分析脚本

对比今天和昨天的抓取结果，只保留新增的公告。

输入:
  - output/{today}/combined_results.json
  - output/{yesterday}/combined_results.json
输出:
  - output/{today}/incremental_results.json
  - output/{today}/增量日报.md

用法:
  python3 scripts/incremental_analysis.py --date 2026-03-15
"""

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Set, Tuple

PROJECT_DIR = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_DIR / "output"

def load_json(path: Path) -> dict:
    """加载 JSON 文件"""
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path: Path, data: dict):
    """保存 JSON 文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_announcement_key(ann: dict) -> str:
    """
    生成公告的唯一标识

    使用 URL 作为主键，如果 URL 不存在则使用 标题+日期
    """
    url = ann.get("url", "")
    if url:
        # 使用 URL 的路径部分作为 key（去除域名变化的影响）
        return url.split("//")[-1].split("/", 1)[-1] if "/" in url else url

    # 备选：标题 + 日期
    title = ann.get("title", "").strip()
    date = ann.get("date", "")
    return f"{title}|{date}"

def extract_existing_keys(results: List[dict]) -> Set[str]:
    """
    从结果中提取所有已存在的公告 key
    """
    keys = set()
    for result in results:
        for ann in result.get("announcements", []):
            key = get_announcement_key(ann)
            keys.add(key)
    return keys

def filter_new_announcements(
    today_results: List[dict],
    yesterday_keys: Set[str]
) -> List[dict]:
    """
    过滤出新增的公告

    只保留今天有，但昨天没有的公告
    """
    new_results = []

    for result in today_results:
        site_id = result.get("siteId", "")
        site_name = result.get("siteName", "")
        url = result.get("url", "")
        status = result.get("status", "")

        # 过滤新增公告
        new_announcements = []
        for ann in result.get("announcements", []):
            key = get_announcement_key(ann)
            if key not in yesterday_keys:
                new_announcements.append(ann)

        # 只保留有新增公告的网站
        if new_announcements:
            new_results.append({
                "siteId": site_id,
                "siteName": site_name,
                "url": url,
                "status": status,
                "announcements": new_announcements,
                "newCount": len(new_announcements)
            })

    return new_results

def generate_incremental_report(
    new_results: List[dict],
    date_str: str,
    output_path: Path
):
    """
    生成增量日报 Markdown
    """
    lines = []

    # 标题
    lines.append(f"# 增量公告日报 - {date_str}")
    lines.append("")

    # 统计
    total_new = sum(r.get("newCount", 0) for r in new_results)
    sites_with_new = len(new_results)

    lines.append("## 概览")
    lines.append("")
    lines.append("| 指标 | 数值 |")
    lines.append("|------|------|")
    lines.append(f"| 有新增公告的网站 | {sites_with_new} |")
    lines.append(f"| 新增公告总数 | {total_new} |")
    lines.append("")

    if not new_results:
        lines.append("今日无新增公告。")
    else:
        # 按网站分组显示
        lines.append("## 新增公告")
        lines.append("")

        for result in new_results:
            site_name = result.get("siteName", "Unknown")
            announcements = result.get("announcements", [])

            lines.append(f"### {site_name}")
            lines.append("")
            lines.append(f"**新增 {len(announcements)} 条**")
            lines.append("")
            lines.append("| 日期 | 公告名称 | 链接 |")
            lines.append("|------|---------|------|")

            for ann in announcements:
                date = ann.get("date", "-")
                title = ann.get("title", "")[:50]
                url = ann.get("url", "")
                link = f"[查看]({url})" if url else "-"
                lines.append(f"| {date} | {title} | {link} |")

            lines.append("")

    # 写入文件
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"[INFO] 增量日报已生成: {output_path}")

def main():
    parser = argparse.ArgumentParser(description="增量分析：对比今天和昨天的抓取结果")
    parser.add_argument("--date", type=str, default="", help="今天的日期 (YYYY-MM-DD)")
    parser.add_argument("--today", type=str, default="", help="今天的结果文件路径")
    parser.add_argument("--yesterday", type=str, default="", help="昨天的结果文件路径")
    parser.add_argument("--output", type=str, default="", help="输出目录")

    args = parser.parse_args()

    # 确定日期和路径
    if args.date:
        today_str = args.date
        today_path = OUTPUT_DIR / today_str / "combined_results.json"

        # 计算昨天日期
        today = datetime.strptime(today_str, "%Y-%m-%d")
        yesterday = today - timedelta(days=1)
        yesterday_str = yesterday.strftime("%Y-%m-%d")
        yesterday_path = OUTPUT_DIR / yesterday_str / "combined_results.json"

        output_dir = OUTPUT_DIR / today_str
    elif args.today:
        today_path = Path(args.today)
        today_str = today_path.parent.name

        if args.yesterday:
            yesterday_path = Path(args.yesterday)
        else:
            # 尝试推断昨天路径
            today = datetime.strptime(today_str, "%Y-%m-%d")
            yesterday = today - timedelta(days=1)
            yesterday_str = yesterday.strftime("%Y-%m-%d")
            yesterday_path = OUTPUT_DIR / yesterday_str / "combined_results.json"

        output_dir = today_path.parent
    else:
        # 默认使用今天日期
        today_str = datetime.now().strftime("%Y-%m-%d")
        today_path = OUTPUT_DIR / today_str / "combined_results.json"

        today = datetime.now()
        yesterday = today - timedelta(days=1)
        yesterday_str = yesterday.strftime("%Y-%m-%d")
        yesterday_path = OUTPUT_DIR / yesterday_str / "combined_results.json"

        output_dir = OUTPUT_DIR / today_str

    # 加载今天的结果
    today_data = load_json(today_path)
    if not today_data:
        print(f"[ERROR] 无法加载今天的结果: {today_path}")
        return

    today_results = today_data.get("results", [])
    print(f"[INFO] 加载今天的结果: {today_path} ({len(today_results)} 个网站)")

    # 加载昨天的结果（可选）
    yesterday_keys = set()
    if yesterday_path.exists():
        yesterday_data = load_json(yesterday_path)
        if yesterday_data:
            yesterday_results = yesterday_data.get("results", [])
            yesterday_keys = extract_existing_keys(yesterday_results)
            print(f"[INFO] 加载昨天的结果: {yesterday_path} ({len(yesterday_keys)} 条公告)")
    else:
        print(f"[INFO] 昨天的结果不存在: {yesterday_path}")
        print(f"[INFO] 将保留今天的所有公告作为新增")

    # 过滤新增公告
    new_results = filter_new_announcements(today_results, yesterday_keys)

    # 统计
    total_new = sum(r.get("newCount", 0) for r in new_results)
    print(f"[INFO] 新增公告: {total_new} 条，涉及 {len(new_results)} 个网站")

    # 构建增量结果
    incremental_data = {
        "date": today_str,
        "generatedAt": datetime.now().isoformat(),
        "stage": "incremental",
        "comparison": {
            "todayDate": today_str,
            "yesterdayDate": yesterday_str if yesterday_keys else None,
            "yesterdayExists": len(yesterday_keys) > 0
        },
        "results": new_results,
        "summary": {
            "sitesWithNew": len(new_results),
            "totalNewAnnouncements": total_new
        }
    }

    # 保存增量结果
    incremental_path = output_dir / "incremental_results.json"
    save_json(incremental_path, incremental_data)
    print(f"[INFO] 增量结果已保存: {incremental_path}")

    # 生成增量日报
    report_path = output_dir / "增量日报.md"
    generate_incremental_report(new_results, today_str, report_path)

if __name__ == "__main__":
    main()
