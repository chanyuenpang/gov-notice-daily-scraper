#!/usr/bin/env python3
"""
迁移脚本: urls.json v2 → v3 + per-URL 规则文件

输入:
  - config/urls.json (v2 格式)
  - config/crawl-state.json

输出:
  - config/urls.json (v3 精简格式)
  - config/rules/{site_id}.json (per-URL 规则文件)
  - config/urls-v2-backup.json (备份)
"""

import json
import shutil
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
CONFIG_DIR = PROJECT_DIR / "config"
RULES_DIR = CONFIG_DIR / "rules"

def load_json(path: Path) -> dict:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(path: Path, data: dict, indent=2):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)

def migrate_source_to_rule(source: dict, crawl_state: dict) -> dict | None:
    """
    将 v2 source 转换为 per-URL 规则文件格式
    
    返回 None 表示不生成规则文件（让它走冷启动）
    """
    site_id = source["id"]
    selector = source.get("selector", {})
    confidence = selector.get("confidence", 0)
    selector_source = selector.get("source", "manual")
    
    # 迁移决策：
    # 1. 如果 confidence >= 0.7 且 source="learned" → 生成 css 规则
    # 2. 如果 crawl_state 显示该网站有成功记录 → 生成 css 规则（选择器有效）
    # 3. 否则不生成规则文件（让它走冷启动）
    
    site_state = crawl_state.get("sites", {}).get(site_id, {})
    has_success = site_state.get("status") == "success" or site_state.get("totalSuccessCount", 0) > 0
    
    should_generate_rule = (
        (confidence >= 0.7 and selector_source == "learned") or
        has_success
    )
    
    if not should_generate_rule:
        return None
    
    # 提取 CSS 选择器
    # v2 的 selector.list 可能是逗号分隔的多个选择器，取第一个
    list_selector = selector.get("list", "")
    if "," in list_selector:
        list_selector = list_selector.split(",")[0].strip()
    
    title_selector = selector.get("title", "")
    if "," in title_selector:
        title_selector = title_selector.split(",")[0].strip()
    
    date_selector = selector.get("date", "")
    if "," in date_selector:
        date_selector = date_selector.split(",")[0].strip()
    
    link_selector = selector.get("link", "a")
    
    rule = {
        "siteId": site_id,
        "version": 1,
        "updatedAt": datetime.now().strftime("%Y-%m-%d"),
        "strategy": "css",
        "confidence": confidence,
        "css": {
            "list": list_selector,
            "title": title_selector,
            "date": date_selector,
            "link": link_selector
        },
        "extraction": {
            "linkPrefix": source.get("baseUrl", ""),
            "dateFormats": ["YYYY-MM-DD", "YYYY/MM/DD", "YYYY年MM月DD日", "MM-DD"]
        },
        "antiCrawl": {
            "waitAfterLoad": 2000,
            "userAgent": "random"
        },
        "timeout": 30000,
        "metadata": {
            "source": f"migrated_from_v2_{selector_source}",
            "pageStructure": source.get("learning", {}).get("pageStructure", {})
        },
        "notes": source.get("fallback", {}).get("notes", "") or ""
    }
    
    return rule

def migrate_source_to_v3(source: dict, crawl_state: dict) -> dict:
    """将 v2 source 转换为 v3 精简格式"""
    site_id = source["id"]
    site_state = crawl_state.get("sites", {}).get(site_id, {})
    
    return {
        "id": site_id,
        "name": source["name"],
        "category": source.get("category", ""),
        "url": source["url"],
        "baseUrl": source.get("baseUrl", ""),
        "enabled": True,
        "state": {
            "lastCrawlDate": site_state.get("lastCrawlDate"),
            "lastSuccessDate": site_state.get("lastSuccessDate"),
            "lastAnnouncementTitle": None,  # v2 没有这个字段
            "lastAnnouncementDate": site_state.get("lastAnnouncementDate"),
            "consecutiveFailures": site_state.get("consecutiveFailures", 0)
        }
    }

def main():
    print("=" * 60)
    print("迁移脚本: urls.json v2 → v3 + per-URL 规则文件")
    print("=" * 60)
    
    # 加载输入文件
    urls_v2_path = CONFIG_DIR / "urls.json"
    crawl_state_path = CONFIG_DIR / "crawl-state.json"
    
    if not urls_v2_path.exists():
        print(f"错误: {urls_v2_path} 不存在")
        return
    
    urls_v2 = load_json(urls_v2_path)
    crawl_state = load_json(crawl_state_path) if crawl_state_path.exists() else {"sites": {}}
    
    print(f"加载 v2 urls.json: {len(urls_v2.get('sources', []))} 个 URL")
    print(f"加载 crawl-state.json: {len(crawl_state.get('sites', {}))} 个状态")
    
    # 备份 v2 文件
    backup_path = CONFIG_DIR / "urls-v2-backup.json"
    shutil.copy(urls_v2_path, backup_path)
    print(f"备份 v2 到: {backup_path}")
    
    # 创建规则目录
    RULES_DIR.mkdir(parents=True, exist_ok=True)
    
    # 迁移每个 source
    v3_sources = []
    rules_created = 0
    rules_skipped = 0
    
    for source in urls_v2.get("sources", []):
        site_id = source["id"]
        
        # 生成 v3 source
        v3_source = migrate_source_to_v3(source, crawl_state)
        v3_sources.append(v3_source)
        
        # 生成规则文件
        rule = migrate_source_to_rule(source, crawl_state)
        if rule:
            rule_path = RULES_DIR / f"{site_id}.json"
            save_json(rule_path, rule)
            rules_created += 1
            status_icon = "✓" if crawl_state.get("sites", {}).get(site_id, {}).get("status") == "success" else "?"
            print(f"  生成规则: {site_id}.json {status_icon}")
        else:
            rules_skipped += 1
            print(f"  跳过规则: {site_id} (将走冷启动)")
    
    # 生成 v3 urls.json
    urls_v3 = {
        "version": "3.0",
        "globalConfig": {
            "scriptTimeout": 30000,
            "subagentTimeout": 60000,
            "concurrentLimit": urls_v2.get("globalConfig", {}).get("concurrentLimit", 3)
        },
        "sources": v3_sources
    }
    
    save_json(urls_v2_path, urls_v3)
    
    # 输出统计
    print()
    print("=" * 60)
    print("迁移完成!")
    print(f"  - v3 sources: {len(v3_sources)}")
    print(f"  - 规则文件创建: {rules_created}")
    print(f"  - 规则文件跳过: {rules_skipped} (将走冷启动)")
    print(f"  - 输出目录: {RULES_DIR}")
    print("=" * 60)
    
    # 验证
    print("\n验证:")
    print(f"  ls {RULES_DIR} | wc -l  → 应为 {rules_created}")
    
    # 列出生成的规则文件
    rule_files = list(RULES_DIR.glob("*.json"))
    print(f"  实际规则文件数: {len(rule_files)}")

if __name__ == "__main__":
    main()
