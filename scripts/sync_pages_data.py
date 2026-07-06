#!/usr/bin/env python3
"""同步抓取产物到 docs/data/，用于 GitHub Pages 展示。

数据源：output/notices/{YYYY-MM}/*.json（月度站点文件）
产出：docs/data/notices/{YYYY-MM}.json（按月合并）
      docs/data/index.json（日期索引+计数）
      docs/data/sites.json（站点信息）
"""

import json
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
NOTICES_DIR = OUTPUT_DIR / "notices"
DOCS_DATA_DIR = PROJECT_ROOT / "docs" / "data"
DOCS_NOTICES_DIR = DOCS_DATA_DIR / "notices"
CONFIG_URLS_PATH = PROJECT_ROOT / "config" / "urls.json"


def load_site_config() -> dict:
    """从 config/urls.json 加载站点配置"""
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
    """获取所有月度站点文件，返回 [(month, file_path), ...]"""
    if not NOTICES_DIR.exists():
        return []
    result = []
    for month_dir in sorted(NOTICES_DIR.iterdir()):
        if not month_dir.is_dir():
            continue
        for f in sorted(month_dir.glob("*.json")):
            result.append((month_dir.name, f))
    return result


def generate_monthly_notices(site_config: dict):
    """按月合并站点文件到 docs/data/notices/{YYYY-MM}.json"""
    DOCS_NOTICES_DIR.mkdir(parents=True, exist_ok=True)
    
    month_data = defaultdict(list)  # month -> [announcements]
    total = 0
    
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
                "id": ann.get("url", ""),
                "title": ann.get("title", ""),
                "url": ann.get("url", ""),
                "date": date,
                "siteId": site_id,
                "siteName": site_name,
                "siteUrl": site_url,
                "category": category,
                "summary": ann.get("summary", ""),
            }
            month_data[month].append(item)
            total += 1
    
    # 写入月度文件
    for month, items in sorted(month_data.items()):
        items.sort(key=lambda x: (x.get("siteName", ""), x.get("date", ""), x.get("title", "")))
        dst = DOCS_NOTICES_DIR / f"{month}.json"
        with open(dst, 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        print(f"  ✅ {month}.json: {len(items)} 条")
    
    print(f"  📊 共合并 {total} 条公告，{len(month_data)} 个月度文件")
    return month_data


def generate_index_json(month_data: dict):
    """从月度数据生成 index.json（日期列表+计数）"""
    date_counts = {}
    for month, items in month_data.items():
        for item in items:
            date = item.get("date", "")
            if date:
                date_counts[date] = date_counts.get(date, 0) + 1
    
    dates = sorted(date_counts.keys(), reverse=True)
    index = {"dates": dates, "counts": date_counts}
    with open(DOCS_DATA_DIR / "index.json", 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print(f"  ✅ index.json: {len(dates)} 个日期")
    return dates


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


def ensure_nojekyll():
    """确保 docs/.nojekyll 存在，避免 Jekyll 处理 JSON 导致构建超时"""
    nojekyll = PROJECT_ROOT / "docs" / ".nojekyll"
    if not nojekyll.exists():
        nojekyll.touch()
        subprocess.run(["git", "add", "docs/.nojekyll"], cwd=PROJECT_ROOT, capture_output=True)
        print("📄 创建 docs/.nojekyll")


def check_pages_build(max_retries=3):
    """检查 GitHub Pages 构建状态，失败时自动 push 空 commit 重试"""
    print("\n🔍 等待 GitHub Pages 构建...")
    repo = "chanyuenpang/gov-notice-daily-scraper"
    
    for attempt in range(max_retries):
        time.sleep(20)
        try:
            r = subprocess.run(
                ["gh", "api", f"repos/{repo}/pages/builds", "--jq", ".[0].status"],
                cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=15
            )
            if r.returncode != 0:
                print(f"  ⚠️  gh api 失败: {r.stderr.strip()[:80]}")
                continue
            status = r.stdout.strip()
            if status == "built":
                print("✅ GitHub Pages 构建成功")
                return True
            elif status == "errored":
                print(f"⚠️  构建失败，第 {attempt+1}/{max_retries} 次重试...")
                subprocess.run(
                    ["git", "commit", "--allow-empty", "-m", "chore: retry pages build"],
                    cwd=PROJECT_ROOT, capture_output=True
                )
                subprocess.run(["git", "push", "origin", "main"], cwd=PROJECT_ROOT, capture_output=True)
            else:
                print(f"⏳ 状态: {status}，等待...")
        except (subprocess.TimeoutExpired, Exception) as e:
            print(f"  ⚠️  检查异常: {e}")
    
    print("⚠️  构建验证超时，请手动确认 https://notice.yop.hk/")
    return False


def git_commit_and_push():
    """提交并推送 docs/data/ 的变更到 GitHub Pages"""
    print("\n📦 Git 提交...")
    # 确保 .nojekyll 存在（防止 Jekyll 处理大 JSON 超时）
    ensure_nojekyll()
    subprocess.run(["git", "add", "docs/data/"], cwd=PROJECT_ROOT, capture_output=True)
    r = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=PROJECT_ROOT, capture_output=True)
    if r.returncode == 0:
        print("ℹ️  无变化，无需提交")
        return
    subprocess.run(["git", "commit", "-m", "chore: sync pages data"], cwd=PROJECT_ROOT, capture_output=True)
    print("🚀 推送中...")
    r = subprocess.run(["git", "push", "origin", "main"], cwd=PROJECT_ROOT, capture_output=True)
    if r.returncode != 0:
        print(f"❌ 推送失败: {r.stderr.decode()[:200]}")
        return
    print("✅ 已推送")
    # 验证 Pages 构建
    check_pages_build()


def main():
    DOCS_NOTICES_DIR.mkdir(parents=True, exist_ok=True)
    
    site_config = load_site_config()
    print(f"  📋 加载 {len(site_config)} 个站点配置")
    
    print("\n📁 生成月度公告文件...")
    month_data = generate_monthly_notices(site_config)
    
    if not month_data:
        print("❌ 未找到任何公告数据")
        return 1
    
    print("\n📋 生成辅助文件...")
    generate_sites_json(site_config)
    
    print(f"\n🎉 同步完成！共 {len(month_data)} 个月度文件")

    git_commit_and_push()

    return 0


if __name__ == "__main__":
    sys.exit(main())
