# Daily News Crawler

政府网站公告抓取系统，采用 4 阶段流水线架构。

## 目录结构

```
daily-news-crawler/
├── config/                          # 配置目录
│   ├── urls.json                    # 网站列表 + 状态
│   └── rules/                       # 抓取规则（按网站ID命名）
│       ├── xm_hrss.json
│       ├── most_gov_cn.json
│       └── ...
│
├── scripts/                         # 脚本目录
│   ├── crawl_batch.py              # 阶段1: 批量抓取
│   ├── merge_results.py            # 阶段3: 结果合并
│   ├── generate_daily_report.py    # 阶段3: 日报生成
│   └── incremental_analysis.py     # 阶段4: 增量分析
│
├── output/                          # 输出目录（按日期组织）
│   └── {YYYY-MM-DD}/               # 每日输出
│       ├── stage1_results.json     # 阶段1 产出
│       ├── stage2_announcements.json # 阶段2A 产出
│       ├── combined_results.json   # 阶段3 合并结果
│       ├── 日报.md                  # 阶段3: 全量报告
│       ├── incremental_results.json # 阶段4: 增量结果
│       ├── 增量日报.md              # 阶段4: 增量报告
│       └── 增量日报.docx            # 阶段4: 发飞书 ⭐
│
└── README.md                        # 本文件
```

---

## 各阶段产出

### 阶段1: 脚本批量抓取

| 文件 | 路径 | 说明 |
|------|------|------|
| 抓取结果 | `output/{date}/stage1_results.json` | 所有网站的抓取结果 |

**stage1_results.json 结构**:
```json
{
  "date": "2026-03-15",
  "stage": 1,
  "results": [
    {
      "siteId": "xm_hrss",
      "siteName": "厦门市人社局",
      "url": "http://hrss.xm.gov.cn/xygk/tzgg/",
      "status": "success",
      "strategyUsed": "css",
      "announcements": [
        { "title": "...", "url": "...", "date": "2026-03-15" }
      ],
      "error": null
    },
    {
      "siteId": "most_gov_cn",
      "siteName": "科技部",
      "url": "http://www.most.gov.cn/",
      "status": "failed",
      "strategyUsed": "css",
      "announcements": [],
      "error": "CSS选择器失效"
    },
    {
      "siteId": "xm_sme",
      "siteName": "厦门中小企业",
      "url": "http://www.xmsme.cn/",
      "status": "failed",
      "announcements": [],
      "error": "无规则文件"
    }
  ],
  "summary": {
    "total": 25,
    "success": 10,
    "failed": 15,
    "totalAnnouncements": 276
  }
}
```

**状态说明**:
- `success`: 抓取成功，有公告
- `failed`: 抓取失败（包括无规则文件、选择器失效等），需要阶段2处理

---

### 阶段2: 失败处理（并行）

| 文件 | 路径 | 说明 |
|------|------|------|
| 抓取结果 | `output/{date}/stage2_announcements.json` | Subagent A 产出 |
| 配置文件 | `config/rules/{siteId}.json` | Subagent B 产出 |

**stage2_announcements.json 结构**:
```json
{
  "date": "2026-03-15",
  "stage": 2,
  "results": [
    {
      "siteId": "most_gov_cn",
      "siteName": "科技部",
      "status": "success",
      "announcements": [
        { "title": "...", "url": "...", "date": "2026-03-15" }
      ],
      "error": null
    }
  ]
}
```

**config/rules/{siteId}.json 结构**:
```json
{
  "siteId": "most_gov_cn",
  "version": 1,
  "updatedAt": "2026-03-15",
  "strategy": "css",
  "confidence": 0.8,
  "css": {
    "list": ".news-list li",
    "title": "a",
    "date": ".date"
  },
  "extraction": {
    "linkPrefix": "http://www.most.gov.cn"
  },
  "timeout": 30000,
  "metadata": {
    "source": "agent_analyzed"
  }
}
```

---

### 阶段3: 合并 + 报告

| 文件 | 路径 | 说明 |
|------|------|------|
| 合并结果 | `output/{date}/combined_results.json` | 最终抓取结果 |
| 全量日报 | `output/{date}/日报.md` | 所有抓取到的公告 |

**combined_results.json 结构**:
```json
{
  "date": "2026-03-15",
  "stage": "combined",
  "results": [...],
  "summary": {
    "total": 25,
    "success": 24,
    "failed": 1,
    "totalAnnouncements": 520,
    "agentRecovered": 14
  }
}
```

**日报.md 内容**:
- 概览统计
- 新公告列表（按网站分组）
- 失败网站列表
- Agent 降级分析结果

---

### 阶段4: 增量分析 → 发飞书

| 文件 | 路径 | 说明 |
|------|------|------|
| 增量结果 | `output/{date}/incremental_results.json` | 只包含新增公告 |
| 增量日报 | `output/{date}/增量日报.docx` | **发送到飞书群** ⭐ |

**处理流程**:
1. 增量分析 → `增量日报.md`
2. docx-converter-agent 转换 → `增量日报.docx`
3. 频道 agent 直接发送飞书群（无需额外配置）

**incremental_results.json 结构**:
```json
{
  "date": "2026-03-15",
  "stage": "incremental",
  "comparison": {
    "todayDate": "2026-03-15",
    "yesterdayDate": "2026-03-14",
    "yesterdayExists": true
  },
  "results": [
    {
      "siteId": "xm_hrss",
      "siteName": "厦门市人社局",
      "announcements": [
        { "title": "新公告标题", "url": "...", "date": "2026-03-15" }
      ],
      "newCount": 5
    }
  ],
  "summary": {
    "sitesWithNew": 8,
    "totalNewAnnouncements": 42
  }
}
```

**增量判断逻辑**:
- 使用公告 URL 作为唯一标识
- 如果 URL 不存在，使用 标题+日期 组合
- **只保留今天有、昨天没有的公告**（不是差异，是新增）

**特殊情况处理**:
- 如果昨天的结果不存在（冷启动），保留今天的所有公告
- 如果某网站今天没有新增，不出现在增量结果中

---

## 配置文件

### urls.json

网站列表和状态管理：

```json
{
  "sources": [
    {
      "id": "xm_hrss",
      "name": "厦门市人社局",
      "url": "http://hrss.xm.gov.cn/xygk/tzgg/",
      "enabled": true,
      "state": {
        "lastCrawlDate": "2026-03-15",
        "lastSuccessDate": "2026-03-15",
        "consecutiveFailures": 0
      }
    }
  ]
}
```

### rules/{siteId}.json

每个网站的抓取规则，支持 3 种策略：

| 策略 | 适用场景 | 配置字段 |
|------|---------|---------|
| `css` | 有明确 class/id | `css.list`, `css.title`, `css.date` |
| `anchor` | 有栏目锚点文本 | `anchor.text`, `anchor.scope` |
| `semantic` | 通用兜底 | 无需配置 |

---

## 脚本用法

```bash
# 阶段1: 批量抓取
python3 scripts/crawl_batch.py --urls config/urls.json --output output/2026-03-15/stage1_results.json

# 阶段3: 合并结果
python3 scripts/merge_results.py --date 2026-03-15

# 阶段3: 生成日报
python3 scripts/generate_daily_report.py output/2026-03-15/combined_results.json

# 阶段4: 增量分析
python3 scripts/incremental_analysis.py --date 2026-03-15
```

---

## 触发方式

1. **定时触发**: 每天 06:00 自动运行
2. **手动触发**: 在飞书群发送 "抓取公告"

---

## 故障排查

| 问题 | 检查文件 | 解决方案 |
|------|---------|---------|
| 某网站一直失败 | `output/{date}/stage1_results.json` | 查看 error 字段 |
| 配置文件不存在 | `config/rules/{siteId}.json` | 阶段2会自动生成 |
| 合并结果不正确 | `output/{date}/combined_results.json` | 检查 stage2_announcements.json |
| 增量分析无结果 | `output/{yesterday}/combined_results.json` | 检查昨天结果是否存在 |
| 日报格式问题 | `output/{date}/日报.md` | 检查 combined_results.json |

---

## 版本历史

### v5.0.0 (2026-03-15)
- 新增阶段4：增量分析
- 只保留新增公告，避免重复推送
- 新增 incremental_analysis.py 脚本

### v4.0.0 (2026-03-15)
- 重构为 3 阶段流水线
- 职责分离：抓取和配置生成分开
- 并行 Subagent 处理失败 URL
- 新增 merge_results.py 脚本

### v3.0.0 (2026-03-14)
- Per-URL 规则文件
- 5 种页面定位策略

### v2.0.0 (2026-03-14)
- 项目整合：合并 adaptive-scraper
- 添加分层抓取策略

### v1.0.0 (2025-03-13)
- 初始版本
