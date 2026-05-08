#!/usr/bin/env python3
"""迁移旧 output/{date}/ 到新目录协议：notices/ reports/ crawl-artifacts/。

默认 dry-run，加 --apply 才执行。
"""
import json, shutil, sys
from pathlib import Path
from output_paths import OUTPUT_DIR, notices_dir, reports_dir, artifacts_dir, is_date_dir_name

REPORT_FILES = {'日报.md', '日报.docx', '增量日报.md', '增量日报.docx', 'announcements.json', 'crawl-meta.json', 'crawl-plan.json', 'crawl-tasks.json'}
ARTIFACT_PATTERNS = ['stage1_', 'stage2_', 'browser_agent_', 'combined_results', 'incremental_results', 'crawl_announcements', 'stage2_', '.phase1_done']

def is_artifact(name: str) -> bool:
    return any(name.startswith(p) or name == p for p in ARTIFACT_PATTERNS) or (name.endswith('.json') and name not in REPORT_FILES and name != 'announcements.json')

def classify_files(date_dir: Path):
    report, artifact, notice = [], [], []
    for f in date_dir.iterdir():
        if f.is_dir(): 
            # stage1/stage2 subdirs are artifacts
            artifact.append(f)
            continue
        name = f.name
        if name in REPORT_FILES:
            report.append(f)
        elif is_artifact(name):
            artifact.append(f)
        else:
            # remaining files treated as report
            report.append(f)
    return report, artifact

def migrate_date_dir(date_dir: Path, apply: bool = False):
    date_str = date_dir.name
    month = date_str[:7]
    
    report_files, artifact_files = classify_files(date_dir)
    
    # Copy report files
    dst_report = reports_dir(date_str)
    for f in report_files:
        dst = dst_report / f.name
        print(f"  {'COPY' if apply else '[DRY]'} {f.relative_to(OUTPUT_DIR)} → {dst.relative_to(OUTPUT_DIR)}")
        if apply:
            dst_report.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst)
    
    # Copy artifact files
    dst_artifact = artifacts_dir(date_str)
    for f in artifact_files:
        if f.is_dir():
            dst = dst_artifact / f.name
            print(f"  {'COPY' if apply else '[DRY]'} {f.relative_to(OUTPUT_DIR)}/ → {dst.relative_to(OUTPUT_DIR)}/")
            if apply:
                dst_artifact.mkdir(parents=True, exist_ok=True)
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(f, dst)
        else:
            dst = dst_artifact / f.name
            print(f"  {'COPY' if apply else '[DRY]'} {f.relative_to(OUTPUT_DIR)} → {dst.relative_to(OUTPUT_DIR)}")
            if apply:
                dst_artifact.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dst)

def migrate_month_dir(month_dir: Path, apply: bool = False):
    """迁移 output/{YYYY-MM}/ 月目录中站点 json 到 output/notices/{YYYY-MM}/"""
    month = month_dir.name
    dst = notices_dir(month)
    for f in month_dir.glob("*.json"):
        if f.name.startswith('stage') or f.name.startswith('browser') or f.name.startswith('.'):
            continue
        target = dst / f.name
        print(f"  {'COPY' if apply else '[DRY]'} {f.relative_to(OUTPUT_DIR)} → {target.relative_to(OUTPUT_DIR)}")
        if apply:
            dst.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target)

def main():
    apply = '--apply' in sys.argv
    
    if not apply:
        print("🔍 DRY RUN (加 --apply 执行实际迁移)\n")
    else:
        print("🚀 APPLY MODE\n")
    
    date_dirs = sorted([d for d in OUTPUT_DIR.iterdir() if d.is_dir() and is_date_dir_name(d.name)])
    month_dirs = sorted([d for d in OUTPUT_DIR.iterdir() if d.is_dir() and not is_date_dir_name(d.name) and len(d.name) == 7 and d.name[4] == '-'])
    
    print(f"📅 日期目录: {len(date_dirs)} 个")
    for d in date_dirs:
        migrate_date_dir(d, apply)
    
    print(f"\n📋 月目录: {len(month_dirs)} 个")
    for d in month_dirs:
        migrate_month_dir(d, apply)
    
    print(f"\n{'✅ 迁移完成' if apply else 'ℹ️ Dry run 完成'}")

if __name__ == '__main__':
    main()
