#!/usr/bin/env python3
"""同步抓取产物到 docs/data/，用于 GitHub Pages 展示。

数据源：output/notices/{YYYY-MM}/*.json（月度站点文件）
产出：docs/data/{date}.json、index.json、latest.json、sites.json

支持两种模式：
  1) 不带参数：增量同步（只处理最新月份 + 重新生成 index/latest/sites）
  2) --full：全量同步（扫描所有月份，适用于数据迁移后）
"""

import json
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
NOTICES_DIR = OUTPUT_DIR / "notices"
DOCS_DATA_DIR = PROJECT_ROOT / "docs" / "data"
CONFIG_URLS_PATH = PROJECT_ROOT / "config" / "urls.json"


def run(cmd, **kwargs):
    print(f"  $ {cmd}")
    return subprocess.run(cmd, shell=True, cwd=PROJECT_ROOT, **kwargs)


def load_site_config() -> dict:
    """从 config/urls.json 加载站点配置，返回 site_id -> {name, category, url} 的映射"""
    if not CONFIG_URLS_PATH.exists():
        return {}
    with open(CONFIG_URLS_PATH, encoding='utf-8') as f:
        data = json.load(f)
    config = {}
    for s in data.get("sources", []):
        sid = s.get("id", "")
        if sid:
            config[sid] = {
                "name": s.get("displayName", s.get("name", "")),
                "category": s.get("category", ""),
                "baseUrl": s.get("url", ""),
            }
    return config


def get_monthly_site_files():
    """获取所有月度站点文件，返回 [(month, file_path), ...] 排序"""
    if not NOTICES_DIR.exists():
        return []
    months = sorted(
        [d for d in NOTICES_DIR.iterdir() if d.is_dir()],
        key=lambda x: x.name
    )
    result = []
    for month_dir in months:
        for f in sorted(month_dir.glob("*.json")):
            result.append((month_dir.name, f))
    return result


def extract_all_from_notices(site_config: dict) -> dict:
    """从所有月度文件中提取公告，按日期分组

    返回: {date_str: [announcement, ...]}
    """
    by_date = defaultdict(list)
    total_items = 0

    for month, filepath in get_monthly_site_files():
        try:
            with open(filepath, encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            print(f"  ⚠️  无法读取 {filepath}")
            continue

        if not isinstance(data, dict):
            continue

        site_id = data.get("siteId", "")
        site_name = data.get("siteName", "")
        announcements = data.get("announcements", [])
        if not isinstance(announcements, list):
            continue

        cfg = site_config.get(site_id, {})
        site_url = cfg.get("baseUrl", "")
        category = cfg.get("category", "")

        for ann in announcements:
            if not isinstance(ann, dict):
                continue
            date = ann.get("date", "")
            if not date:
                continue

            item = {
                "id": ann.get("url", ""),  # 用 url 作为唯一标识
                "title": ann.get("title", ""),
                "url": ann.get("url", ""),
                "date": date,
                "siteId": site_id,
                "siteName": site_name,
                "siteUrl": site_url,
                "category": category,
                "summary": ann.get("summary", ""),
            }
            by_date[date].append(item)
            total_items += 1

    print(f"  📊 从月度文件中共提取 {total_items} 条公告，覆盖 {len(by_date)} 个日期")
    return by_date


def write_date_files(by_date: dict):
    """写入每个日期的 docs/data/{date}.json"""
    written = 0
    for date, items in sorted(by_date.items()):
        # 按 siteName 排序
        items.sort(key=lambda x: (x.get("siteName", ""), x.get("title", "")))
        dst = DOCS_DATA_DIR / f"{date}.json"
        with open(dst, 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        written += 1
        if written <= 5 or written == len(by_date):
            print(f"  ✅ {date}: {len(items)} 条")
        elif written == 6:
            print(f"  ... (共 {len(by_date)} 个日期)")
    print(f"  📁 写入 {written} 个日期文件")


def generate_index_json():
    """从 docs/data/ 已有文件生成 index.json"""
    dates = sorted(
        f.stem for f in DOCS_DATA_DIR.glob("*.json")
        if len(f.stem) == 10 and f.stem[4] == '-'
    )
    index = {"dates": dates}
    with open(DOCS_DATA_DIR / "index.json", 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print(f"  ✅ index.json: {len(dates)} 个日期")
    return dates


def generate_latest(dates: list):
    """生成 latest.json"""
    if not dates:
        return
    latest_date = dates[-1]
    src = DOCS_DATA_DIR / f"{latest_date}.json"
    if src.exists():
        shutil.copy2(src, DOCS_DATA_DIR / "latest.json")
        print(f"  ✅ latest.json → {latest_date}")


def generate_sites_json(site_config: dict):
    """生成 docs/data/sites.json"""
    sites = sorted(
        [{"id": sid, "name": cfg["name"], "category": cfg["category"]}
         for sid, cfg in site_config.items()],
        key=lambda x: x["name"]
    )
    with open(DOCS_DATA_DIR / "sites.json", 'w', encoding='utf-8') as f:
        json.dump(sites, f, ensure_ascii=False, indent=2)
    print(f"  ✅ sites.json: {len(sites)} 个站点")


def main():
    full_mode = '--full' in sys.argv
    DOCS_DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 加载站点配置（需要 siteUrl 和 category）
    site_config = load_site_config()
    print(f"  📋 加载 {len(site_config)} 个站点配置")

    # 提取所有公告，按日期分组
    print()
    if full_mode:
        print("🔄 全量同步模式 — 从所有月度文件读取")
    else:
        print("🔄 增量同步模式 — 从所有月度文件读取")
    by_date = extract_all_from_notices(site_config)

    if not by_date:
        print("❌ 未找到任何公告数据")
        return 1

    # 写入日期文件
    print("\n📁 写入日期文件...")
    write_date_files(by_date)

    # 生成辅助文件
    print("\n📋 生成辅助文件...")
    dates = generate_index_json()
    generate_latest(dates)
    generate_sites_json(site_config)

    # Git 操作
    print("\n📦 Git 提交")
    run("git add docs/data")
    r = run("git diff --cached --quiet")
    if r.returncode == 0:
        print("ℹ️  无变化，无需提交")
        return 0

    msg = f"chore: sync pages data ({'full' if full_mode else 'incremental'})"
    run(f'git commit -m "{msg}"')
    print("\n🚀 推送...")
    r = run("git push origin main")
    if r.returncode != 0:
        print("❌ git push 失败")
        return 1

    print(f"\n🎉 同步完成！")
    return 0


if __name__ == "__main__":
    sys.exit(main())
