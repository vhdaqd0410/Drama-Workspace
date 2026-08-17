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

  // 轮询进度（和 deliverBatch 类似，读 sync_progress 字段）
  var pollCount = 0;
  var maxPolls = 300; // 最多等 10 分钟
  var startTs = Date.now();
  var poll = setInterval(async function(){
    pollCount++;
    if(pollCount > maxPolls){
      clearInterval(poll);
      var barEl2 = document.getElementById(progBarId);
      if(barEl2){ barEl2.querySelector('.deliv-folder-text').textContent = '⏱ 超时'; }
      return;
    }
    try{
      var d = await api('GET', '/api/projects');
      var flat = (d.production || []).concat(d.group_all || []);
      var target = flat.find(function(x){ return x.name === name; });
      if(!target) return;

      var sp = target.sync_progress || '';
      var pct = 0;
      var label = sp;

      // 解析 "回传 X/Y 文件" 格式
      var m = sp.match(/回传\s*(\d+)\s*\/\s*(\d+)/);
      if(m){
        var cur = parseInt(m[1]);
        var tot = parseInt(m[2]);
        pct = tot > 0 ? Math.round(cur * 100 / tot) : 0;
        label = cur + ' / ' + tot + ' 文件';
      }else if(sp.indexOf('正在复制') >= 0){
        // 整目录复制（系统进度对话框已在显示详细进度），显示 0~100% 的平滑伪进度
        var elapsedSec = (Date.now() - startTs) / 1000;
        // 假设最多 60 分钟，log 增长曲线
        pct = Math.min(95, Math.round(3 + 95 * (1 - Math.exp(-elapsedSec / 240))));
        label = '📋 正在全量复制（请查看系统复制进度窗口）';
      }

      // 更新进度条 UI
      var barFill = document.querySelector('#' + progBarId + ' .deliv-folder-fill');
      var barText = document.querySelector('#' + progBarId + ' .deliv-folder-text');
      if(barFill) barFill.style.width = Math.max(2, pct) + '%';
      if(barText) barText.textContent = label || (pct + '%');

      // 判断完成
      var st = target.delivery_status || target.sync_status || '';
      if(sp.indexOf('批量回传完成') >= 0 || sp.indexOf('交付完成') >= 0){
        clearInterval(poll);
        var barEl3 = document.getElementById(progBarId);
        if(barEl3){
          barEl3.style.background = '#e2efda';
          if(barFill) barFill.style.width = '100%';
          if(barText){ barText.style.color = '#006100'; barText.textContent = '✅ 回传完成'; }
        }
        setTimeout(function(){
          toast('✅ 文件夹回传完成', 'success');
          refreshDeliverablesList();
          if(typeof renderDashboard === 'function') renderDashboard();
          _showDeliverDoneModal(name);
        }, 500);
      } else if(sp.indexOf('失败') >= 0 || sp.indexOf('超时') >= 0 || sp.indexOf('异常') >= 0){
        clearInterval(poll);
        var barEl4 = document.getElementById(progBarId);
        if(barEl4){
          barEl4.style.background = '#fde2e2';
          if(barText){ barText.style.color = '#c5221f'; barText.textContent = '❌ ' + (sp || '回传失败'); }
        }
      }
    }catch(err){}
  }, 2000);

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

        // 判断完成（后端完成时 sync_progress = "批量回传完成（N 个文件）"）
        var st = target.delivery_status || target.sync_status || '';
        var isDone = sp.indexOf('批量回传完成') >= 0 || sp.indexOf('交付完成') >= 0
          || (st === 'delivered' && sp.indexOf('回传') !== 0);
        if(isDone){
          clearInterval(poll);
          var bar2 = document.getElementById(progBarId);
          if(bar2) bar2.style.background = '#e2efda';
          var txt2 = document.querySelector('#' + progBarId + ' .deliv-batch-text');
          if(txt2){ txt2.style.color = '#006100'; txt2.textContent = '✅ ' + (sp || '回传完成'); }
          setTimeout(function(){
            toast('✅ 批量回传完成', 'success');
            refreshDeliverablesList();
            _showDeliverDoneModal(name);
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

// ===== 回传完成弹窗：打开回传目录 + 复制回传目录路径 =====
async function _showDeliverDoneModal(projectName){
  // 获取目标目录（制作部上映单集版）
  let dst = '';
  try{
    const d = await api('GET', '/api/project/' + encodeURIComponent(projectName) + '/deliver_dst');
    if(d && d.ok && d.path) dst = d.path;
  }catch(_){}

  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay active';
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
      ${dst ? `<button class="btn btn-sm btn-primary" onclick="openDeliverDst('${jsq(dst)}')">📂 打开回传目录</button>
      <button class="btn btn-sm" onclick="copyDeliverDst('${jsq(dst)}')">📋 复制路径</button>` : ''}
      <button class="btn btn-sm" onclick="this.closest('.modal-overlay').remove()">关闭</button>
    </div>
  </div>`;
  document.body.appendChild(overlay);
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
