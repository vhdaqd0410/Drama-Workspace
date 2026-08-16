/* 命令面板（Ctrl+K）— 融合自「项目档案管理器」command-palette.js
 * 模糊搜索 标签页 + 项目 + 命令，↑↓ 选择，Enter 执行，Esc 关闭。
 */
(function() {
  'use strict';

  let _overlay = null, _input = null, _list = null;
  let _items = [], _activeIdx = 0;

  // 需要跳转打开的页面 tab 名（与 index.html 一致）
  const TABS = [
    { id: 'dashboard', label: '📋 项目看板', hint: '' },
    { id: 'fenji', label: '📑 分集管理', hint: '' },
    { id: 'qa', label: '🔍 质检中心', hint: '' },
    { id: 'activity', label: '📜 任务中心', hint: '' },
    { id: 'report', label: '📊 月度报告', hint: '' },
    { id: 'nameplate', label: '🧰 工具箱', hint: '' },
    { id: 'settings', label: '⚙️ 设置', hint: '' },
  ];

  // 常用命令（引用全局函数，尽量容错）
  const COMMANDS = [
    { id: 'newproj', label: '🆕 新建/打开项目', hint: '', action: () => openGlobalSearch() },
    { id: 'refresh', label: '🔄 刷新项目列表', hint: 'F5', action: () => safeCall(() => loadProjects && loadProjects()) },
    { id: 'fenji', label: '📑 打开分集管理', hint: '', action: () => switchTab('fenji') },
    { id: 'qa', label: '🔍 打开质检中心', hint: '', action: () => switchTab('qa') },
    { id: 'toolbox', label: '🧰 打开工具箱', hint: '', action: () => switchTab('nameplate') },
    { id: 'settings', label: '⚙️ 打开设置', hint: '', action: () => switchTab('settings') },
    { id: 'backup', label: '💾 数据备份', hint: '', action: () => openBackupDialog() },
  ];

  function safeCall(fn) {
    try { fn(); } catch(e) { console.error('命令执行失败:', e); if (window.toast) toast('命令执行失败: ' + e.message, 'error'); }
  }

  function getProjects() {
    const list = [];
    const seen = {};
    (window.allSections || []).forEach(s => (s.projects || []).forEach(p => {
      if (!seen[p.name]) { seen[p.name] = 1; list.push(p); }
    }));
    (window.projects || []).forEach(p => { if (!seen[p.name]) { seen[p.name] = 1; list.push(p); } });
    return list;
  }

  function buildItems() {
    const items = [];
    // 标签页
    TABS.forEach(t => items.push({ type: 'tab', id: t.id, label: t.label, sub: t.hint || '跳转到页面', icon: '→', action: () => switchTab(t.id) }));
    // 项目
    getProjects().forEach(p => {
      items.push({
        type: 'project', id: p.name, label: p.name,
        sub: (p.custom_status || p.delivery_status || '') + (p.total_episodes ? ' · ' + p.total_episodes + '集' : ''),
        icon: '📁', action: () => { switchTab('dashboard'); safeCall(() => openProjectDetail && openProjectDetail(p.name)); },
      });
    });
    // 命令
    COMMANDS.forEach(c => items.push({ type: 'command', id: c.id, label: c.label, sub: c.hint || '', icon: '', action: c.action }));
    return items;
  }

  // 模糊匹配：query 字符依次出现在 text 中
  function fuzzyMatch(text, query) {
    if (!query) return true;
    text = String(text).toLowerCase(); query = query.toLowerCase();
    let ti = 0;
    for (let i = 0; i < query.length; i++) {
      const found = text.indexOf(query[i], ti);
      if (found < 0) return false;
      ti = found + 1;
    }
    return true;
  }

  function score(text, query) {
    if (!query) return 0;
    text = String(text).toLowerCase(); query = query.toLowerCase();
    if (text === query) return 1000;
    if (text.startsWith(query)) return 500;
    if (text.includes(query)) return 200;
    let s = 0, ti = 0, consecutive = 0;
    for (let i = 0; i < query.length; i++) {
      const found = text.indexOf(query[i], ti);
      if (found < 0) return -1;
      if (found === ti) consecutive++; else consecutive = 0;
      s += 10 + consecutive * 5;
      ti = found + 1;
    }
    return s;
  }

  function filter(query) {
    if (!query) return _items.slice(0, 30);
    const scored = [];
    _items.forEach(it => { const s = score(it.label, query); if (s >= 0) scored.push({ it, s }); });
    scored.sort((a, b) => b.s - a.s);
    return scored.slice(0, 30).map(x => x.it);
  }

  function render(filtered) {
    _activeIdx = 0;
    _list.innerHTML = filtered.map((it, i) => `
      <div class="cp-item${i===0?' active':''}" data-idx="${i}" onmousedown="event.preventDefault();window.__cpSelect(${i})">
        <span class="cp-icon">${it.icon || '•'}</span>
        <div class="cp-main">
          <div class="cp-label">${escHtml(it.label)}</div>
          <div class="cp-sub">${escHtml(it.sub || '')}</div>
        </div>
      </div>`).join('');
    if (!filtered.length) _list.innerHTML = '<div class="cp-empty">无匹配结果</div>';
  }

  function nav(delta) {
    const items = _list.querySelectorAll('.cp-item');
    if (!items.length) return;
    _activeIdx = (_activeIdx + delta + items.length) % items.length;
    items.forEach((el, i) => el.classList.toggle('active', i === _activeIdx));
    const el = items[_activeIdx];
    if (el) el.scrollIntoView({ block: 'nearest' });
  }

  function exec() {
    const filtered = filter(_input.value);
    const item = filtered[_activeIdx];
    if (!item) return;
    close();
    item.action();
  }

  function ensureCreated() {
    if (_overlay) return;
    _overlay = document.createElement('div');
    _overlay.id = 'cmdPaletteOverlay';
    _overlay.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.45);z-index:20000;display:none;align-items:flex-start;justify-content:center;padding-top:14vh';
    _overlay.innerHTML = `
      <div id="cmdPalette" style="width:92%;max-width:580px;background:var(--card,#fff);border:1px solid var(--border,#e5e5ea);border-radius:14px;box-shadow:0 18px 50px rgba(0,0,0,.3);overflow:hidden">
        <div style="display:flex;align-items:center;padding:12px 16px;border-bottom:1px solid var(--border,#e5e5ea)">
          <span style="margin-right:10px;font-size:15px;color:var(--text-sec)">⌘</span>
          <input id="cmdInput" placeholder="输入页面名、项目名或命令…（↑↓ 选择，Enter 执行，Esc 关闭）" style="flex:1;background:transparent;border:none;outline:none;font-size:15px;color:inherit" autocomplete="off">
          <kbd style="font-size:10px;color:var(--text-sec);border:1px solid var(--border,#e5e5ea);border-radius:4px;padding:1px 6px">Esc</kbd>
        </div>
        <div id="cmdList" style="max-height:52vh;overflow-y:auto;padding:6px"></div>
      </div>`;
    document.body.appendChild(_overlay);
    _input = _overlay.querySelector('#cmdInput');
    _list = _overlay.querySelector('#cmdList');
    _input.addEventListener('input', () => render(filter(_input.value)));
    _input.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown') { e.preventDefault(); nav(1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); nav(-1); }
      else if (e.key === 'Enter') { e.preventDefault(); exec(); }
      else if (e.key === 'Escape') { close(); }
    });
    _overlay.addEventListener('mousedown', (e) => { if (e.target === _overlay) close(); });
    // 选中项样式
    const style = document.createElement('style');
    style.textContent = `
      .cp-item{display:flex;align-items:center;gap:10px;padding:8px 10px;border-radius:8px;cursor:pointer}
      .cp-item.active{background:var(--blue,#0071e3);color:#fff}
      .cp-item .cp-icon{width:20px;text-align:center}
      .cp-main{flex:1;min-width:0}
      .cp-label{font-size:14px}
      .cp-sub{font-size:11px;opacity:.7;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
      .cp-empty{padding:20px;text-align:center;color:var(--text-sec);font-size:13px}
    `;
    document.head.appendChild(style);
    // 全局选中回调
    window.__cpSelect = function(i) { _activeIdx = i; exec(); };
  }

  function open() {
    ensureCreated();
    _items = buildItems();
    _overlay.style.display = 'flex';
    _input.value = '';
    render(_items.slice(0, 30));
    setTimeout(() => _input.focus(), 30);
  }

  function close() {
    if (_overlay) _overlay.style.display = 'none';
  }

  // Ctrl+P 或 Ctrl+Shift+K 打开命令面板（避免覆盖已有的 Ctrl+K 页面内搜索）
  document.addEventListener('keydown', (e) => {
    const k = e.key.toLowerCase();
    if ((e.ctrlKey || e.metaKey) && (k === 'p')) {
      e.preventDefault();
      if (_overlay && _overlay.style.display === 'flex') close(); else open();
    } else if ((e.ctrlKey || e.metaKey) && e.shiftKey && (k === 'k')) {
      e.preventDefault();
      if (_overlay && _overlay.style.display === 'flex') close(); else open();
    }
  });

  window.openCommandPalette = open;
})();

// 全局搜索：命令面板「新建/打开项目」入口（聚焦看板顶部的搜索框）
function openGlobalSearch(){
  switchTab('dashboard');
  const el = document.getElementById('globalSearch');
  if (el) { setTimeout(() => { el.focus(); el.select(); }, 80); }
}
