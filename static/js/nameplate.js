// ====== 人名条识别插件 前端逻辑 (plugins/nameplate) ======
// API 走全局 api() 封装（自动携带 X-API-KEY）。
// 下载用 <a href=?key=> 直链，因为原生下载不走 fetch，需把 key 放 query 参数。

function npKey() {
  return window.__API_KEY__ || '';
}

function npFileUrl(name) {
  var url = '/api/nameplate/output/' + encodeURIComponent(name);
  var key = npKey();
  if (key) url += (url.indexOf('?') >= 0 ? '&' : '?') + 'key=' + encodeURIComponent(key);
  return url;
}

// 触发浏览器下载（相当于"直接打开"，本地关联 Excel 会自动打开）
function npTriggerDownload(name) {
  var a = document.createElement('a');
  a.href = npFileUrl(name);
  a.download = name || '';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

function loadNameplateTab() {
  loadNameplateFiles();
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
      var href = npFileUrl(f.name);
      return '<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 4px;border-bottom:1px solid #eee">'
        + '<span>📄 ' + esc(f.name) + ' <small style="color:#999">(' + f.mtime + ', ' + (f.size/1024).toFixed(1) + 'KB)</small></span>'
        + '<span style="display:flex;gap:6px">'
        +   '<button class="btn btn-sm" onclick="npTriggerDownload(\'' + f.name.replace(/'/g, "\\'") + '\')" title="下载/打开">⬇️ 下载</button>'
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
  // 集数：留空 = 全本
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
      // 轮询等待结果生成，完成后自动下载打开
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

// 轮询指定输出文件是否生成，生成后自动下载并刷新列表
function npWaitForResult(expected, tries) {
  tries = tries || 0;
  if (tries > 120) {  // 最多等 ~60s
    document.getElementById('npStatus').textContent = '⏳ 等待超时，请手动刷新结果列表';
    return;
  }
  api('GET', '/api/nameplate/files').then(function (d) {
    var files = (d && d.files) || [];
    if (expected) {
      var hit = files.find(function (f) { return f.name === expected; });
      if (hit) {
        document.getElementById('npStatus').textContent = '✅ 解析完成，正在打开...';
        npTriggerDownload(hit.name);          // 直接打开/下载
        loadNameplateFiles();                 // 刷新结果列表
        setTimeout(function () {
          var el = document.getElementById('npStatus');
          if (el) el.textContent = '✅ 已完成，可直接下载';
        }, 4000);
        return;
      }
    } else if (files.length) {
      // 无预期文件名时，取最新生成的文件
      var latest = files[0];
      document.getElementById('npStatus').textContent = '✅ 解析完成，正在打开...';
      npTriggerDownload(latest.name);
      loadNameplateFiles();
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
