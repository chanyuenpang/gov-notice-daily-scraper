#!/usr/bin/env python3
"""
飞书消息发送模块
"""

import json
import os
import sys
import time
import requests
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

# 配置
PROJECT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_DIR / "output"


class FeishuSender:
    """飞书消息发送器"""

    MAX_FILE_SIZE = 30 * 1024 * 1024  # 30MB
    TOKEN_REFRESH_INTERVAL = 6000  # 100分钟，飞书token有效期2小时，留20分钟buffer
    REQUEST_TIMEOUT = 30
    MAX_RETRIES = 2

    FILE_TYPE_MAP = {
        ".opus": "opus",
        ".mp4": "mp4",
        ".pdf": "pdf",
        ".doc": "doc",
        ".docx": "doc",
        ".xls": "xls",
        ".xlsx": "xls",
        ".ppt": "ppt",
        ".pptx": "ppt",
    }

    def __init__(self):
        self.app_id = os.environ.get("FEISHU_APP_ID", "")
        self.app_secret = os.environ.get("FEISHU_APP_SECRET", "")
        self.tenant_access_token = None
        self._token_acquired_at = None

    def _ensure_token(self) -> bool:
        """确保 token 可用，过期则自动刷新"""
        if self.tenant_access_token and self._token_acquired_at:
            elapsed = time.time() - self._token_acquired_at
            if elapsed < self.TOKEN_REFRESH_INTERVAL:
                return True
            print("[INFO] token 即将过期，刷新中...")

        return self.get_tenant_access_token() is not None

    def _request_with_retry(self, method, url, max_retries=None, **kwargs):
        """带重试的 HTTP 请求，仅对 5xx 和网络异常重试"""
        if max_retries is None:
            max_retries = self.MAX_RETRIES
        kwargs.setdefault("timeout", self.REQUEST_TIMEOUT)

        last_response = None
        for attempt in range(max_retries + 1):
            try:
                response = requests.request(method, url, **kwargs)
                last_response = response
                if response.status_code == 200:
                    return response
                if response.status_code >= 500:
                    print(f"[WARN] HTTP {response.status_code}, 重试 {attempt + 1}/{max_retries}")
                    time.sleep(1 * (attempt + 1))
                    continue
                return response  # 4xx 不重试
            except requests.exceptions.RequestException as e:
                if attempt < max_retries:
                    print(f"[WARN] 请求失败: {e}, 重试 {attempt + 1}/{max_retries}")
                    time.sleep(1 * (attempt + 1))
                    continue
                raise
        return last_response

    def get_tenant_access_token(self) -> Optional[str]:
        """获取 tenant_access_token"""
        if not self.app_id or not self.app_secret:
            print("[WARN] 飞书配置缺失，跳过发送")
            return None

        try:
            url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
            data = {
                "app_id": self.app_id,
                "app_secret": self.app_secret
            }

            response = self._request_with_retry("POST", url, json=data)
            if response.status_code != 200:
                print(f"[ERROR] 获取 token HTTP {response.status_code}: {response.text[:200]}")
                return None

            result = response.json()

            if result.get("code") == 0:
                self.tenant_access_token = result.get("tenant_access_token")
                self._token_acquired_at = time.time()
                return self.tenant_access_token
            else:
                print(f"[ERROR] 获取 token 失败: {result}")
                return None

        except Exception as e:
            print(f"[ERROR] 获取 token 异常: {e}")
            return None

    def send_message(
        self,
        receive_id: str,
        message: str,
        receive_id_type: str = "user_id"
    ) -> bool:
        """发送消息"""
        if not self._ensure_token():
            return False

        try:
            url = "https://open.feishu.cn/open-apis/im/v1/messages"
            params = {
                "receive_id_type": receive_id_type
            }
            data = {
                "receive_id": receive_id,
                "msg_type": "text",
                "content": json.dumps({"text": message})
            }
            headers = {
                "Authorization": f"Bearer {self.tenant_access_token}",
                "Content-Type": "application/json"
            }

            response = self._request_with_retry("POST", url, params=params, json=data, headers=headers)
            if response.status_code != 200:
                print(f"[ERROR] 发送消息 HTTP {response.status_code}: {response.text[:200]}")
                return False

            result = response.json()

            if result.get("code") == 0:
                print(f"[INFO] 消息发送成功: {receive_id}")
                return True
            else:
                print(f"[ERROR] 消息发送失败: {result}")
                return False

        except Exception as e:
            print(f"[ERROR] 发送消息异常: {e}")
            return False

    def send_file(
        self,
        receive_id: str,
        file_path: Path,
        receive_id_type: str = "user_id"
    ) -> bool:
        """发送文件"""
        if not self._ensure_token():
            return False

        if not file_path.exists():
            print(f"[ERROR] 文件不存在: {file_path}")
            return False

        file_size = file_path.stat().st_size
        if file_size > self.MAX_FILE_SIZE:
            print(f"[ERROR] 文件过大: {file_path.name} ({file_size / 1024 / 1024:.1f}MB), 飞书限制 30MB")
            return False

        try:
            # 检测文件类型
            file_type = self.FILE_TYPE_MAP.get(file_path.suffix.lower(), "stream")

            # 上传文件
            url = "https://open.feishu.cn/open-apis/im/v1/files"
            headers = {
                "Authorization": f"Bearer {self.tenant_access_token}"
            }

            with open(file_path, "rb") as f:
                files = {
                    "file": (file_path.name, f),
                    "file_type": (None, file_type),
                    "file_name": (None, file_path.name)
                }

                response = self._request_with_retry("POST", url, headers=headers, files=files)

            if response.status_code != 200:
                print(f"[ERROR] 上传文件 HTTP {response.status_code}: {response.text[:200]}")
                return False

            result = response.json()

            if result.get("code") != 0:
                print(f"[ERROR] 上传文件失败: {result}")
                return False

            file_key = result.get("data", {}).get("file_key")

            # 发送文件消息
            url = "https://open.feishu.cn/open-apis/im/v1/messages"
            params = {
                "receive_id_type": receive_id_type
            }
            data = {
                "receive_id": receive_id,
                "msg_type": "file",
                "content": json.dumps({"file_key": file_key})
            }
            headers = {
                "Authorization": f"Bearer {self.tenant_access_token}",
                "Content-Type": "application/json"
            }

            response = self._request_with_retry("POST", url, params=params, json=data, headers=headers)
            if response.status_code != 200:
                print(f"[ERROR] 发送文件消息 HTTP {response.status_code}: {response.text[:200]}")
                return False

            result = response.json()

            if result.get("code") == 0:
                print(f"[INFO] 文件发送成功: {file_path.name}")
                return True
            else:
                print(f"[ERROR] 文件发送失败: {result}")
                return False

        except Exception as e:
            print(f"[ERROR] 发送文件异常: {e}")
            return False

    def send_daily_report(
        self,
        receive_id: str,
        date_str: str,
        success_count: int,
        fail_count: int,
        total_announcements: int,
        report_files: List[Path],
        receive_id_type: str = "user_id"
    ) -> bool:
        """发送日报"""
        # 发送摘要消息
        summary = f"""📋 政府网站公告日报

📅 日期: {date_str}
📊 统计:
- 监控网站: {success_count + fail_count}个
- 成功抓取: {success_count}个
- 失败网站: {fail_count}个
- 新增公告: {total_announcements}条

📎 详细报告见附件
"""

        if not self.send_message(receive_id, summary, receive_id_type):
            return False

        # 发送文件
        file_failures = []
        for file_path in report_files:
            if file_path.exists():
                if not self.send_file(receive_id, file_path, receive_id_type):
                    file_failures.append(file_path.name)

        if file_failures:
            print(f"[WARN] 以下文件发送失败: {', '.join(file_failures)}")
            return False

        return True


def send_report_to_feishu(
    user_id: str,
    date_str: Optional[str] = None
) -> bool:
    """发送报告到飞书"""
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    date_dir = OUTPUT_DIR / date_str

    if not date_dir.exists():
        print(f"[ERROR] 报告目录不存在: {date_dir}")
        return False

    # 查找报告文件
    report_files = [
        date_dir / f"公告列表-{date_str}.md",
        date_dir / f"页面结构分析-{date_str}.md",
    ]

    # 读取统计信息
    state_path = PROJECT_DIR / "config" / "crawl-state.json"
    if state_path.exists():
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)

        summary = state.get("summary", {})
        success_count = summary.get("successCount", 0)
        fail_count = summary.get("failCount", 0)
        total_announcements = summary.get("totalAnnouncements", 0)
    else:
        success_count = 0
        fail_count = 0
        total_announcements = 0

    # 发送
    sender = FeishuSender()
    return sender.send_daily_report(
        receive_id=user_id,
        date_str=date_str,
        success_count=success_count,
        fail_count=fail_count,
        total_announcements=total_announcements,
        report_files=report_files
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="飞书消息发送")
    parser.add_argument("--user", required=True, help="接收者用户ID")
    parser.add_argument("--date", help="报告日期，默认今天")
    args = parser.parse_args()

    send_report_to_feishu(args.user, args.date)
