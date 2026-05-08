# Daily Run SOP — 政府公告抓取+日报生成+飞书推送

> 本文档描述每日定时任务的完整执行流程，与 cron job `a5efcd08-372e-4fd6-b4bd-6e69fd238da0` 的 payload 保持同步。

## 工作目录

```
/home/yankeeting/.openclaw/projects/gov-notice-daily-scraper
```

---

## Step 1: 初始化

```bash
cd /home/yankeeting/.openclaw/projects/gov-notice-daily-scraper
DATE=$(date +%F)
MONTH=$(date +%Y-%m)
```

---

## Step 2: Phase 1 — 脚本批量抓取

```bash
python3 scripts/run_daily.py --date $DATE --phase 1
```

- 此阶段使用 CSS 选择器批量抓取 24 个站点。
- 如果命令失败，立即停止并汇报失败原因。

---

## Step 3: Phase 2-Prep — 分析失败站点

```bash
python3 scripts/run_daily.py --date $DATE --phase 2-prep
```

- 此阶段分析 Phase 1 结果，生成 scraper-agent 任务清单。
- 读取 `output/$MONTH/browser_agent_tasks_$DATE.json`。

---

## Step 4: 失败站点补抓（如果有）

检查 `output/$MONTH/browser_agent_tasks_$DATE.json` 是否存在且包含任务：

- 如果文件不存在或为空数组 `[]`，跳过此步骤，直接进入 Step 5。
- 如果有任务，对每个任务 spawn 一个 scraper-agent subagent：

```
sessions_spawn({
  agentId: "scraper-agent",
  runtime: "subagent",
  task: "站点规则学习：{siteId}，URL: {url}，原因: {reason}。项目目录: /home/yankeeting/.openclaw/projects/gov-notice-daily-scraper"
})
```

scraper-agent 会自动：

a) 用 BrowserOS MCP 打开页面分析 DOM
b) 学习精确的 CSS 选择器（带 class/id 限定）
c) 写入 config/rules/{siteId}.json
d) 将抓取结果写入 output/$MONTH/{siteId}.json 和 output/$MONTH/stage2_results_$DATE.json

---

## Step 5: 等待 scraper-agent 完成（文件轮询，最多 5 分钟）

对 Step 4 中 spawn 的每个 scraper-agent，轮询检查其输出文件是否存在：

- **检查文件**：`output/$MONTH/{siteId}.json`（每个失败站点的独立 JSON 文件）
- **轮询方式**：用 exec 执行 shell 循环，每 30 秒检查一次
- **最多等待 5 分钟**（300 秒），超时后不再等待，直接进入 Step 6
- 如果 5 分钟内所有 scraper-agent 都已完成（输出文件都已生成），立即进入 Step 6
- 如果没有 spawn scraper-agent（Step 4 被跳过），直接进入 Step 6

> ⚠️ **绝对不要**使用任何 session 等待/查询/历史工具（如 yield/list/history）。只用文件存在性判断完成。

在 exec 中执行以下 shell 脚本（`WAIT_SITES` 根据实际失败站点动态设置）：

```bash
WAIT_SITES=("most_gov_cn" "siming_gov_cn")  # 示例，实际根据 Step 3 输出设置
MAX_WAIT=300
INTERVAL=30
ELAPSED=0
while [ $ELAPSED -lt $MAX_WAIT ]; do
  ALL_DONE=true
  for SITE in "${WAIT_SITES[@]}"; do
    if [ ! -f "output/$MONTH/${SITE}.json" ]; then
      ALL_DONE=false
      break
    fi
  done
  if [ "$ALL_DONE" = true ]; then
    echo "All scraper-agents completed after ${ELAPSED}s"
    break
  fi
  sleep $INTERVAL
  ELAPSED=$((ELAPSED + INTERVAL))
  echo "Waiting... ${ELAPSED}s elapsed"
done
if [ $ELAPSED -ge $MAX_WAIT ]; then
  echo "Timeout after ${MAX_WAIT}s, proceeding with available data"
fi
```

---

## Step 6: Phase 3 — 合并+日报+增量+GitHub Page 同步（必须执行）

> ⚠️ **无论 Phase 2 是否成功完成，都必须执行此步骤。** Phase 3 会自动用 Phase 1 数据生成日报。

```bash
python3 scripts/run_daily.py --date $DATE --phase 3
```

- 此阶段会自动检测是否有 stage2 补抓结果：有则合并，无则直接用 Phase 1 数据。
- 生成日报、增量分析、同步 GitHub Page。
- 如果命令失败，记录错误但继续执行飞书推送。

---

## Step 7: 飞书推送

读取 `output/$DATE/增量日报.md` 的内容（注意：增量日报仍在日期目录下，由 Phase 3 生成），通过飞书将增量日报发送到群 `oc_00c2c690e5a60b6803a38b121568e4c1`。

- 使用飞书消息工具发送，内容为增量日报的 markdown 正文。
- 在增量日报内容末尾追加一行：

```
🔗 查看完整公告：https://chanyuenpang.github.io/gov-notice-daily-scraper/
```

- 如果增量日报.md 不存在或为空，发送简要说明，但仍附上 GitHub Pages 链接。

---

## 最终汇报

必须包含以下信息：

- 成功/失败站点数
- 总公告数
- 新增公告数（增量）
- 日报/GitHub Page 是否已更新
- 是否有新的抓取规则生成
- GitHub Pages 链接：https://chanyuenpang.github.io/gov-notice-daily-scraper/
- 各步骤的成功/失败状态和关键错误信息

---

## 注意事项

- 只在上述项目目录内工作。
- 可以读取并复用项目内已有脚本、配置、输出目录结构。
- 不要修改其他 cron job。
