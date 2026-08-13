// 成片状态 + 刷新 + 渲染 + 导航 + 选择
// ===== 成片预览状态 =====
var _deliverablesState = {
    projectName: null,
    mode: 'auto',
    subpath: '',
    files: [],
    folders: [],
    breadcrumbs: [],
    selected: {},
    selectedFolders: {},
    running: false
};

function openDeliverablesModal(projectName, forceMode){
    _deliverablesState.projectName = projectName;
    _deliverablesState.mode = forceMode || 'auto';
    _deliverablesState.subpath = '';
    _deliverablesState.selected = {};
    _deliverablesState.selectedFolders = {};
    var modal = document.getElementById('detailModal');
    if(modal){ modal.classList.add('active'); }
    refreshDeliverablesList();
}

async function refreshDeliverablesList(){
    var name = _deliverablesState.projectName;
    var content = document.getElementById('detailContent');
    if(content){
        content.innerHTML = '<div style="padding:40px;text-align:center;color:#86868b">⏳ 扫描成片目录...</div>';
    }
    try{
        var mode = _deliverablesState.mode;
        if(mode === 'auto'){
            try{
                var pinfo = await api('GET', '/api/project/' + encodeURIComponent(name));
                var proj = pinfo.project || pinfo;
                var st = proj.custom_status || '';
                mode = (st === '修改中') ? 'revising' : 'editing';
            }catch(_){ mode = 'editing'; }
        }
        _deliverablesState.mode = mode;

        var url = '/api/output_files/' + encodeURIComponent(name) + '?mode=' + encodeURIComponent(mode);
        if(_deliverablesState.subpath) url += '&subpath=' + encodeURIComponent(_deliverablesState.subpath);

        var resp = await api('GET', url);

        if(Array.isArray(resp)){
            _deliverablesState.files = resp;
            _deliverablesState.folders = [];
            _deliverablesState.breadcrumbs = [];
        } else {
            _deliverablesState.files = resp.files || [];
            _deliverablesState.folders = resp.folders || [];
            _deliverablesState.breadcrumbs = resp.breadcrumbs || [];

        }
        renderDeliverablesModal();
    }catch(e){
        console.error("[deliverables]", e);
        var c2 = document.getElementById('detailContent');
        if(c2) c2.innerHTML = '<div style="padding:40px;text-align:center;color:#ff3b30">❌ 加载失败: ' + e.message + '</div>';
    }
}

// === 进入修改子文件夹 ===
function navDelivFolder(subpath){
  var cur = _deliverablesState.subpath ? _deliverablesState.subpath + '/' + subpath : subpath;
  _deliverablesState.subpath = cur;
  refreshDeliverablesList();
}

// === 导航到指定面包屑层级 ===
function navDelivTo(subpath){
  _deliverablesState.subpath = subpath || '';
  refreshDeliverablesList();
}

function switchDelivMode(projectName, newMode){
  _deliverablesState.mode = newMode;
  _deliverablesState.subpath = '';
  refreshDeliverablesList();
}

function _fmtSize(bytes){
  if(bytes < 1024) return bytes + ' B';
  if(bytes < 1024*1024) return (bytes/1024).toFixed(1) + ' KB';
  if(bytes < 1024*1024*1024) return (bytes/1024/1024).toFixed(1) + ' MB';
  return (bytes/1024/1024/1024).toFixed(2) + ' GB';
}

function _extractEpNum(filename){
  var m;
  // 1.mp4 / 01.mp4
  m = filename.match(/^(\d+)/);
  if(m) return parseInt(m[1], 10);
  // 第1集 / 第01集
  m = filename.match(/第\s*(\d+)\s*集/);
  if(m) return parseInt(m[1], 10);
  // EP01 / ep1 / Ep01
  m = filename.match(/[Ee][Pp][\s_-]*(\d+)/);
  if(m) return parseInt(m[1], 10);
  // S01E01 取 E 后面
  m = filename.match(/[Ee](\d+)/);
  if(m) return parseInt(m[1], 10);
  return null;
}

function renderDeliverablesModal(){
  var content = $('detailContent');
  var name = _deliverablesState.projectName;
  var files = _deliverablesState.files || [];
  var folders = _deliverablesState.folders || [];

  if(files.length === 0 && folders.length === 0){
    var curMode = _deliverablesState.mode || 'editing';
    var isRevising = curMode === 'revising';
    var title = isRevising ? '📝 修改文件夹' : '🎬 成片输出详情';
    var emptyText = isRevising
      ? '📭 该项目还没有修改文件夹<br><span style="font-size:12px;color:#a1a1a6">请先设状态为「修改中」，或点下方按钮切成片模式</span>'
      : '📭 组内NAS 01上映单集版 目录中暂时没有找到视频文件';
    var switchBtn = isRevising
      ? '<button class="btn btn-sm" style="background:#0071e3;color:#fff" onclick="switchDelivMode(\'' + htm(name) + '\', \'editing\')">🎬 看成片</button>'
      : '';
    content.innerHTML =
      '<div style="padding:24px">'
        + '<div style="font-size:15px;font-weight:600;margin-bottom:16px">' + title + '</div>'
        + '<div style="padding:40px;text-align:center;color:#86868b;border:2px dashed #e5e5ea;border-radius:12px">'
          + emptyText
          + '<div style="margin-top:12px;display:flex;gap:8px;justify-content:center">'
            + switchBtn
            + '<button class="btn btn-sm" onclick="openSmart(\'' + htm(name) + '\', \'dest\')">📁 打开成片目录</button>'
            + '<button class="btn btn-sm" onclick="$(' + "'" + 'detailModal' + "'" + ').classList.remove(' + "'" + 'active' + "'" + ')">关闭</button>'
          + '</div>'
        + '</div>'
      + '</div>';
    return;
  }

  // 统计
  var totalBytes = files.reduce(function(s, f){ return s + (f.size||0); }, 0);
  var vids = files.filter(function(f){ var e = (f.ext||'').toLowerCase(); return ['.mp4','.mov','.mkv','.avi','.webm'].indexOf(e) >= 0; });
  var epNums = files.map(function(f){ return _extractEpNum(f.name); }).filter(function(n){ return n !== null; });
  var epMin = epNums.length ? Math.min.apply(null, epNums) : '-';
  var epMax = epNums.length ? Math.max.apply(null, epNums) : '-';

  // 全选 checkbox 状态
  var allSelected = files.length > 0 && files.every(function(f){ return _deliverablesState.selected[f.name]; });

  // 文件行
  var rows = files.map(function(f, idx){
    var ep = _extractEpNum(f.name);
    var epHtml = (ep !== null)
      ? '<span class="deliv-ep-badge">第' + String(ep).padStart(2,'0') + '集</span>'
      : '<span style="color:#c5221f;font-size:11px">未识别</span>';
    var checked = _deliverablesState.selected[f.name] ? 'checked' : '';
    var rowId = 'deliv-row-' + idx;
    var ext = (f.ext||'').toLowerCase();
    var isVideo = ['.mp4','.mov','.mkv','.avi','.webm'].indexOf(ext) >= 0;
    var icon = isVideo ? '🎥' : '📄';
    var btnClass = isVideo ? 'btn-primary' : '';

    return '<tr id="' + rowId + '">'
      + '<td class="deliv-td-ck"><input type="checkbox" ' + checked + ' data-deliv-ck="' + htm(f.name) + '" onchange="toggleDelivRow(\'' + htm(f.name).replace(/'/g,"\'") + '\')"></td>'
      + '<td class="deliv-td-ep">' + epHtml + '</td>'
      + '<td class="deliv-td-name" title="' + htm(f.path) + '">' + icon + ' ' + htm(f.name) + '</td>'
      + '<td class="deliv-td-size">' + _fmtSize(f.size||0) + '</td>'
      + '<td class="deliv-td-time">' + htm(f.mtime||'') + '</td>'
      + '<td class="deliv-td-actions">'
        + '<button class="btn btn-sm ' + btnClass + '" onclick="previewDelivFile(\'' + htm(name).replace(/'/g,"\'") + '\', \'' + htm(f.name).replace(/'/g,"\'") + '\')">▶ 预览</button> '
        + '<button class="btn btn-sm" onclick="deliverOne(\'' + htm(name).replace(/'/g,"\'") + '\', \'' + htm(f.name).replace(/'/g,"\'") + '\', ' + idx + ')">⚡ 回传</button>'
      + '</td>'
    + '</tr>';
  }).join('');

  // 选中计数
  var selCount = Object.values(_deliverablesState.selected).filter(Boolean).length;

  content.innerHTML =
    '<div class="deliv-modal-wrap">'
      // Header
      + '<div class="deliv-header">'
        + '<div class="deliv-title">🎬 成片输出详情</div>'
        + '<span class="deliv-close" onclick="$(' + "'" + 'detailModal' + "'" + ').classList.remove(' + "'" + 'active' + "'" + ')">×</span>'
      + '</div>'

            // Breadcrumbs (revising 模式)
      + (_deliverablesState.mode === 'revising' && _deliverablesState.breadcrumbs.length > 0 ? (function(){
          var crumbs = _deliverablesState.breadcrumbs.map(function(b, idx){
            var clickable = idx < _deliverablesState.breadcrumbs.length - 1;
            var sp = _deliverablesState.breadcrumbs.slice(0, idx+1).map(function(x){ return x.path; }).filter(Boolean).join('/');
            var safeSp = sp.replace(/'/g, "\\'");
            return (clickable
              ? '<a href="javascript:void(0)" onclick="navDelivTo(\'' + safeSp + '\')" style="color:#0071e3;text-decoration:none">' + htm(b.name) + '</a>'
              : '<span style="color:#1d1d1f;font-weight:600">' + htm(b.name) + '</span>');
          }).join(' <span style="color:#86868b">/</span> ');
          return '<div style="padding:10px 16px;background:#f5f5f7;border-bottom:1px solid #e5e5ea;font-size:12px">' + crumbs + '</div>';
        })() : '')

// 修改模式提示 banner
      + (_deliverablesState.mode === 'revising'
        ? '<div style="padding:8px 16px;background:#fff3cd;color:#856404;border-bottom:1px solid #ffeaa7;font-size:12px">📝 当前是 <b>修改中</b> 状态，正在查看修改文件夹里的视频</div>'
        : '')

        // Folders 列表 (revising 模式根目录，带 checkbox 勾选整文件夹回传)
      + (_deliverablesState.folders.length > 0 ? (function(){
          var mode = _deliverablesState.mode;
          var selFolders = _deliverablesState.selectedFolders || {};
          var folderSelectable = (mode === 'revising' && !_deliverablesState.subpath);
          var allFoldersSel = folderSelectable && _deliverablesState.folders.length > 0 && _deliverablesState.folders.every(function(f){ return selFolders[f.name]; });
          var folderRows = _deliverablesState.folders.map(function(f){
            var checked = selFolders[f.name] ? 'checked' : '';
            var cbHtml = folderSelectable
              ? '<input type="checkbox" ' + checked + ' onclick="event.stopPropagation();toggleDelivFolderSel(\'' + htm(f.name).replace(/'/g,"\\'") + '\')" style="width:16px;height:16px">'
              : '';
            var selBg = selFolders[f.name] ? 'background:#e8f4fd;' : '';
            return '<div style="display:flex;align-items:center;gap:12px;padding:12px 16px;border-bottom:1px solid #f0f0f0;cursor:pointer;' + selBg + '" onclick="navDelivFolder(\'' + htm(f.path).replace(/'/g,"\\'") + '\')">'
              + cbHtml
              + '<span style="font-size:24px">📁</span>'
              + '<div style="flex:1">'
                + '<div style="font-weight:600;font-size:14px">' + htm(f.name) + '</div>'
                + '<div style="font-size:11px;color:#86868b">' + (folderSelectable ? '点击进入 · 勾选整文件夹回传' : '点击进入查看修改文件') + '</div>'
              + '</div>'
              + '<span style="color:#86868b">▶</span>'
            + '</div>';
          }).join('');
          var selFolderCount = Object.values(selFolders).filter(Boolean).length;
          var headerHtml = folderSelectable
            ? '<div style="display:flex;align-items:center;gap:8px;padding:8px 16px;background:#fafafa;border-bottom:1px solid #e5e5ea;font-size:12px">'
                + '<input type="checkbox" ' + (allFoldersSel?'checked':'') + ' onchange="toggleAllDelivFolders(this.checked)" style="width:14px;height:14px">'
                + '<b>全选文件夹</b>'
                + '<span style="color:#86868b">已选文件夹 ' + selFolderCount + ' / ' + _deliverablesState.folders.length + '</span>'
                + '<span style="flex:1"></span>'
                + '<button class="btn btn-sm btn-primary" onclick="deliverFolders()" style="padding:2px 10px;font-size:11px"' + (selFolderCount===0?' disabled':'') + '>⚡ 回传选中文件夹</button>'
              + '</div>'
            : '';
          return '<div style="border:1px solid #e5e5ea;border-radius:8px;margin:12px 16px;overflow:hidden">' + headerHtml + folderRows + '</div>';
        })() : '')

// Stats banner
      + '<div class="deliv-stats">'
        + '<div class="deliv-stat-item"><b>' + files.length + '</b> 个文件</div>'
        + '<div class="deliv-stat-item"><b>' + _fmtSize(totalBytes) + '</b> 总大小</div>'
        + '<div class="deliv-stat-item"><b>' + vids.length + '</b> 个视频</div>'
        + '<div class="deliv-stat-item">集号范围 <b>' + epMin + ' ~ ' + epMax + '</b></div>'
      + '</div>'

      // Toolbar
      + '<div class="deliv-toolbar">'
        + '<label class="deliv-all-label"><input type="checkbox" ' + (allSelected?'checked':'') + ' onchange="toggleAllDeliv(this.checked)"> 全选</label>'
        + '<span style="margin-left:16px;color:#6b6b70;font-size:12px">已选 <b style="color:#0071e3">' + selCount + '</b> / ' + files.length + '</span>'
        + '<div style="flex:1"></div>'
        + '<button class="btn btn-sm" onclick="openSmart(\'' + htm(name).replace(/'/g,"\'") + '\', \'dest\')">📁 打开成片目录</button>'
        + '<button class="btn btn-sm" onclick="refreshDeliverablesList()">🔄 刷新列表</button>'
        + '<button class="btn btn-sm btn-primary" onclick="deliverBatch()" ' + (selCount===0||_deliverablesState.running?'disabled':'') + '>⚡ 批量回传 (' + selCount + ')</button>'
      + '</div>'

      // Table
      + '<div class="deliv-table-wrap">'
        + '<table class="deliv-table">'
          + '<thead><tr>'
            + '<th style="width:36px"></th>'
            + '<th style="width:80px">集号</th>'
            + '<th>文件名</th>'
            + '<th style="width:90px">大小</th>'
            + '<th style="width:130px">修改时间</th>'
            + '<th style="width:170px">操作</th>'
          + '</tr></thead>'
          + '<tbody>' + rows + '</tbody>'
        + '</table>'
      + '</div>'
    + '</div>';
}

function toggleDelivRow(filename){
  _deliverablesState.selected[filename] = !_deliverablesState.selected[filename];
  renderDeliverablesModal();
}

function toggleAllDeliv(checked){
  _deliverablesState.selected = {};
  if(checked){
    (_deliverablesState.files||[]).forEach(function(f){ _deliverablesState.selected[f.name] = true; });
  }
  renderDeliverablesModal();
}

function toggleDelivFolderSel(folderName){
  _deliverablesState.selectedFolders = _deliverablesState.selectedFolders || {};
  _deliverablesState.selectedFolders[folderName] = !_deliverablesState.selectedFolders[folderName];
  renderDeliverablesModal();
}

function toggleAllDelivFolders(checked){
  _deliverablesState.selectedFolders = {};
  if(checked){
    (_deliverablesState.folders||[]).forEach(function(f){ _deliverablesState.selectedFolders[f.name] = true; });
  }
  renderDeliverablesModal();
}

