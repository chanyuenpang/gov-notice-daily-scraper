#!/usr/bin/env python3
"""Stage 2 站点抓取脚本"""
import json
import asyncio
import sys
from playwright.async_api import async_playwright

async def crawl_site(site_id, name, url, base_url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto(url, timeout=45000)
            await page.wait_for_load_state('networkidle', timeout=20000)
            
            articles = []
            for sel in ['ul li a', 'table a', '.list a', '.news a']:
                els = await page.query_selector_all(sel)
                if len(els) > 0:
                    for el in els[:30]:
                        try:
                            title = (await el.inner_text()).strip()
                            href = await el.get_attribute('href')
                            if title and len(title) > 2:
                                full_url = href if href.startswith('http') else base_url + href
                                articles.append({'title': title, 'url': full_url, 'site_id': site_id, 'site_name': name})
                        except: pass
                    if articles:
                        break
            return {'site_id': site_id, 'name': name, 'url': url, 'success': True, 'articles': articles[:30]}
        except Exception as e:
            return {'site_id': site_id, 'name': name, 'url': url, 'success': False, 'error': str(e)[:100]}
        finally:
            await browser.close()

async def main():
    sites = [
        ('sti_xm_gov_cn', '厦门市科学技术局', 'http://sti.xm.gov.cn/', 'http://sti.xm.gov.cn'),
        ('siming_gov_cn', '厦门市思明区科技和信息化局', 'http://www.siming.gov.cn/gbmzl/kjhxxhj/', 'http://www.siming.gov.cn'),
        ('gxt_fujian_gov_cn', '福建省供销合作社', 'http://gxt.fujian.gov.cn/', 'http://gxt.fujian.gov.cn'),
        ('xmtorch_xm_gov_cn', '厦门市火炬开发区', 'http://xmtorch.xm.gov.cn/xxgk/zfxxgkml/glfw/', 'http://xmtorch.xm.gov.cn'),
        ('kgxj_haikou_gov_cn', '海口市科工局', 'http://kgxj.haikou.gov.cn/zfxxgk/gsgg/', 'http://kgxj.haikou.gov.cn'),
    ]
    
    results = []
    for sid, name, url, base in sites:
        print(f'抓取: {name}')
        r = await crawl_site(sid, name, url, base)
        results.append(r)
        print(f'  -> {len(r.get("articles", []))} 条')
        await asyncio.sleep(2)
    
    output_path = 'output/2026-04-15/stage2_results.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f'已保存: {output_path}')

if __name__ == '__main__':
    asyncio.run(main())