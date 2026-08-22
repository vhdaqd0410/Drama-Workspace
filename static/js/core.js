// 工具函数 + 常量 + 渲染函数
/* ============ Config & Utils ============ */
const API='';
const WF_STEPS=['分集','剪辑','审核','修改','交付','质检','完成'];
let projects=[], allSections=[], allProjects={}, fenjiLight=[], qaRunning=false, pollDashboard=null, pollQA=null, qaStartTime=0;

function $(id){return document.getElementById(id)}
function el(tag,cls,html){const e=document.createElement(tag);if(cls)e.className=cls;if(html!==undefined)e.innerHTML=html;return e}
async function api(method,path,body){const opts={method,headers:{}};if(body!==undefined){if(body instanceof FormData){opts.body=body}else{opts.headers['Content-Type']='application/json';opts.body=JSON.stringify(body)}}const r=await fetch(API+path,opts);if(!r.ok)throw new Error(r.status+' '+r.statusText);const ct=r.headers.get('content-type')||'';return ct.includes('application/json')?r.json():r.text()}

// 安全地把任意字符串嵌入 JS 单引号字符串（用于 onclick 属性等）。
// escHtml/htm 只处理 HTML 实体，浏览器解析 onclick 属性时会先解码实体再交给 JS，
// 导致 ' 被实体转义后仍能逃逸出 JS 字符串 → XSS。jsq 额外转义 \ 与换行、</script>。
function jsq(s){
  if(s===undefined||s===null)return '';
  return String(s)
    .replace(/\\/g,'\\\\')
    .replace(/'/g,"\\'")
    .replace(/"/g,'&quot;')
    .replace(/\r/g,'\\r')
    .replace(/\n/g,'\\n')
    .replace(/</g,'\\u003C')
    .replace(/>/g,'\\u003E');
}
// 统一 HTML 内容转义（各文件已有的 escHtml/htm 行为不一致，这里给一个兜底别名）
window.jsq = jsq;

function toast(msg,type='info'){
  const container=$('toastContainer');
  const icons={success:'✅',error:'❌',warning:'⚠️',info:'ℹ️'};
  const t=el('div',`toast ${type}`,`<span class="toast-icon">${icons[type]||'ℹ️'}</span><span class="toast-msg">${msg}</span>`);
  const c=el('span','toast-close','×');c.onclick=()=>t.remove();t.appendChild(c);container.appendChild(t);
  setTimeout(()=>{t.style.opacity='0';t.style.transition='all .3s';setTimeout(()=>t.remove(),300)},3500);
}

/* ============ 桌面版 SSE 实时通知 ============ */
let _sseSource=null;
function initDesktopSSE(){
  if(_sseSource)return;
  try{
    _sseSource=new EventSource('/api/sse');
    _sseSource.onopen=()=>console.log('[SSE] 连接已建立');
    _sseSource.onmessage=(evt)=>{
      if(!evt.data) return;
      try{
        const payload=JSON.parse(evt.data);
        if(payload.type==='notify'){
          const level=payload.level==='error'?'error':'success';
          toast(payload.title+': '+payload.message, level);
          _scheduleSseRefresh();
        } else if(payload.type==='sync'){
          // 同步进度事件 → 更新卡片进度显示 + 完成后刷新
          if(payload.status==='done'){
            toast('✅ '+payload.project+' 同步完成','success');
            _scheduleSseRefresh();
          } else if(payload.status==='error'){
            toast('❌ '+payload.project+' 同步失败','error');
            _scheduleSseRefresh();
          } else {
            // 纯进度变化 → 静默刷新（让卡片上的进度条动起来）
            _scheduleSseRefresh(800);
          }
        } else if(payload.type==='deliver'){
          if(payload.status==='start'){
            toast('📤 '+payload.project+' 开始回传','info');
          } else if(payload.status==='done'){
            toast('✅ '+payload.project+' 回传完成','success');
            // 000交付整目录回传（deliver_to_production）：完成时项目会被自动归档
            // 到 00已完成，前端轮询 /api/projects 会找不到 target 而无法弹窗，
            // 因此这里由 SSE 事件直接触发回传完成弹窗（指向制作部 000交付 目录）。
            if(payload.mode === 'delivery'){
              setTimeout(function(){
                if(typeof _showDeliverDoneModal === 'function'){
                  _showDeliverDoneModal(payload.project, { mode:'delivery', subpath:'', folder:'' });
                }
              }, 300);
            }
          } else if(payload.status==='error'){
            toast('❌ '+payload.project+' 回传失败','error');
          }
          _scheduleSseRefresh();
        } else if(payload.type==='search'){
          // 全局搜索热键按下 → 打开搜索框
          if(typeof openSearchModal === 'function'){
            setTimeout(function(){ openSearchModal(); }, 120);
          }
        } else if(payload.type==='nas'){
          // NAS 可达性变化 → 显示/隐藏离线横幅
          _handleNasStatus(payload.ok, payload.roots);
        }
      }catch(_){}
    };
    _sseSource.onerror=()=>{
      console.warn('[SSE] 连接断开，3s 后重连');
      _sseSource=null;
      setTimeout(()=>{try{initDesktopSSE();}catch(_){}},3000);
    };
  }catch(e){console.warn('SSE init exception',e);}
}
let _sseRefreshTimer=null;
function _scheduleSseRefresh(delay){
  delay = delay || 1500;
  if(_sseRefreshTimer) clearTimeout(_sseRefreshTimer);
  _sseRefreshTimer = setTimeout(()=>{
    _sseRefreshTimer = null;
    try{ loadProjects(); }catch(_){}
  }, delay);
}

// ===== NAS 离线横幅 =====
let _nasOfflineEl = null;
function _handleNasStatus(ok, roots){
  if(ok){
    // 恢复在线
    if(_nasOfflineEl){ _nasOfflineEl.remove(); _nasOfflineEl = null; }
    return;
  }
  if(_nasOfflineEl) return; // 已显示
  // 找出离线的根路径
  let offlineList = '';
  if(roots){
    offlineList = Object.keys(roots).filter(function(r){ return !roots[r]; });
  }
  const names = offlineList.length ? offlineList.join('<br>') : 'NAS 路径不可访问';
  const bar = document.createElement('div');
  bar.id = 'nasOfflineBanner';
  bar.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:23000;background:#c5221f;color:#fff;padding:10px 16px;text-align:center;font-size:13px;font-weight:600;box-shadow:0 2px 10px rgba(0,0,0,.3)';
  bar.innerHTML = '⚠️ NAS 离线：以下路径不可访问<br><span style="font-size:11px;font-weight:400;opacity:.9">' + names + '</span>'
    + '<span style="margin-left:12px;cursor:pointer;font-weight:400;font-size:12px" onclick="if(window.WB){WB.offline.enable();}">📴 切换离线模式</span>'
    + '<button onclick="this.parentElement.remove()" style="position:absolute;right:10px;top:6px;background:none;border:none;color:#fff;font-size:16px;cursor:pointer">✕</button>';
  document.body.appendChild(bar);
  _nasOfflineEl = bar;
}

/* ============ 全局快捷键 ============ */
// 快捷键配置（从后端设置加载，可在设置界面修改）
// search: 如 'ctrl+space' / 'ctrl+g' / '' = 默认 ctrl+space
window._shortcutConfig = { search: '' };
function _getSearchShortcut(){
  var s = window._shortcutConfig && window._shortcutConfig.search;
  var sc = s ? String(s).toLowerCase().trim() : '';
  // 未配置时默认用 Ctrl+Space
  return sc || 'ctrl+space';
}
// ===== 剪辑完成自动扫描提醒 =====
var _editWatcherStarted = false;
var _editAlertedProjects = {};  // 记录已提醒过的项目，避免重复提醒
function initEditCompleteWatcher(){
  if(_editWatcherStarted) return;
  _editWatcherStarted = true;
  // 首次启动延迟检查，之后每3分钟
  setTimeout(checkEditCompleteProjects, 15000);
  setInterval(checkEditCompleteProjects, 3*60*1000);
}
async function checkEditCompleteProjects(){
  try{
    var flat = [];
    try{
      var d = await api('GET', '/api/projects');
      flat = (d.group_all || []).filter(function(p){ return p.project_type === 'group'; });
    }catch(_){ return; }

    for(var i=0; i<flat.length; i++){
      var p = flat[i];
      if(String(p.custom_status||'').trim() !== '剪辑中') continue;
      var total = Number(p.total_episodes) || 0;
      if(total <= 0) continue;
      // 已提醒过则跳过
      if(_editAlertedProjects[p.name]) continue;
      // 获取实时集数
      try{
        var st = await api('GET', '/api/project/' + encodeURIComponent(p.name) + '/episodes_status');
        if(st && st.ok && (st.current_count || 0) >= total){
          _editAlertedProjects[p.name] = true;
          showEditCompleteDialog(p.name, total, st.current_count);
          break;  // 一次提醒一个，避免轰炸
        }
      }catch(_){}
    }
  }catch(_){}
}
function showEditCompleteDialog(name, total, current){
  var overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.4);z-index:10000;display:flex;align-items:center;justify-content:center';
  overlay.innerHTML = `<div style="background:#fff;border-radius:12px;width:440px;overflow:hidden;box-shadow:0 8px 30px rgba(0,0,0,.2)">
    <div style="padding:16px 18px;background:linear-gradient(135deg,#e3f2fd,#bbdefb);font-weight:700;font-size:15px">✂️ 项目已剪完</div>
    <div style="padding:16px 18px">
      <div style="font-size:14px;margin-bottom:6px">项目「<b>${htm(name)}</b>」已剪辑完成</div>
      <div style="font-size:12px;color:#666">已产出 <b>${current}</b> / ${total} 集，是否进入审核？</div>
    </div>
    <div style="padding:12px 18px;border-top:1px solid #eee;display:flex;justify-content:flex-end;gap:8px">
      <button class="btn btn-sm" onclick="closeEditCompleteDialog(this)">稍后</button>
      <button class="btn btn-sm btn-primary" onclick="confirmEditComplete('${jsq(name)}', this)">✅ 进入审核</button>
    </div>
  </div>`;
  // 点击遮罩空白处也关闭
  overlay.addEventListener('click', function(ev){ if(ev.target === overlay) closeEditCompleteDialog(null, overlay); });
  document.body.appendChild(overlay);
}
// 关闭“项目已剪完”弹窗（兼容旧调用：有的按钮传 this，有的只传遮罩）
function closeEditCompleteDialog(btn, overlayEl){
  var node = overlayEl || (btn && btn.closest && btn.closest('.modal-overlay'));
  if(!node && btn){ node = btn.parentElement && btn.parentElement.parentElement && btn.parentElement.parentElement.parentElement; }
  while(node && node.classList && !node.classList.contains('modal-overlay')) node = node.parentElement;
  if(node && node.remove) node.remove();
}
async function confirmEditComplete(name, btn){
  var overlayEl = btn && btn.closest ? btn.closest('.modal-overlay') : null;
  try{
    await api('POST', '/api/project/' + encodeURIComponent(name) + '/custom_status', { custom_status: '审核中' });
    toast('✅ ' + name + ' 已进入审核', 'success');
  }catch(e){
    toast('操作失败: '+e.message, 'error');
  }finally{
    closeEditCompleteDialog(null, overlayEl || btn);
    if(typeof loadProjects === 'function') loadProjects();
  }
}
// 解析快捷键配置字符串，判断当前按键是否匹配
function _matchShortcut(e, shortcutStr){
  if(!shortcutStr) return false;
  var parts = String(shortcutStr).toLowerCase().split('+').map(function(x){return x.trim();});
  // e.metaKey / e.ctrlKey 可能在非浏览器环境为 undefined，做布尔归一
  var ctrl = !!(e.ctrlKey || e.metaKey);
  var alt = !!e.altKey;
  var shift = !!e.shiftKey;
  var key = e.key ? e.key.toLowerCase() : '';
  if(key === ' ') key = 'space';
  // 用 e.code 兜底（浏览器里 e.key 可能是大写/特殊值）
  if(e.code){
    var c = e.code;
    if(/^Key[A-Z]$/.test(c)) key = c.slice(3).toLowerCase();
    else if(c === 'Space') key = 'space';
    else if(c === 'Enter') key = 'enter';
  }
  var hasCtrl = parts.indexOf('ctrl')>=0 || parts.indexOf('control')>=0;
  var hasAlt = parts.indexOf('alt')>=0;
  var hasShift = parts.indexOf('shift')>=0;
  if(hasCtrl !== ctrl) return false;
  if(hasAlt !== alt) return false;
  if(hasShift !== shift) return false;
  var main = parts[parts.length-1];
  return key === main;
}

function bindShortcuts(){
  document.addEventListener('keydown', function(e){
    var tag = (e.target.tagName || '').toUpperCase();
    var isInput = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || e.target.isContentEditable;
    var searchSc = _getSearchShortcut();

    // 打开全局搜索：优先用配置的快捷键；未配置时用默认 Ctrl+K / Ctrl+F
    var defaultSearch = (e.ctrlKey || e.metaKey) && (e.key.toLowerCase() === 'k' || e.key.toLowerCase() === 'f');
    if(defaultSearch || _matchShortcut(e, searchSc)){
      e.preventDefault();
      openSearchModal();
      return;
    }
    if(isInput) return;
    if(e.key === 'F5' || ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'r' && !e.shiftKey)){
      e.preventDefault();
      toast('🔄 刷新中...','info');
      try{ loadProjects(); }catch(_){}
      return;
    }
    if((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 'r'){
      e.preventDefault();
      toast('♻️  强制重新扫描...','info');
      try{ localStorage.removeItem('wb_scan_cache'); }catch(_){}
      api('POST','/api/scan').then(function(){ loadProjects(); }).catch(function(){});
      return;
    }
    if(e.key === 'Escape'){
      var modal = document.querySelector('.modal-overlay');
      if(modal){
        // detailModal 必须先走 closeDeliverablesModal() 清理轮询，否则直接 remove
        // 会导致 deliver-events.js 的进度轮询泄漏（继续每 2s 打 /api/projects 直到超时）
        if(modal.id === 'detailModal' && typeof closeDeliverablesModal === 'function'){
          closeDeliverablesModal();
          return;
        }
        modal.remove();
      }
      return;
    }
  });
}

function openSearchModal(){
  // 已有搜索框则移除，避免重复
  var old = document.getElementById('searchModal');
  if(old) old.remove();
  var sc = _getSearchShortcut() || 'Ctrl+K / Ctrl+F';
  var html = '<div id="searchModal" style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.35);z-index:22000;display:flex;justify-content:center;align-items:flex-start;padding-top:12vh" onclick="if(event.target===this)this.remove()">'
    + '<div style="width:min(700px,92vw);background:#fff;border-radius:14px;box-shadow:0 16px 48px rgba(0,0,0,.25);overflow:hidden">'
    + '<div style="display:flex;align-items:center;gap:10px;padding:16px 20px;border-bottom:1px solid #e5e5ea">'
    + '<span style="font-size:18px">🔍</span>'
    + '<input id="searchInput" placeholder="搜索项目/月份/部门/剪辑师/交付日期/待办..." autofocus style="flex:1;border:none;outline:none;font-size:16px;background:transparent" oninput="filterSearchResults()" onkeydown="if(event.key===\'Enter\')jumpToFirstResult();if(event.key===\'Escape\')this.closest(\'#searchModal\').remove()">'
    + '<span style="font-size:11px;color:#86868b;background:#f0f2f5;padding:3px 8px;border-radius:6px;white-space:nowrap">'+sc+'</span>'
    + '</div>'
    + '<div id="searchResults" style="max-height:60vh;overflow-y:auto"></div>'
    + '<div style="padding:8px 16px;background:#fafafa;border-top:1px solid #f0f0f0;font-size:11px;color:#86868b;display:flex;gap:14px;flex-wrap:wrap">'
    + '<span>↑↓ 选择 · Enter 打开 · Esc 关闭</span>'
    + '<span style="margin-left:auto">跨项目·待办·剪辑师 搜索</span>'
    + '</div>'
    + '</div></div>';
  document.body.insertAdjacentHTML('beforeend', html);
  var inp = document.getElementById('searchInput');
  if(inp) inp.focus();
  filterSearchResults();
}

// 回车跳转到第一个搜索结果
function jumpToFirstResult(){
  var first = document.querySelector('#searchResults .search-result-item');
  if(first) jumpToProjectItem(first);
}

// 模糊匹配：支持子序列匹配（如 "昼夜回响" 匹配 "昼夜回响"）
function fuzzyMatch(text, pattern){
  if(!pattern) return true;
  text = String(text||'').toLowerCase();
  pattern = String(pattern||'').toLowerCase();
  if(text.indexOf(pattern) >= 0) return true;      // 子串包含
  // 子序列匹配：pattern 的字符按顺序出现在 text 里（如 "zh" 匹配 "z...h..."）
  let pi = 0;
  for(let i=0; i<text.length && pi<pattern.length; i++){
    if(text[i] === pattern[pi]) pi++;
  }
  return pi === pattern.length;
}

function searchSectionTitle(title, items, builder){
  if(!items || !items.length) return '';
  var rows = items.map(builder).join('');
  return '<div style="font-size:11px;font-weight:700;color:#86868b;padding:8px 12px 4px;text-transform:uppercase;letter-spacing:.4px;background:#fafafa">'+title+' ('+items.length+')</div>'+rows;
}

function filterSearchResults(){
  var kw = (document.getElementById('searchInput')?.value || '').trim();
  var results = document.getElementById('searchResults');
  if(!results) return;
  if(!kw){
    // 空关键词：显示本地项目列表
    var secs = (typeof allSections !== 'undefined' && allSections) ? allSections : [];
    var items = [];
    secs.forEach(function(sec){ (sec.projects||[]).forEach(function(p){ items.push({name:p.name||'', section:sec.name, month:p.project_month||'', status:p.custom_status||''}); }); });
    if(!items.length){ results.innerHTML = '<div style="color:#86868b;padding:20px;text-align:center">暂无项目</div>'; return; }
    var html = items.slice(0, 50).map(searchItemRow).join('');
    results.innerHTML = html;
    return;
  }
  // 有关键词：走后端全局搜索
  api('GET','/api/search?q=' + encodeURIComponent(kw)).then(function(d){
    if(!d || !d.ok){ results.innerHTML = '<div style="color:#86868b;padding:20px;text-align:center">搜索失败</div>'; return; }
    var html = '';
    html += searchSectionTitle('📁 项目', d.projects, searchItemRow);
    html += searchSectionTitle('🎬 剪辑师', d.editors, function(ed){
      return '<div class="search-result-item" style="padding:10px 12px;cursor:pointer;border-bottom:1px solid #f0f0f0;font-size:13px" onclick="toast(\''+jsq(ed.name+' 负责 '+ed.count+' 集 / '+ed.projects+' 部')+'\',\'info\')"><b>'+escHtml(ed.name)+'</b> <span style="color:#86868b;font-size:11px;margin-left:6px">'+ed.count+' 集 · '+ed.projects+' 部项目</span></div>';
    });
    html += searchSectionTitle('📌 待办', d.todos, function(t){
      return '<div class="search-result-item" style="padding:10px 12px;cursor:pointer;border-bottom:1px solid #f0f0f0;font-size:13px" onclick="jumpToProject(\''+jsq(t.project||'')+'\')"><span style="color:#0071e3">📌</span> '+escHtml(t.text)+' <span style="color:#86868b;font-size:11px;margin-left:6px">· '+escHtml(t.project)+'</span></div>';
    });
    html += searchSectionTitle('📅 交付日期', d.delivered_dates, function(p){
      return '<div class="search-result-item" style="padding:10px 12px;cursor:pointer;border-bottom:1px solid #f0f0f0;font-size:13px" onclick="jumpToProject(\''+jsq(p.name||'')+'\')">📅 '+escHtml(p.date)+' · <b>'+escHtml(p.name)+'</b> <span style="color:#86868b;font-size:11px;margin-left:6px">'+escHtml(p.department)+'</span></div>';
    });
    if(!html) html = '<div style="color:#86868b;padding:20px;text-align:center">未找到匹配：项目 / 剪辑师 / 待办 / 交付日期</div>';
    results.innerHTML = html;
  }).catch(function(e){
    results.innerHTML = '<div style="color:#86868b;padding:20px;text-align:center">搜索失败: '+escHtml(e.message)+'</div>';
  });
}

function searchItemRow(it){
  var monthBadge = it.month ? '<span style="background:#e3f2fd;color:#1565c0;padding:1px 7px;border-radius:10px;font-size:11px;margin-left:6px">📅 '+it.month+'</span>' : '';
  var ddBadge = it.delivered_date ? '<span style="background:#e8f5e9;color:#137333;padding:1px 7px;border-radius:10px;font-size:11px;margin-left:6px">📦 '+it.delivered_date+'</span>' : '';
  return '<div class="search-result-item" data-name="' + (it.name||'').replace(/"/g, "&quot;") + '" style="padding:10px 12px;cursor:pointer;border-radius:6px;display:flex;justify-content:space-between;align-items:center;font-size:13px;border-bottom:1px solid #f0f0f0" onclick="jumpToProjectItem(this)">'
    + '<span><span style="font-weight:500">'+escHtml(it.name)+'</span>'+monthBadge+ddBadge+'</span>'
    + '<span style="color:#86868b;font-size:11px">'+escHtml(it.section)+ (it.status?' · '+escHtml(it.status):'')+'</span>'
    + '</div>';
}

function jumpToProjectItem(el){
  var name = el.getAttribute('data-name') || '';
  var m = document.getElementById('searchModal');
  if(m) m.remove();
  jumpToProject(name);
}
function jumpToProject(name){
  // 切到 dashboard tab
  try{ switchTab('dashboard'); }catch(_){}
  // 清除所有筛选，确保卡片可见
  try{
    if($('globalSearch'))$('globalSearch').value='';
    if($('filterDept'))$('filterDept').value='';
    if($('filterStatus'))$('filterStatus').value='';
    if($('filterMonth'))$('filterMonth').value='';
  }catch(_){}
  // 强制全量渲染（绕过懒加载分批，保证目标卡片存在DOM里，避免"未找到项目卡片"）
  window._forceFullRender = true;
  // 重新渲染确保卡片存在
  try{ renderDashboard(); }catch(_){}

  setTimeout(function(){
    // 定位项目卡片：通过卡片标题查找
    var cards = document.querySelectorAll('.card');
    var target = null;
    for(var i=0;i<cards.length;i++){
      var tn = cards[i].querySelector('.card-title-name');
      if(tn && (tn.getAttribute('title') === name || tn.textContent === name)){
        target = cards[i];
        break;
      }
    }
    // 释放强制全量标志
    window._forceFullRender = false;
    if(!target){
      toast('未找到项目卡片（可能已不在当前数据中）', 'info');
      return;
    }
    // 若目标所在分组处于折叠状态，先展开该分组，确保卡片可见可定位（已完成组默认折叠）
    var secBlock = target.closest('.section-block');
    if(secBlock && secBlock.classList.contains('section-collapsed')){
      secBlock.classList.remove('section-collapsed');
      var arrow = secBlock.querySelector('.section-arrow');
      if(arrow) arrow.textContent = '▼';
    }
    // 滚动到卡片
    target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    // 高亮动画
    target.classList.add('search-highlight');
    // 移除旧的高亮（清理）
    document.querySelectorAll('.card.search-highlight').forEach(function(c){ if(c!==target) c.classList.remove('search-highlight'); });
    setTimeout(function(){ target.classList.remove('search-highlight'); }, 3000);
  }, 300);
}


  function switchTab(name){
  document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active',t.dataset.tab===name));
  document.querySelectorAll('.tab-panel').forEach(p=>p.classList.toggle('active',p.id==='tab-'+name));
  // 离开 QA 页时停止质检进度轮询，避免切走后仍在后台每 1.5s 打请求
  if(name!=='qa' && typeof qa2StopPolling==='function') qa2StopPolling();
  if(name==='fenji'){
    loadFenjiProjects();
    if(typeof fjUpdateTplBadge==='function')fjUpdateTplBadge();
    if(typeof fjUpdateTargetBadge==='function')fjUpdateTargetBadge();
  }
  if(name==='qa'){ loadQAProjects(); if(typeof loadQASummary==='function') loadQASummary(); }
  if(name==='nameplate' && typeof loadNameplateTab==='function'){ loadNameplateTab(); }
  if(name==='settings')loadConfig();
}

/* ============ Dashboard ============ */
function getStepIndex(status){
  const map={
    fenji:0, 分集:0, 分集中:0,
    jianji:1, 剪辑:1, 剪辑中:1,
    shenhe:2, 审核:2, 审核中:2,
    xiugai:3, 修改:3, 修改中:3,
    jiaofu:4, 交付:4, 交付中:4, 待交付:4,
    zhijian:5, 质检:5, 待质检:5, 质检中:5,
    wancheng:6, 完成:6, 已完成:6
  };
  if(!status)return -1;
  const key=String(status).trim();
  if(map[key]!==undefined)return map[key];
  const lk=key.toLowerCase();
  if(map[lk]!==undefined)return map[lk];
  // 包含匹配
  if(key.includes('分集'))return 0;
  if(key.includes('剪辑'))return 1;
  if(key.includes('审核'))return 2;
  if(key.includes('修改'))return 3;
  if(key.includes('交付'))return 4;
  if(key.includes('质检'))return 5;
  if(key.includes('完成'))return 6;
  return -1;
}
const WF_STATUS_OPTIONS = [
  {v:'', label:'— 未设置 —', cls:'default'},
  {v:'分集中', label:'📋 分集中', cls:'fenji'},
  {v:'剪辑中', label:'✂️ 剪辑中', cls:'jianji'},
  {v:'审核中', label:'👀 审核中', cls:'shenhe'},
  {v:'修改中', label:'✏️ 修改中', cls:'xiugai'},
  {v:'交付中', label:'📦 交付中', cls:'jiaofu'},
  {v:'待交付', label:'📦 待交付', cls:'daijiaofu'},
  {v:'待质检', label:'🔍 待质检', cls:'zhijian'},
  {v:'质检中', label:'🔍 质检中', cls:'zhijian'},
  {v:'已完成', label:'✅ 已完成', cls:'completed'},
];
function getBadge(status){
  if(!status)return{cls:'default',text:'未设置'};
  const s=String(status);
  for(const opt of WF_STATUS_OPTIONS){
    if(opt.v && s===opt.v)return{cls:opt.cls, text:opt.label};
  }
  if(s.includes('完成'))return{cls:'completed',text:s};
  return{cls:'default',text:s};
}
function workflowHTML(currentStep){
  const step=getStepIndex(currentStep);
  let html='<div class="workflow"><div class="wf-steps"><div class="wf-line"><div class="wf-line-fill" style="width:'+(step/(WF_STEPS.length-1)*100)+'%"></div></div>';
  WF_STEPS.forEach((label,i)=>{
    let cls='pending',num=i+1;
    if(i<step){cls='done';num='✓';}else if(i===step){cls='active';num=i+1;}
    html+=`<div class="wf-step"><div class="wf-dot ${cls}">${num}</div><div class="wf-label">${label}</div></div>`;
  });
  html+='</div></div>';return html;
}
function qaBadgeHTML(qa){
  if(!qa||qa.status===undefined||qa.status===null)return'<span class="qa-badge pending">⚪ 未质检</span>';
  const q=String(qa.status).toLowerCase();
  if(q==='pass'||q==='ok'||q==='passed')return'<span class="qa-badge pass">🟢✅ 全部通过</span>';
  if(q==='warn'||q==='warning')return`<span class="qa-badge warn">🟡⚠️ ${qa.count||qa.warnings||1}</span>`;
  if(q==='fail'||q==='error')return`<span class="qa-badge fail">🔴❌ ${qa.count||qa.failed||1}</span>`;
  return`<span class="qa-badge pending">${qa.status}</span>`;
}
function assignSummaryHTML(proj){
  const plan=proj.episode_plan||proj.episodes_plan||{};
  const byEditor={};
  if(plan&&typeof plan==='object'&&Object.keys(plan).length>0){
    Object.entries(plan).forEach(([ep,name])=>{if(!name)return;if(!byEditor[name])byEditor[name]=[];byEditor[name].push(parseInt(ep))});
  } else {
    const ep=proj.episodes||proj.episode_assign||[];
    if(ep&&ep.length){ep.forEach(e=>{const epn=e.episode_number||e.episode;if(!byEditor[e.editor])byEditor[e.editor]=[];byEditor[e.editor].push(epn)})}
  }
  if(Object.keys(byEditor).length===0)return'暂无分配';
  return Object.entries(byEditor).map(([name,eps])=>{
    eps.sort((a,b)=>a-b);const ranges=[];let s=eps[0],prev=eps[0];
    for(let i=1;i<eps.length;i++){if(eps[i]===prev+1)prev=eps[i];else{ranges.push(s===prev?`${s}`:`${s}-${prev}`);s=prev=eps[i]}}
    ranges.push(s===prev?`${s}`:`${s}-${prev}`);return`${name} ${ranges.join(',')}集`;
  }).join(' | ');
}
function renderActions(p){
  const s=String(p.custom_status||'');
  const btns=[];
  const has = function(zh){ return s.indexOf(zh) >= 0; };
  const pname = jsq(p.name);
  // 属性值转义（HTML 属性上下文，区别于 onclick 内的 JS 字符串）
  const pnameAttr = String(p.name||'').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
  // 关键判断：项目在组NAS存在吗？
  const groupExists = p.on_group !== false;  // 后端 production 项目会给 on_group 字段
  const hasProdPath = !!p.production_path;
  const syncStatus = p.sync_status || '';
  const needSync = hasProdPath && !groupExists;  // 有制作部路径但组NAS没有 → 必须同步

  if(!s){
    // 状态为空 → 默认给分集按钮（但同步按钮也可能加）
    if(needSync){
      btns.push(['📦 同步素材',`syncMaterial('${pname}')`,'btn-primary']);
    } else {
      btns.push(['📋 分集',`openFenjiFor('${pname}')`,'btn-primary']);
    }
  } else {
    if(has('分集中')||has('待分集'))btns.push(['📋 继续分集',`openFenjiFor('${pname}')`,'btn-primary']);
    else if(has('待质检')||has('质检中'))btns.push(['🔍 开始质检',`qaStartFor('${pname}')`,'btn-primary']);
    if(has('剪辑中')||has('审核中'))btns.push(['✏️ 标记修改',`updateStatus('${pname}','修改中')`,'']);
    if(has('修改中'))btns.push(['📦 待交付',`updateStatus('${pname}','待交付')`,'']);
    if(has('已交付')||has('交付中')||has('待交付'))btns.push(['📦 初版交付',`updateStatus('${pname}','待质检')`,'btn-primary']);
    if(has('已交付')||has('待交付'))btns.push(['🔍 去质检',`qaStartFor('${pname}')`,'']);
    // 同步按钮：仅当组NAS还没有这个项目 或 sync_status=pending 时显示
    if(needSync)btns.push(['📦 同步素材',`syncMaterial('${pname}')`,'btn-primary']);
  }
  if(syncStatus === 'syncing')btns.push(['⏳ 同步中...','void(0)','']);
    // 分秒帧按钮：仅一部海外 / 九部海外 的项目显示
  const _fmDepts = (window._fmConfig&&window._fmConfig.enabled_departments)||['AI漫剧一部海外','AI漫剧九部海外'];
  const _dept = p.department||'';
  if(_fmDepts.some(d => _dept.includes(d))){
    const _fmAttr = 'data-fm-proj="' + pnameAttr + '"';
    btns.push(['🔗 分秒帧',`openFenmiaozhen('${pname}')`,'fm-main',_fmAttr]);
    btns.push(['✏️',`editFenmiaozhenLink('${pname}')`,'','title="修改分秒帧链接"']);
  }
  if(btns.length===0)btns.push(['🔍 质检',`qaStartFor('${pname}')`,'']);
  btns.push(['📋 详情',`openProjectDetail('${pname}')`,'']);
  return btns.map(([label,fn,cls,extra])=>`<button class="btn btn-sm ${cls||''}" ${extra||''} onclick="${fn}">${label}</button>`).join('');
}
function renderStats(){
  // 优先用后端统一计算的概览统计（口径一致），不存在则本地兜底
  const os = (typeof window._overviewStats !== 'undefined' && window._overviewStats) || null;
  const nowMonth = new Date().getFullYear() + '-' + String(new Date().getMonth()+1).padStart(2,'0');

  let total, thisMonth, thisMonthDone, inProd;
  if (os && typeof os.total === 'number') {
    total = os.total;
    thisMonth = os.this_month;
    thisMonthDone = os.this_month_done;
    inProd = os.producing;
  } else {
    // 本地兜底计算（口径：制作中含分集中等所有进行中状态）
    const list = (typeof projects !== 'undefined' && Array.isArray(projects)) ? projects : [];
    total = list.length;
    const activeList = list.filter(p => {
      const s = String(p.custom_status || '').trim();
      const d = String(p.delivery_status || '').trim();
      const t = Number(p.total_episodes || 0);
      return s || (d && d !== 'pending') || t > 0;
    });
    const monthList = activeList.filter(p => p.project_month === nowMonth);
    thisMonth = monthList.length;
    thisMonthDone = monthList.filter(p => String(p.custom_status || '').trim() === '已完成').length;
    inProd = monthList.filter(p => { const s = String(p.custom_status || '').trim(); return !!s && s !== '已完成'; }).length;
  }

  $('statsRow').innerHTML=`
    <div class="stat-card" onclick="$('globalSearch').value='';$('filterStatus').value='';$('filterDept').value='';$('filterMonth').value='';renderDashboard()" style="cursor:pointer"><div class="stat-icon blue">📁</div><div><div class="stat-num">${total}</div><div class="stat-label">总项目</div></div></div>
    <div class="stat-card" onclick="$('filterMonth').value='${nowMonth}';$('filterStatus').value='';renderDashboard()" style="cursor:pointer"><div class="stat-icon" style="background:#fff3cd;color:#856404">📅</div><div><div class="stat-num">${thisMonth}</div><div class="stat-label">本月项目</div></div></div>
    <div class="stat-card" onclick="$('filterMonth').value='${nowMonth}';$('filterStatus').value='已完成';renderDashboard()" style="cursor:pointer"><div class="stat-icon green">✅</div><div><div class="stat-num">${thisMonthDone}</div><div class="stat-label">本月已完成</div></div></div>
    <div class="stat-card" onclick="$('filterMonth').value='${nowMonth}';$('filterStatus').value='';$('globalSearch').value='';renderDashboard()" style="cursor:pointer"><div class="stat-icon orange">🎬</div><div><div class="stat-num">${inProd}</div><div class="stat-label">制作中</div></div></div>`;
  renderOverviewCharts();
}

// ===== 首页概览图表（部门分布 + 工作流状态分布，仅当月项目）=====
function renderOverviewCharts(){
  const wrap = $('overviewCharts');
  if(!wrap) return;
  const allList = (typeof projects !== 'undefined' && Array.isArray(projects)) ? projects : [];
  const nowMonth = new Date().getFullYear() + '-' + String(new Date().getMonth()+1).padStart(2,'0');
  // 只统计当月项目（project_month == 当前月）
  const list = allList.filter(p => (p.project_month || '') === nowMonth);
  if(list.length === 0){ wrap.innerHTML=''; return; }

  // 部门分布
  const deptCount = {};
  list.forEach(p=>{ const d=(p.department||'未分部门'); deptCount[d]=(deptCount[d]||0)+1; });
  const deptArr = Object.entries(deptCount).sort((a,b)=>b[1]-a[1]);
  const deptMax = deptArr[0] ? deptArr[0][1] : 1;

  // 工作流状态分布（含未设置）
  const statusOrder = ['分集中','剪辑中','审核中','修改中','待交付','交付中','待质检','质检中','已完成'];
  const statusCount = {};
  list.forEach(p=>{ const s=(p.custom_status||'').trim()||'未设置'; statusCount[s]=(statusCount[s]||0)+1; });
  const statusArr = statusOrder.filter(s=>statusCount[s]).map(s=>[s,statusCount[s]])
    .concat(statusCount['未设置'] ? [['未设置',statusCount['未设置']]] : [])
    .sort((a,b)=>b[1]-a[1]);
  const statusMax = statusArr[0] ? statusArr[0][1] : 1;

  const statusColor = {
    '分集中':'#8e44ad','剪辑中':'#2980b9','审核中':'#16a085','修改中':'#e67e22',
    '待交付':'#d35400','交付中':'#c0392b','待质检':'#f39c12','质检中':'#9b59b6',
    '已完成':'#27ae60','未设置':'#bdc3c7'
  };

  function barChart(title, data, max, colorFn){
    const rows = data.map(([label, val])=>{
      const w = max>0 ? Math.max(3, Math.round(val/max*100)) : 0;
      const c = colorFn(label);
      return `<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
        <div style="width:90px;font-size:12px;color:#4a4a4a;text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${label}</div>
        <div style="flex:1;height:18px;background:#f0f2f5;border-radius:4px;overflow:hidden"><div style="width:${w}%;height:100%;background:${c};border-radius:4px;transition:width .4s"></div></div>
        <div style="width:30px;font-size:12px;font-weight:600;color:#333">${val}</div>
      </div>`;
    }).join('');
    return `<div style="background:#fff;border:1px solid var(--border);border-radius:12px;padding:16px 18px;box-shadow:var(--shadow)">
      <div style="font-weight:700;font-size:14px;margin-bottom:12px">${title}</div>
      ${rows}
    </div>`;
  }

  wrap.innerHTML =
    barChart('🏢 部门项目分布（本月）', deptArr, deptMax, ()=>'#5c6bc0') +
    barChart('📊 工作流状态分布（本月）', statusArr, statusMax, l=>statusColor[l]||'#95a5a6');
}

// ===== 工作量 / 数据看板（可指定容器，月度报告复用） =====
// 工作量看板排序状态
let _wlSortKey = 'assigned';
let _wlSortDir = 1;
function workloadSort(val){
  if(val === 'assigned'){ _wlSortKey='assigned'; _wlSortDir=1; }
  else if(val === 'assigned_asc'){ _wlSortKey='assigned'; _wlSortDir=-1; }
  else if(val === 'status'){ _wlSortKey='status'; _wlSortDir=1; }
  else if(val === 'name'){ _wlSortKey='name'; _wlSortDir=1; }
  // 重新渲染所有工作量看板（数据洞察/月度报告共用）
  ['workloadBoard','reportWorkloadBoard'].forEach(function(id){
    if(document.getElementById(id)) renderWorkloadBoard(id);
  });
}
async function renderWorkloadBoard(containerId){
  const board = document.getElementById(containerId || 'workloadBoard');
  if(!board) return;
  try{
    const d = await api('GET', '/api/stats/dashboard');
    if(!d || !d.ok) return;
    const editors = d.editors || [];
    const dept = d.dept_stats || [];
    const trend = d.trend || [];
    const summary = d.summary || {};

    // === 剪辑师工作量看板（全宽卡片网格 + 排序） ===
    let html = '<div style="margin-top:20px">';

    // 排序状态（全局，点下拉切换）
    const sortKey = _wlSortKey || 'assigned';
    const sortDir = _wlSortDir === -1 ? -1 : 1;
    // 排序后的编辑器列表：assigned 默认从高到低(dir=1)，assigned_asc 从低到高(dir=-1)
    const sortedEditors = editors.slice().sort(function(a,b){
      let va, vb;
      if(sortKey === 'name'){ va=String(a.name||''); vb=String(b.name||''); return sortDir*(va<vb?-1:va>vb?1:0); }
      if(sortKey === 'status'){
        const rank = function(e){ if(!(e.quota||0)) return 1; return (e.assigned||0)>=(e.quota||0)?0:2; };
        const r = rank(a)-rank(b); if(r!==0) return r; // 达标在前
        va=a.assigned||0; vb=b.assigned||0; return vb-va; // 同状态按集数从高到低
      }
      va=a.assigned||0; vb=b.assigned||0;
      return sortDir===1 ? (vb-va) : (va-vb); // assigned: dir1=高到低, dir-1=低到高
    });

    const maxAssigned = editors.length ? editors[0].assigned : 1;
    const editorCards = sortedEditors.map(function(e){
      const assigned = e.assigned || 0;
      const quota = e.quota || 0;
      const reached = quota>0 && assigned>=quota;
      const gap = quota>0 ? Math.max(0, quota-assigned) : 0;
      const qpct = quota>0 ? Math.min(100, Math.round(assigned/quota*100)) : (maxAssigned>0?Math.round(assigned/maxAssigned*100):0);
      const barColor = reached ? '#34c759' : '#ff3b30';
      let state;
      if(quota<=0) state = '<span style="font-size:11px;color:#86868b">组长</span>';
      else if(reached) state = '<span style="color:#34c759;font-weight:700">✓ 达标</span>';
      else state = `<span style="color:#ff3b30;font-weight:700">✗ 差${gap}集</span>`;
      return `<div style="border:1px solid ${reached?'#c8f0d6':'#ffd7d7'};background:${reached?'#f6fff8':'#fff7f7'};border-radius:10px;padding:10px 12px;display:flex;flex-direction:column;gap:5px;cursor:pointer;transition:transform .08s" title="点击查看「${htm(e.name)}」的集数明细" onclick="showEditorDetail('${jsq(e.name)}')" onmouseover="this.style.transform='scale(1.02)'" onmouseout="this.style.transform=''">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span style="font-weight:700;font-size:13px" title="${htm(e.name)}">${htm(e.name)}</span>
          <span style="font-size:11px;color:#86868b">${e.projects}部</span>
        </div>
        <div style="display:flex;align-items:baseline;gap:4px">
          <span style="font-size:20px;font-weight:800;color:${reached?'#1a8a3a':'#c5221f'}">${assigned}</span>
          <span style="font-size:11px;color:#86868b">集${quota>0?' / '+quota+'提':''}</span>
        </div>
        <div style="height:7px;background:#f0f2f5;border-radius:4px;overflow:hidden;position:relative">
          <div style="width:${qpct}%;height:100%;background:${barColor};border-radius:4px"></div>
          ${quota>0?`<div style="position:absolute;top:-1px;bottom:-1px;left:100%;width:2px;background:#ff9500" title="卡点${quota}"></div>`:''}
        </div>
        <div style="font-size:11px">${state}</div>
      </div>`;
    }).join('');

    // 排序下拉
    const sortOpts = [
      ['assigned','按集数','⬇ 从高到低'],
      ['assigned_asc','按集数','⬆ 从低到高'],
      ['status','按达标状态','达标在前'],
      ['name','按姓名','A-Z'],
    ];
    const sortSelect = '<select id="wlSortSelect" onchange="workloadSort(this.value)" style="padding:5px 8px;border:1px solid var(--border,#e5e5ea);border-radius:6px;font-size:12px">'
      + sortOpts.map(function(o){
          const selVal = (sortKey==='assigned'&&sortDir===1)?'assigned':(sortKey==='assigned'?'assigned_asc':sortKey);
          return '<option value="'+o[0]+'"'+(selVal===o[0]?' selected':'')+'>'+o[1]+' '+o[2]+'</option>';
        }).join('')
      + '</select>';

    html += `<div style="background:#fff;border:1px solid var(--border);border-radius:12px;padding:16px 18px;box-shadow:var(--shadow)">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;flex-wrap:wrap;gap:8px">
        <div style="font-weight:700;font-size:14px">👥 剪辑师工作量（本月）</div>
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
          <span style="font-size:11px;color:#86868b">共 ${summary.total_editors||0} 人 · ${summary.total_assigned||0} 集 · <span style="color:#ff3b30">红=未达</span> · <span style="color:#34c759">绿=达标</span> · <span style="color:#ff9500">橙=卡点</span></span>
          ${sortSelect}
        </div>
      </div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px">${editorCards || '<div style="color:#86868b;padding:20px;text-align:center">暂无分集数据</div>'}</div>
    </div>`;

    html += '</div>';

    // === 产能趋势（近6个月） ===
    if(trend.length){
      const tMax = Math.max(...trend.map(x=>Math.max(x.total,x.done,x.delivered,1)));
      const trendHtml = trend.map(function(t){
        const wTotal = Math.round(t.total/tMax*100);
        const wDone = Math.round(t.done/tMax*100);
        const wDel = Math.round(t.delivered/tMax*100);
        return `<div style="flex:1;min-width:80px;display:flex;flex-direction:column;align-items:center;gap:4px">
          <div style="display:flex;align-items:flex-end;height:120px;gap:3px">
            <div title="立项 ${t.total}" style="width:16px;background:#5c6bc0;border-radius:3px 3px 0 0;height:${wTotal}%"></div>
            <div title="完成 ${t.done}" style="width:16px;background:#27ae60;border-radius:3px 3px 0 0;height:${wDone}%"></div>
            <div title="交付 ${t.delivered}" style="width:16px;background:#3498db;border-radius:3px 3px 0 0;height:${wDel}%"></div>
          </div>
          <div style="font-size:11px;color:#666">${t.month.slice(5)}月</div>
          <div style="font-size:10px;color:#999">${t.total}·${t.done}·${t.delivered}</div>
        </div>`;
      }).join('');
      html += `<div style="background:#fff;border:1px solid var(--border);border-radius:12px;padding:16px 18px;box-shadow:var(--shadow);margin-top:16px">
        <div style="font-weight:700;font-size:14px;margin-bottom:12px">📈 产能趋势（近6个月）</div>
        <div style="display:flex;justify-content:space-around;margin-bottom:8px">${trendHtml}</div>
        <div style="display:flex;gap:14px;justify-content:center;font-size:11px;color:#86868b">
          <span><span style="display:inline-block;width:10px;height:10px;background:#5c6bc0;border-radius:2px;margin-right:4px"></span>立项</span>
          <span><span style="display:inline-block;width:10px;height:10px;background:#27ae60;border-radius:2px;margin-right:4px"></span>完成</span>
          <span><span style="display:inline-block;width:10px;height:10px;background:#3498db;border-radius:2px;margin-right:4px"></span>交付</span>
        </div>
      </div>`;
    }

    board.innerHTML = html;
  }catch(e){
    board.innerHTML = '';
  }
}

// ===== 点击剪辑师卡片：弹出集数明细（按项目分组的集号构成）=====
// 支持两种形态：完整弹窗 / 紧凑浮窗（跳转项目卡片后保留，可拖动、可展开）
async function showEditorDetail(editorName){
  try{
    const d = await api('GET', '/api/stats/dashboard');
    if(!d || !d.ok){ toast('加载明细失败', 'error'); return; }
    const editors = d.editors || [];
    const e = editors.find(function(x){ return x.name === editorName; });
    if(!e){ toast('未找到「' + editorName + '」的明细', 'warning'); return; }

    // 明细行：每个项目一行，展示集号构成
    const detail = e.project_detail || [];
    const buildRows = function(){
      if(detail.length === 0){
        return '<div style="color:#86868b;padding:14px;text-align:center;font-size:13px">暂无集数明细（该剪辑师当月未分配分集）</div>';
      }
      return detail.map(function(pd){
        const eps = pd.episodes || [];
        const segs = [];
        const sorted = eps.slice().sort(function(a,b){ return a-b; });
        sorted.forEach(function(n, i){
          const prev = sorted[i-1];
          if(i===0 || n !== prev+1){ segs.push([n, n]); }
          else { segs[segs.length-1][1] = n; }
        });
        const segText = segs.map(function(s){ return s[0]===s[1] ? s[0] : s[0]+'-'+s[1]; }).join('、');
        return '<div style="padding:9px 2px;border-bottom:1px solid #f0f2f5">'
          + '<div style="display:flex;justify-content:space-between;align-items:center;gap:8px">'
            + '<div style="font-weight:600;font-size:12.5px;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:pointer;color:var(--blue,#1d4ed8);text-decoration:underline" title="点击前往项目卡片「'+htm(pd.project)+'」，明细窗口将保留为右下角浮窗" onclick="event.stopPropagation();jumpToProjectKeepFloat(\''+jsq(pd.project)+'\')">📁 '+htm(pd.project)+'</div>'
            + '<span style="font-size:11px;color:#2E7D32;font-weight:700;white-space:nowrap">'+pd.count+'集</span>'
          + '</div>'
          + '<div style="font-size:12px;color:#555;margin-top:3px;word-break:break-all">集号：<b>'+htm(segText)+'</b></div>'
        + '</div>';
      }).join('');
    };

    // 头部分（标题 + 统计行）
    const headerHtml = function(){
      return '<div style="padding:14px 16px;background:linear-gradient(135deg,#eef4ff,#dbe8ff);display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #dbe3f0">'
        + '<div style="font-weight:700;font-size:14px">👤 '+htm(e.name)+' — 集数明细（本月 '+(d.month||'')+'）</div>'
        + '<button onclick="closeEditorDetail(this)" style="border:none;background:none;font-size:18px;cursor:pointer;color:#666;line-height:1" title="关闭">×</button>'
      + '</div>'
      + '<div style="padding:6px 16px;border-bottom:1px solid #f0f2f5;font-size:12px;color:#86868b;display:flex;gap:14px;flex-wrap:wrap">'
        + '<span>总集数：<b style="color:#c5221f">'+(e.assigned||0)+'</b> 集</span>'
        + '<span>涉及项目：<b>'+(e.projects||0)+'</b> 部</span>'
        + (e.quota?'<span>提成卡点：<b style="color:#ff9500">'+e.quota+'</b> 集</span>':'')
        + '<span style="color:#aaa">点击项目 → 保留本窗并跳转卡片</span>'
      + '</div>';
    };
    // 列表滚动区：min-height:0 让 flex 子项可收缩形成滚动；onwheel 阻止滚轮穿透主页面
    const listHtml = '<div class="editor-detail-list" style="padding:10px 16px;overflow-y:auto;flex:1;min-height:0;-webkit-overflow-scrolling:touch" onwheel="editorDetailWheel(event)">'+buildRows()+'</div>';

    // 创建浮窗容器（初始即完整形态）
    const wrap = document.createElement('div');
    wrap.id = 'editorDetailFloat';
    wrap.style.cssText = 'position:fixed;z-index:21000;width:460px;max-width:92vw;display:flex;flex-direction:column;box-shadow:0 10px 34px rgba(0,0,0,.25);border-radius:12px;overflow:hidden;background:#fff;border:1px solid #dbe3f0';
    // 打开时居中显示完整明细
    wrap.style.top = '50%';
    wrap.style.left = '50%';
    wrap.style.transform = 'translate(-50%,-50%)';
    wrap.style.height = '70vh';
    wrap.style.maxHeight = '82vh';
    wrap.innerHTML = '<div class="editor-detail-float-body" style="display:flex;flex-direction:column;height:100%;min-height:0">'
      + headerHtml() + listHtml
      + '<div style="padding:10px 16px;border-top:1px solid #eee;display:flex;justify-content:space-between;align-items:center;gap:8px">'
        + '<span style="font-size:11px;color:#aaa">⬅ 拖动边缘可移动本窗</span>'
        + '<div style="display:flex;gap:8px">'
          + '<button class="btn btn-sm" onclick="floatEditorDetailToggleMin()" title="收起为小浮窗">⬇ 收起</button>'
          + '<button class="btn btn-sm btn-primary" onclick="closeEditorDetail(this)">关闭</button>'
        + '</div>'
      + '</div>'
      + '</div>';
    document.body.appendChild(wrap);

    // 启用拖动（标题栏）
    makeEditorDetailDraggable(wrap);
  }catch(err){
    toast('❌ 加载明细失败: ' + err.message, 'error');
  }
}

// 拖动浮窗
function makeEditorDetailDraggable(el){
  let dragging = false, offX = 0, offY = 0;
  el.addEventListener('mousedown', function(e){
    // 只在标题栏区域拖动
    if(!e.target.closest('.editor-detail-float-body') && !(e.target === el)) return;
    // 排除点击按钮/链接
    if(e.target.closest('button,a,input')) return;
    dragging = true;
    el.style.transform = 'none';
    el.style.transition = 'none';
    offX = e.clientX - el.offsetLeft;
    offY = e.clientY - el.offsetTop;
    function mv(ev){
      if(!dragging) return;
      el.style.left = (ev.clientX - offX) + 'px';
      el.style.top = (ev.clientY - offY) + 'px';
    }
    function up(){ dragging = false; document.removeEventListener('mousemove', mv); document.removeEventListener('mouseup', up); }
    document.addEventListener('mousemove', mv);
    document.addEventListener('mouseup', up);
  });
}

// 关闭明细（浮窗/完整）
function closeEditorDetail(btn){
  const w = document.getElementById('editorDetailFloat');
  if(w) w.remove();
}

// 阻止滚轮事件穿透到主页面：
//  - 列表内部可继续滚动（原生平滑滚动）时，仅阻止事件冒泡
//  - 列表已到滚动边界时，阻止默认的滚动链（scroll chaining），避免滚轮滚动主页面
function editorDetailWheel(e){
  const el = e.currentTarget;
  if(!el) return;
  const canScroll = el.scrollHeight > el.clientHeight;
  if(canScroll){
    // 列表本身可滚动：让原生滚动生效，仅阻断事件向主页面传播
    e.stopPropagation();
    return;
  }
  // 列表不可滚动或已到边界：阻止穿透到主页面
  e.preventDefault();
  e.stopPropagation();
}

// 跳转项目卡片，但保留明细浮窗
function jumpToProjectKeepFloat(name){
  // 把完整浮窗切换为右下角小浮窗（不遮页面）
  const w = document.getElementById('editorDetailFloat');
  if(w){
    // 记录原始内容引用（从当前 DOM 读取即可，无需重建）
    w.style.transform = 'none';
    w.style.top = '';
    w.style.left = '';
    w.style.bottom = '16px';
    w.style.right = '16px';
    w.style.width = '340px';
    w.style.height = '40vh';
    w.style.maxHeight = '40vh';
    // 切换为可展开的紧凑视图
    const body = w.querySelector('.editor-detail-float-body');
    if(body){
      // 保持 flex 布局 + 固定高度，保证内部列表区形成滚动容器
      body.style.height = '100%';
      body.style.minHeight = '0';
    }
    // 标记为迷你态，供展开按钮判断
    w.dataset.mode = 'mini';
    // 替换底部操作为"展开"按钮
    const foot = w.querySelector('.editor-detail-float-body > div:last-child');
    if(foot){
      foot.innerHTML = '<span style="font-size:11px;color:#aaa">集数明细已保留</span>'
        + '<div style="display:flex;gap:8px">'
        + '<button class="btn btn-sm" onclick="floatEditorDetailToggleMin()">↕ 展开</button>'
        + '<button class="btn btn-sm" onclick="closeEditorDetail(this)">✕</button>'
        + '</div>';
    }
  }
  // 跳转到项目卡片（与搜索逻辑一致）
  jumpToProject(name);
}

// 在迷你浮窗与完整浮窗之间切换
function floatEditorDetailToggleMin(){
  const w = document.getElementById('editorDetailFloat');
  if(!w) return;
  const isMini = w.dataset.mode === 'mini';
  if(isMini){
    // 展开为完整明细
    w.dataset.mode = 'full';
    w.style.width = '460px';
    w.style.maxHeight = '82vh';
    w.style.height = '70vh';
    // 恢复底部按钮
    const foot = w.querySelector('.editor-detail-float-body > div:last-child');
    if(foot){
      foot.innerHTML = '<span style="font-size:11px;color:#aaa">⬅ 拖动边缘可移动本窗</span>'
        + '<div style="display:flex;gap:8px">'
          + '<button class="btn btn-sm" onclick="floatEditorDetailToggleMin()">⬇ 收起</button>'
          + '<button class="btn btn-sm btn-primary" onclick="closeEditorDetail(this)">关闭</button>'
        + '</div>';
    }
  } else {
    // 收起为小浮窗
    w.dataset.mode = 'mini';
    w.style.width = '340px';
    w.style.height = '40vh';
    w.style.maxHeight = '40vh';
    const foot = w.querySelector('.editor-detail-float-body > div:last-child');
    if(foot){
      foot.innerHTML = '<span style="font-size:11px;color:#aaa">集数明细已保留</span>'
        + '<div style="display:flex;gap:8px">'
        + '<button class="btn btn-sm" onclick="floatEditorDetailToggleMin()">↕ 展开</button>'
        + '<button class="btn btn-sm" onclick="closeEditorDetail(this)">✕</button>'
        + '</div>';
    }
  }
}

function getDeptStyle(dept){
  if(!dept)return '';
  const map={
    'AI漫剧二部':'background:#e3f2fd;color:#1565c0;border:1px solid #bbdefb',
    'AI漫剧六部':'background:#fff3e0;color:#e65100;border:1px solid #ffe0b2',
    'AI漫剧一部海外':'background:#f3e5f5;color:#7b1fa2;border:1px solid #e1bee7',
    'AI漫剧九部海外':'background:#e8f5e9;color:#2e7d32;border:1px solid #c8e6c9',
    '组内NAS':'background:#fce4ec;color:#c2185b;border:1px solid #f8bbd0',
    '已完成':'background:#f5f5f5;color:#616161;border:1px solid #e0e0e0',
  };
  for(const[k,v]of Object.entries(map)){if(dept.includes(k))return v;}
  return 'background:#f0f0f5;color:#555;border:1px solid #e0e0e0';
}

function projectCardHTML(p){
  const badge=getBadge(p.custom_status);
  const _st=p.custom_status||'';
  const _hasEdit=_st==='剪辑中'||_st==='审核中'||_st==='修改中'||_st==='待质检'||_st==='质检中'||_st==='待交付'||_st==='交付中';
  const _hasDeliver=_st==='审核中'||_st==='修改中'||_st==='待质检'||_st==='质检中'||_st==='待交付'||_st==='交付中'||_st==='已交付'||_st==='已完成';
  const m=p.material_sync===true?'<span class="sr-val">✅ 已同步</span>':p.material_sync===false?'<span class="sr-val">⏳ 待同步</span>':_hasEdit?'<span class="sr-val">✅ 已同步</span>':'<span class="sr-val">—</span>';
  const d=p.delivered===true?'<span class="sr-val">✅ 已交付</span>':p.delivered===false?'<span class="sr-val">⏳ 待交付</span>':_hasDeliver?'<span class="sr-val">✅ 已交付</span>':'<span class="sr-val">—</span>';
  const qa=qaBadgeHTML(p.qa_status);
    const dept=p.department?`<span class="dept-badge" style="${getDeptStyle(p.department)}">${p.department}</span>`:'';

  // === 进度条 — 先用占位，fetchEpisodeStatus 回来后更新 ===
  const total = p.total_episodes || 0;
  const progressId = 'prog-' + p.name.replace(/[^a-zA-Z0-9_]/g,'_');
  let progressHTML = '';
  // 审核中/修改中不显示输出进度（此时关注的是成片验收/修改，而非剪辑进度）
  const _hideProgress = (_st === '审核中' || _st === '修改中');
  if (total > 0 && !_hideProgress) {
    progressHTML = `<div class="card-progress" id="${progressId}">
      <div class="card-progress-bar"><div class="card-progress-fill" style="width:0%"></div></div>
      <div class="card-progress-text"><span>输出进度（扫描目录中...）</span><span>— / ${total} 集</span></div>
    </div>`;
  }

  // === 同步进度条 — syncing 时显示 ===
  const syncProgId = 'sync-prog-' + p.name.replace(/[^a-zA-Z0-9_]/g,'_');
  let syncProgressHTML = '';
  if (p.sync_status === 'syncing') {
    const sp = p.sync_progress || '准备中...';
    const m = sp.match(/^(\d+)%\s*(.*)$/);
    const pct = m ? parseInt(m[1]) : 0;
    const label = m ? m[2] : sp;
    syncProgressHTML = `<div class="card-progress card-sync-progress" id="${syncProgId}">
      <div class="card-progress-bar"><div class="card-progress-fill sync-fill" style="width:${pct}%"></div></div>
      <div class="card-progress-text"><span>📦 ${label}</span><span class="sync-pct">${pct}%</span></div>
    </div>`;
  }

  // === 智能打开按钮 ===
  const pname = jsq(p.name);
  // DOM id / 属性用安全标识（jsq 转义后的内容不适合做 id，故单独从原始名生成）
  const safeId = String(p.name||'').replace(/[^a-zA-Z0-9_]/g,'_');
  const pnameAttr = String(p.name||'').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
  // 空壳项目（无状态+未交付+0集）强制不显示月份，即使有脏数据
  const _s = String(p.custom_status||'').trim(), _d = String(p.delivery_status||'').trim(), _t = Number(p.total_episodes||0);
  const _isShell = !_s && (!_d || _d==='pending') && _t===0;
  const month = (!_isShell && p.project_month)
    ? `<span class="dept-badge" onclick="setProjectMonth('${pname}')" style="background:#fff3cd;color:#856404;border:1px solid #ffe08a;cursor:pointer" title="点击修改月份">📅 ${p.project_month}</span>`
    : (_isShell ? '' : `<span class="dept-badge" onclick="setProjectMonth('${pname}')" style="background:#f0f0f5;color:#999;border:1px dashed #ccc;cursor:pointer" title="点击设置月份">📅 未设月份</span>`);
  let openBtns = '';
  const isGroup = p.project_type === 'group' || p.source_path;
  const hasGroup = !!p.group_path;
  const hasProd = !!p.production_path;
  const status = p.custom_status || '';

  if (hasGroup && isGroup) {
    openBtns += `<button class="btn btn-sm" onclick="openSmart('${pname}','group')">📁 组内NAS</button>`;
  } else if (hasProd) {
    openBtns += `<button class="btn btn-sm" onclick="openSmart('${pname}','prod')">📁 打开项目</button>`;
  }
  if (hasProd && (p.project_type === 'production' || p.has_production_match)) {
    let which = 'prod';
    if (status === '修改中') which = 'dest_revision';
    else if (status === '剪辑中' || status === '审核中') which = 'dest';
    openBtns += `<button class="btn btn-sm" onclick="openSmart('${pname}','${which}')">🏢 制作部</button>`;
  }
  openBtns += `<button class="btn btn-sm" onclick="toggleEpisodesPanel('${pname}', this)">📺 分集</button>`;
  openBtns += `<button class="btn btn-sm" onclick="refreshProjectStatus('${pname}', this)" title="扫描目录刷新进度">🔄 刷新</button>`;

  if (status === '修改中') {

  }

  const epPanel = `<div class="card-episodes-panel" id="ep-panel-${safeId}"></div>`;
  const epSummaryBox = `<div class="ep-missing-summary" data-ep-summary="${pnameAttr}"></div>`;

  const bulkChk = window._bulkMode
    ? `<input type="checkbox" class="bulk-card-chk" data-pname="${pnameAttr}" onchange="updateBulkBar()" title="选择此项目">`
    : '';
  return`<div class="card">
    <div class="card-head">
      <div class="card-title-line">${bulkChk}<span class="card-title-name" title="${pnameAttr}" data-project-name="${pnameAttr}">${p.name}</span><button class="btn btn-sm ep-search-btn" onclick="searchEpisodeEditor('${jsq(p.name)}')" title="按集号检索该集剪辑师">🔍 查剪辑</button></div>
      <div class="card-meta-line">${dept}${month}${(() => {
  const cur = p.custom_status || '';
  const optsHtml = WF_STATUS_OPTIONS.map(o =>
    `<option value="${o.v}" ${o.v===cur?'selected':''}>${o.label}</option>`
  ).join('');
  return `<select class="badge editable-badge ${badge.cls}" onchange="onStatusChange('${jsq(p.name)}', this)" title="点击修改项目状态">${optsHtml}</select>`;
})()}</div>
    </div>
    ${workflowHTML(p.custom_status)}
    ${syncProgressHTML}
    ${progressHTML}
    ${epSummaryBox}
    ${epPanel}
    <div class="status-rows">
      <div class="status-row"><span class="sr-label">素材同步</span>${m}</div>
      <div class="status-row"><span class="sr-label">成片交付</span>${d}</div>
      <div class="status-row"><span class="sr-label">视频质检</span>${qa}</div>
    </div>
    <div class="card-todo" id="ctodo-trigger-${pname.replace(/[^a-zA-Z0-9_]/g,'_')}" onclick="cardToggleTodo('${pname}')">📌 待办 <span class="ctodo-count"></span></div>
    <div class="assign-summary">👥 ${assignSummaryHTML(p)}</div>
    <div class="card-actions"><div class="card-open-group">${openBtns}</div>${renderActions(p)}</div>
  </div>`;
}

// ===== 项目卡片：按集号快速检索该集剪辑师 =====
var _epSearchModal = null;
function searchEpisodeEditor(projectName){
  // 从当前项目列表里找该项目对象（含 episode_plan）
  var proj = null;
  try{
    var list = window.__projectsCache || [];
    if(!list || !list.length){
      // 从 DOM 拿不到，直接先请求一次项目列表缓存到全局
      proj = null;
    } else {
      proj = list.find(function(x){ return x.name === projectName; }) || null;
    }
  }catch(_){ proj = null; }
  // 若内存无缓存，则异步拉取后再弹
  if(!proj){
    api('GET', '/api/projects').then(function(d){
      var flat = (d.production || []).concat(d.group_all || []);
      window.__projectsCache = flat;
      var p2 = flat.find(function(x){ return x.name === projectName; }) || null;
      _openEpSearchModal(projectName, p2 ? (p2.episode_plan || p2.episodes_plan || {}) : {});
    }).catch(function(){ _openEpSearchModal(projectName, {}); });
    return;
  }
  _openEpSearchModal(projectName, proj.episode_plan || proj.episodes_plan || {});
}

function _parsePlan(plan){
  var out = {};
  try{
    if(!plan) return out;
    var p = (typeof plan === 'string') ? JSON.parse(plan) : plan;
    if(p && typeof p === 'object' && !Array.isArray(p)){
      Object.entries(p).forEach(function(kv){
        var ep = kv[0].trim();
        var ed = String(kv[1] || '').trim();
        if(ed) out[ep] = ed;
      });
    }
  }catch(_){}
  return out;
}

function _openEpSearchModal(projectName, plan){
  var parsed = _parsePlan(plan);
  var total = Object.keys(parsed).length;

  if(_epSearchModal){ _epSearchModal.remove(); _epSearchModal = null; }
  var overlay = document.createElement('div');
  overlay.className = 'modal-overlay active';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.4);z-index:1000;display:flex;align-items:center;justify-content:center';

  var resultBoxId = 'ep-search-result';
  overlay.innerHTML = '<div style="background:#fff;border-radius:12px;width:440px;overflow:hidden;box-shadow:0 8px 30px rgba(0,0,0,.2)">'
    + '<div style="padding:14px 18px;background:linear-gradient(135deg,#e3f2fd,#bbdefb);font-weight:700;font-size:14px">🔍 检索集数剪辑师</div>'
    + '<div style="padding:16px 18px">'
      + '<div style="font-size:12px;color:#86868b;margin-bottom:6px;word-break:break-all">项目：<b>' + htm(projectName) + '</b>' + (total>0 ? '（已登记 '+total+' 集）' : '（未登记分集数据）') + '</div>'
      + '<div style="display:flex;gap:8px;align-items:center">'
        + '<input id="ep-search-input" type="number" min="1" placeholder="输入集号，如 12" '
        +   'style="flex:1;padding:8px 10px;border:1px solid #ccc;border-radius:6px;font-size:13px" '
        +   'onkeydown="if(event.key===\'Enter\')doEpSearch(\'' + jsq(projectName) + '\',this.value,\'' + resultBoxId + '\')">'
        + '<button class="btn btn-sm btn-primary" onclick="doEpSearch(\'' + jsq(projectName) + '\',document.getElementById(\'ep-search-input\').value,\'' + resultBoxId + '\')" style="padding:8px 14px">查询</button>'
      + '</div>'
      + '<div id="' + resultBoxId + '" style="margin-top:12px;min-height:20px"></div>'
      + (total>0 ? '<div style="margin-top:12px;border-top:1px solid #eee;padding-top:10px;font-size:11px;color:#86868b">也可直接按剪辑师查：<span id="ep-search-editor-hint" style="word-break:break-all"></span></div>' : '')
    + '</div>'
    + '<div style="padding:12px 18px;border-top:1px solid #eee;display:flex;justify-content:flex-end;gap:8px">'
      + '<button class="btn btn-sm" onclick="this.closest(\'.modal-overlay\').remove()">关闭</button>'
    + '</div>'
  + '</div>';

  // 将解析后的 plan 存到全局，供 doEpSearch 使用
  window.__epSearchPlan = parsed;
  window.__epSearchProject = projectName;

  document.body.appendChild(overlay);
  _epSearchModal = overlay;
  setTimeout(function(){
    var inp = document.getElementById('ep-search-input');
    if(inp) inp.focus();
    // 生成"剪辑师→集数"提示
    var byEditor = {};
    Object.entries(parsed).forEach(function(kv){ var ed=kv[1]; if(!byEditor[ed])byEditor[ed]=[]; byEditor[ed].push(kv[0]); });
    var hint = document.getElementById('ep-search-editor-hint');
    if(hint && Object.keys(byEditor).length){
      hint.innerHTML = Object.entries(byEditor)
        .map(function(e){ return '<span style="background:#f0f0f5;border-radius:4px;padding:1px 6px;margin-right:4px;cursor:pointer" onclick="doEpSearch(\'' + jsq(projectName) + '\',\'\',\'' + resultBoxId + '\',\'' + jsq(e[0]) + '\')">' + htm(e[0]) + ':' + e[1].join(',') + '</span>'; })
        .join('');
    }
  }, 50);
}

function doEpSearch(projectName, epNum, resultBoxId, editorName){
  var box = document.getElementById(resultBoxId);
  if(!box) return;
  var plan = window.__epSearchPlan || {};
  var n = String(epNum || '').trim();

  // 若给了剪辑师名，则按剪辑师反查集数
  if(editorName){
    var eps = [];
    Object.entries(plan).forEach(function(kv){ if(kv[1] === editorName) eps.push(kv[0]); });
    eps.sort(function(a,b){ return parseInt(a)-parseInt(b); });
    box.innerHTML = eps.length
      ? '<div style="padding:10px 12px;background:#e8f5e9;border-radius:6px;font-size:13px">剪辑师 <b>'+htm(editorName)+'</b> 负责：第 '+eps.map(htm).join('、')+' 集</div>'
      : '<div style="padding:10px 12px;background:#fff3cd;border-radius:6px;font-size:13px">未找到剪辑师 <b>'+htm(editorName)+'</b> 的分集记录</div>';
    return;
  }

  if(!n || isNaN(parseInt(n))){
    box.innerHTML = '<div style="color:#c5221f;font-size:12px">请输入有效的集号</div>';
    return;
  }
  var key = String(parseInt(n));
  var editor = plan[key];
  if(editor){
    box.innerHTML = '<div style="padding:12px;background:#e8f5e9;border-radius:6px;font-size:14px">第 <b>'+key+'</b> 集 → 剪辑师 <b style="color:#1d4ed8;font-size:15px">'+htm(editor)+'</b></div>';
  } else {
    box.innerHTML = '<div style="padding:12px;background:#fff3cd;border-radius:6px;font-size:13px">⚠️ 未找到第 <b>'+key+'</b> 集的剪辑师登记（可能未分配或该集无数据）</div>';
  }
}



// 优先级配置
var TODO_PRIORITY = {
  '2': {label:'高', cls:'priority-h'},
  '1': {label:'中', cls:'priority-m'},
  '0': {label:'低', cls:'priority-l'}
};

// 关闭所有已打开的待办模态框
function _ctCloseAll(){
  if(_ctModal){ _ctModal.remove(); _ctModal = null; }
}

// 打开项目待办居中模态框
var _ctModal = null;
function cardToggleTodo(name){
  try{
    if(_ctModal){ _ctModal.remove(); _ctModal = null; }
    const ov = document.createElement('div');
    ov.className = 'todo-modal-overlay';
    ov.id = 'todo-modal-overlay';
    ov.innerHTML = `
      <div class="todo-modal">
        <div class="todo-modal-head">
          <h3>📌 项目待办</h3>
          <span class="todo-modal-close" title="关闭" onclick="closeTodoModal()">✕</span>
        </div>
        <div class="todo-modal-body" id="todoModalBody">
          <div style="text-align:center;padding:32px 0;color:var(--text-sec)">⏳ 加载中...</div>
        </div>
        <div class="todo-form">
          <div class="todo-form-row">
            <input type="text" id="todoAddText" placeholder="添加待办..." onkeydown="if(event.key==='Enter')todoAdd('${jsq(name)}')">
          </div>
          <div class="todo-form-row">
            <select id="todoAddPriority" title="优先级">
              <option value="0">低优先级</option>
              <option value="1" selected>中优先级</option>
              <option value="2">高优先级</option>
            </select>
            <input type="date" id="todoAddDue" title="截止日期">
            <input type="text" id="todoAddAssignee" placeholder="负责人（可选）" style="min-width:110px;flex:1">
            <button class="btn-add" onclick="todoAdd('${jsq(name)}')">＋ 添加</button>
          </div>
        </div>
      </div>`;
    ov.addEventListener('mousedown', function(e){ if(e.target === ov) closeTodoModal(); });
    document.addEventListener('keydown', function _esc(e){
      if(e.key === 'Escape') closeTodoModal();
      document.removeEventListener('keydown', _esc);
    });
    document.body.appendChild(ov);
    _ctModal = ov;
    todoLoad(name);
    // 更新触发按钮计数（如果卡片已渲染）
    const trig = document.getElementById('ctodo-trigger-' + name.replace(/[^a-zA-Z0-9_]/g,'_'));
    if(trig){ const cnt = trig.querySelector('.ctodo-count'); if(cnt) cnt.textContent = '…'; }
  }catch(err){
    console.error('[cardToggleTodo]', err);
    // 兜底：即使某一步出错也要让弹窗能打开，并把错误显示在内容区
    const body = document.getElementById('todoModalBody');
    if(body){
      body.innerHTML = '<div style="text-align:center;padding:32px;color:var(--red)">待办加载失败: '+htm(String(err&&err.message||err))+'</div>';
    }
  }
}

function closeTodoModal(){
  _ctCloseAll();
}

// 渲染单条待办 → HTML
function _todoItemHTML(name, t){
  const pr = TODO_PRIORITY[t.priority] || null;
  const prHtml = pr ? `<span class="todo-tag ${pr.cls}">${pr.label}优先</span>` : '';
  let dueHtml = '';
  if(t.due_date){
    const dd = String(t.due_date).slice(0,10);
    const today = new Date().toISOString().slice(0,10);
    const overdue = !t.done && dd < today;
    const soon = !t.done && !overdue && dd <= new Date(Date.now()+3*864e5).toISOString().slice(0,10);
    dueHtml = `<span class="todo-tag ${overdue?'due-overdue':(soon?'due-soon':'')}">📅 ${dd}${overdue?' ⚠️':''}</span>`;
  }
  const assigneeHtml = t.assignee ? `<span class="todo-tag assignee">👤 ${htm(t.assignee)}</span>` : '';
  const statusHtml = t.status && t.status !== 'todo' ? `<span class="todo-tag status">${htm(t.status)}</span>` : '';
  return `
    <div class="todo-item ${t.done?'done':''}" data-id="${t.id}">
      <div class="todo-check" title="切换完成" onclick="todoToggle('${jsq(name)}',${t.id},${t.done?0:1})">${t.done?'✓':''}</div>
      <div class="todo-main">
        <div class="todo-text">${htm(t.text)}</div>
        <div class="todo-meta">${prHtml}${dueHtml}${assigneeHtml}${statusHtml}</div>
      </div>
      <button class="todo-del" title="删除" onclick="todoDel('${jsq(name)}',${t.id})">🗑</button>
    </div>`;
}

// 加载并渲染待办列表
async function todoLoad(name){
  const body = document.getElementById('todoModalBody');
  if(!body) return;
  try{
    const d = await api('GET', `/api/project/${encodeURIComponent(name)}/todos`);
    const todos = (d && d.todos) || [];
    const doneCnt = todos.filter(t=>t.done).length;
    const total = todos.length;
    // 更新卡片触发按钮计数
    const trig = document.getElementById('ctodo-trigger-' + name.replace(/[^a-zA-Z0-9_]/g,'_'));
    if(trig){ const cnt = trig.querySelector('.ctodo-count'); if(cnt) cnt.textContent = total ? `(${doneCnt}/${total})` : ''; }
    const pct = total ? Math.round(doneCnt/total*100) : 0;
    const listHtml = todos.length
      ? todos.map(t=>_todoItemHTML(name,t)).join('')
      : `<div class="todo-empty"><div class="e-ico">🗒️</div>暂无待办<br><span style="font-size:12px;color:var(--text-sec)">在下方输入框添加第一条待办</span></div>`;
    body.innerHTML = `
      <div class="todo-modal-summary">
        <div class="todo-sum-item"><div class="v">${total}</div><div class="l">全部</div></div>
        <div class="todo-sum-item"><div class="v" style="color:var(--green)">${doneCnt}</div><div class="l">已完成</div></div>
        <div class="todo-sum-item"><div class="v" style="color:var(--orange)">${total-doneCnt}</div><div class="l">进行中</div></div>
        <div class="todo-sum-item"><div class="v" style="color:var(--blue)">${pct}%</div><div class="l">完成率</div></div>
      </div>
      <div id="todoList">${listHtml}</div>`;
  }catch(e){
    body.innerHTML = '<div style="text-align:center;padding:32px;color:var(--red)">加载失败: '+htm(e.message)+'</div>';
  }
}

// 添加待办（支持优先级/截止日/负责人）
async function todoAdd(name){
  const inp = document.getElementById('todoAddText');
  const text = inp ? inp.value.trim() : '';
  if(!text){ toast('请输入待办内容','warning'); return; }
  const priority = parseInt(document.getElementById('todoAddPriority')?.value || '0', 10);
  const due_date = document.getElementById('todoAddDue')?.value || '';
  const assignee = (document.getElementById('todoAddAssignee')?.value || '').trim();
  try{
    const d = await api('POST', `/api/project/${encodeURIComponent(name)}/todos`, {
      text: text, priority: priority, due_date: due_date, assignee: assignee
    });
    if(d && d.ok){
      if(inp) inp.value='';
      if(document.getElementById('todoAddDue')) document.getElementById('todoAddDue').value='';
      if(document.getElementById('todoAddAssignee')) document.getElementById('todoAddAssignee').value='';
      todoLoad(name);
      toast('已添加待办','success');
    } else toast((d&&d.message)||'添加失败','error');
  }catch(e){ toast('添加失败: '+e.message,'error'); }
}

// 切换完成状态
async function todoToggle(name, id, done){
  try{
    await api('PUT', `/api/project/${encodeURIComponent(name)}/todos/${id}`, { done: !!done });
    todoLoad(name);
  }catch(e){ toast('更新失败: '+e.message,'error'); }
}
// 删除待办
async function todoDel(name, id){
  try{
    await api('DELETE', `/api/project/${encodeURIComponent(name)}/todos/${id}`);
    todoLoad(name);
  }catch(e){ toast('删除失败: '+e.message,'error'); }
}

function updateMonthFilter(){
  const months=[...new Set((projects||[]).filter(p=>{const s=String(p.custom_status||'').trim(),d=String(p.delivery_status||'').trim(),t=Number(p.total_episodes||0);return !!s||(d&&d!=='pending')||t>0;}).map(p=>p.project_month).filter(Boolean))].sort().reverse();
  const sel=$('filterMonth');
  if(!sel)return;
  const cur=sel.value;
  sel.innerHTML='<option value="">全部月份</option>'+months.map(m=>`<option>${m}</option>`).join('');
  if(cur){const opts=Array.from(sel.options);for(const o of opts){if(o.value===cur){sel.value=cur;break}}}
}

// 清除所有筛选条件
function clearAllFilters(){
  try{
    if($('globalSearch'))$('globalSearch').value='';
    if($('filterDept'))$('filterDept').value='';
    if($('filterStatus'))$('filterStatus').value='';
    if($('filterMonth'))$('filterMonth').value='';
    renderDashboard();
    toast('已清除全部筛选', 'info');
  }catch(e){}
}

function updateDepartmentFilter(){
  const depts=[...new Set(projects.map(p=>p.department).filter(Boolean))];
  const sel=$('filterDept');
  if(!sel)return;
  const cur=sel.value;
  sel.innerHTML='<option value="">全部部门</option>'+depts.sort().map(d=>`<option>${d}</option>`).join('');
  if(cur){const opts=Array.from(sel.options);for(const o of opts){if(o.value===cur){sel.value=cur;break}}}
}

function matchFilter(p){
  const q=($('globalSearch')?.value||'').toLowerCase();
  const fd=$('filterDept')?.value||'';
  const fs=$('filterStatus')?.value||'';
  const fm=$('filterMonth')?.value||'';
  if(q&&!p.name.toLowerCase().includes(q))return false;
  if(fd&&p.department!==fd)return false;
  if(fs&&p.custom_status!==fs)return false;
  if(fm&&p.project_month!==fm)return false;
  return true;
}

function sortProjects(list){
  const key=$('sortBy')?.value||'name';
  const order=$('sortOrder')?.value||'asc';
  return [...list].sort((a,b)=>{
    let va=a[key]||'',vb=b[key]||'';
    if(typeof va==='string'){va=va.toLowerCase();vb=(vb||'').toLowerCase();}
    if(va<vb)return order==='asc'?-1:1;
    if(va>vb)return order==='asc'?1:-1;
    return 0;
  });
}

function renderDashboard(){
  renderStats();
  updateMonthFilter();
  updateDepartmentFilter();
  const container=$('projectGrid');
  if(!container)return;

  // 总筛选（搜索框的关键词对所有 section 生效）
  const q=($('globalSearch')?.value||'').toLowerCase().trim();
  const fd=$('filterDept')?.value||'';
  const fs=$('filterStatus')?.value||'';
  const fm=$('filterMonth')?.value||'';
  const sortKey=$('sortBy')?.value||'custom_status';
  const sortOrder=$('sortOrder')?.value||'asc';

  function matchProject(p){
    if(q&&!p.name.toLowerCase().includes(q))return false;
    if(fd&&p.department!==fd)return false;
    if(fs&&p.custom_status!==fs)return false;
    if(fm&&p.project_month!==fm)return false;
    return true;
  }
  function sortList(list){
    return [...list].sort((a,b)=>{
      let va=a[sortKey]||'',vb=b[sortKey]||'';
      // 按状态排序：用工作流步数而非字符串
      if(sortKey==='custom_status'){
        let sa=getStepIndex(va),sb=getStepIndex(vb);
        if(sa<0)sa=99;if(sb<0)sb=99;
        if(sa!==sb)return sortOrder==='asc'?sa-sb:sb-sa;
        return 0;
      }
      // 按交付状态排序：delivered 在后面
      if(sortKey==='delivery_status'){
        const order={pending:0,partial:1,delivered:2,done:3};
        let oa=order[String(va).toLowerCase()]??9,ob=order[String(vb).toLowerCase()]??9;
        if(oa!==ob)return sortOrder==='asc'?oa-ob:ob-oa;
        return 0;
      }
      // 按部门排序：组内NAS优先
      if(sortKey==='department'){
        const priority={'组内NAS':0};
        let pa=priority[va]??9,pb=priority[vb]??9;
        if(pa!==pb)return sortOrder==='asc'?pa-pb:pb-pa;
        va=String(va).toLowerCase();vb=String(vb).toLowerCase();
        return sortOrder==='asc'?(va<vb?-1:va>vb?1:0):(vb<va?-1:vb>va?1:0);
      }
      // 默认字符串比较
      if(typeof va==='string'){va=va.toLowerCase();vb=String(vb||'').toLowerCase();}
      if(va<vb)return sortOrder==='asc'?-1:1;
      if(va>vb)return sortOrder==='asc'?1:-1;
      return 0;
    });
  }

  // ===== 懒加载：默认只渲染组内NAS进行中的完整卡片，其他分页 =====
  const _LAZY_BATCH = 20;      // 非活跃 section 每批渲染的卡片数
  const _forceFull = !!(q || fd || fs || fm) || window._forceFullRender;  // 筛选激活或跳转定位时全渲染
  let totalShown=0;
  const sectionHTML=allSections.map(sec=>{
    let projs=(sec.projects||[]).filter(matchProject);
    projs=sortList(projs);
    if(projs.length===0)return '';

    const collapsed=sec.collapsed?'section-collapsed':'';
    const arrow=sec.collapsed?'▶':'▼';
    totalShown+=projs.length;

    // 组内NAS section 高亮（本部门进行中，最常看）
    const isGroupActive = sec.key === 'group_active';
    const sectionHeaderStyle = isGroupActive
      ? 'background:linear-gradient(135deg,#f0f7ff,#e3eefb);'
      : '';
    const titlePrefix = isGroupActive ? '🎯 ' : (sec.type==='completed' ? '✅ ' : '');

    // 组内NAS (group_active) 或筛选激活 → 全渲染
    const alwaysFull = (sec.key === 'group_active') || _forceFull;
    const renderCount = alwaysFull ? projs.length : Math.min(_LAZY_BATCH, projs.length);
    const rendered = projs.slice(0, renderCount);
    const hasMore = projs.length > renderCount;

    // 只给组内NAS section 加批量刷新按钮
    const batchRefreshBtn = (sec.key === 'group_active' && projs.length > 0)
      ? `<button class="btn btn-sm section-refresh-btn"
                 onclick="event.stopPropagation(); batchRefreshSection('${sec.key}', this)"
                 title="批量扫描目录，刷新本组所有项目的输出进度">🔄 一键刷新进度</button>`
      : '';
    const moreBtn = hasMore
      ? `<div style="text-align:center;padding:12px"><button class="btn btn-sm" onclick="expandSectionLazy('${sec.key}', this)">⬇️ 加载剩余 ${projs.length - renderCount} 个项目</button></div>`
      : '';
    return `
    <div class="section-block ${collapsed}" data-section-key="${sec.key}">
      <div class="section-header" onclick="toggleSection('${sec.key}')" style="${sectionHeaderStyle}">
        <span class="section-arrow">${arrow}</span>
        <span class="section-title">${titlePrefix}${sec.name}</span>
        ${batchRefreshBtn}
        <span class="section-count">${projs.length} 个项目${hasMore?' (首次显示 '+renderCount+')':''}</span>
      </div>
      <div class="section-body" data-section-full="false">
        <div class="grid">
          ${rendered.map(projectCardHTML).join('')}
        </div>
        ${moreBtn}
      </div>
    </div>`;
  }).join('');

  // 全局扩展 section 完整渲染（点击"加载更多"或筛选激活）
  window.expandSectionLazy = function(key, btn){
    const sec = (allSections||[]).find(s => s.key === key);
    if(!sec) return;
    const container = btn.closest('.section-body');
    const grid = container.querySelector('.grid');
    // 用 DOM 方式重算一次筛选，把剩余的补渲染
    let all = (sec.projects||[]).filter(matchProject);
    all = sortList(all);
    // 直接重写 entire grid，更可靠
    grid.innerHTML = all.map(projectCardHTML).join('');
    container.dataset.sectionFull = 'true';
    btn.remove();
    // 更新 section-count 标签
    const countLabel = container.previousElementSibling.querySelector('.section-count');
    if(countLabel) countLabel.textContent = all.length + ' 个项目 (全部)';
  };

  const fc=$('filterCount');
  if(fc){
    const total=allSections.reduce((s,sec)=>s+(sec.projects?.length||0),0);
    fc.textContent=`显示 ${totalShown} / ${total} 个项目`;
  }

  // 清除筛选按钮：有激活筛选时显示
  const clearBtn=$('clearFilterBtn');
  if(clearBtn){
    const hasFilter = q || fd || fs || fm;
    clearBtn.style.display = hasFilter ? 'inline-block' : 'none';
  }

  // 批量栏
  const bulkBar = $('bulkBar');
  if(window._bulkMode){
    if(!bulkBar){
      const bar = document.createElement("div");
      bar.id = "bulkBar";
      bar.style.cssText = "position:sticky;top:0;z-index:50;background:#007aff;color:#fff;padding:10px 16px;border-radius:8px;margin:12px 0;display:flex;align-items:center;gap:12px;box-shadow:0 2px 10px rgba(0,0,0,.15)";
      bar.innerHTML = `<span>已选 <b id="bulkCount">0</b> 个项目</span>
        <button class="btn btn-sm" style="background:#fff;color:#007aff" onclick="bulkSetMonth()">📅 批量改月份</button>
        <button class="btn btn-sm" style="background:#fff;color:#007aff" onclick="bulkSetStatus()">🏷️ 批量改状态</button>
        <button class="btn btn-sm" style="background:#fff;color:#007aff" onclick="bulkSetDeliveredDate()">🗓 批量交付日期</button>
        <button class="btn btn-sm" style="background:#fff;color:#007aff" onclick="bulkExport()">📥 批量导出</button>
        <button class="btn btn-sm" style="background:#fff;color:#007aff" onclick="bulkClear()">全部取消</button>
        <button class="btn btn-sm" style="background:rgba(255,255,255,.25);color:#fff" onclick="toggleBulkMode()">✕ 退出批量</button>`;
      container.parentElement.insertBefore(bar, container);
    }
  } else {
    if(bulkBar) bulkBar.remove();
  }

  if(totalShown===0){
    container.innerHTML=`<div class="empty-state"><div>📭 没有匹配的项目</div></div>`;
  }else{
    container.innerHTML=sectionHTML;
  }
}

function toggleBulkMode(){
  window._bulkMode = !window._bulkMode;
  toast((window._bulkMode?'✅ 进入':'退出') + ' 批量选择模式' + (window._bulkMode?' — 每张卡片左上角出现 checkbox':'') , 'info');
  renderDashboard();
}
function updateBulkBar(){
  const checked = document.querySelectorAll('.bulk-card-chk:checked');
  const lbl = document.getElementById('bulkCount');
  if(lbl) lbl.textContent = checked.length;
}
function getBulkSelected(){
  return Array.from(document.querySelectorAll('.bulk-card-chk:checked')).map(c => c.dataset.pname);
}
function bulkClear(){
  document.querySelectorAll('.bulk-card-chk').forEach(c => c.checked = false);
  updateBulkBar();
}
async function bulkSetMonth(){
  const names = getBulkSelected();
  if(!names.length){ toast('请先选择项目','warning'); return; }
  const now = new Date();
  const months = [];
  for(let y=now.getFullYear()-1; y<=now.getFullYear()+1; y++){
    for(let m=1; m<=12; m++){
      months.push(y + '-' + String(m).padStart(2,'0'));
    }
  }
  const html = `<div class="modal-overlay" onclick="if(event.target===this)this.remove()">
    <div class="modal" style="width:320px">
      <div class="modal-head">📅 批量设置月份 (${names.length} 个项目)</div>
      <div style="padding:15px">
        <select id="bulkMonth" style="width:100%;padding:8px">
          <option value="">— 清空（不统计）—</option>
          ${months.map(m=>`<option>${m}</option>`).join('')}
        </select>
      </div>
      <div class="modal-foot">
        <button class="btn" onclick="document.querySelectorAll('.modal-overlay').forEach(m=>m.remove());document.getElementById('bulkModal').remove()">取消</button>
        <button class="btn btn-primary" onclick="_bulkSetMonthGo('${jsq(names.join('||'))}')">确定</button>
      </div>
    </div></div>`;
  document.body.insertAdjacentHTML('beforeend', html);
}
async function _bulkSetMonthGo(namesStr){
  const names = namesStr.split('||').filter(Boolean);
  const month = document.getElementById('bulkMonth').value;
  document.querySelectorAll('.modal-overlay').forEach(m=>m.remove());
  try{
    const r = await api('POST','/api/bulk/update_month', {names, month});
    toast('✅ 已更新 '+r.updated+' 个项目','success');
    await loadProjects();
  }catch(e){ toast('❌ 批量设置失败: '+e.message,'error'); }
}
async function bulkSetStatus(){
  const names = getBulkSelected();
  if(!names.length){ toast('请先选择项目','warning'); return; }
  const STATUS_OPTS = ['分集中','剪辑中','审核中','修改中','交付中','待质检','质检中','已完成','已交付'];
  const html = `<div class="modal-overlay" onclick="if(event.target===this)this.remove()">
    <div class="modal" style="width:320px">
      <div class="modal-head">🏷️ 批量设置状态 (${names.length} 个项目)</div>
      <div style="padding:15px">
        <select id="bulkStatus" style="width:100%;padding:8px">
          ${STATUS_OPTS.map(s=>`<option>${s}</option>`).join('')}
        </select>
      </div>
      <div class="modal-foot">
        <button class="btn" onclick="document.querySelectorAll('.modal-overlay').forEach(m=>m.remove())">取消</button>
        <button class="btn btn-primary" onclick="_bulkSetStatusGo('${jsq(names.join('||'))}')">确定</button>
      </div>
    </div></div>`;
  document.body.insertAdjacentHTML('beforeend', html);
}
async function _bulkSetStatusGo(namesStr){
  const names = namesStr.split('||').filter(Boolean);
  const status = document.getElementById('bulkStatus').value;
  document.querySelectorAll('.modal-overlay').forEach(m=>m.remove());
  try{
    const r = await api('POST','/api/bulk/update_status', {names, custom_status: status});
    toast('✅ 已更新 '+r.updated+' 个项目','success');
    await loadProjects();
  }catch(e){ toast('❌ 批量设置失败: '+e.message,'error'); }
}

async function bulkSetDeliveredDate(){
  const names = getBulkSelected();
  if(!names.length){ toast('请先选择项目','warning'); return; }
  const today = new Date().toISOString().slice(0,10);
  const html = `<div class="modal-overlay" onclick="if(event.target===this)this.remove()">
    <div class="modal" style="width:320px">
      <div class="modal-head">🗓 批量设置交付日期 (${names.length} 个项目)</div>
      <div style="padding:15px;display:flex;flex-direction:column;gap:8px">
        <input type="date" id="bulkDD" value="${today}" style="padding:8px;border:1px solid #d1d5db;border-radius:8px;font-size:14px">
        <label style="font-size:12px;color:#666;display:flex;align-items:center;gap:4px"><input type="checkbox" id="bulkDDClear"> 清除交付日期</label>
      </div>
      <div class="modal-foot">
        <button class="btn" onclick="document.querySelectorAll('.modal-overlay').forEach(m=>m.remove())">取消</button>
        <button class="btn btn-primary" onclick="_bulkDDGo('${jsq(names.join('||'))}')">确定</button>
      </div>
    </div></div>`;
  document.body.insertAdjacentHTML('beforeend', html);
  // 勾选清除时禁用日期输入
  const clearChk = document.getElementById('bulkDDClear');
  clearChk.addEventListener('change', function(){
    document.getElementById('bulkDD').disabled = this.checked;
  });
}
async function _bulkDDGo(namesStr){
  const names = namesStr.split('||').filter(Boolean);
  const clear = document.getElementById('bulkDDClear').checked;
  const date = clear ? '' : document.getElementById('bulkDD').value;
  document.querySelectorAll('.modal-overlay').forEach(m=>m.remove());
  try{
    const r = await api('POST','/api/bulk/update_delivered_date', {names, date});
    toast('✅ 已更新 '+r.updated+' 个项目的交付日期','success');
    if(typeof loadInsightsCalendar==='function') loadInsightsCalendar();
  }catch(e){ toast('❌ 批量设置失败: '+e.message,'error'); }
}
function bulkExport(){
  const names = getBulkSelected();
  if(!names.length){ toast('请先选择项目','warning'); return; }
  // 用 fetch 直接下载后端生成的 CSV（带鉴权 body）
  const key = window.__API_KEY__ || '';
  fetch('/api/bulk/export', {
    method:'POST',
    headers:{'Content-Type':'application/json', ...(key?{'X-API-KEY':key}:{})},
    body: JSON.stringify({names: names})
  }).then(function(res){ return res.text(); }).then(function(text){
    const blob = new Blob([text], {type:'text/csv;charset=utf-8'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = '项目档案-批量-' + new Date().toISOString().slice(0,10) + '.csv';
    document.body.appendChild(a); a.click();
    setTimeout(function(){ URL.revokeObjectURL(a.href); a.remove(); }, 200);
    toast('✅ 已导出 '+names.length+' 个项目','success');
  }).catch(function(e){ toast('导出失败: '+e.message,'error'); });
}

function toggleSection(key){
  const block=document.querySelector(`[data-section-key="${key}"]`);
  if(!block)return;
  block.classList.toggle('section-collapsed');
  const arrow=block.querySelector('.section-arrow');
  if(arrow)arrow.textContent=block.classList.contains('section-collapsed')?'▶':'▼';
}

