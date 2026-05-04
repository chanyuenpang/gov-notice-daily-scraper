const $ = id => document.getElementById(id);

let allDataCache = []; // 全量数据缓存（所有日期文件合并后按 id 去重）
let allData = [];      // 当前日期筛选后的数据
let filteredData = [];
let cachedSites = null;

// 初始化
document.addEventListener('DOMContentLoaded', async () => {
  $('exportWordBtn').addEventListener('click', exportToWord);
  $('siteFilter').addEventListener('change', applyFilters);
  $('search').addEventListener('input', applyFilters);
  $('dateInput').addEventListener('change', loadData);
  $('dateInput').addEventListener('keydown', e => { if (e.key === 'Enter') loadData(); });
  await loadSites();
  loadData();
});

/**
 * 加载全量站点列表
 */
async function loadSites() {
  try {
    const res = await fetch('data/sites.json');
    if (res.ok) {
      cachedSites = await res.json();
      populateSiteFilterFromCache();
    }
  } catch (_) {}
}

function populateSiteFilterFromCache() {
  if (!cachedSites) return;
  const cur = $('siteFilter').value;
  $('siteFilter').innerHTML = '<option value="">全部站点</option>' +
    cachedSites.map(s => `<option value="${esc(s.name)}">${esc(s.name)}</option>`).join('');
  $('siteFilter').value = cur;
}

/**
 * 加载全量数据（所有日期文件合并，按 id 去重），结果缓存
 */
async function loadAllData() {
  if (allDataCache.length > 0) return allDataCache;

  try {
    const res = await fetch('data/index.json');
    if (!res.ok) return [];
    const { dates } = await res.json();

    const results = await Promise.all(
      dates.map(async date => {
        try {
          const r = await fetch(`data/${date}.json`);
          if (r.ok) return await r.json();
        } catch (_) {}
        return [];
      })
    );

    const seen = new Set();
    allDataCache = results.flat().filter(item => {
      if (seen.has(item.id)) return false;
      seen.add(item.id);
      return true;
    });

    return allDataCache;
  } catch (_) {
    return [];
  }
}

/**
 * 按发布日期筛选并显示
 */
async function loadData() {
  const date = $('dateInput').value;
  if (!date) {
    $('announcementList').innerHTML = '<div class="empty-state">请选择日期</div>';
    $('stats').textContent = '';
    return;
  }

  $('stats').textContent = '';
  $('announcementList').innerHTML = '<div class="empty-state">加载中...</div>';

  try {
    const allItems = await loadAllData();
    // 按公告发布日期筛选
    allData = allItems.filter(item => item.date === date);

    if (!cachedSites) {
      populateSiteFilter();
    }
    applyFilters();
  } catch (e) {
    allData = [];
    $('announcementList').innerHTML = `<div class="error">加载失败：${esc(e.message)}</div>`;
  }
}

function populateSiteFilter() {
  const sites = [...new Set(allData.map(d => d.siteName).filter(Boolean))].sort();
  const cur = $('siteFilter').value;
  $('siteFilter').innerHTML = '<option value="">全部站点</option>' +
    sites.map(s => `<option value="${s}">${s}</option>`).join('');
  $('siteFilter').value = cur;
}

function applyFilters() {
  const site = $('siteFilter').value;
  const keyword = $('search').value.trim().toLowerCase();

  filteredData = allData.filter(d => {
    if (site && d.siteName !== site) return false;
    if (keyword && !(d.title || '').toLowerCase().includes(keyword)) return false;
    return true;
  });

  renderList();
  const total = allData.length;
  const shown = filteredData.length;
  $('stats').textContent = shown === total
    ? `共 ${total} 条发布于 ${$('dateInput').value} 的公告`
    : `显示 ${shown} / ${total} 条发布于 ${$('dateInput').value} 的公告`;
}

function renderList() {
  if (!filteredData.length) {
    $('announcementList').innerHTML = '<div class="empty-state">暂无匹配的公告</div>';
    return;
  }

  $('announcementList').innerHTML = filteredData.map(item => `
    <div class="card" id="card-${esc(item.id)}">
      <div class="card-header" onclick="toggleDetail('${esc(item.id)}')">
        <span class="card-title">${esc(item.title)}</span>
        <span class="card-meta">
          ${item.date ? `<span class="tag date-tag">${esc(item.date)}</span>` : ''}
          ${item.category ? `<span class="tag">${esc(item.category)}</span>` : ''}
          ${item.siteName ? `<span class="tag">${esc(item.siteName)}</span>` : ''}
        </span>
      </div>
      <div class="card-detail" id="detail-${esc(item.id)}">
        ${item.url ? `<div class="field"><span class="field-label">链接：</span><a href="${esc(item.url)}" target="_blank" rel="noopener">${esc(item.url)}</a></div>` : ''}
        ${item.summary ? `<div class="field"><span class="field-label">摘要：</span>${esc(item.summary)}</div>` : ''}
        ${item.siteUrl ? `<div class="field"><span class="field-label">来源站点：</span><a href="${esc(item.siteUrl)}" target="_blank" rel="noopener">${esc(item.siteUrl)}</a></div>` : ''}
      </div>
    </div>
  `).join('');
}

function exportToWord() {
  if (!filteredData.length) {
    window.alert('当前没有可导出的公告，请先调整筛选条件或加载数据。');
    return;
  }

  const exportDate = new Date();
  const selectedDate = $('dateInput').value;
  const selectedSite = $('siteFilter').value;
  const keyword = $('search').value.trim();
  const fileDate = formatFileDate(exportDate);
  const html = buildWordDocument({
    exportDate,
    selectedDate,
    selectedSite,
    keyword,
    announcements: filteredData,
  });

  const blob = new Blob(['\ufeff', html], {
    type: 'application/msword;charset=utf-8',
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');

  link.href = url;
  link.download = `政府公告日报-${fileDate}.doc`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);

  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function buildWordDocument({ exportDate, selectedDate, selectedSite, keyword, announcements }) {
  const conditions = [];
  if (selectedSite) conditions.push(`站点：${selectedSite}`);
  if (keyword) conditions.push(`搜索词：${keyword}`);

  const conditionText = conditions.length ? conditions.join('；') : '无';
  const selectedDateText = selectedDate || '未指定';
  const exportTimeText = formatDateTime(exportDate);
  const itemHtml = announcements.map((item, index) => `
    <div class="notice-item">
      <h2>${index + 1}. ${escapeWordHtml(item.title || '未命名公告')}</h2>
      <p><strong>日期：</strong>${escapeWordHtml(item.date || '未提供')}</p>
      <p><strong>站点：</strong>${escapeWordHtml(item.siteName || '未提供')}</p>
      <p><strong>分类：</strong>${escapeWordHtml(item.category || '未提供')}</p>
      <p><strong>URL：</strong>${item.url ? `<a href="${escapeAttribute(item.url)}">${escapeWordHtml(item.url)}</a>` : '未提供'}</p>
      <p><strong>摘要：</strong>${escapeWordHtml(item.summary || '未提供')}</p>
    </div>
  `).join('');

  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>政府公告日报</title>
  <style>
    body { font-family: "Microsoft YaHei", "PingFang SC", sans-serif; color: #222; line-height: 1.6; margin: 24px; }
    h1 { text-align: center; margin-bottom: 16px; }
    .meta { margin-bottom: 20px; font-size: 14px; }
    .meta p { margin: 6px 0; }
    .notice-item { margin-bottom: 20px; padding-bottom: 16px; border-bottom: 1px solid #d9d9d9; }
    .notice-item h2 { font-size: 18px; margin-bottom: 10px; }
    .notice-item p { margin: 6px 0; word-break: break-all; }
    a { color: #2563eb; text-decoration: none; }
  </style>
</head>
<body>
  <h1>政府公告日报</h1>
  <div class="meta">
    <p><strong>导出时间：</strong>${escapeWordHtml(exportTimeText)}</p>
    <p><strong>当前日期：</strong>${escapeWordHtml(selectedDateText)}</p>
    <p><strong>筛选条件：</strong>${escapeWordHtml(conditionText)}</p>
    <p><strong>公告数量：</strong>${announcements.length}</p>
  </div>
  ${itemHtml}
</body>
</html>`;
}

function formatFileDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function formatDateTime(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  const seconds = String(date.getSeconds()).padStart(2, '0');
  return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
}

function escapeWordHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
    .replace(/\n/g, '<br>');
}

function escapeAttribute(str) {
  return escapeWordHtml(str).replace(/<br>/g, '');
}

function toggleDetail(id) {
  const el = $(`detail-${id}`);
  if (el) el.classList.toggle('open');
}

function esc(str) {
  if (!str) return '';
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}
