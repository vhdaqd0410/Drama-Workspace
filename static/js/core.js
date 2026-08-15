// 工具函数 + 常量 + 渲染函数
/* ============ Config & Utils ============ */
const API='';
const WF_STEPS=['分集','剪辑','审核','修改','交付','质检','完成'];
let projects=[], allSections=[], allProjects={}, fenjiLight=[], qaRunning=false, pollDashboard=null, pollQA=null, qaStartTime=0;

function $(id){return document.getElementById(id)}
function el(tag,cls,html){const e=document.createElement(tag);if(cls)e.className=cls;if(html!==undefined)e.innerHTML=html;return e}
async function api(method,path,body){const opts={method,headers:{}};if(body!==undefined){if(body instanceof FormData){opts.body=body}else{opts.headers['Content-Type']='application/json';opts.body=JSON.stringify(body)}}const r=await fetch(API+path,opts);if(!r.ok)throw new Error(r.status+' '+r.statusText);const ct=r.headers.get('content-type')||'';return ct.includes('application/json')?r.json():r.text()}

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
      if(!evt.data||evt.data.startsWith('{'))return;
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
window._shortcutConfig = { search: '' };  // search: 如 'ctrl+space' / 'ctrl+g' / ''=默认ctrl+k/f
function _getSearchShortcut(){
  var s = window._shortcutConfig && window._shortcutConfig.search;
  return s ? String(s).toLowerCase().trim() : '';
}
// 解析快捷键配置字符串，判断当前按键是否匹配
function _matchShortcut(e, shortcutStr){
  if(!shortcutStr) return false;
  var parts = String(shortcutStr).toLowerCase().split('+').map(function(x){return x.trim();});
  var key = e.key ? e.key.toLowerCase() : '';
  // 特殊键
  if(key === ' ') key = 'space';
  if(key.length === 1 && e.code && e.code.indexOf('Key')===0) key = e.code.slice(3).toLowerCase();
  var hasCtrl = parts.indexOf('ctrl')>=0 || parts.indexOf('control')>=0;
  var hasAlt = parts.indexOf('alt')>=0;
  var hasShift = parts.indexOf('shift')>=0;
  var hasMeta = parts.indexOf('meta')>=0;
  if(hasCtrl !== (e.ctrlKey||e.metaKey)) return false;
  if(hasAlt !== e.altKey) return false;
  if(hasShift !== e.shiftKey) return false;
  // 取主键（最后一个非修饰键）
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
  var secs = (typeof allSections !== 'undefined' && allSections) ? allSections : [];
  var items = [];
  secs.forEach(function(sec){
    (sec.projects||[]).forEach(function(p){
      items.push({ name: p.name, section: sec.name, month: p.project_month || '', status: p.custom_status || '' });
    });
  });
  if(!items.length){ toast('暂无项目','info'); return; }
  var html = '<div class="modal-overlay" id="searchModal" onclick="if(event.target===this)this.remove()">'
    + '<div class="modal" style="width:480px">'
    + '<div class="modal-head">🔍 快速搜索 <span style="font-size:11px;color:#86868b;font-weight:400;margin-left:auto">Ctrl+K</span></div>'
    + '<div style="padding:14px">'
    + '<input id="searchInput" placeholder="输入项目名称或月份（如 2026-07）" style="width:100%;padding:10px 12px;border:1px solid #e5e5ea;border-radius:8px;font-size:14px;outline:none;box-sizing:border-box" oninput="filterSearchResults()">'
    + '<div id="searchResults" style="margin-top:10px;max-height:320px;overflow-y:auto"></div>'
    + '</div></div></div>';
  document.body.insertAdjacentHTML('beforeend', html);
  var inp = document.getElementById('searchInput');
  if(inp) inp.focus();
  filterSearchResults();
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

function filterSearchResults(){
  var kw = (document.getElementById('searchInput')?.value || '').toLowerCase().trim();
  var results = document.getElementById('searchResults');
  if(!results) return;
  var secs = (typeof allSections !== 'undefined' && allSections) ? allSections : [];
  var items = [];
  secs.forEach(function(sec){
    (sec.projects||[]).forEach(function(p){
      var name = p.name||'';
      var month = p.project_month||'';
      if(!kw || fuzzyMatch(name, kw) || fuzzyMatch(month, kw)){
        items.push({ name: name, section: sec.name, month: month, status: p.custom_status || '' });
      }
    });
  });
  if(!items.length){
    results.innerHTML = '<div style="color:#86868b;padding:20px;text-align:center">未找到匹配的项目</div>';
    return;
  }
  var html = items.slice(0, 50).map(function(it){
    var monthBadge = it.month ? '<span style="background:#e3f2fd;color:#1565c0;padding:1px 7px;border-radius:10px;font-size:11px;margin-left:6px">📅 '+it.month+'</span>' : '';
    return '<div class="search-result-item" data-name="' + it.name.replace(/"/g, "&quot;") + '" style="padding:10px 12px;cursor:pointer;border-radius:6px;display:flex;justify-content:space-between;align-items:center;font-size:13px;border-bottom:1px solid #f0f0f0" onclick="jumpToProjectItem(this)">'
      + '<span><span style="font-weight:500">'+it.name+'</span>'+monthBadge+'</span>'
      + '<span style="color:#86868b;font-size:11px">'+it.section+ (it.status?' · '+it.status:'')+'</span>'
      + '</div>';
  }).join('');
  results.innerHTML = html;
}

function jumpToProjectItem(el){
  var name = el.getAttribute('data-name') || '';
  var m = document.getElementById('searchModal');
  if(m) m.remove();
  jumpToProject(name);
}
function jumpToProject(name){
  if(typeof openProjectDetail === 'function'){
    openProjectDetail(name);
  }
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

  // === 异常提醒（后端计算 p.alert = [level, message]）===
  let alertHTML = '';
  if (p.alert && Array.isArray(p.alert) && p.alert[1]) {
    const _lv = p.alert[0] === 'danger' ? 'danger' : 'warn';
    const _bg = _lv === 'danger' ? '#fdecea' : '#fff8e6';
    const _fg = _lv === 'danger' ? '#c5221f' : '#9a6b00';
    const _bd = _lv === 'danger' ? '#f5c6c4' : '#f0dcae';
    const _icon = _lv === 'danger' ? '🔴' : '⚠️';
    alertHTML = `<div style="margin:6px 12px 0;padding:4px 8px;border-radius:6px;font-size:12px;font-weight:600;background:${_bg};color:${_fg};border:1px solid ${_bd}">${_icon} ${htm(p.alert[1])}</div>`;
  }

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
    <div class="card-head">${bulkChk}<div class="card-title"><span class="card-title-name" title="${p.name}">${p.name}</span>${dept}${month}</div>${(() => {
  const cur = p.custom_status || '';
  const optsHtml = WF_STATUS_OPTIONS.map(o =>
    `<option value="${o.v}" ${o.v===cur?'selected':''}>${o.label}</option>`
  ).join('');
  return `<select class="badge editable-badge ${badge.cls}" onchange="onStatusChange('${p.name.replace(/'/g,"\\'")}', this)" title="点击修改项目状态">${optsHtml}</select>`;
})()}</div>
    ${alertHTML}
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
    <div class="assign-summary">👥 ${assignSummaryHTML(p)}</div>
    <div class="card-actions"><div class="card-open-group">${openBtns}</div>${renderActions(p)}</div>
  </div>`;
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
  const _forceFull = !!(q || fd || fs || fm);  // 筛选激活时全渲染
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
        <button class="btn btn-primary" onclick="_bulkSetMonthGo('${names.join('||').replace(/'/g,"")}')">确定</button>
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
        <button class="btn btn-primary" onclick="_bulkSetStatusGo('${names.join('||').replace(/'/g,"")}')">确定</button>
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

function toggleSection(key){
  const block=document.querySelector(`[data-section-key="${key}"]`);
  if(!block)return;
  block.classList.toggle('section-collapsed');
  const arrow=block.querySelector('.section-arrow');
  if(arrow)arrow.textContent=block.classList.contains('section-collapsed')?'▶':'▼';
}

