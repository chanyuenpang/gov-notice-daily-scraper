const { chromium } = require('playwright');

const urls = [
  { url: 'https://www.xmsme.cn/', name: '厦门市中小企业服务中心' },
  { url: 'https://js.xm.gov.cn/', name: '厦门市建设局' },
  { url: 'http://www.xmgh.org/', name: '厦门工会网' },
  { url: 'https://fgw.fujian.gov.cn/xxgk/gsgg/', name: '福建省发改委' },
  { url: 'http://edu.xm.gov.cn/jyxw/tzgg/', name: '厦门教育局' }
];

const results = [];

async function extractAnnouncements(page, sourceName) {
  const announcements = [];
  
  try {
    const newsItems = await page.evaluate(() => {
      const items = [];
      const seenTexts = new Set();
      
      // Try to find news list containers first
      const listSelectors = [
        'ul.news-list li',
        'ul.article-list li', 
        'div.news-list li',
        'div.article-list li',
        'div.list ul li',
        'ul li a',
        '.news ul li',
        '.article ul li',
        'table.announcement td',
        'div.news-item',
        'div.article-item',
        'div.item',
        '.tzgg table tr',
        '.gg table tr',
        '.news table tr'
      ];
      
      for (const sel of listSelectors) {
        const elements = document.querySelectorAll(sel);
        if (elements.length > 0 && elements.length < 200) {
          elements.forEach(el => {
            const link = el.querySelector('a') || el;
            const text = link?.textContent?.trim();
            const href = link?.href;
            
            if (text && text.length > 4 && text.length < 150 && href && 
                !href.includes('javascript') && !seenTexts.has(text.substring(0,30))) {
              seenTexts.add(text.substring(0,30));
              items.push({ text, href });
            }
          });
          if (items.length >= 5) break;
        }
      }
      
      // Fallback: find links with meaningful href patterns
      if (items.length < 3) {
        document.querySelectorAll('a').forEach(a => {
          const text = a.textContent?.trim();
          const href = a.href;
          const hrefLower = href?.toLowerCase() || '';
          
          // Filter for likely announcement/news links
          if (text && text.length > 5 && text.length < 150 && href && 
              !href.includes('javascript') && !hrefLower.includes('void') &&
              (hrefLower.includes('info') || hrefLower.includes('news') || 
               hrefLower.includes('article') || hrefLower.includes('notice') ||
               hrefLower.includes('tzgg') || hrefLower.includes('gg') ||
               hrefLower.endsWith('.htm') || hrefLower.endsWith('.html')) &&
              !seenTexts.has(text.substring(0,30))) {
            seenTexts.add(text.substring(0,30));
            items.push({ text, href });
          }
        });
      }
      
      return items;
    });
    
    // Deduplicate
    const seen = new Set();
    newsItems.forEach(item => {
      const key = item.text.substring(0, 30);
      if (!seen.has(key)) {
        seen.add(key);
        announcements.push({
          title: item.text.replace(/\s+/g, ' ').trim(),
          url: item.href,
          source: sourceName
        });
      }
    });
    
  } catch (e) {
    console.error(`Error extracting from ${sourceName}:`, e.message);
  }
  
  return announcements;
}

async function crawl() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
  });
  
  for (const site of urls) {
    console.log(`\n=== Crawling: ${site.name} ===`);
    console.log(`URL: ${site.url}`);
    
    try {
      const page = await context.newPage();
      page.setDefaultTimeout(30000);
      
      const response = await page.goto(site.url, { 
        waitUntil: 'networkidle',
        timeout: 25000 
      });
      
      if (response && response.ok()) {
        // Additional wait for dynamic content
        await page.waitForTimeout(3000);
        
        const announcements = await extractAnnouncements(page, site.name);
        
        console.log(`Found ${announcements.length} items`);
        
        results.push({
          source: site.name,
          url: site.url,
          status: 'success',
          announcements: announcements.slice(0, 20)
        });
      } else {
        console.log(`Failed to load: ${response?.status()}`);
        results.push({
          source: site.name,
          url: site.url,
          status: 'failed',
          error: `HTTP ${response?.status()}`,
          announcements: []
        });
      }
      
      await page.close();
      
    } catch (e) {
      console.error(`Error: ${e.message}`);
      results.push({
        source: site.name,
        url: site.url,
        status: 'error',
        error: e.message,
        announcements: []
      });
    }
  }
  
  await browser.close();
  
  const output = {
    crawlDate: new Date().toISOString(),
    totalSources: urls.length,
    results: results
  };
  
  console.log('\n=== FINAL OUTPUT ===');
  console.log(JSON.stringify(output, null, 2));
  
  return output;
}

crawl().then(output => {
  const fs = require('fs');
  fs.writeFileSync(
    '/home/yankeeting/.openclaw/workspace/projects/daily-news-crawler/output/2026-03-15/stage2_announcements.json',
    JSON.stringify(output, null, 2)
  );
  console.log('\n✓ Results saved to stage2_announcements.json');
}).catch(e => {
  console.error('Crawl failed:', e);
  process.exit(1);
});
