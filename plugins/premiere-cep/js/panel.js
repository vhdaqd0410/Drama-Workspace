/* 视频工作台 · CEP 面板逻辑
 * 功能：
 *   1. 连接视频工作台（服务器地址 + API Key，检测连通性）
 *   2. 读取当前 Premiere 项目/序列信息（通过 JSX）
 *   3. 在工作台查找匹配项目
 *   4. 标记剪辑完成（状态 → 审核中）
 *   5. 更新当前集数
 */
(function () {
  'use strict';

  var csInterface = (typeof window.__adobe_cep__ !== 'undefined') ? new CSInterface() : null;

  // ---------- 状态 ----------
  var state = {
    server: 'http://127.0.0.1:8089',
    apiKey: '',
    connected: false,
    prInfo: null,       // Premiere 项目信息
    wbProject: null,    // 工作台匹配项目
  };

  // ---------- DOM ----------
  var $ = function (id) { return document.getElementById(id); };

  // ---------- 本地存储（CEP 用 localStorage 受限，用 extendscript 存或内存） ----------
  function loadConfig() {
    try {
      var s = localStorage.getItem('wbcep_cfg');
      if (s) { var c = JSON.parse(s); state.server = c.server || state.server; state.apiKey = c.apiKey || ''; }
    } catch (e) {}
    $('serverUrl').value = state.server;
    $('apiKey').value = state.apiKey;
  }
  function saveConfig() {
    try { localStorage.setItem('wbcep_cfg', JSON.stringify({ server: state.server, apiKey: state.apiKey })); } catch (e) {}
  }

  // ---------- 工作台 API ----------
  async function wbFetch(path, method, body) {
    var url = state.server.replace(/\/+$/, '') + path;
    var headers = { 'X-API-KEY': state.apiKey };
    var opts = { method: method || 'GET', headers: headers };
    if (body !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    var resp = await fetch(url, opts);
    var data;
    try { data = await resp.json(); } catch (e) { data = {}; }
    if (!resp.ok) {
      throw new Error((data && (data.message || data.msg)) || ('HTTP ' + resp.status));
    }
    return data;
  }

  function setStatus(el, text, ok) {
    el.textContent = text;
    el.className = 'status ' + (ok ? 'ok' : 'err');
  }

  // ---------- 连接检测 ----------
  async function connect() {
    state.server = $('serverUrl').value.trim() || state.server;
    state.apiKey = $('apiKey').value.trim() || '';
    saveConfig();
    var st = $('connStatus');
    setStatus(st, '检测中...', true);
    try {
      // 用一个轻量公开接口检测连通（/api/health 无鉴权）
      var resp = await fetch(state.server.replace(/\/+$/, '') + '/api/health');
      if (resp.ok) {
        state.connected = true;
        setStatus(st, '✅ 已连接', true);
        $('btnConnect').disabled = false;
      } else {
        state.connected = false;
        setStatus(st, '❌ 服务器响应异常', false);
      }
    } catch (e) {
      state.connected = false;
      setStatus(st, '❌ 无法连接: ' + e.message, false);
    }
  }

  // ---------- 读取 Premiere 项目 ----------
  function readPremiereProject() {
    if (!csInterface) {
      // 非 CEP 环境（浏览器调试）：用模拟数据
      state.prInfo = { projectName: '示例项目（浏览器预览）', sequences: [{ name: '第5集', ep: 5 }], activeSequence: '第5集', activeEp: 5 };
      renderPrInfo();
      return;
    }
    csInterface.evalScript('__workbenchDispatch("getProjectInfo")', function (res) {
      try {
        var info = JSON.parse(res || '{}');
        if (info.error) { $('prName').textContent = '—'; alert('读取失败: ' + info.error); return; }
        state.prInfo = info;
        renderPrInfo();
      } catch (e) {
        alert('解析失败: ' + e.message);
      }
    });
  }

  function renderPrInfo() {
    if (!state.prInfo) return;
    $('prName').textContent = state.prInfo.projectName || '—';
    $('prSeq').textContent = state.prInfo.activeSequence || '—';
    $('prSeqCount').textContent = (state.prInfo.sequences || []).length + ' 个';
  }

  // ---------- 在工作台查找 ----------
  async function findInWorkbench() {
    if (!state.connected) { await connect(); }
    if (!state.connected) { alert('请先连接到工作台'); return; }
    if (!state.prInfo || !state.prInfo.projectName) { readPremiereProject(); }
    var name = (state.prInfo && state.prInfo.projectName) || '';
    if (!name) { alert('未读取到 Premiere 项目名'); return; }
    // 去掉 .prproj 后缀和常见前缀用于匹配
    var base = name.replace(/\.prproj$/i, '');
    var hint = $('matchHint');
    hint.textContent = '搜索: ' + base;
    try {
      var d = await wbFetch('/api/search?q=' + encodeURIComponent(base));
      var projs = (d && d.projects) || [];
      if (!projs.length) {
        $('matchCard').style.display = 'none';
        alert('工作台未找到匹配项目: ' + base);
        return;
      }
      // 取最相近的
      var best = projs[0];
      state.wbProject = best;
      $('wbName').textContent = best.name;
      $('wbStatus').textContent = best.custom_status || '未设置';
      var eps = best.current_episodes || 0, total = best.total_episodes || 0;
      $('wbEp').textContent = eps + ' / ' + total + ' 集';
      $('matchCard').style.display = '';
      hint.textContent = '匹配到工作台项目（若有多个，取第一个）';
    } catch (e) {
      alert('查找失败: ' + e.message);
    }
  }

  // ---------- 标记剪辑完成（→ 审核中） ----------
  async function markDone() {
    if (!state.wbProject) { await findInWorkbench(); }
    if (!state.wbProject) return;
    var name = state.wbProject.name;
    if (!confirm('将工作台项目「' + name + '」状态设为「审核中」（剪辑完成），继续？')) return;
    try {
      var d = await wbFetch('/api/project/' + encodeURIComponent(name) + '/custom_status', 'POST', { custom_status: '审核中' });
      if (d && d.ok) {
        alert('✅ 已标记「' + name + '」为审核中');
        state.wbProject.custom_status = '审核中';
        $('wbStatus').textContent = '审核中';
      } else { alert('标记失败: ' + ((d && d.message) || '未知')); }
    } catch (e) { alert('标记失败: ' + e.message); }
  }

  // ---------- 更新当前集数 ----------
  async function syncEpisodes() {
    if (!state.wbProject) { await findInWorkbench(); }
    if (!state.wbProject) return;
    var name = state.wbProject.name;
    var ep = (state.prInfo && state.prInfo.activeEp) || 0;
    if (!ep) {
      var input = prompt('未从当前序列解析出集号，请输入集号:', '');
      if (!input) return;
      ep = parseInt(input, 10) || 0;
    }
    try {
      var d = await wbFetch('/api/project/' + encodeURIComponent(name) + '/set_episodes', 'POST', { current: ep });
      if (d && d.ok) {
        alert('✅ 已更新「' + name + '」当前集数为 ' + d.current_episodes + ' 集');
        $('wbEp').textContent = d.current_episodes + ' / ' + d.total_episodes + ' 集';
      } else { alert('更新失败: ' + ((d && d.message) || '未知')); }
    } catch (e) { alert('更新失败: ' + e.message); }
  }

  // ---------- 初始化 ----------
  function init() {
    loadConfig();
    $('btnConnect').addEventListener('click', connect);
    $('btnRefreshPr').addEventListener('click', readPremiereProject);
    $('btnFind').addEventListener('click', findInWorkbench);
    $('btnMarkDone').addEventListener('click', markDone);
    $('btnSyncEp').addEventListener('click', syncEpisodes);
    // 自动读取 Premiere 项目
    readPremiereProject();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
