const $ = id => document.getElementById(id);

let allData = [];
let filteredData = [];
let manifest = [];
let selectedDate = '';
let currentView = 'announcements';

// ── Init ──────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  // Tab switching
  document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => switchView(tab.dataset.view));
  });

  // Sidebar toggle
  $('menuBtn').addEventListener('click', openSidebar);
  $('sidebarClose').addEventListener('click', closeSidebar);
  $('overlay').addEventListener('click', closeSidebar);

  // Filters
  $('siteFilter').addEventListener('change', applyFilters);
  $('search').addEventListener('input', applyFilters);

  // Load manifest & auto-select latest date
  await loadManifest();
});

// ── Sidebar ───────────────────────────────────────────
function openSidebar() {
  $('sidebar').classList.add('open');
  $('overlay').classList.add('active');
}
function closeSidebar() {
  $('sidebar').classList.remove('open');
  $('overlay').classList.remove('active');
}

// ── Manifest ──────────────────────────────────────────
async function loadManifest() {
  try {
    let res = await tryFetch('output/manifest.json');
    if (!res) res = await tryFetch('../output/manifest.json');
    if (!res) res = await tryFetch('data/manifest.json');
    if (res) {
      manifest = await res.json();
    }
  } catch (_) {}

  // Fallback: if no manifest, discover dates from data dir or output dir
  if (!manifest.length) {
    manifest = [{ date: '2026-04-28', count: 0, sites: [], hasIncremental: false, hasDaily: false }];
  }

  renderDateList();

  // Auto-select latest
  selectedDate = manifest[0].date;
  await loadDate(selectedDate);
}

function renderDateList() {
  const container = $('dateList');
  if (!manifest.length) {
    container.innerHTML = '<div class="empty-state">暂无数据</div>';
    return;
  }

  // Group by month
  const groups = {};
  manifest.forEach(item => {
    const month = item.date.substring(0, 7);
    if (!groups[month]) groups[month] = [];
    groups[month].push(item);
  });

  let html = '';
  for (const [month, items] of Object.entries(groups)) {
    html += `<div class="date-group">
      <div class="date-group-title">${formatMonth(month)}</div>
      <div class="date-group-items">`;
    items.forEach(item => {
      const d = item.date.substring(5); // MM-DD
      const badge = item.count > 0 ? `<span class="date-badge">${item.count}</span>` : '';
      html += `<div class="date-item ${item.date === selectedDate ? 'active' : ''}" 
                   data-date="${item.date}" onclick="selectDate('${item.date}')">
        <span class="date-day">${d}</span>
        ${badge}
      </div>`;
    });
    html += '</div></div>';
  }
  container.innerHTML = html;
}

function formatMonth(month) {
  const [y, m] = month.split('-');
  return `${y}年${parseInt(m)}月`;
}

async function selectDate(date) {
  selectedDate = date;
  // Update active state
  document.querySelectorAll('.date-item').forEach(el => {
    el.classList.toggle('active', el.dataset.date === date);
  });
  closeSidebar();
  await loadDate(date);
}

// ── Load Date Data ────────────────────────────────────
async function loadDate(date) {
  $('headerDate').textContent = formatDateCN(date);
  $('announcementList').innerHTML = '<div class="empty-state">加载中...</div>';
  $('statsBar').innerHTML = '';
  $('incrementalContent').innerHTML = '<div class="empty-state">加载中...</div>';
  $('dailyContent').innerHTML = '<div class="empty-state">加载中...</div>';

  // Load announcements
  try {
    const data = await fetchAnnouncements(date);
    allData = Array.isArray(data) ? data : [];
  } catch (e) {
    allData = [];
    $('announcementList').innerHTML = `<div class="error">加载失败：${esc(e.message)}</div>`;
  }

  // Stats
  const sites = [...new Set(allData.map(d => d.siteName).filter(Boolean))];
  $('statsBar').innerHTML = `
    <span class="stat-item">📊 共 <strong>${allData.length}</strong> 条公告</span>
    <span class="stat-item">🌐 <strong>${sites.length}</strong> 个站点</span>
    <span class="stat-item">📅 ${formatDateCN(date)}</span>
  `;

  populateSiteFilter();
  applyFilters();

  // Load reports in parallel
  loadReports(date);
}

async function fetchAnnouncements(date) {
  // Try frontend output symlink
  let res = await tryFetch(`output/reports/${date}/announcements.json`);
  if (res) return res.json();
  // Try parent output path
  res = await tryFetch(`../output/reports/${date}/announcements.json`);
  if (res) return res.json();
  // Try local data/
  res = await tryFetch(`data/${date}.json`);
  if (res) return res.json();
  throw new Error(`找不到 ${date} 的数据`);
}

async function loadReports(date) {
  // Load incremental report
  try {
    let html = await fetchReport(date, '增量日报');
    $('incrementalContent').innerHTML = renderMarkdown(html);
  } catch (_) {
    $('incrementalContent').innerHTML = '<div class="empty-state">该日期暂无增量日报</div>';
  }

  // Load daily report
  try {
    let html = await fetchReport(date, '日报');
    $('dailyContent').innerHTML = renderMarkdown(html);
  } catch (_) {
    $('dailyContent').innerHTML = '<div class="empty-state">该日期暂无完整日报</div>';
  }
}

async function fetchReport(date, name) {
  // Try frontend output symlink
  let res = await tryFetch(`output/reports/${date}/${name}.md`);
  if (res) return res.text();
  // Try parent output path
  res = await tryFetch(`../output/reports/${date}/${name}.md`);
  if (res) return res.text();
  // Try local data
  res = await tryFetch(`data/${date}-${name}.md`);
  if (res) return res.text();
  throw new Error('not found');
}

// ── Markdown → HTML (lightweight) ────────────────────
function renderMarkdown(md) {
  let html = esc(md);
  // Headers
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
  // Bold
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // Horizontal rules
  html = html.replace(/^---$/gm, '<hr>');
  // Links
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  // Tables (basic)
  html = html.replace(/\|(.+)\|/g, (match) => {
    const cells = match.split('|').filter(c => c.trim());
    if (cells.every(c => /^[\s-]+$/.test(c))) return ''; // separator row
    const isHeader = cells.every(c => /^[\s-:]+$/.test(c));
    const tag = 'td';
    return '<tr>' + cells.map(c => `<${tag}>${c.trim()}</${tag}>`).join('') + '</tr>';
  });
  // Wrap tables
  html = html.replace(/((<tr>.*<\/tr>\n?)+)/g, '<table class="report-table">$1</table>');
  // Paragraphs - wrap loose lines
  html = html.replace(/\n{2,}/g, '</p><p>');
  html = '<p>' + html + '</p>';
  // Clean up empty p tags around block elements
  html = html.replace(/<p>\s*<(h[1-3]|hr|table)/g, '<$1');
  html = html.replace(/<\/(h[1-3]|table)>\s*<\/p>/g, '</$1>');
  return html;
}

// ── View Switching ────────────────────────────────────
function switchView(view) {
  currentView = view;
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.view === view));
  document.querySelectorAll('.view-content').forEach(v => v.classList.remove('active'));
  $(`${view}View`).classList.add('active');
  // Show/hide filter bar only for announcements
  $('filterBar').style.display = view === 'announcements' ? '' : 'none';
}

// ── Filters ──────────────────────────────────────────
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
}

// ── Render Announcement List ──────────────────────────
function renderList() {
  if (!filteredData.length) {
    $('announcementList').innerHTML = '<div class="empty-state">暂无匹配的公告</div>';
    return;
  }

  // Group by site
  const grouped = {};
  filteredData.forEach(item => {
    const site = item.siteName || '未知站点';
    if (!grouped[site]) grouped[site] = [];
    grouped[site].push(item);
  });

  let html = '';
  for (const [site, items] of Object.entries(grouped)) {
    html += `<div class="site-group">
      <div class="site-group-header">
        <span class="site-name">🏛️ ${esc(site)}</span>
        <span class="site-count">${items.length} 条</span>
      </div>`;
    items.forEach(item => {
      html += renderCard(item);
    });
    html += '</div>';
  }
  $('announcementList').innerHTML = html;
}

function renderCard(item) {
  const id = (item.id || Math.random().toString(36).substr(2, 9)).replace(/[^a-zA-Z0-9_-]/g, '_');
  return `
    <div class="card" id="card-${id}">
      <div class="card-header" onclick="toggleDetail('${id}')">
        <span class="card-title">${esc(item.title)}</span>
        <span class="card-meta">
          ${item.date ? `<span class="tag date-tag">${esc(item.date)}</span>` : ''}
          ${item.category ? `<span class="tag">${esc(item.category)}</span>` : ''}
          <span class="expand-icon">▼</span>
        </span>
      </div>
      <div class="card-detail" id="detail-${id}">
        ${item.url ? `<div class="field"><span class="field-label">🔗 链接：</span><a href="${esc(item.url)}" target="_blank" rel="noopener">${esc(item.url)}</a></div>` : ''}
        ${item.summary ? `<div class="field"><span class="field-label">📝 摘要：</span>${esc(item.summary)}</div>` : ''}
        ${item.siteUrl ? `<div class="field"><span class="field-label">🌐 来源：</span><a href="${esc(item.siteUrl)}" target="_blank" rel="noopener">${esc(item.siteUrl)}</a></div>` : ''}
        <div class="field"><span class="field-label">⏰ 抓取时间：</span>${esc(item.crawledAt || '')}</div>
      </div>
    </div>`;
}

function toggleDetail(id) {
  const el = $(`detail-${id}`);
  const card = $(`card-${id}`);
  if (el) {
    el.classList.toggle('open');
    if (card) card.classList.toggle('expanded', el.classList.contains('open'));
  }
}

// ── Utils ─────────────────────────────────────────────
async function tryFetch(url) {
  try {
    const res = await fetch(url);
    if (res.ok) return res;
  } catch (_) {}
  return null;
}

function esc(str) {
  if (!str) return '';
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

function formatDateCN(dateStr) {
  if (!dateStr) return '';
  const [y, m, d] = dateStr.split('-');
  return `${y}年${parseInt(m)}月${parseInt(d)}日`;
}
