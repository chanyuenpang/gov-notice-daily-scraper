#!/usr/bin/env python3
"""同步最新抓取产物到 docs/data/，用于 GitHub Pages 展示。"""

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


def generate_sites_json():
    """从 config/urls.json 提取站点列表生成 docs/data/sites.json"""
    urls_path = PROJECT_ROOT / "config" / "urls.json"
    dst_path = DOCS_DATA_DIR / "sites.json"
    if not urls_path.exists():
        print("⚠️  config/urls.json 不存在，跳过生成 sites.json")
        return
    import json
    with open(urls_path, encoding='utf-8') as f:
        data = json.load(f)
    sites = sorted(
        [{"id": s["id"], "name": s["displayName"], "category": s["category"]} for s in data["sources"]],
        key=lambda x: x["name"]
    )
    with open(dst_path, 'w', encoding='utf-8') as f:
        json.dump(sites, f, ensure_ascii=False, indent=2)
    print(f"✅ sites.json 已生成（{len(sites)} 个站点）")


def main():
    # 1. 找最新日期目录
    date_dirs = sorted(
        [d.name for d in OUTPUT_DIR.iterdir() if d.is_dir() and len(d.name) == 10 and d.name[4] == '-']
    )
    if not date_dirs:
        print("❌ output/ 下没有日期目录，退出")
        return 1
    date = date_dirs[-1]
    print(f"📌 最新日期目录: {date}")
    src_dir = OUTPUT_DIR / date

    # 2. 确保目标目录存在
    DOCS_DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 3. 复制文件
    files = [
        ("announcements.json", f"{date}.json"),
        ("crawl-meta.json", f"{date}.meta.json"),
    ]
    for src_name, dst_name in files:
        src = src_dir / src_name
        dst = DOCS_DATA_DIR / dst_name
        if not src.exists():
            print(f"⚠️  {src} 不存在，跳过")
            continue
        shutil.copy2(src, dst)
        print(f"✅ {src_name} → docs/data/{dst_name}")

    # 4. 生成 latest 链接
    ann_src = src_dir / "announcements.json"
    meta_src = src_dir / "crawl-meta.json"
    if ann_src.exists():
        shutil.copy2(ann_src, DOCS_DATA_DIR / "latest.json")
        print(f"✅ latest.json 已生成")
    if meta_src.exists():
        shutil.copy2(meta_src, DOCS_DATA_DIR / "latest.meta.json")
        print(f"✅ latest.meta.json 已生成")

    # 5. 生成 sites.json（全量站点列表，用于前端站点筛选下拉）
    generate_sites_json()

    # 6. Git 操作
    # 7. 检查是否有变化
    print("\n📦 git add docs/data")
    r = run("git add docs/data")
    if r.returncode != 0:
        print("❌ git add 失败")
        return 1

    r = run("git diff --cached --quiet")
    if r.returncode == 0:
        print("ℹ️  无变化，无需提交")
        return 0

    msg = f"chore: sync pages data for {date}"
    print(f"\n📝 git commit: {msg}")
    r = run(f'git commit -m "{msg}"')
    if r.returncode != 0:
        print("❌ git commit 失败")
        return 1

    print("\n🚀 git push origin main")
    r = run("git push origin main")
    if r.returncode != 0:
        print("❌ git push 失败")
        return 1

    print(f"\n🎉 同步完成！日期: {date}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
