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
  toast('⚡ 文件夹回传已启动 ' + sel.length + ' 个...', 'info');
  try{
    var r = await api('POST', '/api/deliver_folder/' + encodeURIComponent(name), { folder_names: sel });
    toast(r.message || '文件夹回传任务已提交', 'success');
    _deliverablesState.selectedFolders = {};
    _deliverablesState.selected = {};
  }catch(e){
    toast('❌ 文件夹回传失败: ' + e.message, 'error');
  }
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

    // 开始轮询进度（参考 syncMaterial 的 setInterval 写法）
    var pollCount = 0;
    var maxPolls = 180; // 最多等 6 分钟
    var poll = setInterval(async function(){
      pollCount++;
      if(pollCount > maxPolls){ clearInterval(poll); return; }
      try{
        var d = await api('GET', '/api/projects');
        var flat = (d.production || []).concat(d.group_all || []);
        var target = flat.find(function(x){ return x.name === name; });
        if(!target) return;

        // 后端写的是 "回传 X/Y" 格式
        var sp = target.sync_progress || '';
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

        // 更新进度条 UI
        var barFill = document.querySelector('#' + progBarId + ' .deliv-batch-fill');
        var barText = document.querySelector('#' + progBarId + ' .deliv-batch-text');
        if(barFill) barFill.style.width = pct + '%';
        if(barText) barText.textContent = label || (pct + '%');

        // 判断完成
        var st = target.delivery_status || target.sync_status || '';
        if(st && st !== 'delivering' && sp.indexOf('回传') !== 0){
          clearInterval(poll);
          var bar2 = document.getElementById(progBarId);
          if(bar2) bar2.style.background = '#e2efda';
          var txt2 = document.querySelector('#' + progBarId + ' .deliv-batch-text');
          if(txt2){ txt2.style.color = '#006100'; txt2.textContent = '✅ ' + (sp || '回传完成'); }
          setTimeout(function(){
            toast('✅ 批量回传完成', 'success');
            refreshDeliverablesList();
          }, 500);
        }
      }catch(err){}
    }, 2000);
  }catch(e){
    toast('❌ 批量回传失败: ' + e.message, 'error');
    var bar = document.getElementById(progBarId);
    if(bar){ bar.style.background = '#fde2e2'; bar.querySelector('.deliv-batch-text').style.color = '#c5221f'; bar.querySelector('.deliv-batch-text').textContent = '❌ ' + e.message; }
  }
  _deliverablesState.running = false;
  renderDeliverablesModal();
}
