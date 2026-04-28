#!/usr/bin/env python3
"""Browser-Agent 抓取编排脚本 - v2"""
import json, sys, argparse
from pathlib import Path
from datetime import date

PROJECT_DIR = Path(__file__).resolve().parent.parent

def load_sites(test_mode=False):
    cfg_file = PROJECT_DIR / "config" / ("urls-test.json" if test_mode else "urls.json")
    data = json.loads(cfg_file.read_text())
    sources = data.get("sources", [])
    return [s for s in sources if s.get("enabled", True)]

def generate_task(site):
    return {
        "siteId": site.get("siteId", ""),
        "siteName": site.get("displayName", ""),
        "siteUrl": site.get("baseUrl", site.get("url", "")),
        "targetUrl": site.get("url", ""),
        "category": site.get("category", ""),
        "outputFields": ["title", "url", "date", "summary"],
        "outputPath": ""  # will be set by caller
    }

def main():
    parser = argparse.ArgumentParser(description="Browser-Agent 抓取编排")
    parser.add_argument("--test", action="store_true", help="使用 urls-test.json")
    parser.add_argument("--dry-run", action="store_true", help="只打印任务")
    parser.add_argument("--date", default=str(date.today()), help="日期 YYYY-MM-DD")
    parser.add_argument("--output-dir", default=None, help="输出目录")
    args = parser.parse_args()

    output_dir = PROJECT_DIR / "output" / args.date
    if args.output_dir:
        output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    sites = load_sites(test_mode=args.test)
    tasks = [generate_task(s) for s in sites]

    if args.dry_run:
        print(f"[DRY-RUN] 将为 {len(tasks)} 个站点生成抓取任务:")
        for t in tasks:
            print(f"  - {t['siteName']} ({t['siteId']}): {t['targetUrl']}")
        print(f"输出目录: {output_dir}")
        return

    # 实际执行时，这里会通过 sessions_spawn 调用 browser-agent
    # 当前版本只生成任务列表到 JSON 文件
    tasks_file = output_dir / "crawl-tasks.json"
    tasks_file.write_text(json.dumps(tasks, ensure_ascii=False, indent=2))
    print(f"已生成 {len(tasks)} 个抓取任务到 {tasks_file}")
    print(f"等待 browser-agent 执行后，结果写入 {output_dir / 'announcements.json'}")

if __name__ == "__main__":
    main()
