#!/usr/bin/env python3
"""
一次性迁移脚本：将旧格式 combined_results.json 转换为 announcements.json，
然后全量同步所有数据到 docs/data/。
"""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
DOCS_DATA_DIR = PROJECT_ROOT / "docs" / "data"


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


def main():
    DOCS_DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: 遍历所有日期目录，迁移旧格式
    print("=" * 60)
    print("Step 1: 迁移旧格式 combined_results.json → announcements.json")
    print("=" * 60)

    migrated = 0
    for d in sorted(OUTPUT_DIR.iterdir()):
        if not d.is_dir():
            continue
        dirname = d.name
        # 跳过月度目录 (长度 != 10)
        if len(dirname) != 10 or dirname[4] != '-':
            continue

        ann_path = d / 'announcements.json'
        combined_path = d / 'combined_results.json'

        if ann_path.exists():
            # 已有 announcements.json，检查是否有效
            try:
                with open(ann_path, encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, list):
                    print(f"  ✅ {dirname}: 已有 announcements.json ({len(data)} 条)")
                    continue
            except json.JSONDecodeError:
                print(f"  ⚠️  {dirname}: announcements.json 损坏，尝试从 combined_results 恢复")

        if not combined_path.exists():
            print(f"  ⏭️  {dirname}: 无 combined_results.json，跳过")
            continue

        # 从 combined_results 提取
        announcements = extract_announcements_from_combined(combined_path)
        if announcements:
            with open(ann_path, 'w', encoding='utf-8') as f:
                json.dump(announcements, f, ensure_ascii=False, indent=2)
            print(f"  🔄 {dirname}: 从 combined_results 提取 {len(announcements)} 条 → announcements.json")
            migrated += 1
        else:
            print(f"  ⚠️  {dirname}: combined_results 中无 announcements 数据")

    print(f"\n共迁移 {migrated} 个日期目录\n")

    # Step 2: 全量同步到 docs/data/
    print("=" * 60)
    print("Step 2: 全量同步到 docs/data/")
    print("=" * 60)

    synced_dates = []
    total_announcements = 0

    for d in sorted(OUTPUT_DIR.iterdir()):
        if not d.is_dir():
            continue
        dirname = d.name
        if len(dirname) != 10 or dirname[4] != '-':
            continue

        ann_path = d / 'announcements.json'
        if not ann_path.exists():
            continue

        try:
            with open(ann_path, encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError:
            print(f"  ⚠️  {dirname}: announcements.json 损坏，跳过")
            continue

        if not isinstance(data, list):
            print(f"  ⚠️  {dirname}: announcements 不是数组，跳过")
            continue

        if len(data) == 0:
            print(f"  ⏭️  {dirname}: 0 条公告，跳过")
            continue

        # 确保每条记录有 date 字段
        for item in data:
            if 'date' not in item or not item['date']:
                item['date'] = dirname

        # 写入 docs/data/{date}.json
        dst_path = DOCS_DATA_DIR / f"{dirname}.json"
        with open(dst_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # 复制 crawl-meta.json 如果存在
        meta_path = d / 'crawl-meta.json'
        if meta_path.exists():
            try:
                with open(meta_path, encoding='utf-8') as f:
                    meta = json.load(f)
                with open(DOCS_DATA_DIR / f"{dirname}.meta.json", 'w', encoding='utf-8') as f:
                    json.dump(meta, f, ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                pass

        synced_dates.append(dirname)
        total_announcements += len(data)
        print(f"  ✅ {dirname}: {len(data)} 条 → docs/data/{dirname}.json")

    print(f"\n共同步 {len(synced_dates)} 个日期，{total_announcements} 条公告")

    # Step 3: 生成 index.json
    print("\n" + "=" * 60)
    print("Step 3: 生成 index.json")
    print("=" * 60)

    index = {"dates": synced_dates}
    with open(DOCS_DATA_DIR / "index.json", 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print(f"  ✅ index.json: {len(synced_dates)} 个日期")

    # Step 4: 生成 latest.json (指向最新日期)
    print("\n" + "=" * 60)
    print("Step 4: 生成 latest.json")
    print("=" * 60)

    if synced_dates:
        latest_date = synced_dates[-1]
        src_path = DOCS_DATA_DIR / f"{latest_date}.json"
        if src_path.exists():
            import shutil
            shutil.copy2(src_path, DOCS_DATA_DIR / "latest.json")
            print(f"  ✅ latest.json → {latest_date}")

            meta_src = DOCS_DATA_DIR / f"{latest_date}.meta.json"
            if meta_src.exists():
                shutil.copy2(meta_src, DOCS_DATA_DIR / "latest.meta.json")
                print(f"  ✅ latest.meta.json → {latest_date}")

    # Step 5: 生成 sites.json
    print("\n" + "=" * 60)
    print("Step 5: 生成 sites.json")
    print("=" * 60)

    urls_path = PROJECT_ROOT / "config" / "urls.json"
    if urls_path.exists():
        with open(urls_path, encoding='utf-8') as f:
            url_data = json.load(f)
        sites = sorted(
            [{"id": s["id"], "name": s["displayName"], "category": s["category"]}
             for s in url_data["sources"]],
            key=lambda x: x["name"]
        )
        with open(DOCS_DATA_DIR / "sites.json", 'w', encoding='utf-8') as f:
            json.dump(sites, f, ensure_ascii=False, indent=2)
        print(f"  ✅ sites.json: {len(sites)} 个站点")

    # Summary
    print("\n" + "=" * 60)
    print("📊 数据统计")
    print("=" * 60)
    print(f"  日期范围: {synced_dates[0] if synced_dates else 'N/A'} ~ {synced_dates[-1] if synced_dates else 'N/A'}")
    print(f"  日期数量: {len(synced_dates)}")
    print(f"  公告总数: {total_announcements}")

    # 每个 docs/data/{date}.json 的行数统计
    print("\n  docs/data/ 文件列表:")
    for f in sorted(DOCS_DATA_DIR.glob("*.json")):
        if f.name in ('index.json', 'sites.json', 'latest.json', 'latest.meta.json'):
            continue
        with open(f, encoding='utf-8') as fp:
            d = json.load(fp)
        count = len(d) if isinstance(d, list) else '?'
        print(f"    {f.name}: {count} 条")


if __name__ == "__main__":
    main()
