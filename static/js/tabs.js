/* ============ 任务中心 Tab ============ */
let _activityCache = null;
async function loadActivityTab(){
  const el = document.getElementById('activityContent');
  if(!el) return;
  if(_activityCache){
    el.innerHTML = _activityCache;
    _bindActivityFilters();
    return;
  }
  el.innerHTML = '<div style="text-align:center;padding:40px;color:#86868b">加载中...</div>';
  try{
    const d = await api('GET','/api/activity_log?limit=200');
    if(!d.ok){ el.innerHTML = '<div style="color:#ff3b30">加载失败</div>'; return; }
    _activityCache = _renderActivityHTML(d);
    el.innerHTML = _activityCache;
    _bindActivityFilters();
  }catch(e){
    el.innerHTML = '<div style="color:#ff3b30">加载失败: '+e.message+'</div>';
  }
}

function _renderActivityHTML(d){
  const logs = d.logs || [];
  const active = d.active_runs || [];
  const fmtSize = (b) => { b = Number(b)||0; if(b<1024) return b+'B'; if(b<1048576) return (b/1024).toFixed(1)+'KB'; if(b<1073741824) return (b/1048576).toFixed(1)+'MB'; return (b/1073741824).toFixed(2)+'GB'; };
  const statusCls = (s) => {
    if(s==='success') return 'color:#34c759';
    if(s==='fail'||s==='error') return 'color:#ff3b30';
    return 'color:#86868b';
  };

  let html = `
  <div style="display:flex;gap:10px;margin-bottom:16px;align-items:center">
    <input id="actSearch" placeholder="🔍 搜索项目名..." style="flex:1;padding:8px;border:1px solid #e5e5ea;border-radius:8px">
    <select id="actType"><option value="">全部类型</option><option value="sync">📦 同步</option><option value="deliver">📤 回传</option></select>
    <select id="actStatus"><option value="">全部状态</option><option value="success">✅ 成功</option><option value="fail">❌ 失败</option></select>
    <button class="btn btn-sm btn-primary" onclick="loadActivityTab()" style="padding:8px 14px">🔄 刷新</button>
  </div>`;

  // 进行中的任务
  if(active.length){
    html += `<div style="margin-bottom:16px;padding:14px;background:#fff3cd;border-radius:8px;border:1px solid #ffe08a">
      <b style="color:#856404">⏳ 进行中的回传任务</b><br>
      ${active.map(r => `<span style="margin-right:12px">${r.project_name} (${r.status})</span>`).join('')}
    </div>`;
  }

  if(!logs.length){
    html += '<div style="text-align:center;padding:60px;color:#86868b">📭 暂无操作日志</div>';
  }else{
    html += `<table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead>
        <tr style="background:#f5f5f7;border-bottom:2px solid #e5e5ea">
          <th style="padding:10px;text-align:left">时间</th>
          <th style="padding:10px;text-align:left">类型</th>
          <th style="padding:10px;text-align:left">项目</th>
          <th style="padding:10px;text-align:left">详情</th>
          <th style="padding:10px;text-align:right">大小</th>
          <th style="padding:10px;text-align:center">状态</th>
        </tr>
      </thead><tbody>`;
    logs.forEach(l => {
      const icon = l.type==='sync' ? '📦' : '📤';
      const st = l.status || '';
      const label = st==='success'?'成功':st==='fail'?'失败':st==='info'?'信息':st;
      const detail = l.message || l.file_name || l.action || '';
      const time = (l.created_at||'').replace('T',' ').slice(0,19);
      html += `<tr style="border-bottom:1px solid #f0f0f0">
        <td style="padding:8px 10px;color:#86868b;font-size:12px">${time}</td>
        <td style="padding:8px 10px">${icon}</td>
        <td style="padding:8px 10px;font-weight:500">${l.project_name}</td>
        <td style="padding:8px 10px;color:#555">${detail}</td>
        <td style="padding:8px 10px;text-align:right;font-variant-numeric:tabular-nums">${fmtSize(l.file_size||0)}</td>
        <td style="padding:8px 10px;text-align:center;font-weight:600;${statusCls(st)}">${label}</td>
      </tr>`;
    });
    html += '</tbody></table>';
  }
  return html;
}

function _bindActivityFilters(){
  const q = document.getElementById('actSearch');
  const t = document.getElementById('actType');
  const s = document.getElementById('actStatus');
  if(q) q.oninput = () => _filterActivity();
  if(t) t.onchange = () => _filterActivity();
  if(s) s.onchange = () => _filterActivity();
}

function _filterActivity(){
  const el = document.getElementById('activityContent');
  if(!el) return;
  const q = (document.getElementById('actSearch')?.value||'').toLowerCase();
  const t = document.getElementById('actType')?.value||'';
  const s = document.getElementById('actStatus')?.value||'';
  const rows = el.querySelectorAll('tbody tr');
  let total = 0;
  rows.forEach(tr => {
    const name = tr.cells[2]?.textContent.toLowerCase()||'';
    const typeIcon = tr.cells[1]?.textContent||'';
    const statusText = tr.cells[5]?.textContent||'';
    const pass = (!q || name.includes(q))
      && (!t || (t==='sync' && typeIcon.includes('📦')) || (t==='deliver' && typeIcon.includes('📤')))
      && (!s || (s==='success' && statusText.includes('成功')) || (s==='fail' && statusText.includes('失败')));
    tr.style.display = pass ? '' : 'none';
    if(pass) total++;
  });
}

/* ============ 月度报告 Tab ============ */
async function loadReportTab(){
  const el = document.getElementById('reportContent');
  if(!el) return;
  const now = new Date();
  const curMonth = now.getFullYear() + '-' + String(now.getMonth()+1).padStart(2,'0');
  const html = `
  <div style="display:flex;gap:10px;margin-bottom:16px;align-items:center">
    <label style="color:#666">📅 选择月份：</label>
    <select id="reportMonth" style="padding:8px;border:1px solid #e5e5ea;border-radius:8px">
      ${_monthOptions()}
    </select>
    <button class="btn btn-sm btn-primary" onclick="_loadReportData()">🔍 查看报告</button>
    <button class="btn btn-sm" id="btnCommission" onclick="showCommissionReport()" style="background:#af52de;color:#fff" title="从分集数据计算本月每人绩效与提成">💰 提成/绩效</button>
    <button class="btn btn-sm" id="btnPersonCards" onclick="showPersonCards()" style="background:#0071e3;color:#fff" title="年度每人工作量卡片与趋势">👥 个人卡片</button>
    <button class="btn btn-sm" onclick="_downloadExcel()" style="background:#34c759;color:#fff">📥 下载 Excel</button>
  </div>
  <div id="reportWorkloadBoard" style="margin-bottom:20px"></div>
  <div id="commissionBoard" style="margin-bottom:20px"></div>
  <div id="personCardsBoard" style="margin-bottom:20px"></div>
  <div id="reportBody">正在加载...</div>`;
  el.innerHTML = html;
  // 渲染工作量/数据看板
  try{ if(typeof renderWorkloadBoard==='function') await renderWorkloadBoard('reportWorkloadBoard'); }catch(_){}
  _loadReportData();
}

// 按钮反馈：高亮当前视图按钮 + 显示加载态
function _setActiveBtn(activeId){
  ['btnCommission','btnPersonCards'].forEach(function(id){
    const b = document.getElementById(id);
    if(!b) return;
    if(id === activeId){ b.style.outline = '2px solid #fff'; b.style.boxShadow = '0 0 0 3px rgba(0,0,0,.25)'; b.style.transform='scale(1.04)'; }
    else { b.style.outline = ''; b.style.boxShadow = ''; b.style.transform=''; }
  });
}
function _btnLoading(id, on){
  const b = document.getElementById(id);
  if(!b) return;
  const txt = id === 'btnCommission' ? '💰 提成/绩效' : '👥 个人卡片';
  if(on){ b.dataset.orig = b.innerHTML; b.innerHTML = txt + ' ⏳'; b.disabled = true; }
  else { b.innerHTML = b.dataset.orig || txt; b.disabled = false; b.dataset.orig=''; }
}

// 个人工作量卡片（功能2）：年度逐月集数 + 角色 + 汇总 + 趋势
async function showPersonCards(){
  _setActiveBtn('btnPersonCards');
  _btnLoading('btnPersonCards', true);
  await _loadPersonCards();
  _btnLoading('btnPersonCards', false);
}
async function _loadPersonCards(){
  const el = document.getElementById('personCardsBoard');
  if(!el) return;
  el.innerHTML = '<div style="text-align:center;padding:20px;color:var(--text-sec)">👥 正在加载个人卡片...</div>';
  try{
    const d = await api('GET','/api/commission/person_cards');
    if(!d || !d.ok){ el.innerHTML = '<div style="color:var(--red);padding:12px">'+escHtml(d?.message||'加载失败')+'</div>'; return; }
    const cards = d.cards || [];
    if(!cards.length){ el.innerHTML = '<div style="color:var(--text-sec);padding:20px;text-align:center">'+escHtml(d.year)+' 年暂无分集数据</div>'; return; }
    // 全年月份序列
    const months = ['01','02','03','04','05','06','07','08','09','10','11','12'].map(m=>d.year+'-'+m);
    const maxTotal = Math.max(...cards.map(c=>c.annual_total), 1);
    let html = '<div style="background:#fff;border:1px solid var(--border,#e5e5ea);border-radius:12px;padding:14px">'
      + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">'
      + '<h4 style="margin:0;font-size:14px">👥 个人工作量卡片（'+escHtml(d.year)+' 年 · '+cards.length+' 人）</h4>'
      + '<span style="font-size:11px;color:var(--text-sec)">点击上方按钮即可刷新 · 数据实时来自分集</span>'
      + '</div><div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px">';
    cards.forEach(c => {
      const barW = Math.round(c.annual_total/maxTotal*100);
      const monthCells = months.map(m => {
        const v = c.monthly[m] || 0;
        return '<div style="flex:1;text-align:center"><div style="font-size:10px;color:var(--text-sec)">'+m.slice(5)+'</div>'
          + '<div style="font-size:11px;font-weight:600">'+(v||'·')+'</div></div>';
      }).join('');
      html += '<div style="border:1px solid var(--border,#e5e5ea);border-radius:10px;padding:10px">'
        + '<div style="display:flex;justify-content:space-between;align-items:center">'
        + '<span style="font-weight:700;font-size:14px">'+escHtml(c.name)+'</span>'
        + '<span style="font-size:11px;color:var(--text-sec)">'+escHtml(c.role)+'</span></div>'
        + '<div style="font-size:11px;color:var(--text-sec);margin:6px 0">年度 <b style="color:#0071e3">'+c.annual_total+'</b> 集 · 参与 '+c.month_count+' 个月 · 峰值 <b>'+c.best_eps+'</b> 集('+escHtml(c.best_month||'—')+')</div>'
        + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">'
        + '<div style="flex:1;height:8px;background:#f0f2f5;border-radius:4px;overflow:hidden"><div style="width:'+barW+'%;height:100%;background:linear-gradient(90deg,#5ac8fa,#0071e3);border-radius:4px"></div></div>'
        + '</div>'
        + '<div style="display:flex;gap:2px;margin-top:6px">'+monthCells+'</div>'
        + '</div>';
    });
    html += '</div></div>';
    el.innerHTML = html;
  }catch(e){
    el.innerHTML = '<div style="color:var(--red);padding:12px">加载失败: '+escHtml(e.message)+'</div>';
  }
}

// 提成/绩效全链路报表（功能1）：从分集数据计算每人绩效+提成，支持各维度排序
let _commissionSort = {key:'commission', dir:-1};
async function showCommissionReport(){
  _setActiveBtn('btnCommission');
  _btnLoading('btnCommission', true);
  await _loadCommissionReport();
  _btnLoading('btnCommission', false);
}
async function _loadCommissionReport(){
  const el = document.getElementById('commissionBoard');
  if(!el) return;
  const month = document.getElementById('reportMonth')?.value || '';
  el.innerHTML = '<div style="text-align:center;padding:20px;color:var(--text-sec)">💰 正在计算提成/绩效...</div>';
  try{
    const d = await api('GET','/api/commission/monthly?month=' + encodeURIComponent(month));
    if(!d || !d.ok){ el.innerHTML = '<div style="color:var(--red);padding:12px">' + escHtml(d?.message||'加载失败') + '</div>'; return; }
    const s = d.summary || {};
    let rows = d.rows || [];
    // 排序：按当前 key + dir
    const {key, dir} = _commissionSort;
    rows = rows.slice().sort(function(a,b){
      let va=a[key], vb=b[key];
      if(key==='name'||key==='role'){ va=String(va||''); vb=String(vb||''); return dir*(va<vb?-1:va>vb?1:0); }
      va=Number(va||0); vb=Number(vb||0);
      return dir*(va-vb);
    });
    // 可排序列定义
    const cols = [
      {k:'name', label:'姓名'},
      {k:'role', label:'角色'},
      {k:'episodes', label:'集数', right:true},
      {k:'quota', label:'基准', right:true},
      {k:'is_complete', label:'达标', center:true},
      {k:'overtime_bonus', label:'超额', right:true},
      {k:'shortage_penalty', label:'缺集扣', right:true},
      {k:'group_bonus', label:'组奖', right:true},
      {k:'commission', label:'提成', right:true},
    ];
    let html = '<div style="background:#fff;border:1px solid var(--border,#e5e5ea);border-radius:12px;padding:14px">';
    html += '<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px;margin-bottom:10px">'
      + '<h4 style="margin:0;font-size:14px">💰 提成 / 绩效（' + escHtml(month) + ' · 分集数据）</h4>'
      + '<span style="font-size:12px;color:var(--text-sec)">总提成 <b style="color:#af52de">'+ (s.total_commission||0) +'</b> 元 · 达标 '+s.met_quota+'/'+s.total_people+' · 集数 '+s.total_episodes+' · 点击表头排序</span>'
      + '</div>';
    html += '<table style="width:100%;border-collapse:collapse;font-size:12px">'
      + '<thead><tr style="background:#f5f5f7;border-bottom:2px solid #e5e5ea">'
      + cols.map(function(c){
        const align = c.right ? 'text-align:right' : (c.center ? 'text-align:center' : 'text-align:left');
        const arrow = key===c.k ? (dir>0?' ▲':' ▼') : '';
        const sortable = c.k !== 'is_complete';
        return '<th style="padding:8px;'+align+';cursor:'+(sortable?'pointer':'default')+';user-select:none" '
          + (sortable ? 'onclick="commissionSort(\''+c.k+'\')" title="点击排序"' : '')
          + '>'+c.label+arrow+'</th>';
      }).join('')
      + '</tr></thead><tbody>';
    rows.forEach(r => {
      html += '<tr style="border-bottom:1px solid #f0f0f0">'
        + '<td style="padding:6px 8px">'+escHtml(r.name)+'</td>'
        + '<td style="padding:6px 8px;color:var(--text-sec)">'+escHtml(r.role)+'</td>'
        + '<td style="padding:6px 8px;text-align:right">'+r.episodes+'</td>'
        + '<td style="padding:6px 8px;text-align:right">'+(r.quota||'—')+'</td>'
        + '<td style="padding:6px 8px;text-align:center;color:'+(r.is_complete?'#34c759':'#ff3b30')+'">'+(r.is_complete?'✔':'✘')+'</td>'
        + '<td style="padding:6px 8px;text-align:right;color:#34c759">'+(r.overtime_bonus||0)+'</td>'
        + '<td style="padding:6px 8px;text-align:right;color:#ff3b30">'+(r.shortage_penalty||0)+'</td>'
        + '<td style="padding:6px 8px;text-align:right">'+(r.group_bonus||0)+'</td>'
        + '<td style="padding:6px 8px;text-align:right;font-weight:700;color:'+(r.commission>=0?'#0071e3':'#c5221f')+'">'+(r.commission||0)+'</td>'
        + '</tr>';
    });
    html += '</tbody></table></div>';
    el.innerHTML = html;
  }catch(e){
    el.innerHTML = '<div style="color:var(--red);padding:12px">加载失败: '+escHtml(e.message)+'</div>';
  }
}
// 表头点击排序（功能2）
function commissionSort(key){
  if(_commissionSort.key === key) _commissionSort.dir = -_commissionSort.dir;
  else _commissionSort = {key:key, dir:key==='name'||key==='role'?1:-1};
  _loadCommissionReport();
}

function _monthOptions(){
  const now = new Date();
  let out = '';
  for(let i=0;i<18;i++){
    const d = new Date(now.getFullYear(), now.getMonth()-i, 1);
    const ym = d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0');
    out += `<option value="${ym}" ${i===0?'selected':''}>${ym}${i===0?' · 本月':''}</option>`;
  }
  return out;
}

async function _loadReportData(){
  const el = document.getElementById('reportBody');
  if(!el) return;
  const monthSel = document.getElementById('reportMonth');
  const month = monthSel ? monthSel.value : '';
  el.innerHTML = '<div style="text-align:center;padding:30px;color:#86868b">🔍 正在加载 ' + (month||'') + ' 报告...</div>';
  try{
    const d = await api('GET','/api/report/monthly?month=' + encodeURIComponent(month));
    if(!d.ok){ el.innerHTML = '<div style="color:#ff3b30;padding:20px">加载失败</div>'; return; }
    el.innerHTML = _renderReportHTML(d);
  }catch(e){
    el.innerHTML = '<div style="color:#ff3b30;padding:20px">加载失败: '+e.message+'</div>';
  }
}

function _renderReportHTML(d){
  const fmtSize = (b) => { b = Number(b)||0; if(b<1024) return b+'B'; if(b<1048576) return (b/1024).toFixed(1)+'MB'; if(b<1073741824) return (b/1048576).toFixed(1)+'MB'; return (b/1073741824).toFixed(2)+'GB'; };
  const ds = d.delivery_stats || {};
  const summary = d.summary_by_department || [];
  const projects = d.projects || [];

  let html = `
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:20px">
    <div style="background:linear-gradient(135deg,#007aff,#5ac8fa);color:#fff;padding:16px;border-radius:12px">
      <div style="font-size:13px;opacity:.85">📦 本月项目</div>
      <div style="font-size:28px;font-weight:700;margin-top:4px">${projects.length}</div>
    </div>
    <div style="background:linear-gradient(135deg,#34c759,#30d158);color:#fff;padding:16px;border-radius:12px">
      <div style="font-size:13px;opacity:.85">📤 总回传数据量</div>
      <div style="font-size:28px;font-weight:700;margin-top:4px">${fmtSize(ds.total_bytes)}</div>
      <div style="font-size:12px;opacity:.75">${ds.file_count||0} 个文件</div>
    </div>
    <div style="background:linear-gradient(135deg,#ff9500,#ff3b30);color:#fff;padding:16px;border-radius:12px">
      <div style="font-size:13px;opacity:.85">🎬 总集数</div>
      <div style="font-size:28px;font-weight:700;margin-top:4px">${summary.reduce((s,x)=>s+(x.total_eps||0),0)}</div>
    </div>
    <div style="background:linear-gradient(135deg,#af52de,#5856d6);color:#fff;padding:16px;border-radius:12px">
      <div style="font-size:13px;opacity:.85">🏢 涉及部门</div>
      <div style="font-size:28px;font-weight:700;margin-top:4px">${summary.length}</div>
    </div>
  </div>`;

  if(!summary.length){
    html += '<div style="text-align:center;padding:60px;color:#86868b">📭 ' + d.month + ' 没有设置月份的项目</div>';
    return html;
  }

  html += `<h3 style="margin:16px 0 8px">🏢 按部门汇总</h3>
  <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:20px">
    <thead><tr style="background:#f5f5f7;border-bottom:2px solid #e5e5ea">
      <th style="padding:10px;text-align:left">部门</th>
      <th style="padding:10px;text-align:right">项目数</th>
      <th style="padding:10px;text-align:right">已完成</th>
      <th style="padding:10px;text-align:right">制作中</th>
      <th style="padding:10px;text-align:right">已交付</th>
      <th style="padding:10px;text-align:right">总集数</th>
    </tr></thead><tbody>`;
  summary.forEach(s => {
    html += `<tr style="border-bottom:1px solid #f0f0f0">
      <td style="padding:8px 10px;font-weight:500">${s.department||'(未分类)'}</td>
      <td style="padding:8px 10px;text-align:right">${s.total}</td>
      <td style="padding:8px 10px;text-align:right;color:#34c759">${s.completed}</td>
      <td style="padding:8px 10px;text-align:right;color:#ff9500">${s.editing}</td>
      <td style="padding:8px 10px;text-align:right;color:#007aff">${s.delivered}</td>
      <td style="padding:8px 10px;text-align:right">${s.total_eps}</td>
    </tr>`;
  });
  html += '</tbody></table>';

  html += `<h3 style="margin:16px 0 8px">📋 项目清单 (${projects.length} 个)</h3>
  <div style="max-height:400px;overflow-y:auto;border:1px solid #e5e5ea;border-radius:8px">
  <table style="width:100%;border-collapse:collapse;font-size:13px">
    <thead style="position:sticky;top:0;background:#f5f5f7">
      <tr>
        <th style="padding:8px 10px;text-align:left">项目</th>
        <th style="padding:8px 10px;text-align:left">部门</th>
        <th style="padding:8px 10px;text-align:left">状态</th>
        <th style="padding:8px 10px;text-align:left">交付</th>
        <th style="padding:8px 10px;text-align:right">集数</th>
      </tr>
    </thead><tbody>`;
  projects.forEach(p => {
    html += `<tr style="border-bottom:1px solid #f5f5f5">
      <td style="padding:6px 10px">${p.name}</td>
      <td style="padding:6px 10px;color:#666">${p.department||''}</td>
      <td style="padding:6px 10px">${p.custom_status||''}</td>
      <td style="padding:6px 10px;color:#666">${p.delivery_status||''}</td>
      <td style="padding:6px 10px;text-align:right">${p.current_episodes||0}/${p.total_episodes||0}</td>
    </tr>`;
  });
  html += '</tbody></table></div>';
  return html;
}

function _downloadExcel(){
  const month = document.getElementById('reportMonth')?.value || '';
  if(!month) return;
  const key = window.__API_KEY__ || '';
  const url = '/api/report/monthly/export?month=' + month + (key ? '&key=' + encodeURIComponent(key) : '');
  window.open(url, '_blank');
}
