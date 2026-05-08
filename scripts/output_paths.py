"""output 新目录协议路径工具。"""
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"

def notices_dir(month: str) -> Path:
    """output/notices/{YYYY-MM}/"""
    return OUTPUT_DIR / "notices" / month

def reports_dir(date_str: str) -> Path:
    """output/reports/{YYYY-MM-DD}/"""
    return OUTPUT_DIR / "reports" / date_str

def artifacts_dir(date_str: str) -> Path:
    """output/crawl-artifacts/{YYYY-MM-DD}/"""
    return OUTPUT_DIR / "crawl-artifacts" / date_str

def is_date_dir_name(name: str) -> bool:
    return len(name) == 10 and name[4] == '-' and name[7] == '-'

def is_month_dir_name(name: str) -> bool:
    return len(name) == 7 and name[4] == '-'

def ensure_dirs(date_str: str):
    """确保 date_str 对应的 reports 和 artifacts 目录存在。"""
    month = date_str[:7]
    notices_dir(month).mkdir(parents=True, exist_ok=True)
    reports_dir(date_str).mkdir(parents=True, exist_ok=True)
    artifacts_dir(date_str).mkdir(parents=True, exist_ok=True)
