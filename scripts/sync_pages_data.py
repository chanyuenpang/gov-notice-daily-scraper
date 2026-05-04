#!/usr/bin/env python3
"""同步抓取产物到 docs/data/，用于 GitHub Pages 展示。

支持两种模式：
  1) 不带参数：增量同步（只处理最新日期 + 重新生成 index/latest/sites）
  2) --full：全量同步（扫描所有日期目录，适用于数据迁移后）
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
DOCS_DATA_DIR = PROJECT_ROOT / "docs" / "data"


def run(cmd, **kwargs):
    print(f"  $ {cmd}")
    return subprocess.run(cmd, shell=True, cwd=PROJECT_ROOT, **kwargs)


def extract_announcements_from_combined(combined_path: Path) -> list:
    """从旧格式 combined_results.json 提取扁平化的 announcements 列表"""
    with open(combined_path, encoding='utf-8') as f:
        data = json.load(f)
    results = data.get('results', [])
    if not isinstance(results, list):
        return []
    announcements = []
    for site in results:
        if not isinstance(site, dict):
            continue
        site_id = site.get('siteId', '')
        site_name = site.get('siteName', '')
        site_url = site.get('url', '')
        for ann in site.get('announcements', []):
            announcements.append({
                'title': ann.get('title', ''),
                'url': ann.get('url', ''),
                'date': ann.get('date', ''),
                'siteId': site_id,
                'siteName': site_name,
                'siteUrl': site_url,
            })
    return announcements


def ensure_announcements_json(date_dir: Path) -> bool:
    """确保日期目录下有有效的 announcements.json，必要时从 combined_results 提取"""
    ann_path = date_dir / 'announcements.json'

    # 如果已存在且有效，直接返回
    if ann_path.exists():
        try:
            with open(ann_path, encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                return len(data) > 0
        except json.JSONDecodeError:
            pass

    # 尝试从 combined_results.json 提取
    combined_path = date_dir / 'combined_results.json'
    if combined_path.exists():
        try:
            announcements = extract_announcements_from_combined(combined_path)
            if announcements:
                with open(ann_path, 'w', encoding='utf-8') as f:
                    json.dump(announcements, f, ensure_ascii=False, indent=2)
                return True
        except (json.JSONDecodeError, KeyError):
            pass

    return False


def sync_date(date_dir: Path) -> bool:
    """同步单个日期目录到 docs/data/，返回是否成功"""
    dirname = date_dir.name
    ann_path = date_dir / 'announcements.json'

    if not ann_path.exists():
        return False

    try:
        with open(ann_path, encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError:
        return False

    if not isinstance(data, list) or len(data) == 0:
        return False

    # 确保每条记录有 date 字段
    for item in data:
        if 'date' not in item or not item['date']:
            item['date'] = dirname

    # 写入 docs/data/{date}.json
    dst_path = DOCS_DATA_DIR / f"{dirname}.json"
    with open(dst_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 复制 crawl-meta.json
    meta_path = date_dir / 'crawl-meta.json'
    if meta_path.exists():
        try:
            with open(meta_path, encoding='utf-8') as f:
                meta = json.load(f)
            with open(DOCS_DATA_DIR / f"{dirname}.meta.json", 'w', encoding='utf-8') as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            pass

    return True


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
    meta_src = DOCS_DATA_DIR / f"{latest_date}.meta.json"
    if meta_src.exists():
        shutil.copy2(meta_src, DOCS_DATA_DIR / "latest.meta.json")
        print(f"  ✅ latest.meta.json → {latest_date}")


def generate_sites_json():
    """从 config/urls.json 提取站点列表生成 docs/data/sites.json"""
    urls_path = PROJECT_ROOT / "config" / "urls.json"
    if not urls_path.exists():
        print("  ⚠️  config/urls.json 不存在，跳过 sites.json")
        return
    with open(urls_path, encoding='utf-8') as f:
        data = json.load(f)
    sites = sorted(
        [{"id": s["id"], "name": s["displayName"], "category": s["category"]}
         for s in data["sources"]],
        key=lambda x: x["name"]
    )
    with open(DOCS_DATA_DIR / "sites.json", 'w', encoding='utf-8') as f:
        json.dump(sites, f, ensure_ascii=False, indent=2)
    print(f"  ✅ sites.json: {len(sites)} 个站点")


def get_date_dirs():
    """获取所有日期目录（排序后）"""
    return sorted(
        [d for d in OUTPUT_DIR.iterdir()
         if d.is_dir() and len(d.name) == 10 and d.name[4] == '-'],
        key=lambda x: x.name
    )


def main():
    full_mode = '--full' in sys.argv
    DOCS_DATA_DIR.mkdir(parents=True, exist_ok=True)

    if full_mode:
        print("🔄 全量同步模式")
        date_dirs = get_date_dirs()
        synced = 0
        for d in date_dirs:
            ensure_announcements_json(d)
            if sync_date(d):
                synced += 1
                print(f"  ✅ {d.name}")
        print(f"\n共同步 {synced} 个日期")
    else:
        print("🔄 增量同步模式")
        date_dirs = get_date_dirs()
        if not date_dirs:
            print("❌ output/ 下没有日期目录")
            return 1
        latest_dir = date_dirs[-1]
        ensure_announcements_json(latest_dir)
        if sync_date(latest_dir):
            print(f"  ✅ 已同步最新日期: {latest_dir.name}")
        else:
            print(f"  ⚠️  最新日期 {latest_dir.name} 无有效数据")

    # 生成辅助文件
    print("\n📋 生成辅助文件...")
    dates = generate_index_json()
    generate_latest(dates)
    generate_sites_json()

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
