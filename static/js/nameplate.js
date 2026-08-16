// ====== 人名条识别插件 前端逻辑 (plugins/nameplate) ======
// API 走全局 api() 封装（自动携带 X-API-KEY）。

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
      var href = '/api/nameplate/output/' + encodeURIComponent(f.name);
      return '<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 4px;border-bottom:1px solid #eee">'
        + '<span>📄 ' + esc(f.name) + ' <small style="color:#999">(' + f.mtime + ', ' + (f.size/1024).toFixed(1) + 'KB)</small></span>'
        + '<a class="btn btn-primary btn-sm" href="' + href + '" download>⬇️ 下载</a>'
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
  var episodes = parseInt(document.getElementById('npEpisodes') && document.getElementById('npEpisodes').value, 10) || 30;

  statusEl.textContent = '⏳ 解析中（后台执行，可稍后刷新结果列表）...';
  var fd = new FormData();
  fd.append('file', file);
  fd.append('episodes', String(episodes));

  try {
    var d = await api('POST', '/api/nameplate/parse', fd);
    if (d && d.ok) {
      statusEl.textContent = '✅ ' + (d.message || '已开始解析');
      toast('解析任务已提交', 'success');
      // 延迟刷新结果列表（给后台解析留时间）
      setTimeout(loadNameplateFiles, 1500);
    } else {
      statusEl.textContent = '❌ ' + ((d && d.message) || '解析失败');
      toast((d && d.message) || '解析失败', 'error');
    }
  } catch (e) {
    statusEl.textContent = '❌ ' + e.message;
    toast('解析请求失败: ' + e.message, 'error');
  }
}

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
