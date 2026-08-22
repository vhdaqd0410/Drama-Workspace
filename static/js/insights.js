/* 数据洞察（融合自「项目档案管理器」，v2 重构）
 * KPI（当月基准）+ 当月状态分布 + 各剪辑当月集数环形图 + 交付日历
 * 交付日历：绿色=当天交付部数，悬停显示项目名，支持修改交付日期，可同步8月胶片日期
 */
async function openInsightsDialog(){
  const overlay = document.createElement('div');
  overlay.id = 'insightsOverlay';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:21000;display:flex;align-items:center;justify-content:center';
  overlay.innerHTML = `
    <div style="background:var(--card,#fff);border-radius:16px;width:820px;max-width:95vw;max-height:92vh;display:flex;flex-direction:column;box-shadow:0 20px 60px rgba(0,0,0,.35);font-family:inherit">
      <div style="padding:16px 22px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--border,#e5e5ea)">
        <h3 style="margin:0">📊 数据洞察</h3>
        <div style="display:flex;gap:8px;align-items:center">
          <button class="btn btn-sm" onclick="syncDeliveryDates()" title="从分集目标表格读取胶片日期并更新交付日历">🔄 同步交付日期</button>
          <button class="btn btn-sm" onclick="exportProjectCSV()">📥 导出档案</button>
          <button onclick="closeInsightsDialog()" style="border:none;background:none;font-size:18px;cursor:pointer">✕</button>
        </div>
      </div>
      <div style="padding:18px 22px;flex:1;overflow-y:auto">
        <div id="insightsBody"><div style="text-align:center;color:var(--text-sec);padding:30px">加载中...</div></div>
      </div>
    </div>`;
  overlay.addEventListener('mousedown', (e)=>{ if(e.target===overlay) closeInsightsDialog(); });
  document.body.appendChild(overlay);
  await loadInsights();
}

function closeInsightsDialog(){
  const o = document.getElementById('insightsOverlay');
  if(o) o.remove();
}

async function loadInsights(){
  const body = document.getElementById('insightsBody');
  if(!body) return;
  try{
    const d = await api('GET','/api/insights/summary');
    if(!d || !d.ok) throw new Error((d&&d.message)||'加载失败');
    // KPI 卡片：优先用首页概览统计（window._overviewStats，与项目看板首页一致），兜底用 summary
    const os = (typeof window._overviewStats !== 'undefined' && window._overviewStats && typeof window._overviewStats.total === 'number') ? window._overviewStats : null;
    const kpis = [
      { label:'项目总数', value: os ? os.total : d.projectCount, icon:'📁' },
      { label:'本月项目', value: os ? os.this_month : d.monthProjectCount, icon:'🗓' },
      { label:'本月已完成', value: os ? os.this_month_done : d.monthCompleted, icon:'✅' },
      { label:'制作中', value: os ? os.producing : d.inProgress, icon:'🔄' },
      { label:'成员', value:d.memberCount, icon:'👥' },
    ];
    let kpiHtml = kpis.map(k=>`
      <div style="flex:1;min-width:120px;background:#f5f5f7;border-radius:12px;padding:12px 14px;text-align:center">
        <div style="font-size:20px">${k.icon}</div>
        <div style="font-size:22px;font-weight:700;color:var(--blue,#0071e3)">${k.value}</div>
        <div style="font-size:11px;color:var(--text-sec);margin-top:2px">${k.label}</div>
      </div>`).join('');

    // 当月状态分布：与项目看板首页一致（projects 数组按 project_month == 当前月过滤）
    const nowMonth = new Date().getFullYear() + '-' + String(new Date().getMonth()+1).padStart(2,'0');
    const allList = (typeof projects !== 'undefined' && Array.isArray(projects)) ? projects : [];
    const monthList = allList.filter(p => (p.project_month || '') === nowMonth);
    const statusMap = {};
    monthList.forEach(p => { const s = (p.custom_status || '').trim() || '未设置'; statusMap[s] = (statusMap[s]||0) + 1; });
    const totalStatus = Object.values(statusMap).reduce((s,v)=>s+v,0) || 1;
    let statusHtml;
    if(Object.keys(statusMap).length===0){
      statusHtml = '<div style="color:var(--text-sec);font-size:12px">本月暂无项目</div>';
    } else {
      statusHtml = Object.entries(statusMap).map(([st,cnt])=>{
        const pct = Math.round(cnt/totalStatus*100);
        return `
          <div style="margin-bottom:8px">
            <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:3px">
              <span>${escHtml(st)}</span><span>${cnt} (${pct}%)</span>
            </div>
            <div style="background:var(--border,#e5e5ea);border-radius:4px;height:8px;overflow:hidden">
              <div style="height:100%;background:var(--blue,#0071e3);width:${pct}%"></div>
            </div>
          </div>`;
      }).join('');
    }

    // 各剪辑当月集数：与月度报告「剪辑师工作量」同源（/api/stats/dashboard editors）
    let editorEps = {};
    try{
      const sd = await api('GET','/api/stats/dashboard');
      if(sd && sd.editors && Array.isArray(sd.editors)){
        editorEps = {};
        sd.editors.forEach(e => { if(e && e.name && e.assigned) editorEps[e.name] = e.assigned; });
      }
    }catch(e){ /* 保留空 */ }
    const editorDonut = buildDonut(editorEps);

    body.innerHTML = `
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:18px">${kpiHtml}</div>
      <div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:16px">
        <div style="flex:1;min-width:260px;background:#fff;border:1px solid var(--border,#e5e5ea);border-radius:12px;padding:14px">
          <h4 style="margin:0 0 10px;font-size:14px">📌 当月项目状态分布</h4>
          ${statusHtml}
        </div>
        <div style="flex:1;min-width:280px;background:#fff;border:1px solid var(--border,#e5e5ea);border-radius:12px;padding:14px">
          <h4 style="margin:0 0 10px;font-size:14px">🎬 各剪辑当月集数</h4>
          ${Object.keys(editorEps).length ? editorDonut.html : '<div style="color:var(--text-sec);font-size:12px">本月暂无分集数据</div>'}
        </div>
      </div>
      <div style="background:#fff;border:1px solid var(--border,#e5e5ea);border-radius:12px;padding:14px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;flex-wrap:wrap;gap:6px">
          <h4 style="margin:0;font-size:14px">📅 交付日历</h4>
          <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
            <select id="calDeptFilter" onchange="insightsCalDept()" style="padding:4px 8px;border:1px solid var(--border,#e5e5ea);border-radius:6px;font-size:12px">
              <option value="">全部部门</option>
            </select>
            <button class="btn btn-sm" onclick="insightsCalNav(-1)">◀</button>
            <span id="calMonthLabel" style="font-size:13px;font-weight:600"></span>
            <button class="btn btn-sm" onclick="insightsCalNav(1)">▶</button>
            <button class="btn btn-sm" onclick="exportCalMonth()" title="导出本月交付清单">📥 导出</button>
          </div>
        </div>
        <div id="insightsCalBox"><div style="color:var(--text-sec);font-size:12px">加载中...</div></div>
        <div id="deliveryStatsStrip" style="margin-top:10px;padding-top:10px;border-top:1px dashed var(--border,#e5e5ea);display:flex;gap:12px;flex-wrap:wrap;align-items:center"></div>
      </div>`;
    insightsCalMonth = new Date().toISOString().slice(0,7);
    populateCalDept();
    await loadInsightsCalendar();
    loadDeliveryStats();
  }catch(e){
    body.innerHTML = '<div style="color:var(--red);text-align:center;padding:30px">加载失败: '+escHtml(e.message)+'</div>';
  }
}

// 交付日历增强统计（功能8）：按时交付率 + 延迟预警
async function loadDeliveryStats(){
  const el = document.getElementById('deliveryStatsStrip');
  if(!el) return;
  try{
    const d = await api('GET','/api/insights/delivery_stats?month=' + insightsCalMonth);
    if(!d || !d.ok) { el.innerHTML=''; return; }
    const rate = d.on_time_rate !== null && d.on_time_rate !== undefined
      ? d.on_time_rate + '%' : '—';
    const pill = function(label, val, color){
      return '<span style="font-size:12px;background:#f5f5f7;border:1px solid var(--border,#e5e5ea);border-radius:8px;padding:4px 10px">'
        + label + ' <b style="color:' + color + '">' + val + '</b></span>';
    };
    let html = pill('✅ 按时交付率', rate, '#34c759');
    html += pill('📦 已交付', d.delivered_count || 0, '#0071e3');
    html += pill('⏳ 未交付', d.undelivered_count || 0, '#86868b');
    html += pill('🔴 迟交', d.late_count || 0, '#ff3b30');
    if(d.overdue_count){
      html += '<span style="font-size:12px;color:#c5221f;font-weight:600">⚠️ ' + d.overdue_count + ' 个逾期预警</span>';
    }
    el.innerHTML = html;
    // 若有过期预警，可点击展开
    if(d.overdue_count){
      el.innerHTML += ' <button class="btn btn-sm" onclick="showOverdueList(' + JSON.stringify(d.overdue || []).replace(/"/g,'&quot;') + ')">查看逾期项目</button>';
    }
  }catch(e){
    el.innerHTML='';
  }
}
function showOverdueList(list){
  if(!list || !list.length) return;
  alert('⚠️ 逾期未交付项目（共 '+list.length+' 个）：\n\n' + list.map(x=>'• '+x.name+'（应于 '+x.due_date+' 交付）').join('\n'));
}

// 环形图（SVG donut），返回 {html, total}
function buildDonut(map){
  const entries = Object.entries(map).filter(([,v])=>v>0);
  const total = entries.reduce((s,[,v])=>s+v,0);
  if(!entries.length) return {html:'', total:0};
  const R = 40, C = 2*Math.PI*R;
  const palette = ['#0071e3','#34c759','#ff9500','#af52de','#ff3b30','#5856d6','#5ac8fa','#ff2d55','#a2845e','#8e8e93'];
  let offset = 0;
  let arcs = '';
  let legend = '';
  entries.forEach(([name,cnt],i)=>{
    const frac = cnt/total;
    const dash = frac*C;
    const color = palette[i % palette.length];
    arcs += `<circle r="${R}" cx="50" cy="50" fill="none" stroke="${color}" stroke-width="12"
      stroke-dasharray="${dash} ${C-dash}" stroke-dashoffset="${-offset}" transform="rotate(-90 50 50)"></circle>`;
    offset += dash;
    legend += `<div style="display:flex;align-items:center;gap:6px;font-size:12px;margin:2px 0">
      <span style="width:10px;height:10px;border-radius:2px;background:${color}"></span>
      <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escHtml(name)}</span>
      <b>${cnt}集</b></div>`;
  });
  const html = `
    <div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap">
      <svg width="100" height="100" viewBox="0 0 100 100" style="flex-shrink:0">
        ${arcs}
        <text x="50" y="50" text-anchor="middle" dominant-baseline="central" font-size="18" font-weight="700" fill="#1d1d1f">${total}</text>
      </svg>
      <div style="flex:1;min-width:160px">${legend}</div>
    </div>`;
  return {html, total};
}

let insightsCalMonth = '';
let _calData = {};

function insightsCalDept(){
  loadInsightsCalendar();
}

async function insightsCalNav(delta){
  const d = new Date(insightsCalMonth + '-01');
  d.setMonth(d.getMonth() + delta);
  insightsCalMonth = d.toISOString().slice(0,7);
  await loadInsightsCalendar();
}

// 填充部门下拉
function populateCalDept(){
  const sel = document.getElementById('calDeptFilter');
  if(!sel) return;
  const cur = sel.value;
  const depts = [];
  (window.projects||[]).forEach(p=>{ const d=(p.department||'').trim(); if(d && depts.indexOf(d)<0) depts.push(d); });
  sel.innerHTML = '<option value="">全部部门</option>' + depts.sort().map(d=>`<option value="${htm(d)}">${htm(d)}</option>`).join('');
  if(cur) sel.value = cur;
}

async function loadInsightsCalendar(){
  const label = document.getElementById('calMonthLabel');
  const box = document.getElementById('insightsCalBox');
  if(label) label.textContent = insightsCalMonth;
  if(!box) return;
  try{
    const deptSel = document.getElementById('calDeptFilter');
    const dept = deptSel ? deptSel.value : '';
    const d = await api('GET','/api/insights/calendar?month=' + insightsCalMonth + '&dept=' + encodeURIComponent(dept));
    _calData = (d && d.days) || {};
    renderCalendar();
  }catch(e){
    box.innerHTML = '<div style="color:var(--red);font-size:12px">加载日历失败</div>';
  }
}

function renderCalendar(){
  const box = document.getElementById('insightsCalBox');
  if(!box) return;
  const [y, m] = insightsCalMonth.split('-').map(Number);
  const firstDow = new Date(y, m-1, 1).getDay();
  const daysInMonth = new Date(y, m, 0).getDate();
  const today = new Date();
  let cells = '';
  // 表头
  ['日','一','二','三','四','五','六'].forEach(dw=>{ cells += `<div style="flex:1;text-align:center;font-size:11px;color:var(--text-sec);font-weight:600;padding:2px">${dw}</div>`; });
  for(let i=0;i<firstDow;i++) cells += '<div style="flex:1"></div>';
  for(let day=1; day<=daysInMonth; day++){
    const key = insightsCalMonth + '-' + String(day).padStart(2,'0');
    const projs = _calData[key] || [];
    const isToday = (y===today.getFullYear() && m===today.getMonth()+1 && day===today.getDate());
    let bg, fg;
    if(projs.length>0){ bg = isToday ? '#0071e3' : '#34c759'; fg = '#fff'; }
    else if(isToday){ bg = '#cfe4ff'; fg = '#1d1d1f'; }
    else { bg = '#f5f5f7'; fg = 'inherit'; }
    cells += `<div style="flex:1;min-width:44px;text-align:center;padding:6px 2px;margin:2px;border-radius:8px;background:${bg};color:${fg};font-size:12px;position:relative;cursor:${projs.length?'pointer':'default'}"
      data-cal-day="${key}" data-projs='${encodeURIComponent(JSON.stringify(projs))}'
      onmouseenter="calHover(this)" onmouseleave="calHide()"
      onclick="calClickDay('${key}')"
      ondragover="event.preventDefault();this.style.outline='2px dashed #0071e3';this.style.outlineOffset='-2px'"
      ondragleave="this.style.outline=''"
      ondrop="calDrop(event,'${key}')">
      <div>${day}</div>
      ${projs.length?`<div style="font-size:11px;font-weight:700">${projs.length}部</div>`:''}
    </div>`;
  }
  // 快捷视图 + 本月可拖拽项目
  const chips = buildCalQuickChips();
  const dragList = buildCalDragList();
  box.innerHTML = `${chips}
    <div style="display:flex;flex-wrap:wrap">${cells}</div>
    ${dragList}
    <div style="font-size:11px;color:var(--text-sec);margin-top:6px">
      <span style="color:#34c759">■</span> 当天交付部数（悬停看项目，点击修改）
      <span style="color:#0071e3;margin-left:8px">■</span> 今天
      <span style="margin-left:8px;color:#86868b">🖱️ 拖拽下方项目到某天即可改期</span>
    </div>`;
}

// 快捷视图：今日 / 明日 / 逾期
function buildCalQuickChips(){
  const today = new Date();
  const fmt = d => d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
  const t = fmt(today);
  const tm = fmt(new Date(today.getTime()+86400000));
  const nowMonth = t.slice(0,7);
  let todayCnt=0, tomorrowCnt=0, overdueCnt=0;
  Object.keys(_calData).forEach(k=>{
    if(k===t) todayCnt = _calData[k].length;
    if(k===tm && k.slice(0,7)===nowMonth) tomorrowCnt = _calData[k].length;
    if(k<t) overdueCnt += _calData[k].length;
  });
  return `<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px">
    <button class="btn btn-sm" style="${t.slice(0,7)===insightsCalMonth?'background:#0071e3;color:#fff;border-color:#0071e3':''}" onclick="gotoCalDate('${t}')">📌 今日 (${todayCnt})</button>
    <button class="btn btn-sm" style="${tm.slice(0,7)===insightsCalMonth?'background:#0071e3;color:#fff;border-color:#0071e3':''}" onclick="gotoCalDate('${tm}')">⏭ 明日 (${tomorrowCnt})</button>
    <button class="btn btn-sm" style="color:#c5221f" onclick="gotoCalDate('${insightsCalMonth}')">⚠️ 本月逾期 (${overdueCnt})</button>
  </div>`;
}
function gotoCalDate(dateKey){
  insightsCalMonth = dateKey.slice(0,7);
  loadInsightsCalendar();
  // 滚动到该日
  setTimeout(function(){
    const el = document.querySelector(`[data-cal-day="${dateKey}"]`);
    if(el){ el.scrollIntoView({block:'center', behavior:'smooth'}); el.style.boxShadow='0 0 0 3px rgba(0,113,227,.5)'; }
  }, 150);
}
// 本月交付项目可拖拽芯片
function buildCalDragList(){
  const items = [];
  Object.keys(_calData).forEach(k=>{
    (_calData[k]||[]).forEach(p=>{ items.push({name:(p&&p.name)||p, date:k}); });
  });
  if(!items.length) return '';
  return `<div style="margin-top:8px;padding:8px 10px;background:#fafafa;border:1px solid var(--border,#e5e5ea);border-radius:8px">
    <div style="font-size:11px;color:var(--text-sec);margin-bottom:6px">🖱️ 拖拽项目到日历某天以改期：</div>
    <div style="display:flex;flex-wrap:wrap;gap:5px;max-height:96px;overflow-y:auto">
      ${items.map(it=>`<span draggable="true" ondragstart="calDragStart(event,'${it.date}','${jsq(it.name)}')" style="padding:3px 9px;background:#fff;border:1px solid #d1d5db;border-radius:14px;font-size:11px;cursor:grab;user-select:none" title="${escHtml(it.name)} · ${it.date}">${escHtml(it.name)}</span>`).join('')}
    </div>
  </div>`;
}
let _calDrag = null;
function calDragStart(e, oldDate, name){
  _calDrag = { oldDate, name };
  e.dataTransfer.setData('text/plain', name);
  e.dataTransfer.effectAllowed = 'move';
}
function calDrop(e, newDate){
  e.preventDefault();
  e.currentTarget.style.outline = '';
  if(!_calDrag){ return; }
  const { oldDate, name } = _calDrag;
  _calDrag = null;
  if(oldDate === newDate){ toast('日期未变化','info'); return; }
  if(!confirm(`将「${name}」的交付日期从 ${oldDate} 改到 ${newDate}？`)) return;
  const p = '/api/project/' + encodeURIComponent(name) + '/delivered_date';
  api('POST', p, { date: newDate }).then(function(d){
    if(d && d.ok){
      toast('✅ 已改期 ' + name + ' → ' + newDate, 'success');
      loadInsightsCalendar();
    } else toast((d&&d.message)||'改期失败','error');
  }).catch(function(e){ toast('改期失败: '+e.message,'error'); });
}

// 悬停显示当天交付的项目名
function calHover(el){
  let projs = [];
  try{ projs = JSON.parse(decodeURIComponent(el.dataset.projs||'[]')); }catch(e){}
  const tip = document.createElement('div');
  tip.id = 'calTip';
  tip.style.cssText = 'position:fixed;z-index:41000;background:rgba(0,0,0,.85);color:#fff;border-radius:8px;padding:8px 12px;font-size:12px;max-width:320px;box-shadow:0 8px 24px rgba(0,0,0,.35);pointer-events:none';
  tip.innerHTML = projs.length
    ? `<div style="font-weight:600;margin-bottom:4px">${el.dataset.calDay} 交付 ${projs.length} 部：</div>` + projs.map(n=>'• '+escHtml(n.name||n)).join('<br>')
    : '当日无交付';
  document.body.appendChild(tip);
  const r = el.getBoundingClientRect();
  tip.style.left = Math.min(r.right, window.innerWidth - tip.offsetWidth - 8) + 'px';
  tip.style.top = (r.bottom + 6) + 'px';
  el._tip = tip;
}
function calHide(){
  const t = document.getElementById('calTip');
  if(t) t.remove();
}
// 点击日历某天：打开「交付日期编辑」，可搜索项目并「选定」设为当天交付
function calClickDay(key){
  api('GET','/api/projects').then(async function(projResp){
    let all = [];
    if(projResp && projResp.sections){ projResp.sections.forEach(s=>(s.projects||[]).forEach(p=>{ if(!all.find(x=>x.name===p.name)) all.push(p); })); }
    else if(projResp && projResp.projects){ all = projResp.projects; }
    else if(window.projects && Array.isArray(window.projects)){ all = window.projects; }
    if(!all.length){ toast('未加载到项目','warning'); return; }
    openDeliveredDateEditor(key, all);
  }).catch(function(e){
    // 兜底：用全局 projects
    const all = (window.projects && Array.isArray(window.projects)) ? window.projects : [];
    if(all.length) openDeliveredDateEditor(key, all);
    else toast('加载项目失败: '+e.message,'error');
  });
}

// 交付日期编辑弹窗：搜索 + 选定按钮
function openDeliveredDateEditor(dateKey, allProjects){
  const overlay = document.createElement('div');
  overlay.id = 'ddEditorOverlay';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:41000;display:flex;align-items:center;justify-content:center';
  const already = (_calData[dateKey] || []).slice();
  // 全局保存的项目列表用于搜索渲染
  window._ddAllProjects = allProjects;
  window._ddDateKey = dateKey;
  overlay.innerHTML = `
    <div style="background:var(--card,#fff);border-radius:14px;width:560px;max-width:94vw;max-height:88vh;display:flex;flex-direction:column;box-shadow:0 18px 50px rgba(0,0,0,.3)">
      <div style="padding:14px 18px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--border,#e5e5ea)">
        <h3 style="margin:0;font-size:15px">📅 交付日期设置</h3>
        <button onclick="closeDdEditor()" style="border:none;background:none;font-size:18px;cursor:pointer">✕</button>
      </div>
      <div style="padding:14px 18px;border-bottom:1px solid var(--border,#e5e5ea)">
        <div style="display:flex;gap:8px;align-items:center;margin-bottom:8px">
          <label style="font-size:13px;font-weight:600;white-space:nowrap">交付日期</label>
          <input type="date" id="ddDateInput" value="${dateKey}" style="flex:1;padding:7px 10px;border:1px solid var(--border);border-radius:8px;font-size:13px;outline:none">
        </div>
        <input id="ddSearchInput" type="text" placeholder="🔍 搜索项目（名称/编号）..." style="width:100%;padding:9px 12px;border:1px solid var(--border);border-radius:8px;font-size:14px;outline:none" oninput="renderDdList()">
        <div style="font-size:11px;color:var(--text-sec);margin-top:6px">搜索后点击「选定」把项目设为该交付日期；已在该日期的可「移除」。</div>
      </div>
      <div style="padding:12px 18px;flex:1;overflow-y:auto" id="ddListBox"><div style="color:var(--text-sec);font-size:13px">加载中...</div></div>
      <div style="padding:14px 18px;display:flex;justify-content:flex-end;gap:8px;border-top:1px solid var(--border,#e5e5ea)">
        <button class="btn btn-sm" onclick="closeDdEditor()">完成</button>
      </div>
    </div>`;
  overlay.addEventListener('mousedown', e=>{ if(e.target===overlay) closeDdEditor(); });
  document.body.appendChild(overlay);
  // 日期变化时刷新列表（更新选中状态）
  document.getElementById('ddDateInput').addEventListener('change', renderDdList);
  renderDdList();
}

function renderDdList(){
  const box = document.getElementById('ddListBox');
  if(!box) return;
  const dateKey = document.getElementById('ddDateInput').value || window._ddDateKey;
  const q = (document.getElementById('ddSearchInput').value || '').trim().toLowerCase();
  const all = window._ddAllProjects || [];
  let list = all;
  if(q){
    list = all.filter(p => (p.name||'').toLowerCase().indexOf(q) >= 0);
  }
  list = list.slice(0, 120);
  // 已在该日期的项目
  const already = (_calData[dateKey] || []).slice();
  const marked = {};
  already.forEach(n => { marked[(n&&n.name)||n] = true; });
  if(!list.length){
    box.innerHTML = '<div style="color:var(--text-sec);font-size:13px;padding:10px 0">无匹配项目</div>';
    return;
  }
  box.innerHTML = list.map(p=>{
    const isOn = marked[p.name];
    return `
      <div style="display:flex;align-items:center;gap:10px;padding:8px 10px;border:1px solid ${isOn?'#34c759':'var(--border,#e5e5ea)'};border-radius:10px;margin-bottom:6px;background:${isOn?'#f0fdf4':'#fff'}">
        <span style="font-size:16px">${isOn?'✅':'📁'}</span>
        <div style="flex:1;min-width:0">
          <div style="font-size:13px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escHtml(p.name)}</div>
          <div style="font-size:11px;color:var(--text-sec)">${escHtml(p.custom_status||p.delivery_status||'')}${isOn?' · 已设置该日':''}</div>
        </div>
        ${isOn
          ? `<button class="btn btn-sm danger" onclick="ddSetDate('${jsq(p.name)}','')" title="从该日移除">🗑 移除</button>`
          : `<button class="btn btn-sm btn-primary" onclick="ddSetDate('${jsq(p.name)}','${dateKey}')">📌 选定</button>`}
      </div>`;
  }).join('');
}

// 「选定」/「移除」：立即设置/清除该项目的交付日期
function ddSetDate(name, dateKey){
  if(!dateKey && !confirm('确定从该交付日期移除该项目？')) return;
  const apiPath = '/api/project/' + encodeURIComponent(name) + '/delivered_date';
  api('POST', apiPath, { date: dateKey }).then(function(d){
    if(d && d.ok){
      toast(dateKey ? ('✅ 已设置 ' + name + ' → ' + dateKey) : ('🗑 已移除 ' + name), 'success');
      loadInsightsCalendar();
      renderDdList();
    } else toast((d&&d.message)||'保存失败','error');
  }).catch(function(e){ toast('保存失败: '+e.message,'error'); });
}

function closeDdEditor(){
  const o = document.getElementById('ddEditorOverlay');
  if(o) o.remove();
  delete window._ddAllProjects;
  delete window._ddDateKey;
}

function exportProjectCSV(){
  api('GET','/api/insights/export?save=1').then(function(d){
    if(d && d.ok){
      toast('✅ 已导出 '+d.count+' 个项目档案', 'success');
      // 弹窗提示保存位置 + 打开文件夹
      const expPath = d.path || '';
      const overlay = document.createElement('div');
      overlay.id = 'exportHint';
      overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.4);z-index:99999;display:flex;align-items:center;justify-content:center';
      overlay.innerHTML = `
        <div style="background:#fff;border-radius:14px;padding:24px;width:460px;max-width:92vw;box-shadow:0 12px 40px rgba(0,0,0,.2)">
          <div style="font-size:17px;font-weight:700;margin-bottom:10px">📥 导出成功</div>
          <div style="font-size:13px;color:#666;margin-bottom:6px">已导出 <b>${d.count||0}</b> 个项目档案到：</div>
          <div style="background:#f5f5f7;border:1px solid var(--border);border-radius:8px;padding:10px 12px;font-size:13px;word-break:break-all;font-family:monospace;margin-bottom:6px">${expPath}</div>
          <div style="font-size:12px;color:#999;margin-bottom:16px">文件：${d.filename||''}（可用 Excel 打开）</div>
          <div style="display:flex;justify-content:flex-end;gap:10px">
            <button onclick="this.closest('#exportHint').remove()" style="padding:8px 16px;border:1px solid var(--border);border-radius:8px;background:#fff;cursor:pointer;font-size:14px">关闭</button>
            <button onclick="openExportFolder()" style="padding:8px 18px;border:none;border-radius:8px;background:#0071e3;color:#fff;cursor:pointer;font-size:14px">📂 打开文件夹</button>
          </div>
        </div>`;
      overlay.addEventListener('mousedown', e=>{ if(e.target===overlay) overlay.remove(); });
      document.body.appendChild(overlay);
    } else toast((d&&d.message)||'导出失败','error');
  }).catch(function(e){ toast('导出失败: '+e.message,'error'); });
}

function openExportFolder(){
  api('POST','/api/insights/export/open_folder').then(function(d){
    if(d && d.ok) toast('已打开导出文件夹','success');
    else toast((d&&d.message)||'打开失败','error');
  }).catch(function(e){ toast('打开失败: '+e.message,'error'); });
}

// 导出当前月份（含部门筛选）的交付清单 CSV
function exportCalMonth(){
  const deptSel = document.getElementById('calDeptFilter');
  const dept = deptSel ? deptSel.value : '';
  const url = '/api/insights/calendar/export?month=' + insightsCalMonth + '&dept=' + encodeURIComponent(dept);
  const key = window.__API_KEY__ || '';
  fetch(url + (key ? '&key=' + encodeURIComponent(key) : '')).then(function(res){ return res.text(); }).then(function(text){
    const blob = new Blob([text], { type:'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = '交付清单-' + insightsCalMonth + (dept ? '-' + dept : '') + '.csv';
    document.body.appendChild(a); a.click();
    setTimeout(function(){ URL.revokeObjectURL(a.href); a.remove(); }, 200);
    toast('✅ 已导出 ' + insightsCalMonth + ' 交付清单','success');
  }).catch(function(e){ toast('导出失败: '+e.message,'error'); });
}

async function syncDeliveryDates(){
  if(!confirm('从分集管理目标表格读取胶片日期，追加到项目交付日期并刷新交付日历？')) return;
  try{
    const d = await api('POST','/api/insights/sync_delivery_dates',{});
    if(d && d.ok){
      toast('✅ 已同步 ' + (d.updated||0) + ' 个项目的交付日期','success');
      await loadInsights();
    } else toast((d&&d.message)||'同步失败','error');
  }catch(e){ toast('同步失败: '+e.message,'error'); }
}
