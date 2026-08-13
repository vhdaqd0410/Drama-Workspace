// 事件委托: ep-refresh / ep-deliverables / ep-revising
// ===== 事件委托：ep-refresh / ep-deliverables / ep-revising 按钮 =====
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
});

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
  window.__previewMode = _deliverablesState.mode || 'source';
  window.__previewSubpath = _deliverablesState.subpath || '';
  _openPreview(projectName, fileName);
}

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

async function deliverBatch(){
  var name = _deliverablesState.projectName;
  var sel = Object.keys(_deliverablesState.selected).filter(function(k){ return _deliverablesState.selected[k]; });
  if(sel.length === 0){ toast('请先选择文件','warning'); return; }
  _deliverablesState.running = true;
  renderDeliverablesModal();
  toast('⚡ 批量回传已启动 ' + sel.length + ' 个文件...', 'info');
  try{
    var r = await api('POST', '/api/deliver_batch/' + encodeURIComponent(name), { file_names: sel, mode: _deliverablesState.mode, subpath: _deliverablesState.subpath });
    toast(r.message || '批量回传任务已提交', 'success');
    _deliverablesState.selected = {};
    _deliverablesState.selectedFolders = {};
  }catch(e){
    toast('❌ 批量回传失败: ' + e.message, 'error');
  }
  _deliverablesState.running = false;
  renderDeliverablesModal();
}

