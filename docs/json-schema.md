# 统一公告 JSON 存储规范

> 版本: 1.1 | 日期: 2026-04-28

## 1. 统一公告 JSON schema

`output/{YYYY-MM-DD}/announcements.json` 中每条公告统一使用以下结构：

```json
{
  "id": "string - 唯一标识，格式: {siteId}_{YYYYMMDD}_{序号}",
  "siteId": "string - 站点标识，如 hrss_xm_gov_cn",
  "siteName": "string - 站点中文名，如 厦门市人力资源和社会保障局",
  "siteUrl": "string - 站点列表页 URL",
  "title": "string - 公告标题",
  "url": "string - 公告详情页 URL",
  "date": "string - 发布日期，YYYY-MM-DD 格式，缺失时允许空字符串",
  "category": "string - 站点分类，如 厦门市 / 福建省 / 国家",
  "summary": "string|null - 公告摘要，可为空",
  "content": "string|null - 公告正文，可为空",
  "crawledAt": "string - 抓取时间，ISO 8601",
  "source": "string - 数据来源阶段，如 stage1 / combined / incremental / stage2"
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| id | string | 是 | 全局唯一 ID，建议按 `siteId + 日期 + 序号` 生成 |
| siteId | string | 是 | 对应 `config/urls.json` 中 `sources[].id` |
| siteName | string | 是 | 站点中文名 |
| siteUrl | string | 是 | 公告所属站点列表页地址 |
| title | string | 是 | 公告标题 |
| url | string | 是 | 公告详情页地址 |
| date | string | 是 | 发布日期；如果源站未给出，保留空字符串 |
| category | string | 是 | 站点所属分类，来自配置文件 |
| summary | string/null | 否 | 页面摘要，当前多数数据暂无 |
| content | string/null | 否 | 正文全文，通常需 stage2 详情抓取补齐 |
| crawledAt | string | 是 | 本条记录归档时间 |
| source | string | 是 | 标记来自哪个产出阶段 |

## 2. 存储结构

```text
output/
  {YYYY-MM-DD}/
    announcements.json         ← 统一公告数组
    crawl-meta.json            ← 抓取元信息
    announcements.sample.json  ← 新 schema 样例（当前为参考文件）
```

说明：
- `announcements.json` 为扁平数组，不再按站点嵌套。
- 站点维度信息统一放进每条公告自身字段中。
- `crawl-meta.json` 只保存抓取统计与站点状态，不重复保存完整公告内容。

## 3. crawl-meta.json 结构

```json
{
  "date": "2026-04-27",
  "crawledAt": "2026-04-27T07:09:23.342977",
  "totalSites": 24,
  "successSites": 21,
  "failedSites": 3,
  "totalAnnouncements": 505,
  "newAnnouncements": 10,
  "sites": [
    {
      "siteId": "hrss_xm_gov_cn",
      "siteName": "厦门市人力资源和社会保障局",
      "status": "success",
      "announcementsCount": 20,
      "newCount": null,
      "durationMs": 12642,
      "strategyUsed": "css -> semantic",
      "error": null
    },
    {
      "siteId": "dpc_xm_gov_cn",
      "siteName": "厦门市发展和改革委员会",
      "status": "success",
      "announcementsCount": 30,
      "newCount": null,
      "durationMs": 12813,
      "strategyUsed": "css -> semantic",
      "error": null
    },
    {
      "siteId": "sti_xm_gov_cn",
      "siteName": "厦门市科学技术局",
      "status": "success",
      "announcementsCount": 24,
      "newCount": null,
      "durationMs": 12447,
      "strategyUsed": "css",
      "error": null
    },
    {
      "siteId": "most_gov_cn",
      "siteName": "科学技术部",
      "status": "success",
      "announcementsCount": 7,
      "newCount": null,
      "durationMs": 2414,
      "strategyUsed": "css",
      "error": null
    },
    {
      "siteId": "xmsme_cn",
      "siteName": "厦门市中小企业服务中心",
      "status": "success",
      "announcementsCount": 5,
      "newCount": null,
      "durationMs": 5359,
      "strategyUsed": "css",
      "error": null
    }
  ]
}
```

### 推荐字段定义

| 字段 | 类型 | 说明 |
|---|---|---|
| date | string | 数据目录日期 |
| crawledAt | string | 本次抓取完成时间 |
| totalSites | number | 已启用站点总数 |
| successSites | number | 抓取成功站点数 |
| failedSites | number | 抓取失败站点数 |
| totalAnnouncements | number | 本次落库的公告总数 |
| newAnnouncements | number | 相比上一日的新增公告数 |
| sites | array | 各站点抓取状态明细 |
| sites[].siteId | string | 站点 ID |
| sites[].siteName | string | 站点名称 |
| sites[].status | string | `success` / `failed` |
| sites[].announcementsCount | number | 该站点抓到的公告数 |
| sites[].newCount | number/null | 该站点新增数；若当前阶段未统计可置空 |
| sites[].durationMs | number/null | 抓取耗时 |
| sites[].strategyUsed | string/null | 实际使用的抓取策略 |
| sites[].error | string/null | 失败错误信息 |

## 4. 与旧结构的差异

### 旧结构概况

当前旧文件主要有三类：
- `stage1_results.json` / `combined_results.json`：顶层是 `results[]`，每个站点下再嵌套 `announcements[]`
- `incremental_results.json`：同样按站点嵌套，但额外包含 `comparison`、`summary`、`newCount`
- `config/urls.json`：站点配置与状态信息独立保存，不在公告记录中

### 新结构变化

| 维度 | 旧结构 | 新结构 |
|---|---|---|
| 公告组织方式 | `results[].announcements[]` 按站点嵌套 | `announcements.json` 直接保存扁平公告数组 |
| 站点信息位置 | 站点字段挂在外层 site 对象 | 每条公告内自带 `siteId/siteName/siteUrl/category` |
| 唯一标识 | 无统一公告 ID | 新增 `id` |
| 分类信息 | 仅在 `config/urls.json` 中存在 | 下沉到每条公告的 `category` |
| 数据来源 | 未显式记录或只靠文件名判断 | 每条公告增加 `source` |
| 抓取时间 | 文件顶层 `generatedAt` | 每条公告保留 `crawledAt` |
| 详情能力 | 只有标题/链接/日期 | 预留 `summary`、`content` |
| 统计信息 | 分散在不同结果文件顶层 | 统一收敛到 `crawl-meta.json` |

## 5. 待补字段

当前已有数据还不完整，后续建议补充：

- `attachments: array`：附件列表，包含文件名、链接、类型
- `summarySource: string`：摘要提取来源（AI 摘要 / 页面 meta / 手工规则）
- `contentHtml: string`：原始正文 HTML，便于二次清洗
- `contentText: string`：纯文本正文；若采用 `content` 保存纯文本，可二选一
- `keywords: array`：主题词或标签
- `authorOrg: string`：发文机构
- `documentNo: string`：文号
- `validFrom` / `validTo`: string：政策生效/失效时间
- `fetchedDetailAt: string`：详情页抓取时间
- `hash: string`：用于去重和变更检测的内容哈希
