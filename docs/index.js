const $ = id => document.getElementById(id);

let allData = [];      // 当前日期筛选后的数据
let filteredData = [];
let cachedSites = null;
let dateCounts = {};   // 按公告发布日期 item.date 统计每日条数
let calendarMonth = '';

function getLatestDateWithData() {
  return Object.keys(dateCounts).sort().pop() || '';
}

function ensureDefaultSelectedDate() {
  if (!$('dateInput').value) {
    const today = formatFileDate(new Date());
    // 优先选当天（若有数据），其次选最新有数据日期，兜底选当天
    if (dateCounts[today]) {
      $('dateInput').value = today;
    } else {
      const latestDate = getLatestDateWithData();
      $('dateInput').value = latestDate || today;
    }
    $('selectedDateText').textContent = $('dateInput').value;
  }

  if (!calendarMonth) {
    calendarMonth = ($('dateInput').value || formatFileDate(new Date())).slice(0, 7);
  }
}

// 初始化
document.addEventListener('DOMContentLoaded', async () => {
  $('exportWordBtn').addEventListener('click', exportToWord);
  $('siteFilter').addEventListener('change', applyFilters);
  $('search').addEventListener('input', applyFilters);
  $('monthCalendar').addEventListener('click', e => {
    const btn = e.target.closest('button[data-date], button[data-month]');
    if (!btn) return;
    if (btn.dataset.date) {
      setSelectedDate(btn.dataset.date);
    } else if (btn.dataset.month) {
      shiftCalendarMonth(Number(btn.dataset.month));
    }
  });
  $('announcementList').addEventListener('click', e => {
    const btn = e.target.closest('button[data-date]');
    if (btn) { setSelectedDate(btn.dataset.date); return; }
    const header = e.target.closest('.card-header');
    if (header) {
      const detail = header.nextElementSibling;
      if (detail && detail.classList.contains('card-detail')) detail.classList.toggle('open');
    }
  });
  await loadSites();
  await loadIndexOnly();
  ensureDefaultSelectedDate();
  renderCalendar();
  loadData();
  renderVersionFooter();
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
 * 仅加载 index.json，获取所有有数据的日期列表，初始化 dateCounts
 */
async function loadIndexOnly() {
  try {
    const res = await fetch('data/index.json');
    if (!res.ok) {
      dateCounts = {};
      return;
    }
    const { dates } = await res.json();
    // 初始化 dateCounts：每个有数据的日期标记为 1 条（实际条数在首次加载时更新）
    dateCounts = {};
    for (const date of dates) {
      dateCounts[date] = 1;
    }
  } catch (_) {
    dateCounts = {};
  }
}

/**
 * 按需加载指定日期的公告数据，只 fetch 单个日期 JSON。
 */
async function loadData(date) {
  date = date || $('dateInput').value;
  if (!date) {
    $('announcementList').innerHTML = '<div class="empty-state">暂无公告数据</div>';
    $('stats').textContent = '';
    $('selectedDateText').textContent = '';
    renderCalendar();
    return;
  }

  $('selectedDateText').textContent = date;
  $('stats').textContent = '';
  $('announcementList').innerHTML = '<div class="empty-state">加载中...</div>';

  try {
    const res = await fetch(`data/${date}.json`);
    if (!res.ok) {
      allData = [];
      delete dateCounts[date];
    } else {
      allData = await res.json();
      // 更新 dateCounts 为实际条数
      if (allData.length > 0) {
        dateCounts[date] = allData.length;
      } else {
        delete dateCounts[date];
      }
    }
  } catch (e) {
    allData = [];
    delete dateCounts[date];
    $('announcementList').innerHTML = `<div class="error">加载失败：${esc(e.message)}</div>`;
    renderCalendar();
    return;
  }

  // 刷新日历，使当前日期的实际条数反映在日历上
  renderCalendar();

  // 如果站点列表未加载（兜底），从当前数据中提取
  if (!cachedSites) {
    populateSiteFilter();
  }
  applyFilters();
}

function populateSiteFilter() {
  const sites = [...new Set(allData.map(d => d.siteName).filter(Boolean))].sort();
  const cur = $('siteFilter').value;
  $('siteFilter').innerHTML = '<option value="">全部站点</option>' +
    sites.map(s => `<option value="${esc(s)}">${esc(s)}</option>`).join('');
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
  const date = $('dateInput').value;
  $('stats').textContent = shown === total
    ? `共 ${total} 条 ${date} 的公告`
    : `显示 ${shown} / ${total} 条 ${date} 的公告`;
}

function renderList() {
  if (!allData.length) {
    $('announcementList').innerHTML = renderNoDataOptions($('dateInput').value);
    return;
  }

  if (!filteredData.length) {
    $('announcementList').innerHTML = '<div class="empty-state">暂无匹配的公告</div>';
    return;
  }

  $('announcementList').innerHTML = filteredData.map(item => `
    <div class="card">
      <div class="card-header">
        <span class="card-title">${esc(item.title)}</span>
        <span class="card-meta">
          ${item.date ? `<span class="tag date-tag" title="公告发布日期">${esc(item.date)}</span>` : ''}
          ${item.category ? `<span class="tag">${esc(item.category)}</span>` : ''}
          ${item.siteName ? `<span class="tag">${esc(item.siteName)}</span>` : ''}
        </span>
      </div>
      <div class="card-detail">
        ${item.url ? `<div class="field"><span class="field-label">链接：</span><a href="${esc(item.url)}" target="_blank" rel="noopener">${esc(item.url)}</a></div>` : ''}
        ${item.summary ? `<div class="field"><span class="field-label">摘要：</span>${esc(item.summary)}</div>` : ''}
        ${item.siteUrl ? `<div class="field"><span class="field-label">来源站点：</span><a href="${esc(item.siteUrl)}" target="_blank" rel="noopener">${esc(item.siteUrl)}</a></div>` : ''}
      </div>
    </div>`
  ).join('');
}

function renderNoDataOptions(date) {
  const dates = Object.keys(dateCounts).sort();
  const prev = [...dates].reverse().find(d => d < date);
  const next = dates.find(d => d > date);
  const optionHtml = [prev, next].filter(Boolean).map(d => `
    <button type="button" class="nearby-date" data-date="${esc(d)}">
      ${d} · ${dateCounts[d]} 条
    </button>
  `).join('');

  return `<div class="empty-state">
    <div>所选日期暂无公告。</div>
    ${optionHtml ? `<div class="nearby-dates"><div class="nearby-title">可跳转到邻近有数据日期：</div>${optionHtml}</div>` : ''}
  </div>`;
}

function renderCalendar() {
  const container = $('monthCalendar');
  if (!container || !calendarMonth) return;
  const [year, month] = calendarMonth.split('-').map(Number);
  const first = new Date(year, month - 1, 1);
  const daysInMonth = new Date(year, month, 0).getDate();
  const selectedDate = $('dateInput').value;
  const blanks = Array(first.getDay()).fill('<div class="calendar-day blank"></div>').join('');
  const dayHtml = Array.from({ length: daysInMonth }, (_, i) => {
    const day = i + 1;
    const date = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    const count = dateCounts[date] || 0;
    const classes = ['calendar-day'];
    if (count) classes.push('has-data');
    if (date === selectedDate) classes.push('selected');
    return `<button type="button" class="${classes.join(' ')}" data-date="${date}">
      <span class="day-number">${day}</span>
      ${count ? `<span class="day-count">${count}条</span>` : ''}
    </button>`;
  }).join('');

  container.innerHTML = `
    <div class="calendar-header">
      <button type="button" class="calendar-nav" data-month="-1">上月</button>
      <strong>${year}年${month}月公告统计</strong>
      <button type="button" class="calendar-nav" data-month="1">下月</button>
    </div>
    <div class="calendar-weekdays"><span>日</span><span>一</span><span>二</span><span>三</span><span>四</span><span>五</span><span>六</span></div>
    <div class="calendar-grid">${blanks}${dayHtml}</div>
  `;
}

function shiftCalendarMonth(delta) {
  const [year, month] = calendarMonth.split('-').map(Number);
  const next = new Date(year, month - 1 + delta, 1);
  calendarMonth = `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, '0')}`;
  renderCalendar();
}

function setSelectedDate(date) {
  $('dateInput').value = date;
  $('selectedDateText').textContent = date;
  calendarMonth = date.slice(0, 7);
  renderCalendar();
  loadData();
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

// toggleDetail removed — expand/collapse handled by event delegation on announcementList

// 页面底部版本信息
function renderVersionFooter() {
  const versionEl = $('footerVersion');
  const rangeEl = $('footerDataRange');
  if (!versionEl) return;

  // 版本 = 当前日期时间
  const now = new Date();
  const pad = n => String(n).padStart(2, '0');
  const version = `${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`;
  versionEl.textContent = `v${version}`;

  // 数据范围：dateCounts 的最小和最大日期
  if (rangeEl) {
    const keys = Object.keys(dateCounts || {}).sort();
    if (keys.length > 0) {
      rangeEl.textContent = ` · 数据: ${keys[0]} ~ ${keys[keys.length-1]}`;
    }
  }
}

function esc(str) {
  if (!str) return '';
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}
