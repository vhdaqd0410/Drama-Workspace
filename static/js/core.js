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
function bindShortcuts(){
  document.addEventListener('keydown', function(e){
    var tag = (e.target.tagName || '').toUpperCase();
    var isInput = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || e.target.isContentEditable;
    if(isInput) return;

    if((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k'){
      e.preventDefault();
      openSearchModal();
      return;
    }
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

function filterSearchResults(){
  var kw = (document.getElementById('searchInput')?.value || '').toLowerCase().trim();
  var results = document.getElementById('searchResults');
  if(!results) return;
  var secs = (typeof allSections !== 'undefined' && allSections) ? allSections : [];
  var items = [];
  secs.forEach(function(sec){
    (sec.projects||[]).forEach(function(p){
      var name = (p.name||'').toLowerCase();
      var month = (p.project_month||'').toLowerCase();
      if(!kw || name.indexOf(kw)>=0 || month.indexOf(kw)>=0){
        items.push({ name: p.name, section: sec.name, month: p.project_month || '', status: p.custom_status || '' });
      }
    });
  });
  if(!items.length){
    results.innerHTML = '<div style="color:#86868b;padding:20px;text-align:center">未找到匹配的项目</div>';
    return;
  }
  var html = items.slice(0, 50).map(function(it){
    var monthBadge = it.month ? '<span style="background:#e3f2fd;color:#1565c0;padding:1px 7px;border-radius:10px;font-size:11px;margin-left:6px">📅 '+it.month+'</span>' : '';
    return '<div onclick="document.getElementById('searchModal')?.remove();jumpToProject(''+it.name.replace(/'/g,"\'")+'')" style="padding:10px 12px;cursor:pointer;border-radius:6px;display:flex;justify-content:space-between;align-items:center;font-size:13px;border-bottom:1px solid #f0f0f0">'
      + '<span><span style="font-weight:500">'+it.name+'</span>'+monthBadge+'</span>'
      + '<span style="color:#86868b;font-size:11px">'+it.section+ (it.status?' · '+it.status:'')+'</span>'
      + '</div>';
  }).join('');
  results.innerHTML = html;
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
  if(name==='qa')loadQAProjects();
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
    if(has('修改中'))btns.push(['📦 待交付',`updateStatus('${pname}','交付中')`,'']);
    if(has('已交付')||has('交付中')||has('待交付'))btns.push(['📦 初版交付',`updateStatus('${pname}','待质检')`,'btn-primary']);
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
  const list = (typeof projects !== 'undefined' && Array.isArray(projects)) ? projects : [];
  const total = list.length;
  // 只统计组内NAS section 里的制作中项目（排除部门项目干扰）
  const groupSection = (allSections || []).find(s => s.key === 'group_active');
  const groupList = groupSection ? (groupSection.projects || []) : list;
  const inProd = groupList.filter(p => {
    const s = String(p.custom_status || '');
    return s.includes('剪辑') || s.includes('审核') || s.includes('修改');
  }).length;
  const passed = list.filter(p => {
    const q = p.qa_status;
    if (!q || typeof q !== 'object') return false;
    return String(q.status || '').toLowerCase() === 'pass';
  }).length;
  const failed = list.filter(p => {
    const q = p.qa_status;
    if (!q || typeof q !== 'object') return false;
    const s = String(q.status || '').toLowerCase();
    return s === 'fail' || s === 'error';
  }).length;
  const nowMonth = new Date().getFullYear() + '-' + String(new Date().getMonth()+1).padStart(2,'0');
  // 只统计"有实际制作痕迹"的项目（排除空壳/模板目录）
  const activeList = list.filter(p => {
    const s = String(p.custom_status || '').trim();
    const d = String(p.delivery_status || '').trim();
    const t = Number(p.total_episodes || 0);
    return s || (d && d !== 'pending') || t > 0;
  });
  const thisMonth = activeList.filter(p => p.project_month === nowMonth).length;
  $('statsRow').innerHTML=`
    <div class="stat-card" onclick="$('filterMonth').value='${nowMonth}';renderDashboard()" style="cursor:pointer"><div class="stat-icon" style="background:#fff3cd;color:#856404">📅</div><div><div class="stat-num">${thisMonth}</div><div class="stat-label">本月项目</div></div></div>
    <div class="stat-card"><div class="stat-icon blue">📁</div><div><div class="stat-num">${total}</div><div class="stat-label">总项目</div></div></div>
    <div class="stat-card"><div class="stat-icon orange">🎬</div><div><div class="stat-num">${inProd}</div><div class="stat-label">制作中</div></div></div>
    <div class="stat-card"><div class="stat-icon green">✅</div><div><div class="stat-num">${passed}</div><div class="stat-label">质检通过</div></div></div>
    <div class="stat-card"><div class="stat-icon red">❌</div><div><div class="stat-num">${failed}</div><div class="stat-label">质检失败</div></div></div>`;
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
  if (total > 0) {
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

  return`<div class="card">
    <div class="card-head"><div class="card-title"><span class="card-title-name" title="${p.name}">${p.name}</span>${dept}${month}</div>${(() => {
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

  // 按 section 分组渲染
  let totalShown=0;
  const sectionHTML=allSections.map(sec=>{
    // 对每个 section 内的项目做筛选
    let projs=(sec.projects||[]).filter(matchProject);
    projs=sortList(projs);
    if(projs.length===0)return '';

    const collapsed=sec.collapsed?'section-collapsed':'';
    const arrow=sec.collapsed?'▶':'▼';
    totalShown+=projs.length;

    // 只给组内NAS section 加批量刷新按钮
    const batchRefreshBtn = (sec.key === 'group_active' && projs.length > 0)
      ? `<button class="btn btn-sm section-refresh-btn"
                 onclick="event.stopPropagation(); batchRefreshSection('${sec.key}', this)"
                 title="批量扫描目录，刷新本组所有项目的输出进度">🔄 一键刷新进度</button>`
      : '';
    return `
    <div class="section-block ${collapsed}" data-section-key="${sec.key}">
      <div class="section-header" onclick="toggleSection('${sec.key}')">
        <span class="section-arrow">${arrow}</span>
        <span class="section-title">${sec.name}</span>
        ${batchRefreshBtn}
        <span class="section-count">${projs.length} 个项目</span>
      </div>
      <div class="section-body">
        <div class="grid">
          ${projs.map(projectCardHTML).join('')}
        </div>
      </div>
    </div>`;
  }).join('');

  const fc=$('filterCount');
  if(fc){
    const total=allSections.reduce((s,sec)=>s+(sec.projects?.length||0),0);
    fc.textContent=`显示 ${totalShown} / ${total} 个项目`;
  }

  if(totalShown===0){
    container.innerHTML=`<div class="empty-state"><div>📭 没有匹配的项目</div></div>`;
  }else{
    container.innerHTML=sectionHTML;
  }
}

function toggleSection(key){
  const block=document.querySelector(`[data-section-key="${key}"]`);
  if(!block)return;
  block.classList.toggle('section-collapsed');
  const arrow=block.querySelector('.section-arrow');
  if(arrow)arrow.textContent=block.classList.contains('section-collapsed')?'▶':'▼';
}

