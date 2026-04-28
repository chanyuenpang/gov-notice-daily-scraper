#!/usr/bin/env python3
"""
Stage 2 结果收集脚本

收集各 Subagent 的输出，合并为 stage2_auto.json。
与 merge_results.py 的 find_stage2_file() glob 兼容。

用法:
  python3 scripts/stage2_collect.py --date 2026-03-15
  python3 scripts/stage2_collect.py --dir output/2026-03-15
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

def save_json(path: Path, data: dict):
    """保存 JSON 文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def collect_results(output_dir: Path) -> dict:
    """
    收集 stage2_site_*.json 文件，合并为标准格式
    
    返回格式:
    {
      "date": "2026-03-15",
      "stage": 2,
      "results": [...],
      "summary": {...}
    }
    """
    # 扫描 stage2_site_*.json 文件
    site_files = list(output_dir.glob("stage2_site_*.json"))
    
    if not site_files:
        print(f"[INFO] 未找到 stage2_site_*.json 文件: {output_dir}")
        return {}
    
    results = []
    rules_generated = 0
    total_announcements = 0
    
    for site_file in site_files:
        try:
            data = load_json(site_file)
            if not data:
                continue
            
            # 验证必需字段
            if "siteId" not in data:
                print(f"[WARN] 跳过无效文件 (缺少 siteId): {site_file.name}")
                continue
            
            # 标准化结果格式
            result = {
                "siteId": data.get("siteId"),
                "siteName": data.get("siteName", data.get("siteId")),
                "url": data.get("url", ""),
                "status": data.get("status", "failed"),
                "strategyUsed": data.get("strategyUsed", "subagent_analyzed"),
                "announcements": data.get("announcements", []),
                "error": data.get("error"),
                "durationMs": data.get("durationMs", 0),
                "ruleGenerated": data.get("ruleGenerated", False),
                "discoveredSelector": data.get("discoveredSelector")
            }
            
            results.append(result)
            
            # 统计
            if result["ruleGenerated"]:
                rules_generated += 1
            total_announcements += len(result["announcements"])
            
            print(f"[INFO] 收集: {result['siteId']} - {result['status']} - {len(result['announcements'])} 条公告")
            
        except Exception as e:
            print(f"[ERROR] 读取文件失败: {site_file.name} - {e}")
            continue
    
    if not results:
        return {}
    
    # 按日期分组（取第一个文件的日期或今天）
    date_str = datetime.now().strftime("%Y-%m-%d")
    
    # 统计
    success_count = len([r for r in results if r["status"] == "success"])
    failed_count = len([r for r in results if r["status"] != "success"])
    
    return {
        "date": date_str,
        "generatedAt": datetime.now().isoformat(),
        "stage": 2,
        "results": results,
        "summary": {
            "total": len(results),
            "success": success_count,
            "failed": failed_count,
            "totalAnnouncements": total_announcements,
            "rulesGenerated": rules_generated
        }
    }

def main():
    parser = argparse.ArgumentParser(description="Stage 2 结果收集脚本")
    parser.add_argument("--date", type=str, default="", help="日期 (YYYY-MM-DD)")
    parser.add_argument("--dir", type=str, default="", help="输出目录路径")
    parser.add_argument("--output", type=str, default="", help="输出文件路径")
    
    args = parser.parse_args()
    
    # 确定目录
    if args.dir:
        output_dir = Path(args.dir)
    elif args.date:
        output_dir = OUTPUT_DIR / args.date
    else:
        # 默认今天
        date_str = datetime.now().strftime("%Y-%m-%d")
        output_dir = OUTPUT_DIR / date_str
    
    if not output_dir.exists():
        print(f"[ERROR] 目录不存在: {output_dir}")
        return
    
    # 收集结果
    collected = collect_results(output_dir)
    
    if not collected:
        print("[INFO] 没有可收集的 Stage 2 结果")
        return
    
    # 确定输出路径
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = output_dir / "stage2_auto.json"
    
    # 保存
    save_json(output_path, collected)
    
    # 输出摘要
    summary = collected["summary"]
    print(f"\n[INFO] Stage 2 结果已合并: {output_path}")
    print(f"[INFO] 处理站点: {summary['total']} 个")
    print(f"[INFO] 成功: {summary['success']}, 失败: {summary['failed']}")
    print(f"[INFO] 公告总数: {summary['totalAnnouncements']} 条")
    print(f"[INFO] 生成规则: {summary['rulesGenerated']} 个")

if __name__ == "__main__":
    main()
