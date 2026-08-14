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
            _deliverablesState.deliveryCheck = resp.delivery_check || null;
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
      : '<button class="btn btn-sm" style="background:#0071e3;color:#fff" onclick="switchDelivMode(\'' + htm(name) + '\', \'revising\')">✏️ 看修改</button>';
    var openSrcBtn = isRevising
      ? '<button class="btn btn-sm" onclick="openSmart(\'' + htm(name) + '\', \'revising\')">📁 打开修改目录</button>'
      : '<button class="btn btn-sm" onclick="openSmart(\'' + htm(name) + '\', \'group_output\')">📁 打开成片目录</button>';
    content.innerHTML =
      '<div style="padding:24px">'
        + '<div style="font-size:15px;font-weight:600;margin-bottom:16px">' + title + '</div>'
        + '<div style="padding:40px;text-align:center;color:#86868b;border:2px dashed #e5e5ea;border-radius:12px">'
          + emptyText
          + '<div style="margin-top:12px;display:flex;gap:8px;justify-content:center">'
            + switchBtn
            + openSrcBtn
            + '<button class="btn btn-sm" onclick="openSmart(\'' + htm(name) + '\', \'delivery\')">📦 打开交付目录</button>'
            + '<button class="btn btn-sm" onclick="$(' + "'" + 'detailModal' + "'" + ').classList.remove(' + "'" + 'active' + "'" + ')">关闭</button>'
          + '</div>'
        + '</div>'
      + '</div>';
    return;
  }

  // 回传状态统计
  var deliveredCount = files.filter(function(f){ return f.delivered; }).length;
  var mismatchCount = files.filter(function(f){ return f.delivery_status === 'size_mismatch'; }).length;
  var pendingCount = files.length - deliveredCount;

  // 过滤
  var filt = _deliverablesState.delivFilter || 'all';
  var filteredFiles = files;
  if(filt === 'pending') filteredFiles = files.filter(function(f){ return !f.delivered || f.delivery_status === 'size_mismatch'; });
  else if(filt === 'delivered') filteredFiles = files.filter(function(f){ return f.delivered && f.delivery_status !== 'size_mismatch'; });

  // 统计
  var totalBytes = files.reduce(function(s, f){ return s + (f.size||0); }, 0);
  var vids = files.filter(function(f){ var e = (f.ext||'').toLowerCase(); return ['.mp4','.mov','.mkv','.avi','.webm'].indexOf(e) >= 0; });
  var epNums = files.map(function(f){ return _extractEpNum(f.name); }).filter(function(n){ return n !== null; });
  var epMin = epNums.length ? Math.min.apply(null, epNums) : '-';
  var epMax = epNums.length ? Math.max.apply(null, epNums) : '-';

  // 全选 checkbox 状态（基于过滤后的文件）
  var allSelected = filteredFiles.length > 0 && filteredFiles.every(function(f){ return _deliverablesState.selected[f.name]; });

  // 文件行（基于过滤后的文件, 但 idx 用原 idx 保证 previewDelivFile 和 deliverOne 正常）
  var rows = filteredFiles.map(function(f, idx){
    var realIdx = files.indexOf(f);
    var ep = _extractEpNum(f.name);
    var epHtml = (ep !== null)
      ? '<span class="deliv-ep-badge">第' + String(ep).padStart(2,'0') + '集</span>'
      : '<span style="color:#c5221f;font-size:11px">未识别</span>';
    var checked = _deliverablesState.selected[f.name] ? 'checked' : '';
    var rowId = 'deliv-row-' + realIdx;
    var ext = (f.ext||'').toLowerCase();
    var isVideo = ['.mp4','.mov','.mkv','.avi','.webm'].indexOf(ext) >= 0;
    var icon = isVideo ? '🎥' : '📄';
    var btnClass = isVideo ? 'btn-primary' : '';

    // 回传状态 badge
    var status = f.delivery_status || (f.delivered ? 'delivered' : 'pending');
    var statusBadge = '';
    var rowBg = '';
    if(status === 'delivered'){
      statusBadge = '<span style="display:inline-flex;align-items:center;gap:2px;padding:1px 8px;border-radius:10px;background:#d4edda;color:#155724;font-size:11px">✅ 已回传</span>';
      rowBg = 'background:#f9fafb';
    } else if(status === 'size_mismatch'){
      statusBadge = '<span style="display:inline-flex;align-items:center;gap:2px;padding:1px 8px;border-radius:10px;background:#fff3cd;color:#856404;font-size:11px">⚠️ 大小不符</span>';
      rowBg = 'background:#fff9e6';
    } else {
      statusBadge = '<span style="display:inline-flex;align-items:center;gap:2px;padding:1px 8px;border-radius:10px;background:#f8d7da;color:#721c24;font-size:11px">❌ 未回传</span>';
      rowBg = 'background:#fff5f5';
    }

    return '<tr id="' + rowId + '" style="' + rowBg + '">'
      + '<td class="deliv-td-ck"><input type="checkbox" ' + checked + ' data-deliv-ck="' + htm(f.name) + '" onchange="toggleDelivRow(\'' + htm(f.name).replace(/'/g,"\'") + '\')"></td>'
      + '<td class="deliv-td-ep">' + epHtml + '</td>'
      + '<td class="deliv-td-name" title="' + htm(f.path) + '">' + icon + ' ' + htm(f.name) + '</td>'
      + '<td class="deliv-td-size">' + _fmtSize(f.size||0) + '</td>'
      + '<td style="font-size:12px">' + statusBadge + '</td>'
      + '<td class="deliv-td-time">' + htm(f.mtime||'') + '</td>'
      + '<td class="deliv-td-actions">'
        + '<button class="btn btn-sm ' + btnClass + '" onclick="previewDelivFile(\'' + htm(name).replace(/'/g,"\'") + '\', \'' + htm(f.name).replace(/'/g,"\'") + '\')">▶ 预览</button> '
        + '<button class="btn btn-sm" onclick="deliverOne(\'' + htm(name).replace(/'/g,"\'") + '\', \'' + htm(f.name).replace(/'/g,"\'") + '\', ' + realIdx + ')">⚡ 回传</button>'
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
      + ((_deliverablesState.mode === 'revising' || _deliverablesState.mode === 'delivery') && _deliverablesState.breadcrumbs.length > 0 ? (function(){
          // 在面包屑最前面加一个显眼的"返回根目录"按钮
          var crumbHtml = '<button onclick="navDelivTo()" style="margin-right:8px;padding:2px 8px;background:#fff;border:1px solid #e5e5ea;border-radius:4px;cursor:pointer;font-size:11px">⬅ 返回根目录</button>';
          var crumbs = _deliverablesState.breadcrumbs.map(function(b, idx){
            var clickable = idx < _deliverablesState.breadcrumbs.length - 1;
            var sp = _deliverablesState.breadcrumbs.slice(0, idx+1).map(function(x){ return x.path; }).filter(Boolean).join('/');
            var safeSp = sp.replace(/'/g, "\\'");
            return (clickable
              ? '<a href="javascript:void(0)" onclick="navDelivTo(\'' + safeSp + '\')" style="color:#0071e3;text-decoration:none">' + htm(b.name) + '</a>'
              : '<span style="color:#1d1d1f;font-weight:600">' + htm(b.name) + '</span>');
          }).join(' <span style="color:#86868b">/</span> ');
          return '<div style="padding:10px 16px;background:#f5f5f7;border-bottom:1px solid #e5e5ea;font-size:12px;display:flex;align-items:center">' + crumbHtml + crumbs + '</div>';
        })() : '')

// 修改模式提示 banner
      + (_deliverablesState.mode === 'revising'
        ? '<div style="padding:8px 16px;background:#fff3cd;color:#856404;border-bottom:1px solid #ffeaa7;font-size:12px">📝 当前是 <b>修改中</b> 状态，正在查看修改文件夹里的视频</div>'
        : (_deliverablesState.mode === 'delivery'
           ? (function(){
                var dc = _deliverablesState.deliveryCheck;
                if(!dc || !dc.base_exists){
                  return '<div style="padding:8px 16px;background:#d4edda;color:#155724;border-bottom:1px solid #c3e6cb;font-size:12px">📦 当前查看 <b>000交付</b> 文件夹 — 尚未创建交付目录，进入后可查看子文件夹</div>';
                }
                if(dc.all_ok){
                  var okCount = dc.folders.length;
                  var safeName = htm(name).replace(/'/g,"\\'");
                  return '<div style="padding:10px 16px;background:#d4edda;color:#155724;border-bottom:1px solid #c3e6cb;font-size:13px;font-weight:600">✅ 交付文件已完成（' + okCount + ' 个文件夹全部齐套）— 请进行下一步质检</div>'
                    + '<div style="padding:8px 16px;background:#f0f8f0;border-bottom:1px solid #c3e6cb;font-size:12px">'
                    + dc.folders.map(function(f){
                        return '<span style="display:inline-block;margin-right:12px;margin-bottom:4px">✅ ' + htm(f.name) + ' (' + f.actual + '/' + f.expected + ')</span>';
                      }).join('')
                    + '</div>'
                    + '<div style="padding:14px 16px;background:#e8f5e9;border-bottom:1px solid #c3e6cb;display:flex;gap:10px;align-items:center">'
                    + '<button onclick="delivGoQA(\'' + safeName + '\')" style="padding:9px 24px;font-size:14px;font-weight:600;background:#2E7D32;color:#fff;border:none;border-radius:6px;cursor:pointer;box-shadow:0 2px 6px rgba(46,125,50,0.3)">🔍 立即质检</button>'
                    + '<button onclick="delivMarkQA(\'' + safeName + '\')" style="padding:9px 16px;font-size:13px;background:#fff;border:1px solid #2E7D32;color:#2E7D32;border-radius:6px;cursor:pointer">⚙️ 标记「待质检」</button>'
                    + '<button onclick="$(\'detailModal\').classList.remove(\'active\')" style="margin-left:auto;padding:9px 16px;font-size:12px;background:transparent;border:none;color:#6b6b70;cursor:pointer">关闭预览</button>'
                    + '</div>';
                }
                // 不齐套 — 显示详细缺失情况
                var bad = dc.folders.filter(function(f){ return !f.ok; });
                var good = dc.folders.filter(function(f){ return f.ok; });
                var header = '<div style="padding:10px 16px;background:#fff3cd;color:#856404;border-bottom:1px solid #ffeaa7;font-size:13px;font-weight:600">⚠️ 交付文件不齐套（共 ' + dc.folders.length + ' 个文件夹，缺 ' + bad.length + ' 个）</div>';
                var gridHtml = '<div style="padding:8px 16px;background:#fffdf0;border-bottom:1px solid #ffeaa7;font-size:12px;display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:6px 16px">';
                dc.folders.forEach(function(f){
                  var color = f.ok ? '#2E7D32' : '#c5221f';
                  var emoji = f.ok ? '✅' : '❌';
                  var label = f.ok
                    ? (f.actual + '/' + f.expected)
                    : (f.actual + '/' + f.expected + ' 缺 ' + Math.max(0, f.expected - f.actual));
                  gridHtml += '<div style="display:flex;align-items:center;gap:6px">'
                    + '<span>' + emoji + '</span>'
                    + '<span style="color:#1d1d1f">' + htm(f.name) + '</span>'
                    + '<span style="color:' + color + ';font-weight:600;margin-left:auto">' + label + '</span>'
                    + '</div>';
                });
                gridHtml += '</div>';
                return header + gridHtml;
              })()
           : ''))

        // Folders 列表 (revising 模式根目录，带 checkbox 勾选整文件夹回传)
      + (_deliverablesState.folders.length > 0 ? (function(){
          var _m = _deliverablesState.mode;
          var selFolders = _deliverablesState.selectedFolders || {};
          var _sp = _deliverablesState.subpath || ''; var _spDeep = _sp.includes('\\') || _sp.includes('/'); var folderSelectable = ((_m === 'revising' && !_sp) || (_m === 'delivery' && _sp && !_spDeep));
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
                + '<div style="font-size:11px;color:#86868b">' + (folderSelectable ? (_m === 'delivery' ? '点击进入 · 勾选回传到制作部' : '点击进入 · 勾选整文件夹回传') : '点击进入查看') + '</div>'
              + '</div>'
              + '<span style="color:#86868b">▶</span>'
            + '</div>';
          }).join('');
          var selFolderCount = Object.values(selFolders).filter(Boolean).length;
          var headerHtml = folderSelectable
            ? '<div style="display:flex;align-items:center;gap:8px;padding:8px 16px;background:#fafafa;border-bottom:1px solid #e5e5ea;font-size:12px">'
                + '<input type="checkbox" ' + (allFoldersSel?'checked':'') + ' onchange="toggleAllDelivFolders(this.checked)" style="width:14px;height:14px">'
                + '<b>' + (_m === 'delivery' ? '全选交付文件夹' : '全选修改文件夹') + '</b>'
                + '<span style="color:#86868b">已选文件夹 ' + selFolderCount + ' / ' + _deliverablesState.folders.length + '</span>'
                + '<span style="flex:1"></span>'
                + '<button class="btn btn-sm btn-primary" onclick="deliverFolders()" style="padding:2px 10px;font-size:11px"' + (selFolderCount===0?' disabled':'') + '>⚡ ' + (_m === 'delivery' ? '回传到制作部' : '回传选中文件夹') + '</button>'
              + '</div>'
            : '';
          return '<div style="border:1px solid #e5e5ea;border-radius:8px;margin:12px 16px;overflow:hidden">' + headerHtml + folderRows + '</div>';
        })() : '')

// delivery 根目录 — 隐藏文件表格相关
      + ((_deliverablesState.mode === 'delivery' && (_deliverablesState.subpath || '').replace('\\','/').split('/').length <= 1) ? '' : (
        // Stats banner
      '<div class="deliv-stats">'
        + '<div class="deliv-stat-item"><b>' + files.length + '</b> 个文件</div>'
        + '<div class="deliv-stat-item"><b>' + _fmtSize(totalBytes) + '</b> 总大小</div>'
        + '<div class="deliv-stat-item"><b>' + vids.length + '</b> 个视频</div>'
        + '<div class="deliv-stat-item">集号范围 <b>' + epMin + ' ~ ' + epMax + '</b></div>'
        + '<div style="flex:1;min-width:12px"></div>'
        // 回传进度
        + '<div style="display:flex;align-items:center;gap:8px">'
          + '<span style="font-size:12px;color:#6b6b70">回传进度</span>'
          + '<div style="width:140px;height:8px;background:#e5e5ea;border-radius:4px;overflow:hidden">'
            + '<div style="width:' + (files.length ? Math.round(deliveredCount*100/files.length) : 0) + '%;height:100%;background:linear-gradient(90deg,#2E7D32,#27ae60);border-radius:4px;transition:width .3s"></div>'
          + '</div>'
          + '<span style="font-size:12px;font-weight:600;color:' + (deliveredCount===files.length?'#2E7D32':'#86868b') + '">' + deliveredCount + '/' + files.length + '</span>'
          + (mismatchCount ? '<span style="font-size:11px;color:#b58100;background:#fff3cd;padding:1px 6px;border-radius:8px">⚠️'+mismatchCount+'</span>' : '')
        + '</div>'
      + '</div>'

      // Toolbar
      + '<div class="deliv-toolbar">'
        + '<label class="deliv-all-label"><input type="checkbox" ' + (allSelected?'checked':'') + ' onchange="toggleAllDeliv(this.checked)"> 全选</label>'
        + '<span style="margin-left:8px;color:#6b6b70;font-size:12px">已选 <b style="color:#0071e3">' + selCount + '</b> / ' + filteredFiles.length + '</span>'
        // 过滤按钮组
        + '<div style="margin-left:16px;display:flex;border:1px solid #e5e5ea;border-radius:6px;overflow:hidden">'
          + '<button class="btn btn-sm" style="border:none;border-radius:0;padding:4px 10px;font-size:11px;' + (filt==='all'?'background:#0071e3;color:#fff':'background:#fff;color:#6b6b70') + '" onclick="setDelivFilter(\'all\')">全部 ' + files.length + '</button>'
          + '<button class="btn btn-sm" style="border:none;border-radius:0;padding:4px 10px;font-size:11px;' + (filt==='pending'?'background:#c5221f;color:#fff':'background:#fff;color:#6b6b70') + '" onclick="setDelivFilter(\'pending\')">未回传 ' + (files.length-deliveredCount) + '</button>'
          + '<button class="btn btn-sm" style="border:none;border-radius:0;padding:4px 10px;font-size:11px;' + (filt==='delivered'?'background:#2E7D32;color:#fff':'background:#fff;color:#6b6b70') + '" onclick="setDelivFilter(\'delivered\')">已回传 ' + deliveredCount + '</button>'
        + '</div>'
        + '<div style="flex:1"></div>'
        + '<button class="btn btn-sm btn-primary" onclick="openBothDirs()" style="background:#2E7D32">📂 源→交付 (拖文件)</button>'
        + (_deliverablesState.mode === 'revising'
          ? '<button class="btn btn-sm" onclick="openSmart(\'' + htm(name).replace(/'/g,"\'") + '\', \'revising\')">📁 修改目录</button>'
          : '<button class="btn btn-sm" onclick="openSmart(\'' + htm(name).replace(/'/g,"\'") + '\', \'group_output\')">📁 成片目录</button>')
        + '<button class="btn btn-sm" onclick="openSmart(\'' + htm(name).replace(/'/g,"\'") + '\', \'delivery\')">📦 交付目录</button>'
        + '<button class="btn btn-sm" onclick="refreshDeliverablesList()">🔄 刷新</button>'
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
      )
    )
    + '</div>';
}

function toggleDelivRow(filename){
  _deliverablesState.selected[filename] = !_deliverablesState.selected[filename];
  renderDeliverablesModal();
}

function setDelivFilter(filter){
  _deliverablesState.delivFilter = filter;
  renderDeliverablesModal();
}

function toggleAllDeliv(checked){
  var filt = _deliverablesState.delivFilter || 'all';
  var base = _deliverablesState.files || [];
  if(filt === 'pending') base = base.filter(function(f){ return !f.delivered || f.delivery_status === 'size_mismatch'; });
  else if(filt === 'delivered') base = base.filter(function(f){ return f.delivered && f.delivery_status !== 'size_mismatch'; });
  _deliverablesState.selected = {};
  if(checked){
    base.forEach(function(f){ _deliverablesState.selected[f.name] = true; });
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


async function delivGoQA(name){
  document.getElementById('detailModal').classList.remove('active');
  if(typeof qaStartFor === 'function'){
    await qaStartFor(name);
  } else if(typeof switchTab === 'function'){
    switchTab('qa');
    toast('已切换到质检 Tab，请手动选择项目', 'info');
  }
}

async function delivMarkQA(name){
  try{
    await api('POST', '/api/project/' + encodeURIComponent(name) + '/custom_status', {
      custom_status: '待质检'
    });
    toast('✅ 状态已更新为「待质检」', 'success');
    renderDashboard();
    refreshDeliverablesList();
  }catch(e){
    toast('❌ 更新失败: ' + e.message, 'error');
  }
}
