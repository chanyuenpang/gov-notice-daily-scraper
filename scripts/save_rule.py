#!/usr/bin/env python3
"""
配置生成脚本

Agent 分析页面后，调用此脚本生成配置文件。
格式由脚本保证，Agent 只需提供参数。

用法:
  python3 scripts/save_rule.py \
    --site-id "as_xm_gov_cn" \
    --site-name "厦门市数据管理局" \
    --url "https://as.xm.gov.cn/zwgk/tzgg/" \
    --strategy "css" \
    --css-list ".news-list li" \
    --css-title "a" \
    --css-date ".date" \
    --link-prefix "https://as.xm.gov.cn"

  python3 scripts/save_rule.py \
    --site-id "xxx" \
    --strategy "anchor" \
    --anchor-text "通知公告"
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
RULES_DIR = PROJECT_DIR / "config" / "rules"

def save_rule(
    site_id: str,
    site_name: str = "",
    url: str = "",
    strategy: str = "css",
    confidence: float = 0.8,
    css_list: str = "",
    css_title: str = "",
    css_date: str = "",
    anchor_text: str = "",
    anchor_scope: str = "parent",
    anchor_depth: int = 2,
    link_prefix: str = "",
    timeout: int = 30000,
    overwrite: bool = False,
    source: str = "manual",
    metadata: dict = None
) -> dict:
    """
    生成并保存配置文件
    
    参数:
        site_id: 网站 ID
        site_name: 网站名称
        url: 网站 URL
        strategy: 抓取策略 (css/anchor/semantic)
        confidence: 置信度 (0-1)
        css_list: CSS 列表选择器
        css_title: CSS 标题选择器
        css_date: CSS 日期选择器
        anchor_text: 锚点文本
        anchor_scope: 锚点范围
        anchor_depth: 锚点深度
        link_prefix: 链接前缀
        timeout: 超时时间(ms)
        overwrite: 是否覆盖现有配置
        source: 规则来源 (manual/stage2_subagent/agent_generated/migrated)
        metadata: 额外元数据字典
    
    返回:
        成功: {"success": True, "path": ..., "siteId": ..., "strategy": ..., "version": ...}
        失败: {"error": "错误信息"}
    """
    
    # 构建配置
    config = {
        "siteId": site_id,
        "siteName": site_name or site_id,
        "url": url,
        "version": 1,
        "updatedAt": datetime.now().strftime("%Y-%m-%d"),
        "strategy": strategy,
        "confidence": confidence,
        "timeout": timeout
    }
    
    # 根据策略添加配置
    if strategy == "css":
        if not css_list or not css_title:
            return {"error": "css 策略需要 --css-list 和 --css-title 参数"}
        config["css"] = {
            "list": css_list,
            "title": css_title,
            "date": css_date
        }
    elif strategy == "anchor":
        if not anchor_text:
            return {"error": "anchor 策略需要 --anchor-text 参数"}
        config["anchor"] = {
            "text": anchor_text,
            "scope": anchor_scope,
            "depth": anchor_depth
        }
    elif strategy == "semantic":
        # semantic 不需要额外配置
        pass
    else:
        return {"error": f"未知策略: {strategy}"}
    
    # 添加链接前缀
    if link_prefix:
        config["extraction"] = {"linkPrefix": link_prefix}
    
    # 添加元数据
    if metadata:
        config["metadata"] = metadata
    else:
        # 默认元数据，包含来源信息
        config["metadata"] = {
            "source": source,
            "generatedAt": datetime.now().isoformat()
        }
    
    # 保存文件
    RULES_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RULES_DIR / f"{site_id}.json"
    
    if output_path.exists() and not overwrite:
        # 读取现有配置，更新版本号
        with open(output_path, "r", encoding="utf-8") as f:
            existing = json.load(f)
            config["version"] = existing.get("version", 1) + 1
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    
    return {
        "success": True,
        "path": str(output_path),
        "siteId": site_id,
        "strategy": strategy,
        "version": config["version"]
    }

def main():
    parser = argparse.ArgumentParser(description="生成抓取配置文件")
    
    # 必需参数
    parser.add_argument("--site-id", required=True, help="网站 ID")
    parser.add_argument("--strategy", required=True, choices=["css", "anchor", "semantic"], help="抓取策略")
    
    # 可选参数
    parser.add_argument("--site-name", default="", help="网站名称")
    parser.add_argument("--url", default="", help="网站 URL")
    parser.add_argument("--confidence", type=float, default=0.8, help="置信度 (0-1)")
    
    # CSS 策略参数
    parser.add_argument("--css-list", default="", help="CSS 列表选择器")
    parser.add_argument("--css-title", default="", help="CSS 标题选择器")
    parser.add_argument("--css-date", default="", help="CSS 日期选择器")
    
    # Anchor 策略参数
    parser.add_argument("--anchor-text", default="", help="锚点文本")
    parser.add_argument("--anchor-scope", default="parent", help="锚点范围")
    parser.add_argument("--anchor-depth", type=int, default=2, help="锚点深度")
    
    # 其他参数
    parser.add_argument("--link-prefix", default="", help="链接前缀")
    parser.add_argument("--timeout", type=int, default=30000, help="超时时间(ms)")
    parser.add_argument("--overwrite", action="store_true", help="覆盖现有配置")
    parser.add_argument("--source", default="manual", 
                        choices=["manual", "stage2_subagent", "agent_generated", "migrated"],
                        help="规则来源 (默认: manual)")
    
    args = parser.parse_args()
    
    result = save_rule(
        site_id=args.site_id,
        site_name=args.site_name,
        url=args.url,
        strategy=args.strategy,
        confidence=args.confidence,
        css_list=args.css_list,
        css_title=args.css_title,
        css_date=args.css_date,
        anchor_text=args.anchor_text,
        anchor_scope=args.anchor_scope,
        anchor_depth=args.anchor_depth,
        link_prefix=args.link_prefix,
        timeout=args.timeout,
        overwrite=args.overwrite,
        source=args.source
    )
    
    if "error" in result:
        print(f"[ERROR] {result['error']}")
        sys.exit(1)
    
    print(f"[INFO] 配置已保存: {result['path']}")
    print(f"[INFO] 网站ID: {result['siteId']}, 策略: {result['strategy']}, 版本: {result['version']}")

if __name__ == "__main__":
    main()
