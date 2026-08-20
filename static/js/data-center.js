/* 数据中心：统一入口（数据洞察 / 数据备份 / 全局待办 / 导出 / 产能分析） */
function openDataCenter(){
  const overlay = document.createElement('div');
  overlay.id = 'dataCenterOverlay';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:22000;display:flex;align-items:center;justify-content:center';
  const cards = [
    { icon:'📊', title:'数据洞察', desc:'KPI / 状态分布 / 剪辑集数 / 交付日历', fn:'openInsightsDialog()' },
    { icon:'🗂️', title:'任务中心', desc:'统一待办看板：分组/筛选/拖拽/新建编辑', fn:'openTaskBoard()' },
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
            <button class="btn btn-sm" onclick="openProjectDetail('${jsq(pname)}')">打开项目</button>
          </div>
          ${items.map(t=>`
            <div style="display:flex;align-items:center;gap:8px;padding:7px 12px;border-top:1px solid #f5f5f5;font-size:13px">
              <button onclick="gtToggle(${t.id},${t.done?0:1},'${jsq(pname)}')" style="background:none;border:none;font-size:16px;cursor:pointer;padding:0" title="切换完成">${t.done?'☑️':'⬜'}</button>
              <span style="flex:1;${t.done?'text-decoration:line-through;color:var(--text-sec)':''}">${escHtml(t.text)}</span>
              <span style="font-size:11px;color:var(--text-sec)">${escHtml((t.created_at||'').slice(0,10))}</span>
              <button onclick="gtDel(${t.id},'${jsq(pname)}')" style="background:none;border:none;color:var(--red);cursor:pointer;font-size:14px" title="删除">🗑</button>
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

// ===== 任务中心（强化看板）：待办/进行中/已完成 或 高/中/低 优先级，可切换分组
// 支持：分组切换、完整卡片（优先级/截止日/负责人/所属项目）、筛选、统计、新建/编辑面板、拖拽
var _taskBoard = {
  group: 'status',      // status | priority
  q: '',
  assignee: '',
  overdueOnly: false,
  projectFilter: '',
  columns: {}
};

function openTaskBoard(){
  const overlay = document.createElement('div');
  overlay.id = 'taskBoardOverlay';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:23000;display:flex;align-items:center;justify-content:center';
  overlay.innerHTML = `<div style="background:#f0f2f5;border-radius:14px;width:1080px;max-width:97vw;height:90vh;display:flex;flex-direction:column;box-shadow:0 20px 60px rgba(0,0,0,.35)">
    <div style="padding:12px 18px;display:flex;align-items:center;justify-content:space-between;background:#fff;border-radius:14px 14px 0 0;flex-wrap:wrap;gap:8px">
      <h3 style="margin:0;font-size:15px">🗂️ 任务中心</h3>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <button class="btn btn-sm btn-primary" onclick="taskNewTodo()">➕ 新建待办</button>
        <button class="btn btn-sm" onclick="taskToggleView()" id="taskViewToggle">👁 列表视图</button>
        <button onclick="this.closest('#taskBoardOverlay').remove()" style="border:none;background:none;font-size:18px;cursor:pointer">✕</button>
      </div>
    </div>
    <div style="padding:10px 18px;background:#fff;border-bottom:1px solid var(--border,#e5e5ea);display:flex;gap:8px;align-items:center;flex-wrap:wrap" id="taskBoardFilter">
      <label style="font-size:12px;display:flex;align-items:center;gap:4px">分组
        <select id="taskGroup" onchange="_taskBoard.group=this.value;loadTaskBoard()" style="padding:5px 8px;border:1px solid var(--border,#e5e5ea);border-radius:6px;font-size:12px">
          <option value="status">按状态</option>
          <option value="priority">按优先级</option>
        </select>
      </label>
      <input id="taskSearch" type="text" placeholder="🔍 搜索待办/项目..." style="flex:1;min-width:140px;padding:6px 10px;border:1px solid var(--border,#e5e5ea);border-radius:6px;font-size:12px;outline:none" oninput="_taskBoard.q=this.value;clearTimeout(window._taskT);window._taskT=setTimeout(loadTaskBoard,250)">
      <select id="taskAssignee" onchange="_taskBoard.assignee=this.value;loadTaskBoard()" style="padding:5px 8px;border:1px solid var(--border,#e5e5ea);border-radius:6px;font-size:12px">
        <option value="">全部负责人</option>
      </select>
      <select id="taskProject" onchange="_taskBoard.projectFilter=this.value;loadTaskBoard()" style="padding:5px 8px;border:1px solid var(--border,#e5e5ea);border-radius:6px;font-size:12px">
        <option value="">全部项目</option>
      </select>
      <label style="font-size:12px;display:flex;align-items:center;gap:4px;cursor:pointer"><input type="checkbox" id="taskOverdue" onchange="_taskBoard.overdueOnly=this.checked;loadTaskBoard()"> 只看逾期</label>
      <span id="taskStats" style="font-size:12px;color:var(--text-sec);margin-left:auto"></span>
    </div>
    <div style="flex:1;overflow-y:auto;padding:14px 18px;display:grid;grid-template-columns:repeat(3,1fr);gap:12px" id="taskBoardCols"></div>
  </div>`;
  overlay.onclick = function(e){ if(e.target===overlay) overlay.remove(); };
  document.body.appendChild(overlay);
  taskLoadFilters();
  loadTaskBoard();
}

// 加载负责人/项目下拉选项
async function taskLoadFilters(){
  try{
    const d = await api('GET','/api/todos/global?done=1');
    const todos = (d && d.todos) || [];
    const assignees = {}; const projects = {};
    todos.forEach(t=>{ if(t.assignee) assignees[t.assignee]=1; if(t.project_name) projects[t.project_name]=1; });
    const as = document.getElementById('taskAssignee');
    const pr = document.getElementById('taskProject');
    if(as) as.innerHTML = '<option value="">全部负责人</option>' + Object.keys(assignees).map(a=>'<option value="'+escHtml(a)+'">'+escHtml(a)+'</option>').join('');
    if(pr) pr.innerHTML = '<option value="">全部项目</option>' + Object.keys(projects).sort().map(p=>'<option value="'+jsq(p)+'">'+escHtml(p)+'</option>').join('');
  }catch(e){}
}

// 视图切换：看板 <-> 列表
function taskToggleView(){
  const cols = document.getElementById('taskBoardCols');
  const btn = document.getElementById('taskViewToggle');
  if(!cols) return;
  const isBoard = cols.dataset.view !== 'list';
  cols.dataset.view = isBoard ? 'list' : 'board';
  btn.textContent = isBoard ? '🗂 看板视图' : '👁 列表视图';
  // 列表视图用单列布局
  if(isBoard){ cols.style.gridTemplateColumns = '1fr'; } else { cols.style.gridTemplateColumns = 'repeat(3,1fr)'; }
  loadTaskBoard();
}

async function loadTaskBoard(){
  const cols = document.getElementById('taskBoardCols');
  if(!cols) return;
  try{
    const q = _taskBoard.q || '';
    const assignee = _taskBoard.assignee || '';
    const overdue = _taskBoard.overdueOnly ? 1 : 0;
    let url = '/api/todos/board?group=' + _taskBoard.group + '&done=1&overdue=' + overdue;
    if(q) url += '&q=' + encodeURIComponent(q);
    if(assignee) url += '&assignee=' + encodeURIComponent(assignee);
    const d = await api('GET', url);
    const c = d.columns || {};
    _taskBoard.columns = c;
    const isList = cols.dataset.view === 'list';

    // 统计条
    const all = Object.values(c).flat() || [];
    const todoCnt = (c.todo||[]).length;
    const today = new Date().toISOString().slice(0,10);
    const overdueList = all.filter(t=>!t.done && t.due_date && String(t.due_date).slice(0,10) < today);
    const highCnt = all.filter(t=>parseInt(t.priority||0)===2).length;
    const stats = document.getElementById('taskStats');
    if(stats) stats.innerHTML = '<b>'+all.length+'</b> 条 · <span style="color:#c5221f">逾期 '+overdueList.length+'</span> · 高优 '+highCnt;

    if(_taskBoard.group === 'priority'){
      var labels = { high:{t:'🔴 高优先级',c:'#c5221f'}, medium:{t:'🟠 中优先级',c:'#ff9f0a'}, low:{t:'🟢 低优先级',c:'#34c759'} };
    } else {
      var labels = { todo:{t:'📋 待办',c:'#86868b'}, in_progress:{t:'🔵 进行中',c:'#0071e3'}, done:{t:'✅ 已完成',c:'#34c759'} };
    }

    if(isList){
      // 列表视图：单列展示全部
      const items = Object.keys(c).map(k=>c[k]).flat() || [];
      cols.innerHTML = '<div style="background:#fff;border-radius:10px;padding:12px 16px;min-height:200px">'
        + (items.length ? items.map(t=>taskListRow(t)).join('') : '<div style="color:var(--text-sec);text-align:center;padding:30px">暂无待办</div>')
        + '</div>';
      return;
    }

    let html = '';
    Object.keys(labels).forEach(function(key){
      const items = c[key] || [];
      html += `<div style="background:#fff;border-radius:10px;padding:10px;display:flex;flex-direction:column;max-height:100%">
        <div style="font-size:13px;font-weight:700;margin-bottom:8px;display:flex;align-items:center;gap:6px">
          <span>${labels[key].t}</span>
          <span style="font-size:11px;color:var(--text-sec)">(${items.length})</span>
        </div>
        <div style="flex:1;overflow-y:auto;min-height:150px" data-col="${key}" ondragover="event.preventDefault()" ondrop="boardDrop(event,'${key}')">
          ${items.map(t => boardCard(t,key)).join('') || '<div style="color:var(--text-sec);font-size:11px;text-align:center;padding:24px">暂无</div>'}
        </div>
      </div>`;
    });
    cols.innerHTML = html;
  }catch(e){
    cols.innerHTML = '<div style="color:var(--red);padding:20px">加载失败: '+escHtml(e.message)+'</div>';
  }
}

function _taskPriorityBadge(p){
  p = parseInt(p||0);
  if(p === 2) return '<span style="background:#ffecec;color:#c5221f;font-size:10px;padding:1px 6px;border-radius:8px;font-weight:600">高</span>';
  if(p === 1) return '<span style="background:#fff4e6;color:#ff9f0a;font-size:10px;padding:1px 6px;border-radius:8px;font-weight:600">中</span>';
  return '';
}
function _taskDueMark(t){
  if(!t.due_date) return '';
  const today = new Date().toISOString().slice(0,10);
  const dd = String(t.due_date).slice(0,10);
  const overdue = !t.done && dd < today;
  const color = overdue ? '#c5221f' : (t.done ? '#999' : '#86868b');
  const icon = overdue ? '⚠️' : '📅';
  const label = (t.done && dd < today) ? '(已逾期)' : '';
  return '<span style="font-size:10px;color:'+color+';font-weight:'+(overdue?'600':'400')+'">'+icon+' '+dd+(label?' '+label:'')+'</span>';
}
function _taskStatusChip(t){
  const m = {todo:'待办', in_progress:'进行中', done:'已完成'};
  return '<span style="font-size:10px;color:var(--text-sec)">'+escHtml(m[t.status]||t.status||'待办')+'</span>';
}

function boardCard(t, col){
  const remind = t.remind_at ? '<span style="font-size:10px;color:#ff9f0a;margin-left:6px">⏰ '+escHtml(t.remind_at)+'</span>' : '';
  const proj = t.project_name ? '<div style="font-size:11px;color:#0071e3;margin-top:4px">📁 '+escHtml(t.project_name)+'</div>' : '<div style="font-size:11px;color:var(--text-sec);margin-top:4px">📌 独立待办</div>';
  const assignee = t.assignee ? '<span style="font-size:10px;color:#5c6bc0">👤 '+escHtml(t.assignee)+'</span>' : '';
  const dueMark = _taskDueMark(t);
  const pri = _taskPriorityBadge(t.priority);
  const doneMark = (t.status==='done'||t.done) ? '<span style="color:#34c759">☑️</span>' : '<span style="color:#bbb">◻️</span>';
  return `<div draggable="true" ondragstart="boardDrag(event,'${t.id}')" onclick="taskEditTodo(${t.id},event)" style="background:#f5f7fa;border:1px solid var(--border,#e5e5ea);border-radius:8px;padding:8px 10px;margin-bottom:6px;cursor:grab;font-size:12px;transition:box-shadow .15s" onmouseenter="this.style.boxShadow='0 3px 10px rgba(0,0,0,.12)'" onmouseleave="this.style.boxShadow=''">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:4px">
      <span style="font-weight:600;${t.done?'text-decoration:line-through;color:var(--text-sec)':''}">${doneMark} ${escHtml(t.text)}</span>
      <span style="display:flex;gap:4px;align-items:center;flex-shrink:0">${pri}</span>
    </div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-top:4px;gap:4px">
      <span style="display:flex;gap:4px;align-items:center;flex-wrap:wrap">${dueMark}${assignee}</span>
      <span style="font-size:11px;opacity:.7">✏️</span>
    </div>
    ${proj}${remind}
  </div>`;
}

// 列表视图行
function taskListRow(t){
  const today = new Date().toISOString().slice(0,10);
  const dd = t.due_date ? String(t.due_date).slice(0,10) : '';
  const overdue = !t.done && dd && dd < today;
  const pri = _taskPriorityBadge(t.priority);
  const stChip = _taskStatusChip(t);
  return `<div style="display:flex;align-items:center;gap:10px;padding:8px 4px;border-bottom:1px solid #f5f5f5;font-size:13px">
    <button onclick="taskToggleDone(${t.id},${t.done?0:1})" style="background:none;border:none;font-size:16px;cursor:pointer;padding:0" title="切换完成">${t.done?'☑️':'⬜'}</button>
    <span style="flex:1;${t.done?'text-decoration:line-through;color:var(--text-sec)':''}">${escHtml(t.text)}</span>
    ${pri}
    ${stChip}
    <span style="font-size:11px;color:${overdue?'#c5221f':'var(--text-sec)'};font-weight:${overdue?'600':'400'}">${dd||'—'}</span>
    <span style="font-size:11px;color:#0071e3">${t.project_name?escHtml(t.project_name):'独立'}</span>
    <button onclick="taskEditTodo(${t.id},event)" style="background:none;border:none;font-size:12px;cursor:pointer;color:var(--text-sec)">✏️</button>
    <button onclick="taskDelTodo(${t.id})" style="background:none;border:none;color:var(--red);cursor:pointer;font-size:13px">🗑</button>
  </div>`;
}

function boardDrag(ev, id){
  ev.dataTransfer.setData('text/plain', id);
}
function boardDrop(ev, status){
  ev.preventDefault();
  const id = ev.dataTransfer.getData('text/plain');
  if(!id) return;
  api('PUT','/api/todos/'+id+'/status', {status:status}).then(function(d){
    if(d && d.ok){ loadTaskBoard(); toast('已移动到'+(status==='done'?'已完成':status==='in_progress'?'进行中':'待办'),'success'); }
    else toast('更新失败','error');
  }).catch(function(e){ toast('更新失败: '+e.message,'error'); });
}

// 新建待办
function taskNewTodo(){
  const today = new Date().toISOString().slice(0,10);
  const html = `
    <div style="background:var(--card,#fff);border-radius:14px;width:520px;max-width:94vw;box-shadow:0 20px 60px rgba(0,0,0,.35)">
      <div style="padding:14px 20px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--border,#e5e5ea)">
        <h3 style="margin:0;font-size:15px">➕ 新建待办</h3>
        <button onclick="taskCloseEdit()" style="border:none;background:none;font-size:18px;cursor:pointer">✕</button>
      </div>
      <div style="padding:16px 20px;display:flex;flex-direction:column;gap:12px">
        <div><label style="font-size:12px;color:var(--text-sec)">内容 *</label>
          <textarea id="te-text" rows="2" style="width:100%;padding:8px;border:1px solid var(--border,#e5e5ea);border-radius:6px;font-size:13px;outline:none" placeholder="待办内容"></textarea></div>
        <div style="display:flex;gap:12px">
          <div style="flex:1"><label style="font-size:12px;color:var(--text-sec)">截止日期</label>
            <input type="date" id="te-due" value="${today}" style="width:100%;padding:7px;border:1px solid var(--border,#e5e5ea);border-radius:6px;font-size:13px"></div>
          <div style="flex:1"><label style="font-size:12px;color:var(--text-sec)">优先级</label>
            <select id="te-priority" style="width:100%;padding:7px;border:1px solid var(--border,#e5e5ea);border-radius:6px;font-size:13px">
              <option value="0">低</option><option value="1">中</option><option value="2" selected>高</option>
            </select></div>
        </div>
        <div style="display:flex;gap:12px">
          <div style="flex:1"><label style="font-size:12px;color:var(--text-sec)">负责人</label>
            <input id="te-assignee" type="text" placeholder="如：张大强" style="width:100%;padding:7px;border:1px solid var(--border,#e5e5ea);border-radius:6px;font-size:13px"></div>
          <div style="flex:1"><label style="font-size:12px;color:var(--text-sec)">所属项目（可选）</label>
            <input id="te-project" type="text" placeholder="留空=独立待办" style="width:100%;padding:7px;border:1px solid var(--border,#e5e5ea);border-radius:6px;font-size:13px"></div>
        </div>
        <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:6px">
          <button class="btn btn-sm" onclick="taskCloseEdit()">取消</button>
          <button class="btn btn-sm btn-primary" onclick="taskSaveNew()">✅ 创建</button>
        </div>
      </div>
    </div>`;
  taskOpenEditOverlay(html);
}
function taskOpenEditOverlay(innerHtml){
  const ov = document.createElement('div');
  ov.id = 'taskEditOverlay';
  ov.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:23500;display:flex;align-items:center;justify-content:center';
  ov.innerHTML = innerHtml;
  ov.onclick = function(e){ if(e.target===ov) ov.remove(); };
  document.body.appendChild(ov);
}
function taskCloseEdit(){
  const ov = document.getElementById('taskEditOverlay');
  if(ov) ov.remove();
}
async function taskSaveNew(){
  const text = (document.getElementById('te-text')?.value||'').trim();
  if(!text){ toast('请输入待办内容','warning'); return; }
  const due = document.getElementById('te-due')?.value || '';
  const pri = parseInt(document.getElementById('te-priority')?.value||0);
  const assignee = (document.getElementById('te-assignee')?.value||'').trim();
  const project = (document.getElementById('te-project')?.value||'').trim();
  try{
    const d = await api('POST','/api/todos', { text:text, due_date:due, priority:pri, assignee:assignee, project_name:project });
    if(d && d.ok){ taskCloseEdit(); toast('已创建待办','success'); loadTaskBoard(); taskLoadFilters(); }
    else toast((d&&d.message)||'创建失败','error');
  }catch(e){ toast('创建失败: '+e.message,'error'); }
}

// 编辑待办
async function taskEditTodo(id, ev){
  if(ev) ev.stopPropagation();
  // 从当前列数据里找该待办
  let t = null;
  Object.keys(_taskBoard.columns||{}).forEach(k=>{
    const f = (_taskBoard.columns[k]||[]).find(x=>x.id===id);
    if(f) t = f;
  });
  if(!t){
    // 回退：全局查询
    try{
      const d = await api('GET','/api/todos/global?done=1');
      t = ((d&&d.todos)||[]).find(x=>x.id===id);
    }catch(e){}
  }
  if(!t){ toast('待办不存在','error'); return; }
  const html = `
    <div style="background:var(--card,#fff);border-radius:14px;width:520px;max-width:94vw;box-shadow:0 20px 60px rgba(0,0,0,.35)">
      <div style="padding:14px 20px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--border,#e5e5ea)">
        <h3 style="margin:0;font-size:15px">✏️ 编辑待办</h3>
        <button onclick="taskCloseEdit()" style="border:none;background:none;font-size:18px;cursor:pointer">✕</button>
      </div>
      <div style="padding:16px 20px;display:flex;flex-direction:column;gap:12px">
        <div><label style="font-size:12px;color:var(--text-sec)">内容 *</label>
          <textarea id="te-text" rows="2" style="width:100%;padding:8px;border:1px solid var(--border,#e5e5ea);border-radius:6px;font-size:13px;outline:none">${escHtml(t.text||'')}</textarea></div>
        <div style="display:flex;gap:12px">
          <div style="flex:1"><label style="font-size:12px;color:var(--text-sec)">截止日期</label>
            <input type="date" id="te-due" value="${escHtml((t.due_date||'').slice(0,10))}" style="width:100%;padding:7px;border:1px solid var(--border,#e5e5ea);border-radius:6px;font-size:13px"></div>
          <div style="flex:1"><label style="font-size:12px;color:var(--text-sec)">优先级</label>
            <select id="te-priority" style="width:100%;padding:7px;border:1px solid var(--border,#e5e5ea);border-radius:6px;font-size:13px">
              ${[['0','低'],['1','中'],['2','高']].map(([v,l])=>'<option value="'+v+'"'+(parseInt(t.priority||0)===parseInt(v)?' selected':'')+'>'+l+'</option>').join('')}
            </select></div>
        </div>
        <div style="display:flex;gap:12px">
          <div style="flex:1"><label style="font-size:12px;color:var(--text-sec)">负责人</label>
            <input id="te-assignee" type="text" value="${escHtml(t.assignee||'')}" style="width:100%;padding:7px;border:1px solid var(--border,#e5e5ea);border-radius:6px;font-size:13px"></div>
          <div style="flex:1"><label style="font-size:12px;color:var(--text-sec)">状态</label>
            <select id="te-status" style="width:100%;padding:7px;border:1px solid var(--border,#e5e5ea);border-radius:6px;font-size:13px">
              ${[['todo','待办'],['in_progress','进行中'],['done','已完成']].map(([v,l])=>'<option value="'+v+'"'+((t.status||'todo')===v?' selected':'')+'>'+l+'</option>').join('')}
            </select></div>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;margin-top:6px">
          <button class="btn btn-sm" style="color:var(--red)" onclick="taskDelTodo(${id})">🗑 删除</button>
          <div style="display:flex;gap:8px">
            <button class="btn btn-sm" onclick="taskCloseEdit()">取消</button>
            <button class="btn btn-sm btn-primary" onclick="taskSaveEdit(${id})">💾 保存</button>
          </div>
        </div>
      </div>
    </div>`;
  taskOpenEditOverlay(html);
}
async function taskSaveEdit(id){
  const text = (document.getElementById('te-text')?.value||'').trim();
  if(!text){ toast('请输入待办内容','warning'); return; }
  const due = document.getElementById('te-due')?.value || '';
  const pri = parseInt(document.getElementById('te-priority')?.value||0);
  const assignee = (document.getElementById('te-assignee')?.value||'').trim();
  const status = document.getElementById('te-status')?.value || 'todo';
  const payload = { text:text, due_date:due, priority:pri, assignee:assignee, status:status };
  if(status==='done') payload.done = 1;
  if(status!=='done') payload.done = 0;
  try{
    const d = await api('PUT','/api/todos/'+id, payload);
    if(d && d.ok){ taskCloseEdit(); toast('已保存','success'); loadTaskBoard(); taskLoadFilters(); }
    else toast((d&&d.message)||'保存失败','error');
  }catch(e){ toast('保存失败: '+e.message,'error'); }
}
async function taskDelTodo(id){
  if(!confirm('确定删除该待办？')) return;
  try{
    const d = await api('DELETE','/api/todos/'+id);
    if(d && d.ok){ taskCloseEdit(); toast('已删除','success'); loadTaskBoard(); taskLoadFilters(); }
    else toast('删除失败','error');
  }catch(e){ toast('删除失败: '+e.message,'error'); }
}
async function taskToggleDone(id, done){
  try{
    // 从当前列数据找该待办的原始状态
    let cur = 'todo';
    Object.keys(_taskBoard.columns||{}).forEach(k=>{
      const f = (_taskBoard.columns[k]||[]).find(x=>x.id===id);
      if(f && f.status) cur = f.status;
    });
    if(done) cur = 'done';
    await api('PUT','/api/todos/'+id, {done:!!done, status: cur});
    loadTaskBoard();
  }catch(e){ toast('更新失败: '+e.message,'error'); }
}
