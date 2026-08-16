// ====== 工具箱：人名条识别插件 前端逻辑 ======
// API 走全局 api() 封装（自动携带 X-API-KEY）。
//
// 说明：桌面版用 pywebview 内嵌浏览器，对 <a download>/window.open 下载支持差。
//   • 打开：后端 os.startfile 本机直接开 Excel
//   • 保存到本地：后端弹系统原生"另存为"对话框，选目录后复制保存

function npKey() { return window.__API_KEY__ || ''; }

function npFileUrl(name) {
  var url = '/api/nameplate/output/' + encodeURIComponent(name);
  var key = npKey();
  if (key) url += (url.indexOf('?') >= 0 ? '&' : '?') + 'key=' + encodeURIComponent(key);
  return url;
}

// 折叠/展开工具卡片（新版工具箱，基于 .open 类 + max-height 过渡）
function tbToggle(headEl) {
  var card = headEl && headEl.closest('.tb-card');
  if (!card) return;
  var isOpen = card.classList.contains('open');
  // 展开当前卡片时收起其他卡片
  var all = document.querySelectorAll('.tb-card.open');
  all.forEach(function(c){ if(c !== card) c.classList.remove('open'); });
  card.classList.toggle('open', !isOpen);
}

// 按 id 展开某张卡片（底部"展开/使用"按钮用）
function npToggleBy(id) {
  var card = document.getElementById(id);
  if (!card) return;
  var all = document.querySelectorAll('.tb-card.open');
  all.forEach(function(c){ if(c !== card) c.classList.remove('open'); });
  card.classList.toggle('open');
}

// 打开：后端 os.startfile 本机直接开 Excel（桌面版最可靠）
async function npOpen(name) {
  try {
    var d = await api('POST', '/api/nameplate/open/' + encodeURIComponent(name));
    if (d && d.ok) { toast('已用 Excel 打开', 'success'); }
    else { toast((d && d.message) || '打开失败', 'error'); }
  } catch (e) {
    toast('打开失败: ' + e.message, 'error');
  }
}

// 保存到本地：后端弹系统"另存为"对话框
async function npSaveAs(name) {
  toast('请在弹出窗口中选择保存位置...', 'info');
  try {
    var d = await api('POST', '/api/nameplate/save_as/' + encodeURIComponent(name));
    if (d && d.ok) {
      if (d.pending) { toast(d.message || '已弹出保存窗口', 'info'); }
      else { toast(d.message || '已保存', 'success'); }
    } else {
      toast((d && d.message) || '保存失败', 'error');
    }
  } catch (e) {
    toast('保存请求失败: ' + e.message, 'error');
  }
}

// 启动拆集工具 GUI
async function dtLaunch() {
  var statusEl = document.getElementById('dtStatus');
  if (statusEl) statusEl.textContent = '⏳ 正在启动拆集工具窗口...';
  try {
    var d = await api('POST', '/api/dramatool/launch');
    if (d && d.ok) {
      if (statusEl) statusEl.textContent = '✅ ' + (d.message || '已启动');
      toast('已启动拆集工具，请在弹出的窗口中操作', 'success');
    } else {
      if (statusEl) statusEl.textContent = '❌ ' + ((d && d.message) || '启动失败');
      toast((d && d.message) || '启动失败', 'error');
    }
  } catch (e) {
    if (statusEl) statusEl.textContent = '❌ ' + e.message;
    toast('启动请求失败: ' + e.message, 'error');
  }
}

function loadNameplateTab() { loadNameplateFiles(); }

// 启动提成工具 GUI
async function cmLaunch() {
  var statusEl = document.getElementById('cmStatus');
  if (statusEl) statusEl.textContent = '⏳ 正在启动提成工具窗口...';
  try {
    var d = await api('POST', '/api/commission/launch');
    if (d && d.ok) {
      if (statusEl) statusEl.textContent = '✅ ' + (d.message || '已启动');
      toast('已启动提成工具，请在弹出的窗口中操作', 'success');
    } else {
      if (statusEl) statusEl.textContent = '❌ ' + ((d && d.message) || '启动失败');
      toast((d && d.message) || '启动失败', 'error');
    }
  } catch (e) {
    if (statusEl) statusEl.textContent = '❌ ' + e.message;
    toast('启动请求失败: ' + e.message, 'error');
  }
}

async function loadNameplateFiles() {
  var box = document.getElementById('npFiles');
  if (!box) return;
  try {
    var d = await api('GET', '/api/nameplate/files');
    if (!d || !d.ok) { box.innerHTML = '<span style="color:#c0392b">加载失败</span>'; return; }
    var files = d.files || [];
    if (!files.length) { box.innerHTML = '暂无生成结果。上传剧本解析后会自动出现在这里。'; return; }
    var rows = files.map(function (f) {
      var safe = String(f.name).replace(/'/g, "\\'");
      return '<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 4px;border-bottom:1px solid #eee">'
        + '<span>📄 ' + esc(f.name) + ' <small style="color:#999">(' + f.mtime + ', ' + (f.size/1024).toFixed(1) + 'KB)</small></span>'
        + '<span style="display:flex;gap:6px">'
        +   '<button class="btn btn-sm btn-primary" onclick="npOpen(\'' + safe + '\')" title="用 Excel 打开">📂 打开</button>'
        +   '<button class="btn btn-sm" onclick="npSaveAs(\'' + safe + '\')" title="选择保存位置">💾 保存到本地</button>'
        + '</span>'
        + '</div>';
    }).join('');
    box.innerHTML = rows;
  } catch (e) {
    box.innerHTML = '<span style="color:#c0392b">加载失败: ' + esc(e.message) + '</span>';
  }
}

async function npParse() {
  var fileInput = document.getElementById('npFile');
  var statusEl = document.getElementById('npStatus');
  if (!fileInput || !fileInput.files || !fileInput.files.length) {
    toast('请先选择 .docx 剧本文件', 'warning');
    return;
  }
  var file = fileInput.files[0];
  if (!/\.docx$/i.test(file.name)) {
    toast('仅支持 .docx 剧本', 'error');
    return;
  }
  var epInput = document.getElementById('npEpisodes');
  var episodes = (epInput && epInput.value || '').trim();

  statusEl.textContent = '⏳ 解析中（后台执行，完成后自动打开）...';
  var fd = new FormData();
  fd.append('file', file);
  fd.append('episodes', episodes);   // 空字符串 = 全本

  try {
    var d = await api('POST', '/api/nameplate/parse', fd);
    if (d && d.ok) {
      statusEl.textContent = '⏳ ' + (d.message || '解析中...');
      toast('已提交' + (d.scope ? '（' + d.scope + '）' : '') + '解析任务', 'success');
      npWaitForResult(d.expected_output);
    } else {
      statusEl.textContent = '❌ ' + ((d && d.message) || '解析失败');
      toast((d && d.message) || '解析失败', 'error');
    }
  } catch (e) {
    statusEl.textContent = '❌ ' + e.message;
    toast('解析请求失败: ' + e.message, 'error');
  }
}

// 轮询结果生成后自动打开
function npWaitForResult(expected, tries) {
  tries = tries || 0;
  if (tries > 400) {   // 最多等 ~200s
    document.getElementById('npStatus').textContent = '⏳ 等待超时，请手动刷新结果列表';
    return;
  }
  api('GET', '/api/nameplate/files').then(function (d) {
    var files = (d && d.files) || [];
    var hit = expected ? files.find(function (f) { return f.name === expected; })
                       : (files.length ? files[0] : null);
    if (hit) {
      document.getElementById('npStatus').textContent = '✅ 解析完成，正在打开...';
      loadNameplateFiles();
      npOpen(hit.name);   // 自动用 Excel 打开
      setTimeout(function () {
        var el = document.getElementById('npStatus');
        if (el) el.textContent = '✅ 已完成（可在列表重新打开/保存到本地）';
      }, 4000);
      return;
    }
    setTimeout(function () { npWaitForResult(expected, tries + 1); }, 500);
  }).catch(function () {
    setTimeout(function () { npWaitForResult(expected, tries + 1); }, 500);
  });
}

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
