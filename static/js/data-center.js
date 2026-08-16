/* 数据中心：统一入口（数据洞察 / 数据备份 / 全局待办 / 导出 / 产能分析） */
function openDataCenter(){
  const overlay = document.createElement('div');
  overlay.id = 'dataCenterOverlay';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:22000;display:flex;align-items:center;justify-content:center';
  const cards = [
    { icon:'📊', title:'数据洞察', desc:'KPI / 状态分布 / 剪辑集数 / 交付日历', fn:'openInsightsDialog()' },
    { icon:'✅', title:'全局待办', desc:'跨项目查看与处理待办事项', fn:'openGlobalTodos()' },
    { icon:'🛡️', title:'数据备份', desc:'数据库备份 / 恢复', fn:'openBackupDialog()' },
    { icon:'📥', title:'导出档案', desc:'导出项目档案 CSV（含交付日期）', fn:'exportProjectCSV()' },
    { icon:'📈', title:'产能趋势', desc:'近 6 个月立项/完成/交付趋势', fn:'openCapacityTrend()' },
    { icon:'📅', title:'月度报告', desc:'按部门/项目维度的月度报告', fn:"switchTab('report')" },
  ];
  overlay.innerHTML = `
    <div style="background:var(--card,#fff);border-radius:16px;width:680px;max-width:94vw;max-height:88vh;display:flex;flex-direction:column;box-shadow:0 20px 60px rgba(0,0,0,.35)">
      <div style="padding:16px 22px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--border,#e5e5ea)">
        <h3 style="margin:0">🧭 数据中心</h3>
        <button onclick="closeDataCenter()" style="border:none;background:none;font-size:18px;cursor:pointer">✕</button>
      </div>
      <div style="padding:18px 22px;flex:1;overflow-y:auto;display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px">
        ${cards.map(c=>`
          <div onclick="closeDataCenter();${c.fn}" style="background:#f5f5f7;border:1px solid var(--border,#e5e5ea);border-radius:12px;padding:16px;cursor:pointer;transition:transform .15s, box-shadow .15s;text-align:center" onmouseenter="this.style.transform='translateY(-2px)';this.style.boxShadow='0 6px 18px rgba(0,0,0,.12)'" onmouseleave="this.style.transform='';this.style.boxShadow=''">
            <div style="font-size:28px">${c.icon}</div>
            <div style="font-size:14px;font-weight:600;margin:6px 0 2px">${c.title}</div>
            <div style="font-size:11px;color:var(--text-sec)">${c.desc}</div>
          </div>`).join('')}
      </div>
    </div>`;
  overlay.addEventListener('mousedown', e=>{ if(e.target===overlay) overlay.remove(); });
  document.body.appendChild(overlay);
}
function closeDataCenter(){
  const o = document.getElementById('dataCenterOverlay');
  if(o) o.remove();
}

// ============ 全局待办 ============
async function openGlobalTodos(){
  const overlay = document.createElement('div');
  overlay.id = 'globalTodosOverlay';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:23000;display:flex;align-items:center;justify-content:center';
  overlay.innerHTML = `
    <div style="background:var(--card,#fff);border-radius:16px;width:640px;max-width:94vw;max-height:88vh;display:flex;flex-direction:column;box-shadow:0 20px 60px rgba(0,0,0,.35)">
      <div style="padding:14px 20px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--border,#e5e5ea)">
        <h3 style="margin:0">✅ 全局待办</h3>
        <button onclick="closeGlobalTodos()" style="border:none;background:none;font-size:18px;cursor:pointer">✕</button>
      </div>
      <div style="padding:12px 20px;border-bottom:1px solid var(--border,#e5e5ea);display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <input id="gtSearch" type="text" placeholder="🔍 搜索项目/待办..." style="flex:1;min-width:160px;padding:8px 12px;border:1px solid var(--border,#e5e5ea);border-radius:8px;font-size:13px;outline:none" oninput="gtLoad()">
        <label style="font-size:12px;display:flex;align-items:center;gap:4px;cursor:pointer"><input type="checkbox" id="gtDone" onchange="gtLoad()"> 显示已完成</label>
        <span id="gtCount" style="font-size:12px;color:var(--text-sec)"></span>
      </div>
      <div id="gtList" style="padding:12px 20px;flex:1;overflow-y:auto"><div style="color:var(--text-sec);text-align:center;padding:24px">加载中...</div></div>
      <div style="padding:12px 20px;display:flex;justify-content:flex-end;border-top:1px solid var(--border,#e5e5ea)">
        <button class="btn btn-sm" onclick="closeGlobalTodos()">关闭</button>
      </div>
    </div>`;
  overlay.addEventListener('mousedown', e=>{ if(e.target===overlay) overlay.remove(); });
  document.body.appendChild(overlay);
  await gtLoad();
}
function closeGlobalTodos(){
  const o = document.getElementById('globalTodosOverlay');
  if(o) o.remove();
}
async function gtLoad(){
  const list = document.getElementById('gtList');
  const count = document.getElementById('gtCount');
  if(!list) return;
  const q = (document.getElementById('gtSearch')?.value||'').trim();
  const done = document.getElementById('gtDone')?.checked ? 1 : 0;
  try{
    const d = await api('GET','/api/todos/global?done='+done+'&q='+encodeURIComponent(q));
    const todos = (d && d.todos) || [];
    if(count) count.textContent = '共 ' + todos.length + ' 条待办';
    if(!todos.length){ list.innerHTML = '<div style="color:var(--text-sec);text-align:center;padding:24px">暂无待办</div>'; return; }
    // 按项目分组
    const groups = {};
    todos.forEach(t => { (groups[t.project_name] = groups[t.project_name]||[]).push(t); });
    list.innerHTML = Object.keys(groups).map(pname=>{
      const items = groups[pname];
      return `
        <div style="border:1px solid var(--border,#e5e5ea);border-radius:10px;margin-bottom:8px;overflow:hidden">
          <div style="background:#fafafa;padding:8px 12px;font-size:13px;font-weight:600;display:flex;justify-content:space-between;align-items:center">
            <span>📁 ${escHtml(pname)} <span style="color:var(--text-sec);font-weight:400">${escHtml(items[0].status||'')}</span></span>
            <button class="btn btn-sm" onclick="openProjectDetail('${pname.replace(/'/g,"\\'")}')">打开项目</button>
          </div>
          ${items.map(t=>`
            <div style="display:flex;align-items:center;gap:8px;padding:7px 12px;border-top:1px solid #f5f5f5;font-size:13px">
              <button onclick="gtToggle(${t.id},${t.done?0:1},'${pname.replace(/'/g,"\\'")}')" style="background:none;border:none;font-size:16px;cursor:pointer;padding:0" title="切换完成">${t.done?'☑️':'⬜'}</button>
              <span style="flex:1;${t.done?'text-decoration:line-through;color:var(--text-sec)':''}">${escHtml(t.text)}</span>
              <span style="font-size:11px;color:var(--text-sec)">${escHtml((t.created_at||'').slice(0,10))}</span>
              <button onclick="gtDel(${t.id},'${pname.replace(/'/g,"\\'")}')" style="background:none;border:none;color:var(--red);cursor:pointer;font-size:14px" title="删除">🗑</button>
            </div>`).join('')}
        </div>`;
    }).join('');
  }catch(e){ list.innerHTML = '<div style="color:var(--red);text-align:center;padding:20px">加载失败: '+escHtml(e.message)+'</div>'; }
}
async function gtToggle(id, done, pname){
  try{ await api('PUT', `/api/project/${encodeURIComponent(pname)}/todos/${id}`, {done:!!done}); gtLoad(); }
  catch(e){ toast('更新失败: '+e.message,'error'); }
}
async function gtDel(id, pname){
  try{ await api('DELETE', `/api/project/${encodeURIComponent(pname)}/todos/${id}`); gtLoad(); }
  catch(e){ toast('删除失败: '+e.message,'error'); }
}

// ============ 产能趋势（近6个月） ============
async function openCapacityTrend(){
  const overlay = document.createElement('div');
  overlay.id = 'capTrendOverlay';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:24000;display:flex;align-items:center;justify-content:center';
  overlay.innerHTML = `
    <div style="background:var(--card,#fff);border-radius:16px;width:640px;max-width:94vw;max-height:88vh;display:flex;flex-direction:column;box-shadow:0 20px 60px rgba(0,0,0,.35)">
      <div style="padding:14px 20px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--border,#e5e5ea)">
        <h3 style="margin:0">📈 产能趋势（近 6 个月）</h3>
        <button onclick="document.getElementById('capTrendOverlay').remove()" style="border:none;background:none;font-size:18px;cursor:pointer">✕</button>
      </div>
      <div id="capTrendBody" style="padding:20px;flex:1;overflow-y:auto"><div style="color:var(--text-sec);text-align:center">加载中...</div></div>
    </div>`;
  overlay.addEventListener('mousedown', e=>{ if(e.target===overlay) overlay.remove(); });
  document.body.appendChild(overlay);
  try{
    const d = await api('GET','/api/stats/dashboard');
    const trend = (d && d.trend) || [];
    const body = document.getElementById('capTrendBody');
    if(!trend.length){ body.innerHTML = '<div style="color:var(--text-sec);text-align:center;padding:20px">暂无数据</div>'; return; }
    const tMax = Math.max(...trend.map(x=>Math.max(x.total||0,x.done||0,x.delivered||0,1)));
    let rows = '';
    const color = { total:'#5c6bc0', done:'#27ae60', delivered:'#3498db' };
    trend.forEach(t=>{
      const wT = Math.round((t.total||0)/tMax*100), wD = Math.round((t.done||0)/tMax*100), wL = Math.round((t.delivered||0)/tMax*100);
      rows += `<div style="margin-bottom:14px">
        <div style="font-size:13px;font-weight:600;margin-bottom:4px">${t.month}</div>
        ${[['total','立项',wT],['done','完成',wD],['delivered','交付',wL]].map(([k,label,w])=>`
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:3px">
            <span style="width:46px;font-size:11px;color:var(--text-sec);text-align:right">${label}</span>
            <div style="flex:1;height:14px;background:#f0f2f5;border-radius:4px;overflow:hidden"><div style="width:${Math.max(w,3)}%;height:100%;background:${color[k]};border-radius:4px"></div></div>
            <span style="width:26px;font-size:12px;font-weight:600;text-align:right">${t[k]||0}</span>
          </div>`).join('')}
      </div>`;
    });
    body.innerHTML = rows + `<div style="display:flex;gap:14px;justify-content:center;font-size:11px;color:var(--text-sec)">
      <span><span style="display:inline-block;width:10px;height:10px;background:#5c6bc0;border-radius:2px;margin-right:4px"></span>立项</span>
      <span><span style="display:inline-block;width:10px;height:10px;background:#27ae60;border-radius:2px;margin-right:4px"></span>完成</span>
      <span><span style="display:inline-block;width:10px;height:10px;background:#3498db;border-radius:2px;margin-right:4px"></span>交付</span>
    </div>`;
  }catch(e){
    const body = document.getElementById('capTrendBody');
    if(body) body.innerHTML = '<div style="color:var(--red);text-align:center;padding:20px">加载失败: '+escHtml(e.message)+'</div>';
  }
}
