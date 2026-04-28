# Browser-Agent 单站抓取任务模板

## 任务输入
browser-agent 接收以下 JSON 格式的任务描述：

{
  "siteId": "hrss_xm_gov_cn",
  "siteName": "厦门市人力资源和社会保障局",
  "targetUrl": "http://hrss.xm.gov.cn/xygk/tzgg/",
  "category": "政策通知",
  "outputFields": ["title", "url", "date", "summary"]
}

## 执行步骤
1. 使用 browseros__navigate_page 打开 targetUrl
2. 使用 browseros__get_page_content 获取页面内容（Markdown 格式）
3. 从页面内容中提取公告列表，每条公告包含：
   - title: 公告标题
   - url: 公告详情页链接（需补全为完整 URL）
   - date: 发布日期
   - summary: 公告摘要（可选）
4. 按 docs/json-schema.md 中定义的格式返回 JSON 数组

## 期望输出格式
[
  {
    "id": "{siteId}_{YYYYMMDD}_{序号}",
    "siteId": "hrss_xm_gov_cn",
    "siteName": "厦门市人力资源和社会保障局",
    "title": "关于xxx的通知",
    "url": "http://hrss.xm.gov.cn/xygk/tzgg/2026/04/xxx.html",
    "date": "2026-04-28",
    "category": "政策通知",
    "summary": "摘要内容...",
    "crawledAt": "2026-04-28T16:00:00+08:00",
    "source": "browser-agent"
  }
]
