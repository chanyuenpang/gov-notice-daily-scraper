const $ = id => document.getElementById(id);

let allData = [];
let filteredData = [];

// 初始化
document.addEventListener('DOMContentLoaded', () => {
  $('loadBtn').addEventListener('click', loadData);
  $('siteFilter').addEventListener('change', applyFilters);
  $('search').addEventListener('input', applyFilters);
  $('dateInput').addEventListener('keydown', e => { if (e.key === 'Enter') loadData(); });
  // 自动加载默认日期
  loadData();
});

async function loadData() {
  const date = $('dateInput').value || '2026-04-28';
  $('stats').textContent = '';
  $('announcementList').innerHTML = '<div class="empty-state">加载中...</div>';

  try {
    const data = await fetchJson(date);
    allData = Array.isArray(data) ? data : [];
    populateSiteFilter();
    applyFilters();
  } catch (e) {
    allData = [];
    $('announcementList').innerHTML = `<div class="error">加载失败：${esc(e.message)}</div>`;
  }
}

/**
 * 从 data/ 目录加载 JSON 数据（GitHub Pages 托管）
 */
async function fetchJson(date) {
  const url = `data/${date}.json`;
  const res = await tryFetch(url);
  if (res) return res.json();
  throw new Error(`找不到 ${date} 的公告数据（${url}）`);
}

async function tryFetch(url) {
  try {
    const res = await fetch(url);
    if (res.ok) return res;
  } catch (_) {}
  return null;
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
    ? `共 ${total} 条公告`
    : `显示 ${shown} / ${total} 条公告`;
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
        <div class="field"><span class="field-label">抓取时间：</span>${esc(item.crawledAt || '')}</div>
      </div>
    </div>
  `).join('');
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
