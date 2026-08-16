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
    // KPI 卡片
    const kpis = [
      { label:'项目总数', value:d.projectCount, icon:'📁' },
      { label:'当月项目数', value:d.monthProjectCount, icon:'🗓' },
      { label:'当月已完成', value:d.monthCompleted, icon:'✅' },
      { label:'进行中项目', value:d.inProgress, icon:'🔄' },
      { label:'成员', value:d.memberCount, icon:'👥' },
    ];
    let kpiHtml = kpis.map(k=>`
      <div style="flex:1;min-width:120px;background:#f5f5f7;border-radius:12px;padding:12px 14px;text-align:center">
        <div style="font-size:20px">${k.icon}</div>
        <div style="font-size:22px;font-weight:700;color:var(--blue,#0071e3)">${k.value}</div>
        <div style="font-size:11px;color:var(--text-sec);margin-top:2px">${k.label}</div>
      </div>`).join('');

    // 当月状态分布
    const statusMap = d.statusMap || {};
    const total = Object.values(statusMap).reduce((s,v)=>s+v,0) || 1;
    let statusHtml;
    if(Object.keys(statusMap).length===0){
      statusHtml = '<div style="color:var(--text-sec);font-size:12px">本月暂无项目</div>';
    } else {
      statusHtml = Object.entries(statusMap).map(([st,cnt])=>{
        const pct = Math.round(cnt/total*100);
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

    // 各剪辑当月集数：环形图（SVG）
    const editorEps = d.editorEpisodes || {};
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
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
          <h4 style="margin:0;font-size:14px">📅 交付日历</h4>
          <div style="display:flex;gap:6px;align-items:center">
            <button class="btn btn-sm" onclick="insightsCalNav(-1)">◀</button>
            <span id="calMonthLabel" style="font-size:13px;font-weight:600"></span>
            <button class="btn btn-sm" onclick="insightsCalNav(1)">▶</button>
          </div>
        </div>
        <div id="insightsCalBox"><div style="color:var(--text-sec);font-size:12px">加载中...</div></div>
      </div>`;
    insightsCalMonth = new Date().toISOString().slice(0,7);
    await loadInsightsCalendar();
  }catch(e){
    body.innerHTML = '<div style="color:var(--red);text-align:center;padding:30px">加载失败: '+escHtml(e.message)+'</div>';
  }
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

async function insightsCalNav(delta){
  const d = new Date(insightsCalMonth + '-01');
  d.setMonth(d.getMonth() + delta);
  insightsCalMonth = d.toISOString().slice(0,7);
  await loadInsightsCalendar();
}

async function loadInsightsCalendar(){
  const label = document.getElementById('calMonthLabel');
  const box = document.getElementById('insightsCalBox');
  if(label) label.textContent = insightsCalMonth;
  if(!box) return;
  try{
    const d = await api('GET','/api/insights/calendar?month=' + insightsCalMonth);
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
      onclick="calClickDay('${key}')">
      <div>${day}</div>
      ${projs.length?`<div style="font-size:11px;font-weight:700">${projs.length}部</div>`:''}
    </div>`;
  }
  box.innerHTML = `<div style="display:flex;flex-wrap:wrap">${cells}</div>
    <div style="font-size:11px;color:var(--text-sec);margin-top:6px">
      <span style="color:#34c759">■</span> 当天交付部数（悬停看项目，点击修改交付日期）
      <span style="color:#0071e3;margin-left:8px">■</span> 今天
    </div>`;
}

// 悬停显示当天交付的项目名
function calHover(el){
  let projs = [];
  try{ projs = JSON.parse(decodeURIComponent(el.dataset.projs||'[]')); }catch(e){}
  const tip = document.createElement('div');
  tip.id = 'calTip';
  tip.style.cssText = 'position:fixed;z-index:41000;background:rgba(0,0,0,.85);color:#fff;border-radius:8px;padding:8px 12px;font-size:12px;max-width:320px;box-shadow:0 8px 24px rgba(0,0,0,.35);pointer-events:none';
  tip.innerHTML = projs.length
    ? `<div style="font-weight:600;margin-bottom:4px">${el.dataset.calDay} 交付 ${projs.length} 部：</div>` + projs.map(n=>'• '+escHtml(n)).join('<br>')
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
function calClickDay(key){
  const projs = _calData[key] || [];
  api('GET','/api/projects').then(async function(projResp){
    let all = [];
    if(projResp && projResp.sections){ projResp.sections.forEach(s=>(s.projects||[]).forEach(p=>{ if(!all.find(x=>x.name===p.name)) all.push(p); })); }
    else if(projResp && projResp.projects){ all = projResp.projects; }
    if(!all.length){ toast('未加载到项目','warning'); return; }
    const existing = projs.map(n=>all.find(p=>p.name===n)).filter(Boolean);
    const others = all.filter(p=>!projs.includes(p.name)).slice(0,100);
    openDeliveredDateEditor(key, existing, others);
  }).catch(function(e){ toast('加载项目失败: '+e.message,'error'); });
}

function openDeliveredDateEditor(dateKey, existing, others){
  const overlay = document.createElement('div');
  overlay.id = 'ddEditorOverlay';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:41000;display:flex;align-items:center;justify-content:center';
  const row = (p, dflt) => `
    <div style="display:flex;align-items:center;gap:8px;padding:4px 0;font-size:13px">
      <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escHtml(p.name)}</span>
      <input type="date" value="${dflt}" data-dd-name="${htm(p.name)}" style="padding:3px 6px;border:1px solid var(--border);border-radius:6px;font-size:12px">
    </div>`;
  const section = (title, list, dflt) => list.length
    ? `<div style="font-size:12px;font-weight:600;color:var(--text-sec);margin:8px 0 4px">${title} (${list.length})</div>` + list.map(p=>row(p, dflt)).join('')
    : '';
  overlay.innerHTML = `
    <div style="background:var(--card,#fff);border-radius:14px;width:520px;max-width:94vw;max-height:86vh;display:flex;flex-direction:column;box-shadow:0 18px 50px rgba(0,0,0,.3)">
      <div style="padding:14px 18px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--border,#e5e5ea)">
        <h3 style="margin:0;font-size:15px">📅 ${dateKey} 交付日期设置</h3>
        <button onclick="closeDdEditor()" style="border:none;background:none;font-size:18px;cursor:pointer">✕</button>
      </div>
      <div style="padding:14px 18px;flex:1;overflow-y:auto">
        <div style="font-size:12px;color:var(--text-sec);margin-bottom:6px">修改日期保存后自动更新日历；清空日期则该项目从日历移除。</div>
        ${section('当日已交付', existing, dateKey)}
        ${section('其他项目（可补录为当天交付）', others, dateKey)}
      </div>
      <div style="padding:14px 18px;display:flex;justify-content:flex-end;gap:8px;border-top:1px solid var(--border,#e5e5ea)">
        <button class="btn btn-sm" onclick="closeDdEditor()">完成</button>
      </div>
    </div>`;
  overlay.addEventListener('mousedown', e=>{ if(e.target===overlay) closeDdEditor(); });
  document.body.appendChild(overlay);
  overlay.querySelectorAll('input[data-dd-name]').forEach(inp=>{
    inp.addEventListener('change', function(){
      const name = this.dataset.ddName;
      const val = this.value || '';
      api('POST','/api/project/' + encodeURIComponent(name) + '/delivered_date', { date: val })
        .then(function(d){ if(d && d.ok){ toast((val?'✅ 已设置 ':'已清除 ') + name,'success'); loadInsightsCalendar(); } else toast('保存失败','error'); })
        .catch(function(e){ toast('保存失败: '+e.message,'error'); });
    });
  });
}
function closeDdEditor(){
  const o = document.getElementById('ddEditorOverlay');
  if(o) o.remove();
}

function exportProjectCSV(){
  api('GET','/api/insights/export').then(function(text){
    const blob = new Blob([text], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = '项目档案-' + new Date().toISOString().slice(0,10) + '.csv';
    document.body.appendChild(a);
    a.click();
    setTimeout(function(){ URL.revokeObjectURL(a.href); a.remove(); }, 200);
    toast('✅ 已导出项目档案','success');
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
