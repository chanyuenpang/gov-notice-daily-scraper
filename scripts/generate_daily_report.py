#!/usr/bin/env python3
"""
日报生成脚本

输入: output/{date}/stage1_results.json 或 combined_results.json
输出: output/{date}/日报.md

用法:
  python3 scripts/generate_daily_report.py output/2026-03-15/stage1_results.json
  python3 scripts/generate_daily_report.py output/2026-03-15/combined_results.json
"""

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_DIR = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_DIR / "output"

def load_json(path: Path) -> dict:
    """加载 JSON 文件"""
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_source_config() -> Dict[str, str]:
    """加载站点配置，返回 siteId -> displayName 的映射"""
    config_path = PROJECT_DIR / "config" / "urls.json"
    config = load_json(config_path)
    
    mapping = {}
    for source in config.get("sources", []):
        site_id = source.get("id", "")
        display_name = source.get("displayName", "")
        if site_id and display_name:
            mapping[site_id] = display_name
    
    return mapping

def categorize_by_site(results: List[dict], source_mapping: Dict[str, str]) -> Dict[str, dict]:
    """按网站分组公告，返回 {siteName: {displayName, announcements}}"""
    categorized = {}
    for result in results:
        site_name = result.get("siteName", "Unknown")
        site_id = result.get("siteId", "")
        
        if site_name not in categorized:
            # 获取 displayName，如果没有则使用 siteName
            display_name = source_mapping.get(site_id, site_name)
            categorized[site_name] = {
                "displayName": display_name,
                "announcements": []
            }
        
        for ann in result.get("announcements", []):
            ann["siteId"] = site_id
            categorized[site_name]["announcements"].append(ann)
    
    return categorized

def generate_report(results_data: dict, output_path: Path):
    """生成日报 MD 文件"""
    date_str = results_data.get("date", datetime.now().strftime("%Y-%m-%d"))
    results = results_data.get("results", [])
    summary = results_data.get("summary", {})
    
    # 加载站点配置获取 displayName
    source_mapping = load_source_config()
    
    # 分类结果
    success_results = [r for r in results if r.get("status") == "success"]
    failed_results = [r for r in results if r.get("status") != "success"]
    
    # 统计
    total_sites = len(results)
    success_count = len(success_results)
    failed_count = len(failed_results)
    
    # 计算总公告数
    total_announcements = sum(len(r.get("announcements", [])) for r in success_results)
    
    # 生成 Markdown
    lines = []
    
    # 标题
    lines.append(f"# 公告抓取日报 - {date_str}")
    lines.append("")
    
    # 概览
    lines.append("## 概览")
    lines.append("")
    lines.append("| 指标 | 数值 |")
    lines.append("|------|------|")
    lines.append(f"| 监控网站 | {total_sites} |")
    lines.append(f"| 成功抓取 | {success_count} |")
    lines.append(f"| 失败 | {failed_count} |")
    lines.append(f"| 新增公告 | {total_announcements} |")
    lines.append("")
    
    # 新公告
    if success_results:
        lines.append("## 新公告")
        lines.append("")
        
        categorized = categorize_by_site(success_results, source_mapping)
        
        for site_name, site_data in categorized.items():
            display_name = site_data["displayName"]
            announcements = site_data["announcements"]
            
            # 显示格式: ### 厦门市人力资源和社会保障局
            lines.append(f"### {display_name}")
            lines.append("")
            lines.append("| 日期 | 公告名称 | 链接 |")
            lines.append("|------|---------|------|")
            
            for ann in announcements[:20]:  # 每个网站最多显示20条
                date = ann.get("date", "-")
                title = ann.get("title", "")[:50]  # 标题截断
                url = ann.get("url", "")
                
                if url:
                    link = f"[查看]({url})"
                else:
                    link = "-"
                
                lines.append(f"| {date} | {title} | {link} |")
            
            lines.append("")
    
    # 抓取失败
    if failed_results:
        lines.append("## 抓取失败")
        lines.append("")
        lines.append("| 网站 | 失败原因 |")
        lines.append("|------|---------|")
        
        for result in failed_results:
            site_name = result.get("siteName", "Unknown")
            site_id = result.get("siteId", "")
            display_name = source_mapping.get(site_id, site_name)
            error = result.get("error", "未知错误")[:50]
            lines.append(f"| {display_name} | {error} |")
        
        lines.append("")
    
    # 写入文件
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    
    print(f"[INFO] 日报已生成: {output_path}")
    print(f"[INFO] 统计: 成功 {success_count}, 失败 {failed_count}, 公告 {total_announcements}")

def main():
    parser = argparse.ArgumentParser(description="生成抓取日报")
    parser.add_argument("input", type=str, help="输入文件路径 (stage1_results.json 或 combined_results.json)")
    parser.add_argument("--output", type=str, default="", help="输出文件路径 (默认: 同目录下的日报.md)")
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    
    if not input_path.exists():
        print(f"[ERROR] 输入文件不存在: {input_path}")
        return
    
    # 默认输出路径
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.parent / "日报.md"
    
    results_data = load_json(input_path)
    
    if not results_data:
        print(f"[ERROR] 无法解析输入文件: {input_path}")
        return
    
    generate_report(results_data, output_path)

if __name__ == "__main__":
    main()
