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
          } else if(payload.status==='error'){
            toast('❌ '+payload.project+' 回传失败','error');
          }
          _scheduleSseRefresh();
        } else if(payload.type==='search'){
          // 全局搜索热键按下 → 打开搜索框
          if(typeof openSearchModal === 'function'){
            setTimeout(function(){ openSearchModal(); }, 120);
          }
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
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.4);z-index:10000;display:flex;align-items:center;justify-content:center';
  overlay.innerHTML = `<div style="background:#fff;border-radius:12px;width:440px;overflow:hidden;box-shadow:0 8px 30px rgba(0,0,0,.2)">
    <div style="padding:16px 18px;background:linear-gradient(135deg,#e3f2fd,#bbdefb);font-weight:700;font-size:15px">✂️ 项目已剪完</div>
    <div style="padding:16px 18px">
      <div style="font-size:14px;margin-bottom:6px">项目「<b>${htm(name)}</b>」已剪辑完成</div>
      <div style="font-size:12px;color:#666">已产出 <b>${current}</b> / ${total} 集，是否进入审核？</div>
    </div>
    <div style="padding:12px 18px;border-top:1px solid #eee;display:flex;justify-content:flex-end;gap:8px">
      <button class="btn btn-sm" onclick="this.closest('.modal-overlay').remove()">稍后</button>
      <button class="btn btn-sm btn-primary" onclick="confirmEditComplete('${jsq(name)}', this)">✅ 进入审核</button>
    </div>
  </div>`;
  document.body.appendChild(overlay);
}
async function confirmEditComplete(name, btn){
  try{
    await api('POST', '/api/project/' + encodeURIComponent(name) + '/custom_status', { custom_status: '审核中' });
    toast('✅ ' + name + ' 已进入审核', 'success');
    btn.closest('.modal-overlay').remove();
    if(typeof loadProjects === 'function') loadProjects();
  }catch(e){ toast('操作失败: '+e.message, 'error'); }
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
      if(modal) modal.remove();
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
  const pname = p.name.replace(/'/g,"\\'");
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
    btns.push(['🔗 分秒帧',`openFenmiaozhen('${pname}')`,'fm-main','']);
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

    let html = '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px;margin-top:20px">';

    // === 剪辑师工作量看板 ===
    const maxAssigned = editors.length ? editors[0].assigned : 1;
    const editorRows = editors.map(function(e){
      const pct = maxAssigned>0 ? Math.round(e.assigned/maxAssigned*100) : 0;
      const hue = Math.max(0, 210 - pct*1.2);  // 工作量高 → 偏红
      const color = pct>=80 ? '#e74c3c' : pct>=50 ? '#e67e22' : '#3498db';
      // 提成卡点(基准集数)标记：70集/120集
      const quota = e.quota || 0;
      const quotaPct = quota && maxAssigned>0 ? Math.round(quota/maxAssigned*100) : 0;
      const quotaMark = quota>0
        ? `<div style="position:absolute;top:-3px;bottom:-3px;left:${quotaPct}%;width:2px;background:#ff9500;z-index:2" title="提成卡点 ${quota} 集"></div>
           <div style="position:absolute;top:-12px;left:${quotaPct}%;transform:translateX(-50%);font-size:9px;color:#ff9500;font-weight:700;white-space:nowrap">${quota}提</div>`
        : '';
      const reached = quota>0 && e.assigned>=quota;
      return `<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
        <div style="width:70px;font-size:12px;color:#4a4a4a;text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="${htm(e.name)}">${htm(e.name)}</div>
        <div style="flex:1;height:18px;background:#f0f2f5;border-radius:4px;overflow:hidden;position:relative">${quotaMark}<div style="width:${pct}%;height:100%;background:linear-gradient(90deg,#3498db,${color});border-radius:4px;transition:width .5s"></div></div>
        <div style="width:55px;font-size:12px;font-weight:600;color:${reached?'#34c759':'#333'}">${e.assigned}集</div>
        <div style="width:50px;font-size:11px;color:#86868b">${e.projects}项目</div>
      </div>`;
    }).join('');

    html += `<div style="background:#fff;border:1px solid var(--border);border-radius:12px;padding:16px 18px;box-shadow:var(--shadow)">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <div style="font-weight:700;font-size:14px">👥 剪辑师工作量（本月）</div>
        <span style="font-size:11px;color:#86868b">共 ${summary.total_editors||0} 人 · ${summary.total_assigned||0} 集 · <span style="color:#ff9500;font-weight:600">橙色竖线=提成卡点(基准集数)</span></span>
      </div>
      <div style="max-height:340px;overflow-y:auto">${editorRows || '<div style="color:#86868b;padding:20px;text-align:center">暂无分集数据</div>'}</div>
    </div>`;

    // === 部门统计 ===
    const deptMax = dept.length ? Math.max(...dept.map(x=>x.total||0), 1) : 1;
    const deptRows = dept.map(function(s){
      const pct = Math.round((s.total||0)/deptMax*100);
      return `<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
        <div style="width:90px;font-size:12px;color:#4a4a4a;text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="${htm(s.department||'未分部门')}">${htm(s.department||'未分部门')}</div>
        <div style="flex:1;height:18px;background:#f0f2f5;border-radius:4px;overflow:hidden"><div style="width:${pct}%;height:100%;background:linear-gradient(90deg,#5c6bc0,#7986cb);border-radius:4px"></div></div>
        <div style="width:80px;font-size:11px;color:#666">${s.total||0}项目 · ${s.completed||0}完成</div>
      </div>`;
    }).join('');
    html += `<div style="background:#fff;border:1px solid var(--border);border-radius:12px;padding:16px 18px;box-shadow:var(--shadow)">
      <div style="font-weight:700;font-size:14px;margin-bottom:12px">🏢 部门项目统计</div>
      ${deptRows || '<div style="color:#86868b;padding:20px;text-align:center">暂无数据</div>'}
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
  const pname = p.name.replace(/'/g,"\'");
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

  const epPanel = `<div class="card-episodes-panel" id="ep-panel-${pname.replace(/[^a-zA-Z0-9_]/g,'_')}"></div>`;
  const epSummaryBox = `<div class="ep-missing-summary" data-ep-summary="${p.name.replace(/"/g,'&quot;')}"></div>`;

  const bulkChk = window._bulkMode
    ? `<input type="checkbox" class="bulk-card-chk" data-pname="${p.name.replace(/"/g,'&quot;')}" onchange="updateBulkBar()" title="选择此项目">`
    : '';
  return`<div class="card">
    <div class="card-head">${bulkChk}<div class="card-title"><span class="card-title-name" title="${p.name}" data-project-name="${p.name.replace(/"/g,'&quot;')}">${p.name}</span>${dept}${month}</div>${(() => {
  const cur = p.custom_status || '';
  const optsHtml = WF_STATUS_OPTIONS.map(o =>
    `<option value="${o.v}" ${o.v===cur?'selected':''}>${o.label}</option>`
  ).join('');
  return `<select class="badge editable-badge ${badge.cls}" onchange="onStatusChange('${p.name.replace(/'/g,"\\'")}', this)" title="点击修改项目状态">${optsHtml}</select>`;
})()}</div>
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
    <div class="card-todo" id="ctodo-trigger-${pname.replace(/[^a-zA-Z0-9_]/g,'_')}" onclick="cardToggleTodo('${jsq(pname)}', this, event)">📌 待办 <span class="ctodo-count"></span></div>
    <div class="card-todo-popup" id="ctodo-popup-${pname.replace(/[^a-zA-Z0-9_]/g,'_')}"></div>
    <div class="assign-summary">👥 ${assignSummaryHTML(p)}</div>
    <div class="card-actions"><div class="card-open-group">${openBtns}</div>${renderActions(p)}</div>
  </div>`;
}

// ===== 项目卡片待办（首页快捷添加 + 悬停查看）=====
function _ctSanitize(name){ return name.replace(/[^a-zA-Z0-9_]/g,'_'); }
function _ctPopup(name){ return document.getElementById('ctodo-popup-' + _ctSanitize(name)); }
function _ctTrigger(name){ return document.getElementById('ctodo-trigger-' + _ctSanitize(name)); }
// 关闭弹窗（带淡出动画）
function _ctHide(pop){
  if(!pop || !pop.classList.contains('show')) return;
  pop.classList.add('hiding');
  setTimeout(function(){
    pop.classList.remove('show');
    pop.classList.remove('hiding');
    delete pop.dataset.pinned;
  }, 175);
}
// 把弹窗定位到鼠标点击处附近，做视口边界钳制
function _ctPosition(pop, anchor, mx, my){
  const pad = 12;
  const w = pop.offsetWidth || 290;
  const h = pop.offsetHeight || 240;
  // 优先用鼠标点击坐标，否则回退到按钮下方
  let x = (typeof mx === 'number' && !isNaN(mx)) ? mx + pad : (anchor ? anchor.getBoundingClientRect().left : pad);
  let y = (typeof my === 'number' && !isNaN(my)) ? my + pad : (anchor ? anchor.getBoundingClientRect().bottom + 8 : pad);
  // 视口边界钳制
  if(x + w > window.innerWidth - 8) x = Math.max(8, (typeof mx === 'number' && !isNaN(mx)) ? mx - w - pad : window.innerWidth - w - 8);
  if(y + h > window.innerHeight - 8) y = Math.max(8, (typeof my === 'number' && !isNaN(my)) ? my - h - pad : window.innerHeight - h - 8);
  pop.style.left = x + 'px';
  pop.style.top = y + 'px';
}
// 关闭所有打开的弹窗（跳过固定的）
function _ctCloseOthers(){
  document.querySelectorAll('.card-todo-popup.show').forEach(p=>{
    if(!p.dataset.pinned) _ctHide(p);
  });
}

// 打开/关闭待办弹层（点击，固定；弹窗跟随鼠标点击位置弹出）
function cardToggleTodo(name, el, ev){
  const pop = _ctPopup(name);
  if(!pop) return;
  const isShow = pop.classList.contains('show');
  // 关闭所有已开的（含固定，淡出）
  document.querySelectorAll('.card-todo-popup.show').forEach(p=>{ _ctHide(p); });
  if(!isShow){
    const mx = ev && typeof ev.clientX === 'number' ? ev.clientX : null;
    const my = ev && typeof ev.clientY === 'number' ? ev.clientY : null;
    _ctPosition(pop, el, mx, my);
    pop.classList.add('show');
    pop.dataset.pinned = '1';
    cardLoadTodos(name, true);
  }
}

async function cardLoadTodos(name, isClick){
  const pop = _ctPopup(name);
  if(!pop) return;
  try{
    const d = await api('GET', `/api/project/${encodeURIComponent(name)}/todos`);
    const todos = (d && d.todos) || [];
    // 更新触发按钮计数
    const trig = _ctTrigger(name);
    const cnt = trig ? trig.querySelector('.ctodo-count') : null;
    if(cnt) cnt.textContent = todos.length ? `(${todos.filter(t=>t.done).length}/${todos.length})` : '';
    const doneCnt = todos.filter(t=>t.done).length;
    const listHtml = todos.length
      ? todos.map(t=>`
          <div style="display:flex;align-items:center;gap:6px;padding:5px 0;font-size:12px;border-bottom:1px dashed var(--border)">
            <button onclick="cardToggleTodoItem('${jsq(name)}',${t.id},${t.done?0:1})" style="background:none;border:none;font-size:15px;cursor:pointer;padding:0" title="切换完成">${t.done?'☑️':'⬜'}</button>
            <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;${t.done?'text-decoration:line-through;color:var(--text-sec)':''}" title="${htm(t.text)}">${htm(t.text)}</span>
            <button onclick="cardDelTodo('${jsq(name)}',${t.id})" style="background:none;border:none;color:var(--red);cursor:pointer;font-size:13px" title="删除">🗑</button>
          </div>`).join('')
      : '<div style="color:var(--text-sec);font-size:12px;padding:6px 0">暂无待办</div>';
    pop.innerHTML = `
      <div class="ctp-head"><span>📌 ${htm(name)}</span><span style="color:var(--text-sec);font-weight:400">${doneCnt}/${todos.length} 完成</span></div>
      <div class="ctp-list">${listHtml}</div>
      <div class="ctp-add">
        <input id="ctodo-input-${_ctSanitize(name)}" type="text" placeholder="添加待办..." onkeydown="if(event.key==='Enter')cardAddTodo('${jsq(name)}')">
        <button onclick="cardAddTodo('${jsq(name)}')">添加</button>
      </div>`;
    const inp = document.getElementById('ctodo-input-' + _ctSanitize(name));
    if(inp && isClick) setTimeout(function(){ inp.focus(); }, 30);
    // 内容渲染后按实际尺寸重新定位（跟随鼠标，钳制视口）
    if(pop.classList.contains('show')) setTimeout(function(){ _ctPosition(pop); }, 20);
  }catch(e){
    pop.innerHTML = '<div class="ctp-head">📌 待办</div><div style="color:var(--red);font-size:12px;padding:10px">加载失败</div>';
    if(pop.classList.contains('show')) setTimeout(function(){ _ctPosition(pop); }, 20);
  }
}

async function cardAddTodo(name){
  const inp = document.getElementById('ctodo-input-' + _ctSanitize(name));
  const text = inp ? inp.value.trim() : '';
  if(!text){ toast('请输入待办内容','warning'); return; }
  try{
    const d = await api('POST', `/api/project/${encodeURIComponent(name)}/todos`, { text: text });
    if(d && d.ok){ if(inp) inp.value=''; cardLoadTodos(name, false); toast('已添加待办','success'); }
    else toast((d&&d.message)||'添加失败','error');
  }catch(e){ toast('添加失败: '+e.message,'error'); }
}

async function cardToggleTodoItem(name, id, done){
  try{
    await api('PUT', `/api/project/${encodeURIComponent(name)}/todos/${id}`, { done: !!done });
    cardLoadTodos(name, false);
  }catch(e){ toast('更新失败: '+e.message,'error'); }
}
async function cardDelTodo(name, id){
  try{
    await api('DELETE', `/api/project/${encodeURIComponent(name)}/todos/${id}`);
    cardLoadTodos(name, false);
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

