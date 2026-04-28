#!/usr/bin/env python3
"""
政府网站公告抓取系统 - 主编排脚本

[DEPRECATED] 此文件已被新的 4 阶段流水线架构替代:
- Stage 1: scripts/crawl_batch.py
- Stage 2-3: 由 SKILL.md 编排
- Stage 4: crawler-optimizer Skill

保留此文件仅供参考。新系统使用:
  python3 scripts/crawl_batch.py --urls config/urls.json

支持分层抓取策略、自动学习、增量抓取
"""

import asyncio
import json
import re
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from urllib.parse import urljoin, urlparse
from dataclasses import dataclass, asdict
from enum import Enum
import traceback

# 尝试导入 playwright
try:
    from playwright.async_api import async_playwright, Page, Browser
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("[WARN] Playwright 未安装，爬虫功能将不可用")

# ==================== 配置 ====================

PROJECT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_DIR / "config"
OUTPUT_DIR = PROJECT_DIR / "output"
LEARNINGS_DIR = PROJECT_DIR / "learnings"

# 全局配置
DEFAULT_TIMEOUT = 120000  # 2分钟
PAGE_LOAD_TIMEOUT = 30000  # 30秒
ELEMENT_WAIT_TIMEOUT = 10000  # 10秒
DAYS_BACK = 7  # 默认抓取最近7天
CONCURRENT_LIMIT = 3  # 并发限制
MIN_CONFIDENCE = 0.7  # 最低置信度

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
]

REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

# ==================== 数据类 ====================

class CrawlStatus(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    FALLBACK = "fallback"

@dataclass
class Announcement:
    """公告数据"""
    site_id: str
    site_name: str
    title: str
    url: str
    date: str
    category: str = ""
    summary: str = ""
    crawled_at: str = ""

@dataclass
class CrawlResult:
    """抓取结果"""
    site_id: str
    site_name: str
    status: CrawlStatus
    announcements: List[Announcement]
    error_message: str = ""
    learned_selector: Optional[Dict] = None
    duration_ms: int = 0

@dataclass
class SelectorInfo:
    """选择器信息"""
    list: str = ""
    title: str = ""
    date: str = ""
    link: str = ""
    confidence: float = 0.0
    source: str = "manual"
    last_validated: str = ""

# ==================== 工具函数 ====================

def parse_date(date_text: str) -> str:
    """解析各种日期格式"""
    if not date_text:
        return ""
    
    date_text = str(date_text).strip()
    
    patterns = [
        (r"(\d{4})-(\d{1,2})-(\d{1,2})", "%Y-%m-%d"),
        (r"(\d{4})/(\d{1,2})/(\d{1,2})", "%Y/%m/%d"),
        (r"(\d{4})年(\d{1,2})月(\d{1,2})日", "%Y年%m月%d日"),
        (r"(\d{1,2})-(\d{1,2})", "%m-%d"),
    ]
    
    for pattern, fmt in patterns:
        match = re.search(pattern, date_text)
        if match:
            try:
                if len(match.groups()) == 2:
                    year = datetime.now().year
                    month, day = match.groups()
                    return f"{year}-{int(month):02d}-{int(day):02d}"
                else:
                    parts = match.group(0).replace("/", "-").replace("年", "-").replace("月", "-").replace("日", "")
                    # 标准化日期格式
                    parts_list = parts.split("-")
                    if len(parts_list) == 3:
                        return f"{parts_list[0]}-{int(parts_list[1]):02d}-{int(parts_list[2]):02d}"
                    return parts
            except:
                continue
    
    return ""

def is_date_in_range(date_str: str, last_date: Optional[str] = None, days_back: int = DAYS_BACK) -> bool:
    """检查日期是否在范围内"""
    try:
        item_date = datetime.strptime(date_str, "%Y-%m-%d")
        
        if last_date:
            cutoff = datetime.strptime(last_date, "%Y-%m-%d")
            return item_date > cutoff
        
        cutoff = datetime.now() - timedelta(days=days_back)
        return item_date >= cutoff
    except:
        return True  # 解析失败时默认包含

def load_json(file_path: Path) -> Dict:
    """加载 JSON 文件"""
    if not file_path.exists():
        return {}
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(file_path: Path, data: Dict):
    """保存 JSON 文件"""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def append_markdown(file_path: Path, content: str):
    """追加 Markdown 内容"""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(content + "\n")

# ==================== 爬虫类 ====================

class Scraper:
    """爬虫执行器"""
    
    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.browser: Optional[Browser] = None
        
    async def init_browser(self, playwright):
        """初始化浏览器"""
        self.browser = await playwright.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-blink-features=AutomationControlled',
            ]
        )
    
    async def close_browser(self):
        """关闭浏览器"""
        if self.browser:
            await self.browser.close()
    
    async def scrape_site(
        self, 
        site_config: Dict, 
        last_date: Optional[str] = None
    ) -> CrawlResult:
        """抓取单个网站"""
        start_time = datetime.now()
        site_id = site_config.get("id", "unknown")
        site_name = site_config.get("name", "Unknown")
        url = site_config.get("url", "")
        base_url = site_config.get("baseUrl", url)
        
        print(f"[INFO] 开始抓取: {site_name} ({url})")
        
        # 获取选择器
        selector = site_config.get("selector", {})
        list_selector = selector.get("list", ".news-list li, .list-item")
        title_selector = selector.get("title", ".title, a")
        date_selector = selector.get("date", ".date, .time")
        link_selector = selector.get("link", "a")
        
        announcements = []
        learned_selector = None
        status = CrawlStatus.SUCCESS
        error_message = ""
        
        page = None
        try:
            page = await self.browser.new_page()
            
            # 设置反爬措施
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            """)
            await page.set_extra_http_headers(REQUEST_HEADERS)
            
            # 访问页面
            await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)
            await page.wait_for_timeout(2000)  # 等待渲染
            
            # 尝试等待列表元素
            try:
                await page.wait_for_selector(list_selector, timeout=ELEMENT_WAIT_TIMEOUT)
            except:
                # 尝试备用选择器
                backup_selectors = [
                    ".news-item", ".list-news li", ".content-list li",
                    "ul li", "tr", ".item", ".list li", "div.list a",
                    ".xxgk-list li", ".tzgg-list li", ".info-list li",
                    "table tbody tr", ".article-list li"
                ]
                found = False
                for backup in backup_selectors:
                    try:
                        elements = await page.query_selector_all(backup)
                        if len(elements) >= 3:
                            list_selector = backup
                            print(f"[INFO] {site_name}: 使用备用选择器 {backup} (找到 {len(elements)} 个元素)")
                            found = True
                            break
                    except:
                        continue
                
                if not found:
                    # 最后尝试：自动学习页面结构
                    print(f"[INFO] {site_name}: 尝试自动学习页面结构...")
                    learned = await self._learn_page_structure(page, site_name)
                    if learned:
                        list_selector = learned.get("list", "")
                        title_selector = learned.get("title", "a")
                        date_selector = learned.get("date", "")
                        learned_selector = learned
                        print(f"[INFO] {site_name}: 学习到选择器 {list_selector}")
                    else:
                        raise Exception(f"未找到列表元素，选择器: {list_selector}")
            
            # 提取公告
            items = await page.query_selector_all(list_selector)
            print(f"[INFO] {site_name}: 找到 {len(items)} 个条目")
            
            for item in items[:30]:  # 最多30条
                try:
                    # 提取标题
                    title_elem = await item.query_selector(title_selector)
                    if not title_elem:
                        title_elem = item
                    
                    title = await title_elem.text_content()
                    title = title.strip() if title else ""
                    
                    if not title or len(title) < 3:
                        continue
                    
                    # 提取链接
                    link_elem = await item.query_selector(link_selector)
                    if link_elem:
                        href = await link_elem.get_attribute("href")
                        link = urljoin(base_url, href) if href else url
                    else:
                        link = url
                    
                    # 提取日期
                    date = ""
                    date_elem = await item.query_selector(date_selector)
                    if date_elem:
                        date_text = await date_elem.text_content()
                        date = parse_date(date_text)
                    
                    if not date:
                        date = datetime.now().strftime("%Y-%m-%d")
                    
                    # 增量过滤
                    if last_date and not is_date_in_range(date, last_date):
                        continue
                    
                    # 创建公告对象
                    announcement = Announcement(
                        site_id=site_id,
                        site_name=site_name,
                        title=title,
                        url=link,
                        date=date,
                        category=site_config.get("category", ""),
                        summary=title[:100] + "..." if len(title) > 100 else title,
                        crawled_at=datetime.now().isoformat()
                    )
                    announcements.append(announcement)
                    
                except Exception as e:
                    continue
            
            print(f"[INFO] {site_name}: 成功提取 {len(announcements)} 条公告")
            
        except asyncio.TimeoutError:
            status = CrawlStatus.TIMEOUT
            error_message = "抓取超时"
            print(f"[WARN] {site_name}: {error_message}")
        except Exception as e:
            status = CrawlStatus.FAILED
            error_message = str(e)
            print(f"[ERROR] {site_name}: {error_message}")
        finally:
            if page:
                await page.close()
        
        duration = int((datetime.now() - start_time).total_seconds() * 1000)
        
        return CrawlResult(
            site_id=site_id,
            site_name=site_name,
            status=status,
            announcements=announcements,
            error_message=error_message,
            learned_selector=learned_selector,
            duration_ms=duration
        )
    
    async def _learn_page_structure(self, page: Page, site_name: str) -> Optional[Dict]:
        """自动学习页面结构，返回选择器"""
        try:
            # 获取页面内容
            content = await page.content()
            
            # 查找包含链接的重复元素
            selectors_to_try = [
                # 政府网站常见选择器
                ("div.list ul li a", "div.list ul li"),
                (".xxgk-list li a", ".xxgk-list li"),
                (".tzgg-list li a", ".tzgg-list li"),
                (".info-list li a", ".info-list li"),
                ("ul.list li a", "ul.list li"),
                (".content ul li a", ".content ul li"),
                (".news ul li a", ".news ul li"),
                ("table.list tbody tr a", "table.list tbody tr"),
                (".item-list .item a", ".item-list .item"),
                # 通用选择器
                ("div[class*='list'] li a", "div[class*='list'] li"),
                ("div[class*='news'] li a", "div[class*='news'] li"),
                ("ul[class*='list'] li a", "ul[class*='list'] li"),
            ]
            
            for link_sel, list_sel in selectors_to_try:
                try:
                    links = await page.query_selector_all(link_sel)
                    if len(links) >= 5:
                        # 找到足够的链接
                        items = await page.query_selector_all(list_sel)
                        
                        # 检查是否包含日期
                        date_sel = ""
                        for ds in [".date", ".time", "span", ".pub-date", ".publish-time"]:
                            try:
                                date_elems = await page.query_selector_all(f"{list_sel} {ds}")
                                if len(date_elems) >= 3:
                                    date_sel = ds
                                    break
                            except:
                                continue
                        
                        selector = {
                            "list": list_sel,
                            "title": link_sel,
                            "date": date_sel,
                            "link": "a",
                            "confidence": min(len(links) / 10, 0.9),
                            "source": "learned",
                            "last_validated": datetime.now().strftime("%Y-%m-%d")
                        }
                        
                        print(f"[INFO] {site_name}: 自动学习成功，找到 {len(links)} 个链接")
                        return selector
                        
                except Exception as e:
                    continue
            
            return None
            
        except Exception as e:
            print(f"[WARN] {site_name}: 自动学习失败 - {e}")
            return None

# ==================== 学习器类 ====================

class Learner:
    """选择器学习器"""
    
    def __init__(self, min_confidence: float = MIN_CONFIDENCE):
        self.min_confidence = min_confidence
    
    async def learn_selectors(self, page: Page, site_config: Dict) -> Optional[Dict]:
        """学习页面选择器"""
        site_id = site_config.get("id", "unknown")
        
        try:
            # 分析页面结构
            content = await page.content()
            
            # 查找重复的列表模式
            list_patterns = await self._find_list_patterns(page)
            
            if not list_patterns:
                return None
            
            # 选择最佳模式
            best_pattern = list_patterns[0]
            
            # 验证选择器
            confidence = await self._validate_selector(page, best_pattern)
            
            if confidence < self.min_confidence:
                return None
            
            selector_info = {
                "list": best_pattern.get("list", ""),
                "title": best_pattern.get("title", ""),
                "date": best_pattern.get("date", ""),
                "link": best_pattern.get("link", "a"),
                "confidence": confidence,
                "source": "learned",
                "last_validated": datetime.now().strftime("%Y-%m-%d"),
                "discovered_at": datetime.now().isoformat()
            }
            
            print(f"[INFO] 学习到选择器: {site_id} (置信度: {confidence:.2f})")
            return selector_info
            
        except Exception as e:
            print(f"[WARN] 学习选择器失败: {e}")
            return None
    
    async def _find_list_patterns(self, page: Page) -> List[Dict]:
        """查找列表模式"""
        patterns = []
        
        # 常见列表容器选择器
        container_selectors = [
            "ul", "ol", ".list", ".news-list", ".content-list",
            "table tbody", ".item-list", ".news-list"
        ]
        
        for container in container_selectors:
            try:
                elements = await page.query_selector_all(container)
                if len(elements) >= 3:  # 至少3个元素
                    # 检查是否包含链接和日期
                    first_elem = elements[0]
                    
                    # 查找标题元素
                    title_elem = await first_elem.query_selector("a, .title, .news-title")
                    title_sel = await self._get_css_selector(title_elem) if title_elem else "a"
                    
                    # 查找日期元素
                    date_elem = await first_elem.query_selector(".date, .time, span")
                    date_sel = await self._get_css_selector(date_elem) if date_elem else ""
                    
                    patterns.append({
                        "list": container,
                        "title": title_sel,
                        "date": date_sel,
                        "link": "a",
                        "count": len(elements)
                    })
            except:
                continue
        
        # 按数量排序
        patterns.sort(key=lambda x: x.get("count", 0), reverse=True)
        return patterns
    
    async def _get_css_selector(self, element) -> str:
        """获取元素的 CSS 选择器"""
        try:
            # 简化实现：使用标签名和类名
            tag = await element.evaluate("el => el.tagName.toLowerCase()")
            classes = await element.evaluate("el => el.className")
            
            if classes:
                class_list = classes.split()[:2]  # 最多取2个类名
                return f"{tag}.{'.'.join(class_list)}"
            return tag
        except:
            return ""
    
    async def _validate_selector(self, page: Page, pattern: Dict) -> float:
        """验证选择器有效性"""
        try:
            items = await page.query_selector_all(pattern.get("list", ""))
            if len(items) < 3:
                return 0.0
            
            valid_count = 0
            for item in items[:10]:
                # 检查是否有标题
                title_elem = await item.query_selector(pattern.get("title", "a"))
                if title_elem:
                    valid_count += 1
            
            return valid_count / min(len(items), 10)
        except:
            return 0.0

# ==================== 报告生成器 ====================

class ReportGenerator:
    """报告生成器"""
    
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.date_str = datetime.now().strftime("%Y-%m-%d")
        self.date_dir = output_dir / self.date_str
        self.date_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_all_reports(
        self, 
        results: List[CrawlResult], 
        config: Dict,
        crawl_state: Dict
    ):
        """生成所有报告"""
        # 生成公告列表
        self.generate_announcement_report(results)
        
        # 生成页面结构分析
        self.generate_structure_report(results)
        
        # 生成失败报告
        failed_results = [r for r in results if r.status != CrawlStatus.SUCCESS]
        if failed_results:
            self.generate_failure_report(failed_results)
        
        print(f"[INFO] 报告已生成: {self.date_dir}")
    
    def generate_announcement_report(self, results: List[CrawlResult]):
        """生成公告列表报告"""
        report_path = self.date_dir / f"公告列表-{self.date_str}.md"
        
        # 收集所有公告
        all_announcements = []
        for result in results:
            all_announcements.extend(result.announcements)
        
        # 按日期排序
        all_announcements.sort(key=lambda x: x.date, reverse=True)
        
        # 按网站分组
        by_site = {}
        for ann in all_announcements:
            if ann.site_name not in by_site:
                by_site[ann.site_name] = []
            by_site[ann.site_name].append(ann)
        
        # 生成 Markdown
        content = f"""# 政府网站公告日报

**报告日期**: {self.date_str}
**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**监控网站数**: {len(results)}
**成功抓取**: {len([r for r in results if r.status == CrawlStatus.SUCCESS])}
**失败网站**: {len([r for r in results if r.status != CrawlStatus.SUCCESS])}

---

## 概览

| 统计项 | 数量 |
|--------|------|
| 监控网站总数 | {len(results)} |
| 成功抓取网站 | {len([r for r in results if r.status == CrawlStatus.SUCCESS])} |
| 失败网站 | {len([r for r in results if r.status != CrawlStatus.SUCCESS])} |
| 新增公告总数 | {len(all_announcements)} |

---

## 公告列表

"""
        
        for site_name, announcements in by_site.items():
            content += f"### {site_name}\n\n"
            content += f"- **公告数**: {len(announcements)}条\n\n"
            content += "| # | 标题 | 发布日期 | 链接 |\n"
            content += "|---|------|----------|------|\n"
            
            for i, ann in enumerate(announcements, 1):
                content += f"| {i} | {ann.title[:50]}{'...' if len(ann.title) > 50 else ''} | {ann.date} | [查看]({ann.url}) |\n"
            
            content += "\n"
        
        # 添加失败报告
        failed = [r for r in results if r.status != CrawlStatus.SUCCESS]
        if failed:
            content += """---

## 失败报告

| 网站名称 | 失败原因 |
|----------|----------|
"""
            for r in failed:
                content += f"| {r.site_name} | {r.error_message} |\n"
        
        content += f"""
---

**报告生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**下次执行时间**: {(datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')} 06:00
"""
        
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        print(f"[INFO] 公告列表已生成: {report_path}")
    
    def generate_structure_report(self, results: List[CrawlResult]):
        """生成页面结构分析报告"""
        report_path = self.date_dir / f"页面结构分析-{self.date_str}.md"
        
        learned = [r for r in results if r.learned_selector]
        
        content = f"""# 页面结构分析报告

**分析日期**: {self.date_str}
**分析网站数**: {len(results)}
**学习到新选择器**: {len(learned)}

---

## 抓取统计

| 网站 | 状态 | 公告数 | 耗时(ms) |
|------|------|--------|----------|
"""
        
        for r in results:
            status_icon = "✅" if r.status == CrawlStatus.SUCCESS else "❌"
            content += f"| {r.site_name} | {status_icon} {r.status.value} | {len(r.announcements)} | {r.duration_ms} |\n"
        
        if learned:
            content += "\n---\n\n## 学习到的选择器\n\n"
            for r in learned:
                content += f"""### {r.site_name}

| 元素类型 | 选择器 |
|----------|--------|
| 列表容器 | `{r.learned_selector.get('list', '')}` |
| 标题 | `{r.learned_selector.get('title', '')}` |
| 日期 | `{r.learned_selector.get('date', '')}` |
| 链接 | `{r.learned_selector.get('link', '')}` |

**置信度**: {r.learned_selector.get('confidence', 0):.2f}

"""
        
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        print(f"[INFO] 页面结构分析已生成: {report_path}")
    
    def generate_failure_report(self, failed_results: List[CrawlResult]):
        """生成失败报告"""
        report_path = self.date_dir / f"失败报告-{self.date_str}.md"
        
        content = f"""# 抓取失败报告

**报告日期**: {self.date_str}
**失败网站数**: {len(failed_results)}

---

## 失败详情

"""
        
        for i, r in enumerate(failed_results, 1):
            content += f"""### {i}. {r.site_name}

| 字段 | 值 |
|------|-----|
| 网站ID | {r.site_id} |
| 失败时间 | {datetime.now().strftime('%H:%M:%S')} |
| 错误类型 | {r.status.value} |
| 错误信息 | {r.error_message} |
| 耗时 | {r.duration_ms}ms |

**建议操作**:
- 检查网站是否可正常访问
- 检查选择器是否需要更新
- 考虑使用 Subagent 重新学习

---

"""
        
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        print(f"[INFO] 失败报告已生成: {report_path}")

# ==================== 主编排器 ====================

class Orchestrator:
    """主编排器"""
    
    def __init__(self):
        self.config = {}
        self.crawl_state = {}
        self.results: List[CrawlResult] = []
        self.scraper: Optional[Scraper] = None
        self.learner: Optional[Learner] = None
        self.report_generator: Optional[ReportGenerator] = None
        
    def load_config(self):
        """加载配置"""
        config_path = CONFIG_DIR / "urls.json"
        state_path = CONFIG_DIR / "crawl-state.json"
        
        self.config = load_json(config_path)
        self.crawl_state = load_json(state_path)
        
        print(f"[INFO] 加载配置: {len(self.config.get('sources', []))} 个网站")
    
    def save_state(self):
        """保存状态"""
        state_path = CONFIG_DIR / "crawl-state.json"
        
        # 更新状态
        sites_state = self.crawl_state.get("sites", {})
        
        for result in self.results:
            site_state = sites_state.get(result.site_id, {})
            
            if result.status == CrawlStatus.SUCCESS:
                site_state["lastSuccessDate"] = datetime.now().strftime("%Y-%m-%d")
                site_state["consecutiveFailures"] = 0
                site_state["totalSuccessCount"] = site_state.get("totalSuccessCount", 0) + 1
                
                # 更新最新公告日期
                if result.announcements:
                    dates = [a.date for a in result.announcements]
                    max_date = max(dates)
                    site_state["lastAnnouncementDate"] = max_date
            else:
                site_state["consecutiveFailures"] = site_state.get("consecutiveFailures", 0) + 1
                site_state["totalFailCount"] = site_state.get("totalFailCount", 0) + 1
            
            site_state["lastCrawlDate"] = datetime.now().strftime("%Y-%m-%d")
            site_state["lastCrawlTime"] = datetime.now().isoformat()
            site_state["status"] = result.status.value
            
            sites_state[result.site_id] = site_state
        
        self.crawl_state["sites"] = sites_state
        self.crawl_state["lastUpdated"] = datetime.now().isoformat()
        self.crawl_state["summary"] = {
            "totalSites": len(self.results),
            "successCount": len([r for r in self.results if r.status == CrawlStatus.SUCCESS]),
            "failCount": len([r for r in self.results if r.status != CrawlStatus.SUCCESS]),
            "totalAnnouncements": sum(len(r.announcements) for r in self.results),
        }
        
        save_json(state_path, self.crawl_state)
        print(f"[INFO] 状态已保存: {state_path}")
    
    def update_learned_selectors(self):
        """更新学习到的选择器到配置"""
        config_path = CONFIG_DIR / "urls.json"
        
        sources = self.config.get("sources", [])
        updated = False
        
        for result in self.results:
            if result.learned_selector and result.learned_selector.get("confidence", 0) >= MIN_CONFIDENCE:
                for source in sources:
                    if source.get("id") == result.site_id:
                        # 添加到已发现选择器列表
                        if "learning" not in source:
                            source["learning"] = {}
                        if "discoveredSelectors" not in source["learning"]:
                            source["learning"]["discoveredSelectors"] = []
                        
                        source["learning"]["discoveredSelectors"].append(result.learned_selector)
                        
                        # 更新当前最佳选择器
                        current_confidence = source.get("selector", {}).get("confidence", 0)
                        if result.learned_selector["confidence"] > current_confidence:
                            source["selector"].update(result.learned_selector)
                            print(f"[INFO] 更新选择器: {result.site_id}")
                        
                        updated = True
                        break
        
        if updated:
            self.config["sources"] = sources
            self.config["lastUpdated"] = datetime.now().strftime("%Y-%m-%d")
            save_json(config_path, self.config)
            print(f"[INFO] 配置已更新: {config_path}")
    
    def log_learning(self, result: CrawlResult):
        """记录学习日志"""
        if not result.learned_selector:
            return
        
        log_path = LEARNINGS_DIR / "LEARNINGS.md"
        
        content = f"""
## [{datetime.now().strftime('%Y%m%d-%H%M%S')}] {result.site_name}

**学习时间**: {datetime.now().isoformat()}
**置信度**: {result.learned_selector.get('confidence', 0):.2f}

### 选择器

| 元素 | 选择器 |
|------|--------|
| 列表 | `{result.learned_selector.get('list', '')}` |
| 标题 | `{result.learned_selector.get('title', '')}` |
| 日期 | `{result.learned_selector.get('date', '')}` |
| 链接 | `{result.learned_selector.get('link', '')}` |

---
"""
        
        append_markdown(log_path, content)
    
    async def run(self, test_sites: Optional[List[str]] = None):
        """运行抓取任务"""
        print("=" * 60)
        print(f"[INFO] 开始抓取任务 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        
        # 加载配置
        self.load_config()
        
        sources = self.config.get("sources", [])
        
        # 测试模式：只处理指定网站
        if test_sites:
            sources = [s for s in sources if s.get("id") in test_sites]
            print(f"[INFO] 测试模式: 只处理 {len(sources)} 个网站")
        
        if not sources:
            print("[ERROR] 没有找到要抓取的网站")
            return
        
        if not PLAYWRIGHT_AVAILABLE:
            print("[ERROR] Playwright 未安装，无法执行抓取")
            return
        
        # 初始化组件
        self.scraper = Scraper()
        self.learner = Learner()
        self.report_generator = ReportGenerator(OUTPUT_DIR)
        
        # 执行抓取
        async with async_playwright() as p:
            await self.scraper.init_browser(p)
            
            try:
                # 分批处理
                batch_size = CONCURRENT_LIMIT
                for i in range(0, len(sources), batch_size):
                    batch = sources[i:i + batch_size]
                    print(f"\n[INFO] 处理批次 {i//batch_size + 1}/{(len(sources)-1)//batch_size + 1}")
                    
                    # 获取上次抓取日期
                    for site in batch:
                        site_id = site.get("id")
                        last_date = None
                        if site_id in self.crawl_state.get("sites", {}):
                            last_date = self.crawl_state["sites"][site_id].get("lastAnnouncementDate")
                        
                        # 执行抓取
                        result = await self.scraper.scrape_site(site, last_date)
                        self.results.append(result)
                        
                        # 记录学习日志
                        if result.learned_selector:
                            self.log_learning(result)
            
            finally:
                await self.scraper.close_browser()
        
        # 生成报告
        self.report_generator.generate_all_reports(self.results, self.config, self.crawl_state)
        
        # 保存状态
        self.save_state()
        
        # 更新学习到的选择器
        self.update_learned_selectors()
        
        # 输出统计
        success_count = len([r for r in self.results if r.status == CrawlStatus.SUCCESS])
        fail_count = len([r for r in self.results if r.status != CrawlStatus.SUCCESS])
        total_announcements = sum(len(r.announcements) for r in self.results)
        
        print("\n" + "=" * 60)
        print(f"[INFO] 抓取完成 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"[INFO] 成功: {success_count} 个网站")
        print(f"[INFO] 失败: {fail_count} 个网站")
        print(f"[INFO] 公告总数: {total_announcements} 条")
        print("=" * 60)


# ==================== 主函数 ====================

async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="政府网站公告抓取系统")
    parser.add_argument("--test", nargs="*", help="测试指定网站ID，不指定则测试所有")
    parser.add_argument("--sites", nargs="+", help="指定要抓取的网站ID")
    args = parser.parse_args()
    
    orchestrator = Orchestrator()
    
    if args.test is not None:
        # 测试模式
        test_sites = args.test if args.test else None
        await orchestrator.run(test_sites=test_sites)
    elif args.sites:
        # 指定网站
        await orchestrator.run(test_sites=args.sites)
    else:
        # 正常运行
        await orchestrator.run()


if __name__ == "__main__":
    asyncio.run(main())
