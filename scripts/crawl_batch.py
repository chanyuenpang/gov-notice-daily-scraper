#!/usr/bin/env python3
"""
Stage 1 批量抓取引擎

职责：
- 纯 Python + Playwright 的批量抓取脚本
- 无状态，不含降级逻辑
- 支持 5 种页面定位策略：css, xpath, anchor, semantic, description
- description 策略标记为 needs_agent，由 Stage 2 处理

用法：
  python3 crawl_batch.py --urls config/urls.json --output output/{date}/stage1_results.json
  python3 crawl_batch.py --urls config/urls.json --sites xm_hrss xm_sti
"""

import argparse
import asyncio
import json
import random
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urljoin
from urllib.request import Request, urlopen

try:
    from playwright.async_api import async_playwright, Page, Browser
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("[ERROR] Playwright 未安装，请运行: pip install playwright && playwright install")
    sys.exit(1)

# ==================== 配置 ====================

PROJECT_DIR = Path(__file__).parent.parent
CONFIG_DIR = PROJECT_DIR / "config"
RULES_DIR = CONFIG_DIR / "rules"
OUTPUT_DIR = PROJECT_DIR / "output"
REPORTS_DIR = OUTPUT_DIR / "reports"
ARTIFACTS_DIR = OUTPUT_DIR / "crawl-artifacts"

DEFAULT_TIMEOUT = 30000  # 30秒
PAGE_LOAD_TIMEOUT = 15000  # 15秒
ELEMENT_WAIT_TIMEOUT = 10000  # 10秒
SITE_HARD_TIMEOUT_SECONDS = 60  # 单站硬超时，避免整批卡死
PAGE_CLOSE_TIMEOUT_SECONDS = 5  # page.close() 兜底超时

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
}

# ==================== 工具函数 ====================

def parse_date(date_text: str) -> str:
    """解析各种日期格式，返回 YYYY-MM-DD 格式"""
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
                    parts_list = parts.split("-")
                    if len(parts_list) == 3:
                        return f"{parts_list[0]}-{int(parts_list[1]):02d}-{int(parts_list[2]):02d}"
                    return parts
            except:
                continue

    return ""


def parse_date_from_url(url: str) -> Tuple[str, str]:
    """
    从 URL 提取精确日期，返回 (date, hint)
    - date: YYYY-MM-DD 或空
    - hint: 命中的模式提示

    支持：
      - tYYYYMMDD
      - YYYYMMDD
      - YYYY-MM-DD
      - YYYY/MM/DD
    对仅 YYYYMM / YYYY-MM 不返回具体日期（避免伪造日）。
    """
    if not url:
        return "", ""

    text = str(url)

    patterns = [
        (r"(?<!\d)t(20\d{2})(\d{2})(\d{2})(?!\d)", "url:tYYYYMMDD"),
        (r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)", "url:YYYYMMDD"),
        (r"(?<!\d)(20\d{2})-(\d{1,2})-(\d{1,2})(?!\d)", "url:YYYY-MM-DD"),
        (r"(?<!\d)(20\d{2})/(\d{1,2})/(\d{1,2})(?!\d)", "url:YYYY/MM/DD"),
    ]

    for pattern, hint in patterns:
        m = re.search(pattern, text)
        if not m:
            continue
        try:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            dt = datetime(y, mo, d)
            return dt.strftime("%Y-%m-%d"), hint
        except Exception:
            continue

    return "", ""


def enrich_announcement_dates(announcements: List[dict], crawl_date: str) -> Tuple[List[dict], Dict[str, int]]:
    """
    日期优先级：页面日期 > URL 精确日期 > firstSeen(首次抓取日期)
    并补充 dateSource 字段用于排障。
    """
    stats = {"page": 0, "url": 0, "firstSeen": 0, "missing": 0}
    enriched: List[dict] = []

    for ann in announcements:
        if not isinstance(ann, dict):
            continue

        item = dict(ann)
        page_date = (item.get("date") or "").strip()
        item["firstSeenDate"] = item.get("firstSeenDate") or crawl_date

        if page_date:
            item["date"] = page_date
            item["dateSource"] = item.get("dateSource") or "page"
            stats["page"] += 1
            enriched.append(item)
            continue

        url_date, url_hint = parse_date_from_url((item.get("url") or "").strip())
        if url_date:
            item["date"] = url_date
            item["dateSource"] = url_hint or "url"
            stats["url"] += 1
            enriched.append(item)
            continue

        if crawl_date:
            item["date"] = crawl_date
            item["dateSource"] = "firstSeen"
            stats["firstSeen"] += 1
        else:
            item["date"] = ""
            item["dateSource"] = "missing"
            stats["missing"] += 1

        enriched.append(item)

    return enriched, stats

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


def build_output(results: List[dict], summary: dict) -> dict:
    """构建 stage1 输出，便于增量落盘复用"""
    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "generatedAt": datetime.now().isoformat(),
        "stage": 1,
        "results": results,
        "summary": summary,
    }


def persist_progress(output_path: Path, results: List[dict], summary: dict):
    """每站完成后增量落盘，避免长任务中断时完全无结果可见"""
    save_json(output_path, build_output(results, summary))

# ==================== 策略实现 ====================

async def css_strategy(page: Page, rule: dict, base_url: str) -> tuple[List[dict], str]:
    """
    CSS 选择器策略
    
    返回: (announcements, error_message)
    """
    css = rule.get("css", {})
    list_sel = css.get("list", "")
    title_sel = css.get("title", "a")
    date_sel = css.get("date", "")
    link_sel = css.get("link", "a")
    
    extraction = rule.get("extraction", {})
    link_prefix = extraction.get("linkPrefix", base_url)
    
    if not list_sel:
        return [], "CSS 选择器未定义 list 字段"
    
    try:
        # 等待列表元素
        await page.wait_for_selector(list_sel, timeout=ELEMENT_WAIT_TIMEOUT)
    except:
        return [], f"未找到列表元素: {list_sel}"
    
    items = await page.query_selector_all(list_sel)
    if len(items) < 3:
        return [], f"列表元素数量不足: {len(items)}"
    
    announcements = []
    for item in items[:30]:
        try:
            # 提取标题
            title_elem = await item.query_selector(title_sel) if title_sel else item
            if not title_elem:
                continue
            title = await title_elem.text_content()
            title = title.strip() if title else ""
            
            if not title or len(title) < 3:
                continue
            
            # 提取链接
            link_elem = await item.query_selector(link_sel) if link_sel else None
            if link_elem:
                href = await link_elem.get_attribute("href")
                link = urljoin(link_prefix, href) if href else ""
            else:
                link = ""
            
            # 提取日期
            date = ""
            if date_sel:
                date_elem = await item.query_selector(date_sel)
                if date_elem:
                    date_text = await date_elem.text_content()
                    date = parse_date(date_text)
            
            announcements.append({
                "title": title,
                "url": link,
                "date": date
            })
            
        except Exception as e:
            continue
    
    return announcements, ""

async def xpath_strategy(page: Page, rule: dict, base_url: str) -> tuple[List[dict], str]:
    """
    XPath 策略
    
    使用 page.evaluate 执行 XPath 查询
    """
    xpath = rule.get("xpath", {})
    list_xpath = xpath.get("list", "")
    
    if not list_xpath:
        return [], "XPath 未定义 list 字段"
    
    try:
        # 使用 JavaScript 执行 XPath
        items = await page.evaluate(f"""
            () => {{
                const result = document.evaluate(
                    '{list_xpath}',
                    document,
                    null,
                    XPathResult.ORDERED_NODE_SNAPSHOT_TYPE,
                    null
                );
                const items = [];
                for (let i = 0; i < Math.min(result.snapshotLength, 30); i++) {{
                    items.push(result.snapshotItem(i));
                }}
                return items.map(item => ({{
                    html: item.outerHTML,
                    text: item.textContent
                }}));
            }}
        """)
        
        if not items or len(items) < 3:
            return [], f"XPath 匹配元素数量不足: {len(items) if items else 0}"
        
        announcements = []
        for item in items:
            text = item.get("text", "").strip()
            if len(text) < 3:
                continue
            
            # 简单提取：从文本中解析
            date = parse_date(text)
            
            # 从 HTML 中提取链接
            html = item.get("html", "")
            href_match = re.search(r'href=["\']([^"\']+)["\']', html)
            link = urljoin(base_url, href_match.group(1)) if href_match else ""
            
            # 标题通常是文本的第一行或链接文本
            title = text.split('\n')[0].strip()[:100]
            
            announcements.append({
                "title": title,
                "url": link,
                "date": date
            })
        
        return announcements, ""
        
    except Exception as e:
        return [], f"XPath 执行失败: {str(e)}"

async def anchor_strategy(page: Page, rule: dict, base_url: str) -> tuple[List[dict], str]:
    """
    文本锚点策略
    
    通过页面上的已知文本（如"通知公告"）定位列表区域
    """
    anchor = rule.get("anchor", {})
    anchor_text = anchor.get("text", "通知公告")
    scope = anchor.get("scope", "parent")  # parent | sibling
    depth = anchor.get("depth", 2)
    list_tag = anchor.get("listTag", "li")
    
    try:
        # 查找包含锚点文本的元素
        anchor_elem = page.get_by_text(anchor_text, exact=False).first
        await anchor_elem.wait_for(timeout=ELEMENT_WAIT_TIMEOUT)
        
        # 获取锚点元素的父级容器
        container = anchor_elem
        
        if scope == "parent":
            # 向上查找父元素
            for _ in range(depth):
                container = container.locator("xpath=..")
        elif scope == "sibling":
            # 查找相邻的列表元素
            container = container.locator(f"xpath=following-sibling::{list_tag}")
        
        # 在容器中查找列表项
        items = await container.locator(list_tag).all()
        
        if len(items) < 3:
            return [], f"锚点区域列表项数量不足: {len(items)}"
        
        announcements = []
        for item in items[:30]:
            try:
                text = await item.text_content()
                text = text.strip() if text else ""
                
                if len(text) < 3:
                    continue
                
                # 提取链接
                link_elem = item.locator("a").first
                href = await link_elem.get_attribute("href") if await link_elem.count() > 0 else None
                link = urljoin(base_url, href) if href else ""
                
                # 提取日期
                date = parse_date(text)
                
                # 标题
                title = text.split('\n')[0].strip()[:100]
                
                announcements.append({
                    "title": title,
                    "url": link,
                    "date": date
                })
            except:
                continue
        
        return announcements, ""
        
    except Exception as e:
        return [], f"锚点定位失败: {str(e)}"

async def api_strategy(rule: dict, base_url: str) -> tuple[List[dict], str]:
    """
    API 策略

    通过规则中的 api 配置直接请求接口并映射公告字段
    """
    api = rule.get("api", {})
    endpoint = api.get("endpoint") or api.get("url", "")
    method = str(api.get("method", "POST")).upper()
    body = api.get("body", {})
    data_path = api.get("dataPath", "")
    fields = api.get("fields", {})
    link_template = api.get("linkTemplate", "")

    if not endpoint:
        return [], "API 策略未定义 endpoint"

    def get_nested_value(obj: Any, path: str) -> Any:
        if not path:
            return None
        current = obj
        for part in str(path).split("."):
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list):
                try:
                    idx = int(part)
                    if idx < 0 or idx >= len(current):
                        return None
                    current = current[idx]
                except Exception:
                    return None
            else:
                return None
            if current is None:
                return None
        return current

    def map_field(item: dict, key: str) -> str:
        mapping = fields.get(key, key)
        value = get_nested_value(item, str(mapping)) if isinstance(mapping, str) else None
        if value is None and key == "title":
            value = item.get("title") or item.get("name")
        if value is None and key == "date":
            value = item.get("date") or item.get("issuedTime")
        return "" if value is None else str(value)

    def extract_by_data_path(payload: Any, path: str) -> Any:
        if not path:
            return payload
        current = payload
        for part in str(path).split("."):
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list):
                try:
                    idx = int(part)
                    current = current[idx]
                except Exception:
                    return None
            else:
                return None
            if current is None:
                return None
        return current

    try:
        req_body = json.dumps(body, ensure_ascii=False).encode("utf-8") if method in ["POST", "PUT", "PATCH"] else None
        req = Request(
            endpoint,
            data=req_body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/plain, */*",
                "User-Agent": random.choice(USER_AGENTS),
            },
            method=method,
        )

        with urlopen(req, timeout=15) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            content = resp.read().decode(charset, errors="ignore")
            payload = json.loads(content)

        data = extract_by_data_path(payload, data_path)
        if data is None:
            return [], f"API 响应中未找到 dataPath: {data_path}"
        if not isinstance(data, list):
            return [], f"API dataPath 提取结果不是列表: {type(data).__name__}"

        announcements = []
        for item in data[:100]:
            if not isinstance(item, dict):
                continue

            title = map_field(item, "title").strip()
            raw_date = map_field(item, "date").strip()
            date = parse_date(raw_date)

            item_id_key = fields.get("id", "id")
            item_id = get_nested_value(item, str(item_id_key)) if isinstance(item_id_key, str) else item.get("id")
            item_id = "" if item_id is None else str(item_id)

            link = ""
            if link_template and item_id:
                link = link_template.replace("{id}", item_id)
            elif item.get("url"):
                link = str(item.get("url"))

            if not title:
                continue

            announcements.append({
                "title": title,
                "url": urljoin(base_url, link) if link else "",
                "date": date
            })

        if not announcements:
            return [], "API 策略未提取到有效公告"

        return announcements, ""

    except Exception as e:
        return [], f"API 请求或解析失败: {str(e)}"


async def semantic_strategy(page: Page, base_url: str) -> tuple[List[dict], str]:
    """
    语义识别策略
    
    启发式查找"看起来像公告列表"的区域
    """
    # 常见列表选择器
    selectors_to_try = [
        ("div.list ul li", "div.list ul li a"),
        ("ul.list li", "ul.list li a"),
        (".news-list li", ".news-list li a"),
        (".content-list li", ".content-list li a"),
        (".xxgk-list li", ".xxgk-list li a"),
        (".tzgg-list li", ".tzgg-list li a"),
        ("div[class*='list'] li", "div[class*='list'] li a"),
        ("div[class*='news'] li", "div[class*='news'] li a"),
        ("table tbody tr", "table tbody tr a"),
        ("ul li", "ul li a"),
    ]
    
    for list_sel, link_sel in selectors_to_try:
        try:
            items = await page.query_selector_all(list_sel)
            if len(items) >= 5:
                announcements = []
                for item in items[:30]:
                    try:
                        # 提取链接
                        link_elem = await item.query_selector("a")
                        if not link_elem:
                            continue
                        
                        href = await link_elem.get_attribute("href")
                        if not href:
                            continue
                        
                        title = await link_elem.text_content()
                        title = title.strip() if title else ""
                        
                        if len(title) < 3:
                            continue
                        
                        link = urljoin(base_url, href)
                        
                        # 提取日期
                        date = ""
                        for date_sel in [".date", ".time", "span"]:
                            date_elem = await item.query_selector(date_sel)
                            if date_elem:
                                date_text = await date_elem.text_content()
                                date = parse_date(date_text)
                                if date:
                                    break
                        
                        announcements.append({
                            "title": title,
                            "url": link,
                            "date": date
                        })
                    except:
                        continue
                
                if len(announcements) >= 3:
                    return announcements, ""
                    
        except:
            continue
    
    return [], "未找到符合条件的列表结构"

# ==================== 主抓取逻辑 ====================

async def crawl_site(
    page: Page,
    source: dict,
    rule: Optional[dict]
) -> dict:
    """
    抓取单个网站
    
    返回结果字典
    """
    start_time = datetime.now()
    site_id = source.get("id", "unknown")
    site_name = source.get("displayName", source.get("name", "Unknown"))
    url = source.get("url", "")
    base_url = source.get("baseUrl", url)
    
    result = {
        "siteId": site_id,
        "siteName": site_name,
        "url": url,
        "status": "failed",
        "strategyUsed": None,
        "announcements": [],
        "error": None,
        "durationMs": 0
    }
    
    print(f"[INFO] 开始抓取: {site_name} ({url})")
    
    # 无规则文件 → 标记为 failed
    if rule is None:
        result["status"] = "failed"
        result["error"] = "无规则文件，需要 Stage 2 处理"
        result["durationMs"] = int((datetime.now() - start_time).total_seconds() * 1000)
        print(f"[INFO] {site_name}: 无规则文件，标记为失败")
        return result
    
    strategy = rule.get("strategy", "css")
    result["strategyUsed"] = strategy
    
    # description 策略 → 标记为 failed
    if strategy == "description":
        result["status"] = "failed"
        result["error"] = "description 策略需要 Stage 2 Agent 处理"
        result["durationMs"] = int((datetime.now() - start_time).total_seconds() * 1000)
        print(f"[INFO] {site_name}: description 策略，需要 Agent 处理")
        return result
    
    try:
        # 设置反爬措施
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)
        await page.set_extra_http_headers(REQUEST_HEADERS)
        
        # 访问页面
        await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)
        
        # 等待渲染
        wait_time = rule.get("antiCrawl", {}).get("waitAfterLoad", 2000)
        await page.wait_for_timeout(wait_time)
        
        # 执行策略
        announcements = []
        error = ""
        
        if strategy == "css":
            announcements, error = await css_strategy(page, rule, base_url)
        elif strategy == "xpath":
            announcements, error = await xpath_strategy(page, rule, base_url)
        elif strategy == "anchor":
            announcements, error = await anchor_strategy(page, rule, base_url)
        elif strategy == "semantic":
            announcements, error = await semantic_strategy(page, base_url)
        elif strategy == "api":
            announcements, error = await api_strategy(rule, base_url)
        else:
            error = f"未知策略: {strategy}"
        
        # 主策略失败 → 尝试 semantic 兜底
        if not announcements and strategy not in ["semantic", "description"]:
            print(f"[INFO] {site_name}: 主策略 {strategy} 失败，尝试 semantic 兜底")
            announcements, error = await semantic_strategy(page, base_url)
            if announcements:
                result["strategyUsed"] = f"{strategy} -> semantic"
        
        if announcements:
            crawl_date = datetime.now().strftime("%Y-%m-%d")
            announcements, date_stats = enrich_announcement_dates(announcements, crawl_date)

            result["status"] = "success"
            result["announcements"] = announcements
            result["dateStats"] = date_stats
            print(
                f"[INFO] {site_name}: 成功提取 {len(announcements)} 条公告 "
                f"(page={date_stats['page']}, url={date_stats['url']}, firstSeen={date_stats['firstSeen']}, missing={date_stats['missing']})"
            )
        else:
            result["status"] = "failed"
            result["error"] = error or "未提取到公告"
            print(f"[WARN] {site_name}: {result['error']}")
            
    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)
        print(f"[ERROR] {site_name}: {e}")
    
    result["durationMs"] = int((datetime.now() - start_time).total_seconds() * 1000)
    return result

async def safe_close_page(page: Page, site_name: str):
    """关闭页面时加兜底超时，避免 page.close() 卡住整个批次"""
    try:
        await asyncio.wait_for(page.close(), timeout=PAGE_CLOSE_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        print(f"[WARN] {site_name}: page.close() 超时，已跳过关闭等待")
    except Exception as e:
        print(f"[WARN] {site_name}: page.close() 失败: {e}")


async def main_async(
    urls_path: Path,
    output_path: Path,
    site_ids: Optional[List[str]] = None
):
    """主异步函数"""
    
    # 加载配置
    urls_config = load_json(urls_path)
    if not urls_config:
        print(f"[ERROR] 无法加载配置: {urls_path}")
        return
    
    sources = urls_config.get("sources", [])
    
    # 过滤指定的 site_ids
    if site_ids:
        sources = [s for s in sources if s.get("id") in site_ids]
    
    # 过滤 enabled=False 的
    sources = [s for s in sources if s.get("enabled", True)]
    
    print(f"[INFO] 准备抓取 {len(sources)} 个网站")
    
    results = []
    summary = {
        "total": len(sources),
        "success": 0,
        "failed": 0
    }

    persist_progress(output_path, results, summary)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-blink-features=AutomationControlled']
        )
        
        for source in sources:
            site_id = source.get("id")
            site_name = source.get("displayName", source.get("name", site_id or "Unknown"))

            # 加载规则文件
            rule_path = RULES_DIR / f"{site_id}.json"
            rule = load_json(rule_path) if rule_path.exists() else None

            # 创建新页面
            page = await browser.new_page()

            try:
                try:
                    result = await asyncio.wait_for(
                        crawl_site(page, source, rule),
                        timeout=SITE_HARD_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    result = {
                        "siteId": site_id,
                        "siteName": site_name,
                        "url": source.get("url", ""),
                        "status": "failed",
                        "strategyUsed": rule.get("strategy", "css") if rule else None,
                        "announcements": [],
                        "error": f"单站抓取超时({SITE_HARD_TIMEOUT_SECONDS}s)",
                        "durationMs": SITE_HARD_TIMEOUT_SECONDS * 1000,
                    }
                    print(f"[ERROR] {site_name}: 单站抓取超时，已跳过")

                results.append(result)

                # 更新统计
                status = result["status"]
                if status == "success":
                    summary["success"] += 1
                else:
                    # 所有非成功状态都算失败
                    summary["failed"] += 1

                persist_progress(output_path, results, summary)

            finally:
                await safe_close_page(page, site_name)

        await browser.close()

    # 保存最终结果
    save_json(output_path, build_output(results, summary))
    print(f"\n[INFO] 结果已保存: {output_path}")
    print(f"[INFO] 统计: 成功 {summary['success']}, 失败 {summary['failed']}")

def main():
    parser = argparse.ArgumentParser(description="Stage 1 批量抓取引擎")
    parser.add_argument("--urls", type=str, default=str(CONFIG_DIR / "urls.json"),
                        help="URLs 配置文件路径")
    parser.add_argument("--output", type=str, default="",
                        help="输出文件路径 (默认: output/{date}/stage1_results.json)")
    parser.add_argument("--sites", nargs="*", default=[],
                        help="指定要抓取的网站 ID (默认: 全部)")
    
    args = parser.parse_args()
    
    urls_path = Path(args.urls)
    
    # 默认输出路径 → crawl-artifacts/{date}/stage1_results.json
    if args.output:
        output_path = Path(args.output)
    else:
        today = datetime.now().strftime("%Y-%m-%d")
        output_path = ARTIFACTS_DIR / today / "stage1_results.json"
    
    site_ids = args.sites if args.sites else None
    
    asyncio.run(main_async(urls_path, output_path, site_ids))

if __name__ == "__main__":
    main()
