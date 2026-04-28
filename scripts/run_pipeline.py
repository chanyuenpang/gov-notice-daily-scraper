#!/usr/bin/env python3
"""
公告抓取流水线脚本

驱动 Stage 1/3/4，Stage 2 由 SKILL 编排的 Subagent 处理:
1. Stage 1: 脚本批量抓取 (本脚本执行)
2. Stage 2: Subagent 分析失败站点 → 生成规则文件 (由 SKILL.md 编排，非本脚本)
3. Stage 3: 合并 + 报告 (本脚本执行)
4. Stage 4: 增量分析 + 发飞书 (本脚本执行)

用法:
  python3 scripts/run_pipeline.py --date 2026-03-15
  python3 scripts/run_pipeline.py --today

注意: 完整流水线请通过 SKILL 触发，而非直接运行本脚本。
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_DIR / "output"
CONFIG_DIR = PROJECT_DIR / "config"

def run_command(cmd: list, timeout: int = 300) -> tuple:
    """运行命令并返回结果"""
    print(f"[RUN] {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=PROJECT_DIR
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Timeout"

def stage1(date: str) -> dict:
    """Stage 1: 脚本批量抓取"""
    print("\n" + "="*50)
    print("Stage 1: 脚本批量抓取")
    print("="*50)
    
    output_path = OUTPUT_DIR / date / "stage1_results.json"
    
    returncode, stdout, stderr = run_command([
        "python3", "scripts/crawl_batch.py",
        "--urls", "config/urls.json",
        "--output", str(output_path)
    ], timeout=300)
    
    print(stdout)
    if stderr:
        print(f"[STDERR] {stderr}")
    
    # 读取结果
    if output_path.exists():
        with open(output_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("summary", {})
    return {}

def stage2_needed(stage1_summary: dict) -> bool:
    """判断是否需要 Stage 2"""
    return stage1_summary.get("failed", 0) > 0

def stage3(date: str) -> dict:
    """Stage 3: 合并 + 报告"""
    print("\n" + "="*50)
    print("Stage 3: 合并 + 报告")
    print("="*50)
    
    # 合并结果
    returncode, stdout, stderr = run_command([
        "python3", "scripts/merge_results.py",
        "--date", date
    ], timeout=60)
    print(stdout)
    
    # 生成日报
    combined_path = OUTPUT_DIR / date / "combined_results.json"
    returncode, stdout, stderr = run_command([
        "python3", "scripts/generate_daily_report.py",
        str(combined_path)
    ], timeout=60)
    print(stdout)
    
    # 读取合并结果
    if combined_path.exists():
        with open(combined_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("summary", {})
    return {}

def stage4(date: str) -> dict:
    """Stage 4: 增量分析 + 发飞书"""
    print("\n" + "="*50)
    print("Stage 4: 增量分析")
    print("="*50)
    
    # 增量分析
    returncode, stdout, stderr = run_command([
        "python3", "scripts/incremental_analysis.py",
        "--date", date
    ], timeout=60)
    print(stdout)
    
    # 转换为 docx
    md_path = OUTPUT_DIR / date / "增量日报.md"
    docx_path = OUTPUT_DIR / date / "增量日报.docx"
    
    if md_path.exists():
        returncode, stdout, stderr = run_command([
            "pandoc", str(md_path), "-o", str(docx_path)
        ], timeout=30)
        
        if returncode == 0:
            print(f"[INFO] 已生成: {docx_path}")
        else:
            print(f"[WARN] pandoc 转换失败: {stderr}")
    
    # 读取增量结果
    incremental_path = OUTPUT_DIR / date / "incremental_results.json"
    if incremental_path.exists():
        with open(incremental_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("summary", {})
    return {}

def main():
    parser = argparse.ArgumentParser(description="公告抓取流水线")
    parser.add_argument("--date", type=str, default="", help="日期 (YYYY-MM-DD)")
    parser.add_argument("--today", action="store_true", help="使用今天日期")
    
    args = parser.parse_args()
    
    # 确定日期
    if args.today or not args.date:
        date = datetime.now().strftime("%Y-%m-%d")
    else:
        date = args.date
    
    print(f"[INFO] 开始执行公告抓取流水线: {date}")
    
    # 创建输出目录
    output_dir = OUTPUT_DIR / date
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Stage 1
    stage1_summary = stage1(date)
    print(f"[Stage 1] 成功: {stage1_summary.get('success', 0)}, "
          f"失败: {stage1_summary.get('failed', 0)}")
    
    # Stage 2 (由 SKILL 编排的 Subagent 处理，非本脚本执行)
    if stage2_needed(stage1_summary):
        failed_count = stage1_summary.get('failed', 0)
        print(f"\n[Stage 2] 检测到 {failed_count} 个失败站点")
        print("[Stage 2] 此阶段由 SKILL 编排的 Executor Subagent 处理:")
        print("[Stage 2]   - Subagent 访问失败站点，分析页面结构")
        print("[Stage 2]   - 调用 save_rule.py 生成规则文件")
        print("[Stage 2]   - 提取公告保存到 stage2_site_*.json")
        print("[Stage 2] 如需手动处理，可运行:")
        print(f"[Stage 2]   python3 scripts/stage2_prepare.py --date {date}")
    else:
        print("\n[Stage 2] 所有站点成功，无需处理")
    
    # Stage 3
    stage3_summary = stage3(date)
    print(f"[Stage 3] 总网站: {stage3_summary.get('total', 0)}, "
          f"成功: {stage3_summary.get('success', 0)}, "
          f"公告: {stage3_summary.get('totalAnnouncements', 0)}")
    
    # Stage 4
    stage4_summary = stage4(date)
    print(f"[Stage 4] 新增公告: {stage4_summary.get('totalNewAnnouncements', 0)}")
    
    # 最终汇总
    print("\n" + "="*50)
    print("执行完成")
    print("="*50)
    print(f"日期: {date}")
    print(f"成功网站: {stage3_summary.get('success', 0)}")
    print(f"总公告: {stage3_summary.get('totalAnnouncements', 0)}")
    print(f"新增公告: {stage4_summary.get('totalNewAnnouncements', 0)}")
    print(f"增量日报: {OUTPUT_DIR / date / '增量日报.docx'}")

if __name__ == "__main__":
    main()
