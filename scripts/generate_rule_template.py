#!/usr/bin/env python3
"""
配置模板生成脚本

为指定的 URL 生成配置模板，包含占位符供 Agent 填充。

用法:
  python3 scripts/generate_rule_template.py --urls '["http://xxx", "http://yyy"]'
  python3 scripts/generate_rule_template.py --file urls_to_process.json
"""

import argparse
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

PROJECT_DIR = Path(__file__).parent.parent
RULES_DIR = PROJECT_DIR / "config" / "rules"

def generate_site_id(url: str) -> str:
    """从 URL 生成 siteId"""
    parsed = urlparse(url)
    # 移除 www. 前缀
    domain = parsed.netloc.replace("www.", "")
    # 替换特殊字符
    site_id = domain.replace(".", "_").replace("-", "_")
    return site_id

def generate_template(url: str, site_name: str = "") -> dict:
    """生成配置模板"""
    site_id = generate_site_id(url)
    
    return {
        "siteId": site_id,
        "siteName": site_name or f"TODO: 填入网站名称",
        "url": url,
        "version": 1,
        "updatedAt": datetime.now().strftime("%Y-%m-%d"),
        "strategy": "TODO: 填入 css 或 anchor 或 semantic",
        "confidence": 0.0,
        "css": {
            "list": "TODO: 填入列表选择器，如 .news-list li",
            "title": "TODO: 填入标题选择器，如 a",
            "date": "TODO: 填入日期选择器，如 .date"
        },
        "anchor": {
            "text": "TODO: 填入锚点文本，如 通知公告",
            "scope": "parent",
            "depth": 2
        },
        "extraction": {
            "linkPrefix": "TODO: 填入链接前缀，如 http://xxx.gov.cn"
        },
        "timeout": 30000,
        "metadata": {
            "source": "agent_generated",
            "needsReview": True
        }
    }

def main():
    parser = argparse.ArgumentParser(description="生成配置模板")
    parser.add_argument("--urls", type=str, default="", help="URL 列表 (JSON 数组)")
    parser.add_argument("--file", type=str, default="", help="包含 URL 的 JSON 文件")
    parser.add_argument("--output", type=str, default="", help="输出目录")

    args = parser.parse_args()

    # 解析 URL 列表
    urls = []
    if args.urls:
        try:
            urls = json.loads(args.urls)
        except:
            # 尝试作为逗号分隔的字符串
            urls = [u.strip() for u in args.urls.split(",") if u.strip()]
    elif args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                urls = data
            elif isinstance(data, dict) and "urls" in data:
                urls = data["urls"]

    if not urls:
        print("[ERROR] 需要提供 URL 列表")
        return

    # 输出目录
    output_dir = Path(args.output) if args.output else RULES_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    # 生成模板
    generated = []
    for url in urls:
        if isinstance(url, dict):
            url_str = url.get("url", "")
            site_name = url.get("siteName", "")
        else:
            url_str = url
            site_name = ""

        if not url_str:
            continue

        template = generate_template(url_str, site_name)
        site_id = template["siteId"]
        
        output_path = output_dir / f"{site_id}.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(template, f, ensure_ascii=False, indent=2)
        
        generated.append({
            "siteId": site_id,
            "url": url_str,
            "templatePath": str(output_path)
        })
        print(f"[INFO] 生成模板: {output_path}")

    print(f"\n[INFO] 共生成 {len(generated)} 个配置模板")
    print("[INFO] 请 Agent 分析页面后填充 TODO 字段")

if __name__ == "__main__":
    main()
