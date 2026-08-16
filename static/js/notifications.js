// 通知中心：交付提醒(逾期/今日/即将) + 待办提醒
async function loadNotifications(){
  try{
    const d = await api('GET','/api/notifications');
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
  box.style.cssText = 'width:420px;max-width:92vw;height:100vh;background:#fff;box-shadow:-12px 0 40px rgba(0,0,0,.15);display:flex;flex-direction:column;animation:notifSlide .25s cubic-bezier(.4,0,.2,1)';
  const head = document.createElement('div');
  head.style.cssText = 'padding:16px 18px;border-bottom:1px solid var(--border,#e5e5ea);display:flex;align-items:center;justify-content:space-between';
  head.innerHTML = '<h3 style="margin:0;font-size:15px">🔔 通知中心</h3><button onclick="this.parentNode.parentNode.parentNode.remove()" style="border:none;background:none;font-size:18px;cursor:pointer">✕</button>';
  const body = document.createElement('div');
  body.style.cssText = 'flex:1;overflow-y:auto;padding:14px 16px';
  box.appendChild(head);
  box.appendChild(body);
  overlay.appendChild(box);
  document.body.appendChild(overlay);
  // 注入样式
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
function notifRow(inner, name){
  const go = name ? 'onclick="jumpToProject(\'' + name.replace(/'/g,"") + '\')"' : '';
  return '<div style="padding:9px 12px;background:#fafafa;border:1px solid var(--border,#e5e5ea);border-radius:9px;margin-bottom:6px;font-size:13px;cursor:'+(name?'pointer':'default')+'" '+go+'>'+inner+'</div>';
}
function renderNotifBody(body){
  const d = window._notifData || {};
  let html = '';
  html += notifGroup('⚠️ 逾期交付 ('+ (d.today||'') +')', '#c5221f', d.overdue, function(p){
    return notifRow('<b>'+escHtml(p.name)+'</b> <span style="color:#c5221f;font-size:11px;margin-left:6px">逾期 '+escHtml(p.date)+'</span>'+(p.department?'<div style="font-size:11px;color:#86868b">'+escHtml(p.department)+'</div>':''), p.name);
  });
  html += notifGroup('✅ 今日交付', '#137333', d.today_deliver, function(p){
    return notifRow('<b>'+escHtml(p.name)+'</b>'+(p.department?'<div style="font-size:11px;color:#86868b">'+escHtml(p.department)+'</div>':''), p.name);
  });
  html += notifGroup('⏳ 即将交付 (3天内)', '#ff9f0a', d.upcoming, function(p){
    return notifRow('<b>'+escHtml(p.name)+'</b> <span style="font-size:11px;color:#ff9f0a;margin-left:6px">'+escHtml(p.date)+'</span>'+(p.department?'<div style="font-size:11px;color:#86868b">'+escHtml(p.department)+'</div>':''), p.name);
  });
  html += notifGroup('📌 待办提醒', '#0071e3', d.todos, function(t){
    const items = (t.items||[]).slice(0,3).map(function(it){ return '<div style="font-size:12px;color:#555">• '+escHtml(it.text)+'</div>'; }).join('');
    return notifRow('<b>'+escHtml(t.project)+'</b> <span style="font-size:11px;color:#86868b">('+t.count+' 条待办)</span>'+items);
  });
  if(!html) html = '<div style="color:#86868b;text-align:center;padding:40px 0">🎉 暂无提醒</div>';
  else html += '<div style="margin-top:16px"><button class="btn" style="width:100%" onclick="openGlobalTodos()">📌 查看全部待办</button></div>';
  body.innerHTML = html;
}
