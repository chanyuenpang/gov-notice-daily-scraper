# Daily News Crawler - 公告抓取系统

## 核心理念

不用预设规则爬虫，而是用 Agent + Playwright 主动观察、学习网页结构，逐步实现自动化抓取。

## 工作流程

```
定时/手动触发
    │
    ▼
从目标列表获取URL
    │
    ▼
分层抓取策略
├── 有CSS选择器 → 爬虫脚本
│       └── 失败 → 降级到 Subagent
└── 无CSS选择器 → Subagent + Playwright MCP
        └── 成功 → 学习CSS选择器
    │
    ▼
结果汇总 → 生成报告
    │
    ▼
发送到飞书群
```

## 目录结构

```
daily-news-crawler/
├── config/           # 配置文件
│   ├── urls.json     # 网站配置
│   └── crawl-state.json  # 抓取状态
├── scrapers/         # 爬虫脚本
├── scripts/          # 主脚本
├── output/           # 输出文件
├── learnings/        # 学习日志
├── docs/             # 文档
└── templates/        # 报告模板
```

## 目标列表 (v2.0)

| 网站 | URL | 状态 |
|------|-----|------|
| 厦门市人力资源和社会保障局 | http://hrss.xm.gov.cn/xygk/tzgg/ | 有选择器 |
| 中华人民共和国科学技术部 | http://www.most.gov.cn/ | 有选择器 |
| 福建省科技厅 | http://kjt.fujian.gov.cn/ | 有选择器 |
| 厦门火炬高技术产业开发区 | http://xmtorch.xm.gov.cn/ | 待学习 |
| 厦门市软件行业协会 | http://www.xmsia.cn/ | 待学习 |

## 迭代日志

### v2.0.0 (2026-03-14)
- 项目整合：合并 adaptive-scraper 到 daily-news-crawler
- 添加分层抓取策略
- 添加学习机制

### v0.1.0 (2026-03-14)
- 初始版本
- 创建 skill 骨架
