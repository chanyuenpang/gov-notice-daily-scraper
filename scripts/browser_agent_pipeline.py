#!/usr/bin/env python3
"""
Browser-Agent 抓取编排入口脚本

职责：
1. 读取 config/urls.json 或 urls-test.json
2. 为每个站点生成 browser-agent 任务输入模板
3. 输出规划结果到 output/{date}/ 下

本脚本不执行真实网页抓取，只生成编排计划和任务模板。
实际抓取由 OpenClaw 的 browser-agent subagent 执行。
"""

import json
import argparse
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
OUTPUT_DIR = PROJECT_ROOT / "output"

CST = timezone(timedelta(hours=8))


def load_sources(config_path: str) -> list[dict]:
    """加载站点配置"""
    p = Path(config_path)
    if not p.exists():
        print(f"[ERROR] 配置文件不存在: {p}", file=sys.stderr)
        sys.exit(1)
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("sources", [])


def filter_enabled(sources: list[dict]) -> list[dict]:
    """只保留 enabled 的站点"""
    return [s for s in sources if s.get("enabled", True)]


def generate_task_template(source: dict, date_str: str, output_base: Path) -> dict:
    """为单个站点生成 browser-agent 任务输入模板"""
    site_id = source["id"]
    task_output_path = output_base / f"task_{site_id}.json"

    return {
        "taskId": f"{site_id}_{date_str}",
        "siteId": site_id,
        "siteName": source.get("displayName", source.get("name", "")),
        "category": source.get("category", ""),
        "targetUrl": source["url"],
        "baseUrl": source.get("baseUrl", ""),
        "extractionGoal": (
            "从该政府网站公告列表页提取最新公告信息，包括：标题、详情页链接、发布日期。"
            "如果是列表页，提取最近30天的公告条目。"
        ),
        "outputFields": [
            {"name": "title", "type": "string", "required": True, "description": "公告标题"},
            {"name": "url", "type": "string", "required": True, "description": "公告详情页URL"},
            {"name": "date", "type": "string", "required": True, "description": "发布日期，YYYY-MM-DD格式"},
            {"name": "summary", "type": "string", "required": False, "description": "公告摘要"},
        ],
        "outputFormat": "json",
        "outputPath": str(task_output_path),
        "expectedSchema": "docs/json-schema.md",
        "options": {
            "waitAfterLoad": 3000,
            "scrollToListBottom": True,
        },
    }


def build_crawl_plan(sources: list[dict], date_str: str) -> dict:
    """构建完整抓取计划"""
    output_base = OUTPUT_DIR / date_str
    output_base.mkdir(parents=True, exist_ok=True)

    tasks = []
    for source in sources:
        task = generate_task_template(source, date_str, output_base)
        tasks.append(task)

    plan = {
        "planVersion": "1.0",
        "date": date_str,
        "createdAt": datetime.now(CST).isoformat(),
        "totalTasks": len(tasks),
        "tasks": tasks,
    }

    # 写入抓取计划
    plan_path = output_base / "crawl-plan.json"
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    print(f"[OK] 抓取计划已写入: {plan_path}")

    # 写入 crawl-meta.json 初始骨架
    meta = {
        "date": date_str,
        "crawledAt": None,
        "totalSites": len(tasks),
        "successSites": 0,
        "failedSites": 0,
        "totalAnnouncements": 0,
        "newAnnouncements": 0,
        "sites": [
            {
                "siteId": t["siteId"],
                "siteName": t["siteName"],
                "status": "pending",
                "announcementsCount": 0,
                "newCount": None,
                "durationMs": None,
                "strategyUsed": "browser-agent",
                "error": None,
            }
            for t in tasks
        ],
    }
    meta_path = output_base / "crawl-meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"[OK] crawl-meta 初始骨架已写入: {meta_path}")

    # 写入 announcements.json 初始空数组
    ann_path = output_base / "announcements.json"
    with open(ann_path, "w", encoding="utf-8") as f:
        json.dump([], f, ensure_ascii=False, indent=2)
    print(f"[OK] announcements.json 初始空数组已写入: {ann_path}")

    return plan


def print_summary(plan: dict):
    """打印摘要"""
    tasks = plan["tasks"]
    print(f"\n{'='*50}")
    print(f"抓取编排计划 | 日期: {plan['date']}")
    print(f"{'='*50}")
    print(f"总站点数: {len(tasks)}")
    for t in tasks:
        print(f"  - [{t['siteId']}] {t['siteName']} -> {t['targetUrl']}")
    print(f"{'='*50}")
    print(f"下一步: 使用 OpenClaw browser-agent 逐站执行任务模板")


def main():
    parser = argparse.ArgumentParser(description="Browser-Agent 抓取编排入口")
    parser.add_argument(
        "--config",
        default=str(CONFIG_DIR / "urls-test.json"),
        help="站点配置文件路径 (默认: config/urls-test.json)",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="抓取日期，YYYY-MM-DD格式 (默认: 今天)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅打印计划，不写文件",
    )
    args = parser.parse_args()

    date_str = args.date or datetime.now(CST).strftime("%Y-%m-%d")

    print(f"[INFO] 加载配置: {args.config}")
    sources = load_sources(args.config)
    sources = filter_enabled(sources)
    print(f"[INFO] 已启用站点数: {len(sources)}")

    if args.dry_run:
        for s in sources:
            print(f"  - [{s['id']}] {s.get('displayName', '')} -> {s['url']}")
        print(f"[DRY-RUN] 共 {len(sources)} 个站点，未写入文件")
        return

    plan = build_crawl_plan(sources, date_str)
    print_summary(plan)


if __name__ == "__main__":
    main()
