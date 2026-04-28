#!/usr/bin/env python3
"""
Stage 2 任务准备脚本

读取 Stage 1 结果，生成 Stage 2 任务清单。供主 Agent 读取后分派 Subagent。

用法:
  python3 scripts/stage2_prepare.py --stage1 output/2026-03-15/stage1_results.json --urls config/urls.json
  python3 scripts/stage2_prepare.py --date 2026-03-15
"""

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_DIR = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_DIR / "output"
CONFIG_DIR = PROJECT_DIR / "config"
RULES_DIR = CONFIG_DIR / "rules"

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

def classify_failure(error: str) -> str:
    """
    分类失败原因
    
    返回:
    - no_rule: 无规则文件
    - strategy_failed: 有规则但策略失败
    - dns_error: DNS 解析失败
    - timeout: 超时
    - unknown: 未知错误
    """
    if not error:
        return "unknown"
    
    error_lower = error.lower()
    
    if "无规则文件" in error or "no rule" in error_lower:
        return "no_rule"
    
    if "dns" in error_lower or "err_name_not_resolved" in error_lower or "getaddrinfo" in error_lower:
        return "dns_error"
    
    if "timeout" in error_lower or "timed out" in error_lower:
        return "timeout"
    
    if "未找到" in error or "未提取" in error or "选择器" in error:
        return "strategy_failed"
    
    return "unknown"

def check_rule_exists(site_id: str) -> bool:
    """检查规则文件是否存在"""
    rule_path = RULES_DIR / f"{site_id}.json"
    return rule_path.exists()

def prepare_tasks(
    stage1_data: dict,
    urls_config: dict
) -> dict:
    """
    准备 Stage 2 任务清单
    
    返回格式:
    {
      "date": "2026-03-15",
      "tasks": [...],
      "skipped": [...],
      "summary": {...}
    }
    """
    date_str = stage1_data.get("date", datetime.now().strftime("%Y-%m-%d"))
    
    # 构建 siteId -> source 映射
    sources_by_id = {}
    for source in urls_config.get("sources", []):
        site_id = source.get("id")
        if site_id:
            # 注意：可能有重复 siteId，用列表存储
            if site_id not in sources_by_id:
                sources_by_id[site_id] = []
            sources_by_id[site_id].append(source)
    
    tasks = []
    skipped = []
    seen_urls = set()  # 用于检测重复 (siteId, url)
    
    for result in stage1_data.get("results", []):
        site_id = result.get("siteId")
        url = result.get("url", "")
        status = result.get("status")
        error = result.get("error", "")
        
        # 只处理失败的站点
        if status == "success":
            continue
        
        # 检查重复 (siteId, url)
        site_url_key = (site_id, url)
        if site_url_key in seen_urls:
            continue
        seen_urls.add(site_url_key)
        
        # 分类失败原因
        fail_class = classify_failure(error)
        
        # DNS 错误直接跳过
        if fail_class == "dns_error":
            skipped.append({
                "siteId": site_id,
                "url": url,
                "reason": "dns_error",
                "originalError": error[:100] if error else ""
            })
            continue
        
        # 获取完整站点配置
        sources = sources_by_id.get(site_id, [])
        source = sources[0] if sources else {}
        
        # 如果有多个相同 siteId 的源，尝试匹配 URL
        if len(sources) > 1:
            for s in sources:
                if s.get("url") == url:
                    source = s
                    break
        
        task = {
            "siteId": site_id,
            "siteName": result.get("siteName") or source.get("name") or site_id,
            "url": url,
            "baseUrl": source.get("baseUrl", url),
            "failReason": fail_class,
            "hasExistingRule": check_rule_exists(site_id),
            "originalError": error[:200] if error else ""
        }
        
        tasks.append(task)
    
    # 统计
    summary = {
        "total": len(stage1_data.get("results", [])),
        "failed": len(tasks) + len(skipped),
        "toProcess": len(tasks),
        "skipped": len(skipped),
        "noRuleCount": len([t for t in tasks if t["failReason"] == "no_rule"]),
        "strategyFailedCount": len([t for t in tasks if t["failReason"] == "strategy_failed"]),
        "timeoutCount": len([t for t in tasks if t["failReason"] == "timeout"])
    }
    
    return {
        "date": date_str,
        "generatedAt": datetime.now().isoformat(),
        "tasks": tasks,
        "skipped": skipped,
        "summary": summary
    }

def main():
    parser = argparse.ArgumentParser(description="Stage 2 任务准备脚本")
    parser.add_argument("--stage1", type=str, default="", help="Stage 1 结果文件路径")
    parser.add_argument("--urls", type=str, default="", help="URLs 配置文件路径")
    parser.add_argument("--date", type=str, default="", help="日期 (YYYY-MM-DD)，自动推导路径")
    parser.add_argument("--output", type=str, default="", help="输出文件路径")
    
    args = parser.parse_args()
    
    # 确定文件路径
    if args.date:
        date_str = args.date
        stage1_path = OUTPUT_DIR / date_str / "stage1_results.json"
        urls_path = CONFIG_DIR / "urls.json"
        output_path = OUTPUT_DIR / date_str / "stage2_tasks.json"
    elif args.stage1:
        stage1_path = Path(args.stage1)
        urls_path = Path(args.urls) if args.urls else CONFIG_DIR / "urls.json"
        output_path = Path(args.output) if args.output else stage1_path.parent / "stage2_tasks.json"
    else:
        print("[ERROR] 需要指定 --date 或 --stage1")
        return
    
    # 加载数据
    stage1_data = load_json(stage1_path)
    if not stage1_data:
        print(f"[ERROR] 无法加载 Stage 1 结果: {stage1_path}")
        return
    
    urls_config = load_json(urls_path)
    if not urls_config:
        print(f"[ERROR] 无法加载 URLs 配置: {urls_path}")
        return
    
    # 准备任务
    tasks_data = prepare_tasks(stage1_data, urls_config)
    
    # 保存
    save_json(output_path, tasks_data)
    
    # 输出摘要
    summary = tasks_data["summary"]
    print(f"[INFO] Stage 2 任务清单已生成: {output_path}")
    print(f"[INFO] 待处理: {summary['toProcess']} 个站点")
    print(f"[INFO]   - 无规则文件: {summary['noRuleCount']}")
    print(f"[INFO]   - 策略失败: {summary['strategyFailedCount']}")
    print(f"[INFO]   - 超时: {summary['timeoutCount']}")
    print(f"[INFO] 已跳过: {summary['skipped']} 个站点 (DNS 错误)")
    
    # 警告重复 siteId
    site_ids = [t["siteId"] for t in tasks_data["tasks"]]
    from collections import Counter
    duplicates = [sid for sid, count in Counter(site_ids).items() if count > 1]
    if duplicates:
        print(f"[WARN] 检测到重复 siteId: {duplicates}，将用 (siteId, url) 联合标识")

if __name__ == "__main__":
    main()
