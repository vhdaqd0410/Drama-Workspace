// ===== 事件委托：ep-refresh / ep-deliverables / ep-revising =====
document.addEventListener('click', function(e){
  var refreshBtn = e.target.closest('[data-action="ep-refresh"]');
  if(refreshBtn){
    var pname = refreshBtn.getAttribute('data-project');
    var btn = refreshBtn.getAttribute('data-btn');
    if(pname) refreshProjectStatus(pname, btn==='null'?null:undefined);
    e.preventDefault();
    return;
  }

  var delivBtn = e.target.closest('[data-action="ep-deliverables"]');
  if(delivBtn){
    var pname2 = delivBtn.getAttribute('data-project');
    if(pname2) openDeliverablesModal(pname2, 'editing');
    e.preventDefault();
    return;
  }

  var revBtn = e.target.closest('[data-action="ep-revising"]');
  if(revBtn){
    var pname3 = revBtn.getAttribute('data-project');
    if(pname3) openDeliverablesModal(pname3, 'revising');
    e.preventDefault();
    return;
  }

  var delivBtn = e.target.closest('[data-action="ep-delivery"]');
  if(delivBtn){
    var pname4 = delivBtn.getAttribute('data-project');
    if(pname4) openDeliverablesModal(pname4, 'delivery');
    e.preventDefault();
    return;
  }
});

// ===== 双开目录：同时打开源目录 + 交付目录 =====
function openBothDirs(){
  var name = _deliverablesState.projectName;
  var mode = _deliverablesState.mode || 'editing';
  // 源目录
  var srcWhich = mode === 'revising' ? 'revising' : 'group_output';
  api('POST', '/api/project/' + encodeURIComponent(name) + '/open_folder', { which: srcWhich }).then(function(r){
    if(r.ok) toast('📂 已打开源目录', 'success');
    else toast('源目录: ' + (r.message||''), 'warning');
  }).catch(function(){});
  // 目标交付目录 (稍微延迟避免竞争)
  setTimeout(function(){
    api('POST', '/api/project/' + encodeURIComponent(name) + '/open_folder', { which: 'delivery' }).then(function(r){
      if(r.ok) toast('📂 已打开交付目录 — 直接把文件拖过去就行', 'success');
    }).catch(function(){});
  }, 400);
}

// ===== 文件夹批量回传 =====
async function deliverFolders(){
  var name = _deliverablesState.projectName;
  var sel = Object.keys(_deliverablesState.selectedFolders||{}).filter(function(k){ return _deliverablesState.selectedFolders[k]; });
  if(sel.length === 0){ toast('请先选择文件夹','warning'); return; }

  // 判断是否勾选了 delivery 模式根目录的虚拟"000交付"文件夹
  var mode = _deliverablesState.mode || 'revising';
  var subp = _deliverablesState.subpath || '';
  var isDeliveryRoot = (mode === 'delivery' && !subp);

  // 高危操作二次确认：整目录交付会把整个 000交付 复制到制作部
  if(isDeliveryRoot){
    if(!confirm('⚠️ 确认执行【整目录交付】？\n\n将把项目「' + name + '」的 000交付 整个文件夹复制到制作部NAS对应项目。\n该操作会替换制作部目标目录内容，且完成后项目自动归档。\n\n确认继续？')) return;
  }

  // 在模态框顶部插入进度条
  var progBarId = 'deliv-folder-prog';
  var existing = document.getElementById(progBarId);
  if(existing) existing.remove();
  var modalWrap = document.querySelector('.deliv-modal-wrap');
  if(modalWrap){
    var bar = document.createElement('div');
    bar.id = progBarId;
    bar.style.cssText = 'padding:10px 16px;background:#e8f4fd;border-bottom:1px solid #c7e2fb;font-size:12px;display:flex;align-items:center;gap:10px';
    bar.innerHTML = '<span style="white-space:nowrap">⚡ 文件夹回传</span>'
      + '<div style="flex:1;height:8px;background:#fff;border-radius:4px;overflow:hidden;border:1px solid #c7e2fb"><div class="deliv-folder-fill" style="width:0%;height:100%;background:linear-gradient(90deg,#2E7D32,#27ae60);transition:width .3s"></div></div>'
      + '<span class="deliv-folder-text" style="color:#2E7D32;font-weight:600;white-space:nowrap">准备中...</span>';
    modalWrap.insertBefore(bar, modalWrap.children[1] || modalWrap.firstChild);
  }

  var toastMsg = isDeliveryRoot
    ? '⚡ 000交付 全量回传启动：将复制整个 000交付 文件夹到制作部（' + sel.join(', ') + '），请查看系统复制进度窗口...'
    : '⚡ 文件夹回传已启动 ' + sel.length + ' 个...';
  toast(toastMsg, 'info');
  try{
    var r = await api('POST', '/api/deliver_folder/' + encodeURIComponent(name), { folder_names: sel, mode: mode });
    toast(r.message || '文件夹回传任务已提交', 'success');
    _deliverablesState.selectedFolders = {};
    _deliverablesState.selected = {};
  }catch(e){
    toast('❌ 文件夹回传失败: ' + e.message, 'error');
    var barEl = document.getElementById(progBarId);
    if(barEl){ barEl.style.background = '#fde2e2'; barEl.querySelector('.deliv-folder-text').style.color = '#c5221f'; barEl.querySelector('.deliv-folder-text').textContent = '❌ ' + e.message; }
    return;
  }

  // 串行递归轮询（避免 setInterval+async 并发：回传时 /api/projects 变慢会堆积回调，
  // 完成瞬间多个在途回调同时命中 -> 重复弹窗 + 卡顿）
  var pollCount = 0;
  var maxPolls = 300; // 最多等 10 分钟
  var startTs = Date.now();
  var _folderDone = false;
  var _folderTimer = null;
  _trackDelivPoll('folder', function(){ _folderDone = true; if(_folderTimer){ clearTimeout(_folderTimer); _folderTimer = null; } });
  var _folderPollOnce = function(){
    if(_folderDone) return;
    _folderTimer = setTimeout(async function(){
      if(_folderDone) return;
      pollCount++;
      if(pollCount > maxPolls){
        _clearDelivPoll('folder');
        var barEl2 = document.getElementById(progBarId);
        if(barEl2){ barEl2.querySelector('.deliv-folder-text').textContent = '⏱ 超时'; }
        return;
      }
      var _keepGoing = true;
      try{
        var d = await api('GET', '/api/projects');
        if(_folderDone) return;
        var flat = (d.production || []).concat(d.group_all || []).concat(d.group_completed || []);
        var target = flat.find(function(x){ return x.name === name; });
        // 同批量路径：找不到 target 时也继续（回退查回传任务状态）
        var sp = target ? (target.sync_progress || '') : '';
        if(!target){
          try{
            var dsx2 = await api('GET', '/api/deliver_status/' + encodeURIComponent(name));
            if(dsx2 && dsx2.task){
              sp = dsx2.task.message || sp;
              if(dsx2.task.status === 'done' && !sp) sp = '回传完成';
            }
          }catch(_){}
        }
        if(target || sp){
          var pct = 0;
          var label = sp;
          var m = sp.match(/回传\s*(\d+)\s*\/\s*(\d+)/);
          if(m){
            var cur = parseInt(m[1]);
            var tot = parseInt(m[2]);
            pct = tot > 0 ? Math.round(cur * 100 / tot) : 0;
            label = cur + ' / ' + tot + ' 文件';
          }else if(sp.indexOf('正在复制') >= 0){
            var elapsedSec = (Date.now() - startTs) / 1000;
            pct = Math.min(95, Math.round(3 + 95 * (1 - Math.exp(-elapsedSec / 240))));
            label = '📋 正在全量复制（请查看系统复制进度窗口）';
          }
          var barFill = document.querySelector('#' + progBarId + ' .deliv-folder-fill');
          var barText = document.querySelector('#' + progBarId + ' .deliv-folder-text');
          if(barFill) barFill.style.width = Math.max(2, pct) + '%';
          if(barText) barText.textContent = label || (pct + '%');

          if(sp.indexOf('批量回传完成') >= 0 || sp.indexOf('交付完成') >= 0 || sp.indexOf('回传完成') >= 0){
            _keepGoing = false;
            _clearDelivPoll('folder');
            var barEl3 = document.getElementById(progBarId);
            if(barEl3){
              barEl3.style.background = '#e2efda';
              if(barFill) barFill.style.width = '100%';
              if(barText){ barText.style.color = '#006100'; barText.textContent = '✅ 回传完成'; }
            }
            setTimeout(function(){
              toast('✅ 文件夹回传完成', 'success');
              try{ refreshDeliverablesList(); }catch(_1){}
              if(typeof renderDashboard === 'function') renderDashboard();
              try{ _showDeliverDoneModal(name, { mode: _deliverablesState.mode || 'editing' }); }catch(_2){}
            }, 500);
          } else if(sp.indexOf('失败') >= 0 || sp.indexOf('超时') >= 0 || sp.indexOf('异常') >= 0){
            _keepGoing = false;
            _clearDelivPoll('folder');
            var barEl4 = document.getElementById(progBarId);
            if(barEl4){
              barEl4.style.background = '#fde2e2';
              if(barText){ barText.style.color = '#c5221f'; barText.textContent = '❌ ' + (sp || '回传失败'); }
            }
          }
        }
      }catch(err){}
      if(_keepGoing && !_folderDone) _folderPollOnce();
    }, 2000);
  };
  _folderPollOnce();

  renderDeliverablesModal();
}

function previewDelivFile(projectName, fileName){
  // 确保传给后端的 mode 是 editing/revising/delivery 之一（后端不认 source/auto）
  var m = _deliverablesState.mode || 'editing';
  if(m === 'auto' || m === 'source') m = 'editing';
  window.__previewMode = m;
  window.__previewSubpath = _deliverablesState.subpath || '';
  window.__previewListProject = projectName;
  if (_deliverablesState.files && _deliverablesState.files.length > 0) {
    window.__previewList = _deliverablesState.files.map(function(f){
      return { name: f.name || f, subpath: _deliverablesState.subpath || '' };
    });
    window.__previewIdx = window.__previewList.findIndex(function(f){ return f.name === fileName; });
  } else {
    window.__previewList = null;
  }
  _openPreview(projectName, fileName);
}

// ===== 单个回传 =====
async function deliverOne(projectName, fileName, rowIdx){
  var rowEl = document.getElementById('deliv-row-' + rowIdx);
  var oldBtns = rowEl ? rowEl.querySelector('.deliv-td-actions').innerHTML : '';
  if(rowEl){
    rowEl.classList.add('deliv-row-loading');
    rowEl.querySelector('.deliv-td-actions').innerHTML = '<span style="color:#0071e3">⏳ 回传中...</span>';
  }
  try{
    var r = await api('POST', '/api/deliver/' + encodeURIComponent(projectName), { file_path: fileName, mode: _deliverablesState.mode, subpath: _deliverablesState.subpath });
    if(r.ok){
      toast('✅ 已回传: ' + fileName, 'success');
      if(rowEl){
        rowEl.classList.add('deliv-row-ok');
        rowEl.querySelector('.deliv-td-actions').innerHTML = '<span style="color:#34c759">✅ 已回传</span>';
      }
    }else{
      toast('❌ 回传失败: ' + (r.message||''), 'error');
      if(rowEl){
        rowEl.classList.add('deliv-row-err');
        rowEl.querySelector('.deliv-td-actions').innerHTML = '<span style="color:#ff3b30">❌ ' + htm(r.message||'') + '</span>';
      }
    }
  }catch(e){
    toast('❌ 回传请求失败: ' + e.message, 'error');
    if(rowEl && oldBtns){ rowEl.classList.remove('deliv-row-loading'); rowEl.querySelector('.deliv-td-actions').innerHTML = oldBtns; }
  }
}

// ===== 批量回传 + 进度轮询 =====
async function deliverBatch(){
  var name = _deliverablesState.projectName;
  var sel = Object.keys(_deliverablesState.selected).filter(function(k){ return _deliverablesState.selected[k]; });
  if(sel.length === 0){ toast('请先选择文件','warning'); return; }
  // 高危操作二次确认：批量回传会把选中的成片复制到制作部
  if(!confirm('⚠️ 确认执行【批量回传】？\n\n将回传 ' + sel.length + ' 个文件到制作部NAS对应项目的成片目录。\n\n确认继续？')) return;
  _deliverablesState.running = true;
  renderDeliverablesModal();
  toast('⚡ 批量回传已启动 ' + sel.length + ' 个文件...', 'info');

  // 在 toolbar 下方插入一个进度条
  var progBarId = 'deliv-batch-prog';
  var existing = document.getElementById(progBarId);
  if(existing) existing.remove();
  var modalWrap = document.querySelector('.deliv-modal-wrap');
  if(modalWrap){
    var bar = document.createElement('div');
    bar.id = progBarId;
    bar.style.cssText = 'padding:8px 16px;background:#e8f4fd;border-bottom:1px solid #c7e2fb;font-size:12px;display:flex;align-items:center;gap:10px';
    bar.innerHTML = '<span>⚡ 批量回传进度</span>'
      + '<div style="flex:1;height:8px;background:#fff;border-radius:4px;overflow:hidden;border:1px solid #c7e2fb"><div class="deliv-batch-fill" style="width:0%;height:100%;background:#0071e3;transition:width .3s"></div></div>'
      + '<span class="deliv-batch-text" style="color:#0071e3;font-weight:600">0 / ' + sel.length + '</span>';
    modalWrap.insertBefore(bar, modalWrap.children[1] || modalWrap.firstChild);
  }

  try{
    var r = await api('POST', '/api/deliver_batch/' + encodeURIComponent(name), { file_names: sel, mode: _deliverablesState.mode, subpath: _deliverablesState.subpath });
    toast(r.message || '批量回传任务已提交', 'success');
    _deliverablesState.selected = {};
    _deliverablesState.selectedFolders = {};

    // 串行递归轮询（避免 setInterval+async 并发导致重复弹窗 + 卡顿）
    var pollCount = 0;
    var maxPolls = 180; // 最多等 6 分钟
    var _batchDone = false;
    var _batchTimer = null;
    _trackDelivPoll('batch', function(){ _batchDone = true; if(_batchTimer){ clearTimeout(_batchTimer); _batchTimer = null; } });
    var _batchPollOnce = function(){
      if(_batchDone) return;
      _batchTimer = setTimeout(async function(){
        if(_batchDone) return;
        pollCount++;
        if(pollCount > maxPolls){ _clearDelivPoll('batch'); return; }
        var _keepGoing = true;
        try{
          var d = await api('GET', '/api/projects');
          if(_batchDone) return;
          var flat = (d.production || []).concat(d.group_all || []).concat(d.group_completed || []);
          var target = flat.find(function(x){ return x.name === name; });
          // 回传完成后项目可能被归档进 00已完成 / 状态切换，
          // 以前在列表里找不到 target 就整段跳过 → “回传完了不弹窗、状态也不改”。
          // 现在找不到也能继续走完成判定（下面会回退查 /api/deliver_status）。
          var sp = target ? (target.sync_progress || '') : '';
          if(!target){
            try{
              var dsx = await api('GET', '/api/deliver_status/' + encodeURIComponent(name));
              if(dsx && dsx.task){
                sp = dsx.task.message || sp;
                if(dsx.task.status === 'done' && !sp) sp = '回传完成';
              }
            }catch(_){}
          }
          if(target || sp){
            var label = sp;
            var pct = 0;
            var m = sp.match(/回传\s*(\d+)\s*\/\s*(\d+)/);
            if(m){
              var cur = parseInt(m[1]);
              var tot = parseInt(m[2]);
              pct = tot > 0 ? Math.round(cur * 100 / tot) : 0;
              label = cur + ' / ' + tot;
            } else {
              var pctM = sp.match(/^(\d+)%\s*(.*)$/);
              if(pctM){ pct = parseInt(pctM[1]); label = pctM[2] || sp; }
            }
            var barFill = document.querySelector('#' + progBarId + ' .deliv-batch-fill');
            var barText = document.querySelector('#' + progBarId + ' .deliv-batch-text');
            if(barFill) barFill.style.width = pct + '%';
            if(barText) barText.textContent = label || (pct + '%');

            var st = (target && (target.delivery_status || target.sync_status)) || '';
            var isDone = sp.indexOf('批量回传完成') >= 0 || sp.indexOf('交付完成') >= 0
              || sp.indexOf('回传完成') >= 0
              || (st === 'delivered' && sp.indexOf('回传') !== 0);
            if(!isDone){
              try{
                var ds2 = await api('GET', '/api/deliver_status/' + encodeURIComponent(name));
                if(ds2 && ds2.task && ds2.task.status === 'done') isDone = true;
              }catch(_){}
            }
            if(isDone){
              _keepGoing = false;
              _clearDelivPoll('batch');
              var bar2 = document.getElementById(progBarId);
              if(bar2) bar2.style.background = '#e2efda';
              var txt2 = document.querySelector('#' + progBarId + ' .deliv-batch-text');
              if(txt2){ txt2.style.color = '#006100'; txt2.textContent = '✅ ' + (sp || '回传完成'); }
              setTimeout(function(){
                toast('✅ 批量回传完成', 'success');
                // 先弹窗（里面可复制路径/打开目录），再刷新与改状态；
                // 每一步独立 try，互不拖累（以前抛错会连带不弹窗/不改状态）。
                try{ _showDeliverDoneModal(name, { mode: (typeof _deliverablesState !== 'undefined' && _deliverablesState.mode) || 'editing' }); }catch(_e1){}
                try{ refreshDeliverablesList(); }catch(_e2){}
                try{
                  var mode2 = _deliverablesState.mode || 'editing';
                  if(mode2 === 'revising'){
                    if(typeof submitRevisionSetStatus === 'function') submitRevisionSetStatus(name);
                  } else {
                    api('POST','/api/project/'+encodeURIComponent(name)+'/custom_status',{custom_status:'审核中'})
                      .then(function(){ if(typeof loadProjects==='function') loadProjects(); })
                      .catch(function(){});
                  }
                }catch(_){} finally {
                  window._afterDeliverBatch = null;
                }
              }, 500);
            }
          }
        }catch(err){}
        if(_keepGoing && !_batchDone) _batchPollOnce();
      }, 2000);
    };
    _batchPollOnce();
  }catch(e){
    toast('❌ 批量回传失败: ' + e.message, 'error');
    var bar = document.getElementById(progBarId);
    if(bar){ bar.style.background = '#fde2e2'; bar.querySelector('.deliv-batch-text').style.color = '#c5221f'; bar.querySelector('.deliv-batch-text').textContent = '❌ ' + e.message; }
  }
  _deliverablesState.running = false;
  renderDeliverablesModal();
}

// ===== 回传完成弹窗：打开回传目录 + 复制回传目录路径 =====
// opts: { mode: 'editing'|'revising'|'delivery', onCopied: function }
// 复制路径后可自动推进状态（默认批量回传后 → 审核中）
async function _showDeliverDoneModal(projectName, opts){
  opts = opts || {};
  // 去重保护：同一项目短时间内只弹一次（防止轮询/SSE 多路径重复触发）
  window._deliverDoneShown = window._deliverDoneShown || {};
  var _prev = window._deliverDoneShown[projectName];
  if(_prev && (Date.now() - _prev) < 8000){
    return;
  }
  window._deliverDoneShown[projectName] = Date.now();
  // 已有该项目的完成弹窗未关闭 → 不重复创建
  var _exist = document.querySelector('.modal-overlay[data-deliver-done="' + (window.CSS && CSS.escape ? CSS.escape(projectName) : projectName) + '"]');
  if(_exist) return;

  // 获取目标目录（制作部上映单集版 / 交付目录）
  // 用 POST 带 mode，才能精确定位到本次回传的真实目标目录。
  // GET 旧逻辑只按项目名猜，整目录交付（delivery）会拿到错目录。
  let dst = '';
  try{
    const d = await api('POST', '/api/project/' + encodeURIComponent(projectName) + '/deliver_dst',
      { mode: opts.mode || (_deliverablesState && _deliverablesState.mode) || 'editing',
        subpath: opts.subpath || '', folder: opts.folder || '' });
    if(d && d.ok && d.path) dst = d.path;
  }catch(_){}
  if(!dst){
    try{
      const d2 = await api('GET', '/api/project/' + encodeURIComponent(projectName) + '/deliver_dst');
      if(d2 && d2.ok && d2.path) dst = d2.path;
    }catch(_){}
  }

  // 复制路径后是否自动推进状态（默认：批量回传完成 → 审核中）
  var _advance = (typeof opts.onCopied === 'function') ? opts.onCopied : function(){
    try{
      api('POST','/api/project/'+encodeURIComponent(projectName)+'/custom_status',{custom_status:'审核中'})
        .then(function(){ if(typeof loadProjects==='function') loadProjects(); })
        .catch(function(){});
    }catch(_){}
  };
  var _projKey = String(projectName).replace(/[^a-zA-Z0-9_\u4e00-\u9fff]/g, '_');
  window.__deliverDoneCopyHandler = window.__deliverDoneCopyHandler || {};
  window.__deliverDoneCopyHandler[_projKey] = { dst: dst, advance: _advance };

  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay active';
  overlay.setAttribute('data-deliver-done', projectName);
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.4);z-index:999;display:flex;align-items:center;justify-content:center';
  const dstHtml = dst
    ? `<div style="font-size:12px;color:#86868b;margin:8px 0 2px">回传目录</div>
       <div style="font-family:monospace;font-size:12px;background:#f5f5f7;padding:8px 10px;border-radius:6px;word-break:break-all">${htm(dst)}</div>`
    : '<div style="font-size:12px;color:#86868b;margin:8px 0 2px">（未能获取回传目录路径）</div>';
  overlay.innerHTML = `<div style="background:#fff;border-radius:12px;width:460px;overflow:hidden;box-shadow:0 8px 30px rgba(0,0,0,.2)">
    <div style="padding:16px 18px;background:linear-gradient(135deg,#e8f5e9,#c8e6c9);font-weight:700;font-size:15px">✅ 回传完成</div>
    <div style="padding:16px 18px">
      <div style="font-size:13px;margin-bottom:4px">项目「<b>${htm(projectName)}</b>」的成片已回传到制作部。</div>
      ${dstHtml}
    </div>
    <div style="padding:12px 18px;border-top:1px solid #eee;display:flex;justify-content:flex-end;gap:8px;flex-wrap:wrap">
      ${dst ? `<button class="btn btn-sm btn-primary" onclick="deliverDoneAction('${_projKey}','open')">📂 打开回传目录</button>
      <button class="btn btn-sm btn-primary" onclick="deliverDoneAction('${_projKey}','copy')">📋 复制路径（并进入审核中）</button>
      <button class="btn btn-sm" onclick="deliverDoneAction('${_projKey}','copyonly')">仅复制路径</button>` : ''}
      <button class="btn btn-sm" onclick="this.closest('.modal-overlay').remove()">关闭</button>
    </div>
  </div>`;
  document.body.appendChild(overlay);
}

// 弹窗按钮统一入口：open = 打开目录 / copy = 复制路径+推进状态 / copyonly = 仅复制路径
function deliverDoneAction(projKey, action){
  var ctx = (window.__deliverDoneCopyHandler || {})[projKey] || {};
  var dst = ctx.dst || '';
  if(action === 'open'){
    if(!dst){ toast('未获取到回传目录', 'error'); return; }
    openDeliverDst(dst);
    return;
  }
  if(action === 'copy' || action === 'copyonly'){
    if(!dst){ toast('未获取到回传目录', 'error'); return; }
    var _after = function(){
      if(action === 'copy' && typeof ctx.advance === 'function'){
        try{ ctx.advance(); }catch(_){}
        toast('📋 已复制路径，项目已进入审核中', 'success');
      }
      // 关闭弹窗
      try{
        var ov = document.querySelector('.modal-overlay[data-deliver-done]');
        if(ov) ov.remove();
      }catch(_){}
    };
    try{
      if(navigator.clipboard && navigator.clipboard.writeText){
        navigator.clipboard.writeText(dst).then(function(){
          toast('📋 已复制路径: ' + dst, 'success');
          _after();
        }).catch(function(){
          _copyFallback(dst);
          _after();
        });
      } else {
        _copyFallback(dst);
        _after();
      }
    }catch(e){ _copyFallback(dst); _after(); }
  }
}

// 打开回传目录（后端 open_folder，弹系统资源管理器）
async function openDeliverDst(path){
  try{
    // 用一个真实项目名（用当前交付的项目）
    const name = _deliverablesState ? _deliverablesState.projectName : '';
    const r = await api('POST', '/api/project/' + encodeURIComponent(name) + '/open_folder', { which: 'path', path: path });
    if(r && r.ok) toast('已打开回传目录', 'success');
    else toast(r && r.message || '打开失败', 'error');
  }catch(e){ toast('打开失败: ' + e.message, 'error'); }
}

// 复制回传目录路径到剪贴板
function copyDeliverDst(path){
  try{
    if(navigator.clipboard && navigator.clipboard.writeText){
      navigator.clipboard.writeText(path).then(function(){
        toast('📋 已复制路径: ' + path, 'success');
      }).catch(function(){
        _copyFallback(path);
      });
    } else {
      _copyFallback(path);
    }
  }catch(e){ _copyFallback(path); }
}
function _copyFallback(text){
  try{
    const ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    toast('📋 已复制路径: ' + text, 'success');
  }catch(e){ toast('复制失败', 'error'); }
}
