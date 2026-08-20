// 通知中心：交付提醒(逾期/今日/即将) + 待办提醒
// 可操作性：逾期/即将可改期或忽略；待办可勾选完成。
// 被忽略的提醒记在 localStorage，下次不再计入角标/展示。

function _notifDismissed(){
  try{ return JSON.parse(localStorage.getItem('_notifDismissed')||'{}'); }catch(e){ return {}; }
}
function _notifDismiss(key){
  const m = _notifDismissed(); m[key] = true;
  localStorage.setItem('_notifDismissed', JSON.stringify(m));
}
function _notifIsDismissed(key){ return !!_notifDismissed()[key]; }

async function loadNotifications(){
  try{
    const d = await api('GET','/api/notifications');
    // 过滤已被忽略的提醒
    ['overdue','today_deliver','upcoming'].forEach(function(k){
      if(Array.isArray(d[k])) d[k] = d[k].filter(function(p){ return !_notifIsDismissed(k+':'+p.name); });
    });
    window._notifData = d || {};
    updateNotifBadge();
    return window._notifData;
  }catch(e){
    window._notifData = {ok:false};
    return window._notifData;
  }
}
function updateNotifBadge(){
  const b = document.getElementById('notifBadge');
  if(!b) return;
  const d = window._notifData || {};
  const n = (d.overdue||[]).length + (d.today_deliver||[]).length + (d.upcoming||[]).length + (d.todos||[]).length;
  if(n > 0){ b.style.display = 'inline-block'; b.textContent = n > 99 ? '99+' : n; }
  else b.style.display = 'none';
}
function openNotifications(){
  const overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.4);z-index:22000;display:flex;align-items:flex-start;justify-content:flex-end';
  overlay.onclick = function(e){ if(e.target===overlay) overlay.remove(); };
  const box = document.createElement('div');
  box.style.cssText = 'width:440px;max-width:94vw;height:100vh;background:#fff;box-shadow:-12px 0 40px rgba(0,0,0,.15);display:flex;flex-direction:column;animation:notifSlide .25s cubic-bezier(.4,0,.2,1)';
  const head = document.createElement('div');
  head.style.cssText = 'padding:16px 18px;border-bottom:1px solid var(--border,#e5e5ea);display:flex;align-items:center;justify-content:space-between';
  head.innerHTML = '<h3 style="margin:0;font-size:15px">🔔 通知中心</h3><div style="display:flex;gap:8px;align-items:center"><button class="btn btn-sm" onclick="notifRefresh()">🔄</button><button onclick="this.parentNode.parentNode.parentNode.remove()" style="border:none;background:none;font-size:18px;cursor:pointer">✕</button></div>';
  const body = document.createElement('div');
  body.style.cssText = 'flex:1;overflow-y:auto;padding:14px 16px';
  window._notifBodyEl = body;
  box.appendChild(head);
  box.appendChild(body);
  overlay.appendChild(box);
  document.body.appendChild(overlay);
  const style = document.createElement('style');
  style.id = 'notifSlideStyle';
  if(!document.getElementById('notifSlideStyle')){
    style.textContent = '@keyframes notifSlide{from{transform:translateX(40px);opacity:0}to{transform:translateX(0);opacity:1}}';
    document.head.appendChild(style);
  }
  renderNotifBody(body);
}
function notifGroup(title, color, items, renderItem){
  if(!items || !items.length) return '';
  const rows = items.map(renderItem).join('');
  return '<div style="margin-bottom:16px"><div style="font-size:12px;font-weight:600;color:'+color+';margin-bottom:6px">'+title+' ('+items.length+')</div>'+rows+'</div>';
}
function notifRow(inner, name, actions){
  const go = name ? 'onclick="jumpToProject(\'' + jsq(name) + '\')"' : '';
  const acts = actions ? '<div style="display:flex;gap:6px;margin-top:6px">'+actions+'</div>' : '';
  return '<div style="padding:9px 12px;background:#fafafa;border:1px solid var(--border,#e5e5ea);border-radius:9px;margin-bottom:6px;font-size:13px;cursor:'+(name?'pointer':'default')+'" '+go+'>'+inner+acts+'</div>';
}
function renderNotifBody(body){
  const d = window._notifData || {};
  let html = '';
  html += notifGroup('⚠️ 逾期交付 ('+ (d.today||'') +')', '#c5221f', d.overdue, function(p){
    return notifRow('<b>'+escHtml(p.name)+'</b> <span style="color:#c5221f;font-size:11px;margin-left:6px">逾期 '+escHtml(p.date)+'</span>'+(p.department?'<div style="font-size:11px;color:#86868b">'+escHtml(p.department)+'</div>':''), p.name,
      '<button class="btn btn-sm" onclick="notifReschedule(\''+jsq(p.name||'')+'\',\''+jsq(p.date)+'\')">🗓 改期</button>'
      +'<button class="btn btn-sm" onclick="notifDismiss(\'overdue:'+jsq(p.name||'')+'\')">🙈 忽略</button>');
  });
  html += notifGroup('✅ 今日交付', '#137333', d.today_deliver, function(p){
    return notifRow('<b>'+escHtml(p.name)+'</b>'+(p.department?'<div style="font-size:11px;color:#86868b">'+escHtml(p.department)+'</div>':''), p.name,
      '<button class="btn btn-sm" onclick="notifDismiss(\'today_deliver:'+jsq(p.name||'')+'\')">🙈 忽略</button>');
  });
  html += notifGroup('⏳ 即将交付 (3天内)', '#ff9f0a', d.upcoming, function(p){
    return notifRow('<b>'+escHtml(p.name)+'</b> <span style="font-size:11px;color:#ff9f0a;margin-left:6px">'+escHtml(p.date)+'</span>'+(p.department?'<div style="font-size:11px;color:#86868b">'+escHtml(p.department)+'</div>':''), p.name,
      '<button class="btn btn-sm" onclick="notifReschedule(\''+jsq(p.name||'')+'\',\''+jsq(p.date)+'\')">🗓 改期</button>'
      +'<button class="btn btn-sm" onclick="notifDismiss(\'upcoming:'+jsq(p.name||'')+'\')">🙈 忽略</button>');
  });
  html += notifGroup('📌 待办提醒', '#0071e3', d.todos, function(t){
    const proj = (t.project||'').replace(/'/g,"");
    const items = (t.items||[]).slice(0,5).map(function(it){
      return '<div style="display:flex;align-items:center;gap:8px;font-size:12px;color:#555;padding:2px 0"><input type="checkbox" onchange="notifTodoDone(\''+proj+'\','+it.id+',this.checked)"><span>'+escHtml(it.text)+'</span></div>';
    }).join('');
    return notifRow('<b>'+escHtml(t.project)+'</b> <span style="font-size:11px;color:#86868b">('+t.count+' 条待办)</span>'+items);
  });
  if(!html) html = '<div style="color:#86868b;text-align:center;padding:40px 0">🎉 暂无提醒</div>';
  else html += '<div style="margin-top:16px"><button class="btn" style="width:100%" onclick="openTaskBoard()">🗂️ 打开任务中心</button></div>';
  // 审核流超时预警（功能5）
  html += '<div id="auditAlertSlot"></div>';
  body.innerHTML = html;
  loadAuditAlerts();
}

// 审核流超时提醒（功能5）：卡在审核/质检/修改超过3天的项目，责任到人
async function loadAuditAlerts(){
  const slot = document.getElementById('auditAlertSlot');
  if(!slot) return;
  try{
    const d = await api('GET','/api/audit/alerts?stale_days=3');
    if(!d || !d.ok || !d.alerts || !d.alerts.length){ return; }
    const rows = d.alerts.slice(0, 10).map(function(a){
      return '<div style="padding:8px 10px;background:#fff5f5;border:1px solid #ffd7d7;border-radius:8px;margin-bottom:6px;font-size:12px">'
        + '<b>'+escHtml(a.name)+'</b> <span style="color:#c5221f">卡在「'+escHtml(a.status)+'」'+a.days_stuck+' 天</span>'
        + '<div style="color:#86868b;margin-top:3px">👤 负责人：'+escHtml(a.owner||'未指派')+' · '+escHtml(a.department||'')+'</div>'
        + '</div>';
    }).join('');
    slot.innerHTML = '<div style="margin-top:16px;font-size:13px;font-weight:700">⚠️ 审核流超时预警 ('+d.alerts.length+')</div>' + rows
      + '<div style="margin-top:6px"><button class="btn btn-sm" onclick="openTaskBoard()">🗂️ 处理待办</button></div>';
  }catch(e){}
}

// 改期：弹日期选择器，设置新交付日期
function notifReschedule(name, oldDate){
  const overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.35);z-index:23000;display:flex;align-items:center;justify-content:center';
  overlay.onclick = function(e){ if(e.target===overlay) overlay.remove(); };
  overlay.innerHTML = '<div style="background:#fff;border-radius:14px;padding:18px;width:320px;box-shadow:0 16px 48px rgba(0,0,0,.25)">'
    + '<div style="font-size:15px;font-weight:600;margin-bottom:12px">🗓 改期 · '+escHtml(name)+'</div>'
    + '<div style="font-size:12px;color:#86868b;margin-bottom:8px">原交付日期：'+escHtml(oldDate)+'</div>'
    + '<input type="date" id="notifNewDate" style="width:100%;padding:8px;border:1px solid #d1d5db;border-radius:8px;font-size:14px">'
    + '<div style="display:flex;gap:8px;margin-top:14px;justify-content:flex-end">'
    + '<button class="btn" onclick="this.closest(\'div[style*="position:fixed"]\').remove()">取消</button>'
    + '<button class="btn btn-primary" onclick="notifRescheduleGo(\''+name+'\',this)">确定</button></div></div>';
  document.body.appendChild(overlay);
  document.getElementById('notifNewDate').focus();
}
function notifRescheduleGo(name, btn){
  const d = document.getElementById('notifNewDate');
  if(!d || !d.value){ toast('请选择日期','warning'); return; }
  const p = '/api/project/' + encodeURIComponent(name) + '/delivered_date';
  api('POST', p, { date: d.value }).then(function(r){
    if(r && r.ok){
      toast('✅ 已改期 ' + name + ' → ' + d.value, 'success');
      // 关闭弹层
      const ov = btn.closest('div[style*="position:fixed"]'); if(ov) ov.remove();
      notifRefresh();
    } else toast((r&&r.message)||'改期失败','error');
  }).catch(function(e){ toast('改期失败: '+e.message,'error'); });
}
// 忽略某条提醒
function notifDismiss(key){
  _notifDismiss(key);
  toast('已忽略该提醒','info');
  notifRefresh();
}
// 待办勾选完成
function notifTodoDone(project, id, done){
  const p = '/api/project/' + encodeURIComponent(project) + '/todos/' + id;
  api('PUT', p, { done: !!done }).then(function(r){
    if(r && r.ok){ toast(done?'✅ 已完成待办':'↩️ 已恢复待办','success'); notifRefresh(); }
    else toast('操作失败','error');
  }).catch(function(e){ toast('操作失败: '+e.message,'error'); });
}
// 刷新通知面板 + 角标
function notifRefresh(){
  loadNotifications().then(function(){
    if(window._notifBodyEl) renderNotifBody(window._notifBodyEl);
  });
}
