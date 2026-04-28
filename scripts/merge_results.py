#!/usr/bin/env python3
"""
结果合并脚本

输入:
  - output/{date}/stage1_results.json
  - output/{date}/stage2_announcements.json (可选)
输出:
  - output/{date}/combined_results.json

用法:
  python3 scripts/merge_results.py --date 2026-03-15
  python3 scripts/merge_results.py --stage1 output/2026-03-15/stage1_results.json --stage2 output/2026-03-15/stage2_announcements.json
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

def normalize_stage2_format(data: dict) -> dict:
    """
    将多种 stage2 格式统一转换为标准格式
    
    支持的格式:
    1. 标准格式: {results: [{siteId, announcements, ...}]}
    2. 简化格式: {siteId: [announcements], ...}
    """
    if not data:
        return {}
    
    # 已经是标准格式
    if "results" in data:
        return data
    
    # 简化格式: {siteId: [announcements]}
    # 自动转换
    results = []
    for site_id, announcements in data.items():
        if isinstance(announcements, list):
            results.append({
                "siteId": site_id,
                "siteName": site_id,  # 没有名称时用 ID
                "status": "success" if announcements else "failed",
                "announcements": announcements,
                "error": None
            })
    
    if results:
        print(f"[INFO] 检测到简化格式，自动转换为标准格式 ({len(results)} 个网站)")
        return {"results": results, "stage": 2}
    
    return data

def find_stage2_file(output_dir: Path) -> Optional[Path]:
    """
    查找 stage2 结果文件，选择公告数最多的
    
    扫描所有 stage2_*.json，选择包含公告最多的文件
    """
    candidates = list(output_dir.glob("stage2_*.json"))
    
    if not candidates:
        return None
    
    # 单个文件直接返回
    if len(candidates) == 1:
        return candidates[0]
    
    # 多个文件时，选择公告数最多的
    best_path = None
    best_count = -1
    
    for path in candidates:
        try:
            data = load_json(path)
            count = count_announcements(data)
            if count > best_count:
                best_count = count
                best_path = path
        except:
            continue
    
    if best_path:
        print(f"[INFO] 选择公告最多的文件: {best_path.name} ({best_count} 条)")
    return best_path

def count_announcements(data: dict) -> int:
    """计算公告数量，支持多种格式"""
    if not data:
        return 0
    
    # 标准格式: {results: [{announcements: [...]}]}
    if "results" in data:
        return sum(len(r.get("announcements", [])) for r in data.get("results", []))
    
    # 简化格式: {siteId: [announcements]}
    total = 0
    for key, value in data.items():
        if isinstance(value, list):
            total += len(value)
    return total

def save_json(path: Path, data: dict):
    """保存 JSON 文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def merge_results(stage1: dict, stage2: dict) -> dict:
    """
    合并 stage1 和 stage2 结果

    合并逻辑:
    - stage1 成功的结果直接保留
    - stage2 成功的结果补充进来
    - 两者都失败的标记为最终失败
    """
    date_str = stage1.get("date", datetime.now().strftime("%Y-%m-%d"))

    # 构建 siteId -> result 映射
    stage1_by_id = {r["siteId"]: r for r in stage1.get("results", [])}
    stage2_by_id = {r["siteId"]: r for r in stage2.get("results", [])}

    # 合并结果
    merged_results = []

    for site_id, stage1_result in stage1_by_id.items():
        stage1_status = stage1_result.get("status")

        if stage1_status == "success":
            # stage1 成功，直接保留
            merged_results.append(stage1_result)
        else:
            # stage1 失败或无规则，检查 stage2
            stage2_result = stage2_by_id.get(site_id)

            if stage2_result and stage2_result.get("status") == "success":
                # stage2 成功，使用 stage2 结果
                merged_results.append(stage2_result)
            elif stage2_result and stage2_result.get("announcements"):
                # stage2 有部分结果，合并
                merged_result = dict(stage1_result)
                merged_result["announcements"] = stage2_result.get("announcements", [])
                merged_result["status"] = "success"
                merged_result["agentRecovered"] = True
                merged_results.append(merged_result)
            else:
                # 两者都失败，保留 stage1 结果
                merged_result = dict(stage1_result)
                if stage2_result and stage2_result.get("error"):
                    merged_result["stage2Error"] = stage2_result.get("error")
                merged_results.append(merged_result)

    # 统计
    success_count = len([r for r in merged_results if r.get("status") == "success"])
    failed_count = len([r for r in merged_results if r.get("status") != "success"])
    total_announcements = sum(len(r.get("announcements", [])) for r in merged_results)

    return {
        "date": date_str,
        "generatedAt": datetime.now().isoformat(),
        "stage": "combined",
        "results": merged_results,
        "summary": {
            "total": len(merged_results),
            "success": success_count,
            "failed": failed_count,
            "totalAnnouncements": total_announcements,
            "agentRecovered": len([r for r in merged_results if r.get("agentRecovered")])
        }
    }

def main():
    parser = argparse.ArgumentParser(description="合并 stage1 和 stage2 结果")
    parser.add_argument("--date", type=str, default="", help="日期 (YYYY-MM-DD)")
    parser.add_argument("--stage1", type=str, default="", help="stage1 结果文件路径")
    parser.add_argument("--stage2", type=str, default="", help="stage2 结果文件路径")
    parser.add_argument("--output", type=str, default="", help="输出文件路径")

    args = parser.parse_args()

    # 确定文件路径
    if args.date:
        date_str = args.date
        stage1_path = OUTPUT_DIR / date_str / "stage1_results.json"
        output_path = OUTPUT_DIR / date_str / "combined_results.json"
        # 不预设 stage2_path，让 find_stage2_file 自动查找
        stage2_path = None
    else:
        if not args.stage1:
            print("[ERROR] 需要指定 --date 或 --stage1")
            return
        stage1_path = Path(args.stage1)
        stage2_path = Path(args.stage2) if args.stage2 else None
        output_path = Path(args.output) if args.output else stage1_path.parent / "combined_results.json"

    # 加载 stage1
    stage1_data = load_json(stage1_path)
    if not stage1_data:
        print(f"[ERROR] 无法加载 stage1 结果: {stage1_path}")
        return

    # 查找并加载 stage2 (可选)
    stage2_data = {}
    
    # 如果指定了 stage2 路径
    if stage2_path and stage2_path.exists():
        stage2_data = load_json(stage2_path)
        print(f"[INFO] 加载 stage2 结果: {stage2_path}")
    # 否则自动查找
    elif args.date:
        output_dir = OUTPUT_DIR / args.date
        found_path = find_stage2_file(output_dir)
        if found_path:
            stage2_data = load_json(found_path)
            print(f"[INFO] 自动发现 stage2 结果: {found_path}")
    
    # 格式标准化
    if stage2_data:
        stage2_data = normalize_stage2_format(stage2_data)

    # 合并
    if stage2_data:
        combined = merge_results(stage1_data, stage2_data)
        print(f"[INFO] 合并完成: stage1 {len(stage1_data.get('results', []))} + stage2 {len(stage2_data.get('results', []))} -> {len(combined['results'])}")
    else:
        # 没有 stage2，直接使用 stage1
        combined = dict(stage1_data)
        combined["stage"] = "combined"
        print(f"[INFO] 无 stage2 结果，直接使用 stage1")

    # 保存
    save_json(output_path, combined)
    print(f"[INFO] 合并结果已保存: {output_path}")
    print(f"[INFO] 统计: 成功 {combined['summary']['success']}, 失败 {combined['summary']['failed']}, 公告 {combined['summary']['totalAnnouncements']}")

if __name__ == "__main__":
    main()
