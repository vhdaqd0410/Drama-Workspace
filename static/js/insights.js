/* 数据洞察（可选增强，融合自「项目档案管理器」）
 * 数据大屏 KPI + 交付日历 + 报告导出中心。入口：openInsightsDialog()
 */
async function openInsightsDialog(){
  const overlay = document.createElement('div');
  overlay.id = 'insightsOverlay';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:21000;display:flex;align-items:center;justify-content:center';
  overlay.innerHTML = `
    <div style="background:var(--card,#fff);border-radius:16px;width:760px;max-width:95vw;max-height:90vh;display:flex;flex-direction:column;box-shadow:0 20px 60px rgba(0,0,0,.35);font-family:inherit">
      <div style="padding:16px 22px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--border,#e5e5ea)">
        <h3 style="margin:0">📊 数据洞察</h3>
        <div style="display:flex;gap:8px;align-items:center">
          <button class="btn btn-sm" onclick="exportProjectCSV()">📥 导出项目档案</button>
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
      { label:'项目数', value:d.projectCount, icon:'📁' },
      { label:'总集数', value:d.totalEpisodes, icon:'🎬' },
      { label:'已生成集数', value:d.doneEpisodes, icon:'✂️' },
      { label:'质检通过', value:(d.qaTotal? d.qaPass+'/'+d.qaTotal : 0), icon:'✅' },
      { label:'待办完成', value:(d.todoTotal? d.todoDone+'/'+d.todoTotal : 0), icon:'☑️' },
      { label:'成员', value:d.memberCount, icon:'👥' },
    ];
    let kpiHtml = kpis.map(k=>`
      <div style="flex:1;min-width:110px;background:#f5f5f7;border-radius:12px;padding:12px 14px;text-align:center">
        <div style="font-size:20px">${k.icon}</div>
        <div style="font-size:22px;font-weight:700;color:var(--blue,#0071e3)">${k.value}</div>
        <div style="font-size:11px;color:var(--text-sec);margin-top:2px">${k.label}</div>
      </div>`).join('');

    // 状态分布
    const statusMap = d.statusMap || {};
    const total = Object.values(statusMap).reduce((s,v)=>s+v,0) || 1;
    const statusHtml = Object.entries(statusMap).map(([st,cnt])=>{
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

    // 近12月交付柱状图
    const months = d.deliveryMonths || {};
    const mArr = Object.entries(months).sort((a,b)=>a[0]<b[0]?-1:1).slice(-12);
    const mMax = Math.max(1, ...mArr.map(x=>x[1]));
    let barHtml = mArr.map(([m,cnt])=>{
      const h = Math.max(6, Math.round(cnt/mMax*70));
      return `
        <div style="flex:1;text-align:center">
          <div style="font-size:11px;color:var(--text-sec)">${cnt}</div>
          <div style="background:var(--blue,#0071e3);border-radius:4px 4px 0 0;margin:0 auto;height:${h}px;width:70%"></div>
          <div style="font-size:9px;color:var(--text-sec);margin-top:3px">${m.slice(2)}</div>
        </div>`;
    }).join('') || '<div style="color:var(--text-sec);font-size:12px">暂无交付数据</div>';

    body.innerHTML = `
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:18px">${kpiHtml}</div>
      <div style="display:flex;gap:16px;flex-wrap:wrap">
        <div style="flex:1;min-width:240px;background:#fff;border:1px solid var(--border,#e5e5ea);border-radius:12px;padding:14px">
          <h4 style="margin:0 0 10px;font-size:14px">📌 项目状态分布</h4>
          ${statusHtml || '<div style="color:var(--text-sec);font-size:12px">暂无项目</div>'}
        </div>
        <div style="flex:1;min-width:240px;background:#fff;border:1px solid var(--border,#e5e5ea);border-radius:12px;padding:14px">
          <h4 style="margin:0 0 10px;font-size:14px">📦 近 12 月交付量</h4>
          <div style="display:flex;align-items:flex-end;height:90px;gap:4px">${barHtml}</div>
        </div>
      </div>
      <div style="margin-top:16px;background:#fff;border:1px solid var(--border,#e5e5ea);border-radius:12px;padding:14px">
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
    // 加载当前月日历
    insightsCalMonth = new Date().toISOString().slice(0,7);
    await loadInsightsCalendar();
  }catch(e){
    body.innerHTML = '<div style="color:var(--red);text-align:center;padding:30px">加载失败: '+escHtml(e.message)+'</div>';
  }
}

let insightsCalMonth = '';

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
    const days = (d && d.days) || {};
    // 当月第一天是周几，计算格子
    const [y, m] = insightsCalMonth.split('-').map(Number);
    const firstDow = new Date(y, m-1, 1).getDay();
    const daysInMonth = new Date(y, m, 0).getDate();
    const today = new Date().getDate();
    let cells = '';
    for(let i=0;i<firstDow;i++) cells += '<div style="flex:1"></div>';
    for(let day=1; day<=daysInMonth; day++){
      const key = insightsCalMonth + '-' + String(day).padStart(2,'0');
      const cnt = days[key] || 0;
      const isToday = (day === today);
      const bg = cnt>0 ? (isToday ? '#0071e3' : '#d4edda') : (isToday ? '#cfe4ff' : '#f5f5f7');
      const fg = cnt>0 ? (isToday ? '#fff' : '#155724') : 'inherit';
      cells += `<div style="flex:1;min-width:34px;text-align:center;padding:6px 2px;margin:2px;border-radius:8px;background:${bg};color:${fg};font-size:12px;position:relative">
        <div>${day}</div>
        ${cnt?`<div style="font-size:10px;font-weight:700">${cnt}</div>`:''}
      </div>`;
    }
    box.innerHTML = `<div style="display:flex;flex-wrap:wrap">${cells}</div>
      <div style="font-size:11px;color:var(--text-sec);margin-top:6px">数字 = 当日交付条数；<span style="color:#155724">绿</span>=有交付，<span style="color:#0071e3">蓝</span>=今天</div>`;
  }catch(e){
    box.innerHTML = '<div style="color:var(--red);font-size:12px">加载日历失败</div>';
  }
}

function exportProjectCSV(){
  // 用 fetch 下载（带鉴权）
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
