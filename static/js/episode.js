// 剧集详情: openProjectDetail, buildEpSummary, 粘贴分集 modal
function setProjectMonth(name){
  // 生成月份选项：2025-01 ~ 2026-12（或当前年+前后各1年）
  var now = new Date();
  var cur = now.getFullYear() + '-' + String(now.getMonth()+1).padStart(2,'0');
  var years = [now.getFullYear()-1, now.getFullYear(), now.getFullYear()+1];
  var months = [];
  years.forEach(function(y){
    for(var m=1; m<=12; m++){
      months.push(y + '-' + String(m).padStart(2,'0'));
    }
  });
  // 找当前值
  var curVal = '';
  (allSections||[]).forEach(function(sec){ (sec.projects||[]).forEach(function(p){ if(p.name===name && p.project_month) curVal=p.project_month; }); });
  if(!curVal) (projects||[]).forEach(function(p){ if(p.name===name && p.project_month) curVal=p.project_month; });

  // 构建 modal
  var overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:99999;display:flex;align-items:center;justify-content:center;';
  overlay.innerHTML = '';  // 占位
  var box = document.createElement('div');
  box.style.cssText = 'background:#fff;border-radius:14px;padding:24px;width:340px;box-shadow:0 12px 40px rgba(0,0,0,.2);font-family:-apple-system,"Segoe UI",sans-serif;';
  box.innerHTML = '<div style="font-size:16px;font-weight:600;margin-bottom:16px">📅 设置项目月份</div>'
    + '<div style="font-size:13px;color:#666;margin-bottom:14px;word-break:break-all">' + name + '</div>'
    + '<select id="_monthSel" style="width:100%;padding:10px 12px;border:1px solid #d1d5db;border-radius:8px;font-size:14px;outline:none">'
    + '<option value="">— 清空（不统计）—</option>'
    + months.map(function(m){
        var sel = m === curVal ? ' selected' : '';
        return '<option value="' + m + '"' + sel + '>' + m + (m === cur ? ' · 本月' : '') + '</option>';
      }).join('')
    + '</select>'
    + '<div style="display:flex;justify-content:flex-end;gap:10px;margin-top:20px">'
    + '<button id="_mCancel" style="padding:8px 16px;border:1px solid #d1d5db;border-radius:8px;background:#fff;cursor:pointer;font-size:14px">取消</button>'
    + '<button id="_mOk" style="padding:8px 20px;border:none;border-radius:8px;background:#0071e3;color:#fff;cursor:pointer;font-size:14px">确定</button>'
    + '</div>';
  overlay.appendChild(box);
  document.body.appendChild(overlay);

  function close(){ document.body.removeChild(overlay); }
  overlay.addEventListener('click', function(e){ if(e.target===overlay) close(); });
  box.querySelector('#_mCancel').addEventListener('click', close);
  box.querySelector('#_mOk').addEventListener('click', function(){
    var val = box.querySelector('#_monthSel').value;
    close();
    api('POST', '/api/project/' + encodeURIComponent(name) + '/update_month', { month: val }).then(function(d){
      if(d.ok){
        toast(val ? ('✅ 月份已更新: ' + val) : '✅ 已清除月份', 'success');
        try{
          var saved = JSON.parse(localStorage.getItem('wb_project_months')||'{}');
          if(val) saved[name] = val; else delete saved[name];
          localStorage.setItem('wb_project_months', JSON.stringify(saved));
        }catch(e){}
        (allSections||[]).forEach(function(sec){ (sec.projects||[]).forEach(function(p){ if(p.name===name) p.project_month=val; }); });
        (projects||[]).forEach(function(p){ if(p.name===name) p.project_month=val; });
        Object.values(allProjects||{}).forEach(function(list){ (list||[]).forEach(function(p){ if(p.name===name) p.project_month=val; }); });
        renderDashboard();
      }else{ toast(d.message || '更新失败', 'error'); }
    }).catch(function(e){ toast('更新失败: '+e.message, 'error'); });
  });
}

async function openProjectDetail(name){
  const modal=$('detailModal');
  const content=$('detailContent');
  content.innerHTML='<div style="padding:40px;text-align:center;color:var(--text-sec)">加载中...</div>';
  modal.classList.add('active');
  try{
    const d=await api('GET',`/api/project/${encodeURIComponent(name)}`);
    const p=d.project||d;
    if(!p.name)throw new Error(d.message||'未找到项目');
    const fieldsToShow=[
      {key:'production_path',label:'制作路径',full:true},
      {key:'group_path',label:'组内路径',full:true},
      {key:'source_root',label:'来源路径',full:true},
      {key:'department',label:'所属部门'},
      {key:'project_month',label:'📅 项目月份'},
      {key:'source',label:'来源'},
      {key:'source_type',label:'来源类型'},
      {key:'sync_status',label:'同步状态'},
      {key:'custom_status',label:'当前状态'},
      {key:'delivery_status',label:'交付状态'},
      {key:'delivered_date',label:'📅 交付日期'},
      {key:'total_episodes',label:'总集数'},
      {key:'current_episodes',label:'已生成集数'},
      {key:'completed_episodes',label:'已完成集数'},
      {key:'material_sync',label:'素材同步'},
      {key:'delivered',label:'是否交付'},
      {key:'created_at',label:'创建时间'},
      {key:'updated_at',label:'更新时间'},
    ];
    let kvHtml=fieldsToShow.map(f=>{
      let val=p[f.key];
      if(val===undefined||val===null||val==='')return'';
      if(typeof val==='object')val=JSON.stringify(val);
      return `<div class="kv ${f.full?'full':''}"><span>${f.label}</span><b>${val}</b></div>`;
    }).join('');
    let extraKeys=Object.keys(p).filter(k=>!fieldsToShow.find(f=>f.key===k)&&k!=='name'&&p[k]!==null&&p[k]!==undefined&&p[k]!=='').filter(k=>typeof p[k]!=='object').slice(0,20);
    let extraHtml=extraKeys.map(k=>`<div class="kv"><span>${k}</span><b>${p[k]}</b></div>`).join('');
    if(kvHtml)kvHtml+='<div class="kv full" style="margin-top:12px;border-top:1px solid var(--border);padding-top:12px">其他字段</div>'+extraHtml;
    let epHtml='';
    if(p.episodes&&p.episodes.length){
      epHtml=p.episodes.slice(0,100).map(e=>{
        const epNum=e.episode_number||e.episode||'';
        return `<tr><td>${epNum}</td><td>${e.editor||e.name||'—'}</td><td>${e.status||'—'}</td></tr>`;
      }).join('');
      if(p.episodes.length>100)epHtml+=`<tr><td colspan="3" style="text-align:center;color:var(--text-sec)">...还有 ${p.episodes.length-100} 集</td></tr>`;
      epHtml=`<table class="issue-table" style="margin-top:8px"><thead><tr><th>集数</th><th>剪辑师</th><th>状态</th></tr></thead><tbody>${epHtml}</tbody></table>`;
    }
    content.innerHTML=`
      <div class="detail-header">
        <h2>📁 ${p.name}</h2>
        <button onclick="$('detailModal').classList.remove('active')">✕</button>
      </div>
      <div class="detail-section">
        <h3>📌 基本信息</h3>
        <div class="kv-grid">${kvHtml||'<div style="color:var(--text-sec)">暂无额外字段</div>'}</div>
      </div>
      <div class="detail-section">
        <h3>📑 分集列表${p.episodes?`（${p.episodes.length} 集）`:''}</h3>${epHtml}
      </div>
      <div class="detail-section">
        <h3>✅ 待办事项 <span id="todoCount" style="font-size:12px;color:var(--text-sec)"></span></h3>
        <div id="todoBox">
          <div style="color:var(--text-sec);font-size:13px;padding:8px 0">加载中...</div>
        </div>
        <div style="display:flex;gap:6px;margin-top:8px">
          <input id="todoInput" placeholder="添加待办，如：补字幕 / 调色 / 等审片..." style="flex:1;padding:8px 10px;border:1px solid var(--border);border-radius:8px;outline:none" onkeydown="if(event.key==='Enter')addTodo('${p.name.replace(/'/g,"\\'")}')">
          <button class="btn btn-sm btn-primary" onclick="addTodo('${p.name.replace(/'/g,"\\'")}')">＋ 添加</button>
        </div>
      </div>
      <div class="detail-section">
        <h3>🕐 项目时间轴 <span id="tlSummary" style="font-size:12px;color:var(--text-sec)"></span></h3>
        <div id="timelineBox"><div style="color:var(--text-sec);font-size:13px;padding:8px 0">加载中...</div></div>
      </div>
      <div class="detail-actions">
        <button onclick="setProjectMonth('${p.name.replace(/'/g,"\\'")}')" class="secondary">📅 设置月份</button>
        <button onclick="setProjectDeliveredDate('${p.name.replace(/'/g,"\\'")}')" class="secondary">🗓 交付日期</button>
        ${p.group_path?`<button onclick="openFolder('group','${p.name.replace(/'/g,"\\'")}')" class="secondary">📁 打开组内文件夹</button>`:''}
        ${p.production_path?`<button onclick="openFolder('production','${p.name.replace(/'/g,"\\'")}')" class="secondary">📁 打开制作文件夹</button>`:''}
        <button onclick="$('detailModal').classList.remove('active');openFenjiFor('${p.name.replace(/'/g,"\\'")}')" class="secondary">📑 管理分集</button>
        <button onclick="$('detailModal').classList.remove('active');qaStartFor('${p.name.replace(/'/g,"\\'")}')" class="secondary">🔍 开始质检</button>
      </div>
    `;
    // 加载待办 + 时间轴
    loadTodos(name);
    loadTimeline(name);
  }catch(e){
    content.innerHTML=`<div style="padding:40px;color:var(--red);text-align:center">加载失败: ${e.message}</div>
      <div style="padding:0 20px 20px;text-align:right"><button class="btn" onclick="$('detailModal').classList.remove('active')">关闭</button></div>`;
  }
}
// ===== 待办事项（融合自「项目档案管理器」）=====
async function loadTodos(name){
  const box=document.getElementById('todoBox');
  if(!box)return;
  try{
    const d=await api('GET',`/api/project/${encodeURIComponent(name)}/todos`);
    const todos=(d&&d.todos)||[];
    renderTodos(name,todos);
  }catch(e){
    box.innerHTML=`<div style="color:var(--red);font-size:13px">加载待办失败</div>`;
  }
}
function renderTodos(name,todos){
  const box=document.getElementById('todoBox');
  if(!box)return;
  const cnt=document.getElementById('todoCount');
  if(cnt){
    const done=todos.filter(t=>t.done).length;
    cnt.textContent=todos.length?`（${done} 已完成 / ${todos.length} 共）`:'';
  }
  if(!todos.length){
    box.innerHTML=`<div style="color:var(--text-sec);font-size:13px;padding:4px 0">暂无待办</div>`;
    return;
  }
  box.innerHTML=todos.map(t=>`
    <div style="display:flex;align-items:center;gap:8px;padding:6px 2px;border-bottom:1px dashed var(--border)">
      <button onclick="toggleTodo('${name.replace(/'/g,"\\'")}',${t.id},${t.done?0:1})" style="background:none;border:none;font-size:18px;cursor:pointer;width:26px;text-align:center;padding:0" title="${t.done?'标记未完成':'标记完成'}">${t.done?'☑️':'⬜'}</button>
      <span style="flex:1;font-size:14px;${t.done?'text-decoration:line-through;color:var(--text-sec)':''}">${escHtml(t.text)}</span>
      <button onclick="delTodo('${name.replace(/'/g,"\\'")}',${t.id})" style="background:none;border:none;color:var(--red,#ff3b30);cursor:pointer;font-size:14px" title="删除">🗑</button>
    </div>`).join('');
}
async function addTodo(name){
  const input=document.getElementById('todoInput');
  const text=input?input.value.trim():'';
  if(!text){toast('请输入待办内容','warning');return;}
  try{
    const d=await api('POST',`/api/project/${encodeURIComponent(name)}/todos`,{text:text});
    if(d&&d.ok){ if(input)input.value=''; loadTodos(name); toast('已添加待办','success'); }
    else toast((d&&d.message)||'添加失败','error');
  }catch(e){toast('添加失败: '+e.message,'error');}
}
async function toggleTodo(name,id,done){
  try{
    await api('PUT',`/api/project/${encodeURIComponent(name)}/todos/${id}`,{done:!!done});
    loadTodos(name);
  }catch(e){toast('更新失败: '+e.message,'error');}
}
async function delTodo(name,id){
  try{
    await api('DELETE',`/api/project/${encodeURIComponent(name)}/todos/${id}`);
    loadTodos(name);
  }catch(e){toast('删除失败: '+e.message,'error');}
}
// ===== 项目时间轴（融合自「项目档案管理器」）=====
async function loadTimeline(name){
  const box=document.getElementById('timelineBox');
  if(!box)return;
  try{
    const d=await api('GET',`/api/project/${encodeURIComponent(name)}/timeline`);
    const events=(d&&d.events)||[];
    const sum=(d&&d.summary)||{};
    const s=document.getElementById('tlSummary');
    if(s)s.textContent=events.length?`（共 ${events.length} 个事件）`:'';
    if(!events.length){
      box.innerHTML=`<div style="color:var(--text-sec);font-size:13px;padding:4px 0">暂无事件</div>`;
      return;
    }
    box.innerHTML=`<div style="max-height:300px;overflow-y:auto;padding:4px 0">`+
      events.map(ev=>`
        <div style="display:flex;gap:10px;padding:5px 0;position:relative;padding-left:18px">
          <span style="position:absolute;left:0;top:9px;width:9px;height:9px;border-radius:50%;background:${ev.color||'#0071e3'}"></span>
          <div style="flex:1;min-width:0">
            <div style="font-size:13px;font-weight:500">${ev.title||''}</div>
            <div style="font-size:12px;color:var(--text-sec);word-break:break-all">${escHtml(ev.detail||'')}</div>
            <div style="font-size:11px;color:var(--text-sec);opacity:.7">${ev.time||''}</div>
          </div>
        </div>`).join('')+`</div>`;
  }catch(e){
    box.innerHTML=`<div style="color:var(--red);font-size:13px">加载时间轴失败</div>`;
  }
}
function openSmart(name, which){
  api('POST', '/api/project/' + encodeURIComponent(name) + '/open_folder', { which: which }).then(function(data){
    if(data.ok) toast('已打开: ' + (data.message || '成功'), 'success');
    else toast(data.message || '打开失败', 'error');
  }).catch(function(e){ toast('打开失败: ' + e.message, 'error'); });
}

// 设置/清除项目交付日期（交付日历用）
function setProjectDeliveredDate(name){
  const overlay = document.createElement('div');
  overlay.id = 'ddEditModal';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:99999;display:flex;align-items:center;justify-content:center';
  overlay.innerHTML = `
    <div style="background:#fff;border-radius:14px;padding:22px;width:340px;box-shadow:0 12px 40px rgba(0,0,0,.2);font-family:-apple-system,'Segoe UI',sans-serif">
      <div style="font-size:16px;font-weight:600;margin-bottom:12px">🗓 设置交付日期</div>
      <div style="font-size:13px;color:#666;margin-bottom:14px;word-break:break-all">${htm(name)}</div>
      <input id="_ddDate" type="date" style="width:100%;padding:9px 10px;border:1px solid #d1d5db;border-radius:8px;font-size:14px;outline:none">
      <div style="display:flex;justify-content:flex-end;gap:10px;margin-top:18px">
        <button id="_ddClear" style="padding:8px 14px;border:1px solid #d1d5db;border-radius:8px;background:#fff;cursor:pointer;font-size:13px">🗑 清除</button>
        <button id="_ddCancel" style="padding:8px 16px;border:1px solid #d1d5db;border-radius:8px;background:#fff;cursor:pointer;font-size:14px">取消</button>
        <button id="_ddOk" style="padding:8px 20px;border:none;border-radius:8px;background:#0071e3;color:#fff;cursor:pointer;font-size:14px">保存</button>
      </div>
    </div>`;
  overlay.addEventListener('mousedown', e=>{ if(e.target===overlay) overlay.remove(); });
  document.body.appendChild(overlay);
  const dateInput = document.getElementById('_ddDate');
  function save(){
    const val = dateInput.value || '';
    overlay.remove();
    api('POST', '/api/project/' + encodeURIComponent(name) + '/delivered_date', { date: val }).then(function(d){
      if(d && d.ok) toast(val ? ('✅ 已设置交付日期: ' + val) : '✅ 已清除交付日期', 'success');
      else toast((d&&d.message)||'保存失败','error');
    }).catch(function(e){ toast('保存失败: ' + e.message, 'error'); });
  }
  document.getElementById('_ddOk').addEventListener('click', save);
  document.getElementById('_ddCancel').addEventListener('click', function(){ overlay.remove(); });
  document.getElementById('_ddClear').addEventListener('click', function(){ overlay.remove(); api('POST','/api/project/' + encodeURIComponent(name) + '/delivered_date',{date:''}).then(function(){toast('✅ 已清除交付日期','success');}); });
  dateInput.focus();
}

async function openFolder(type,name){
  try{
    // 直接调统一的 open_folder，让后端决定开哪个
    const which = type==='group' ? 'group' : 'production';
    api('POST', `/api/project/${encodeURIComponent(name)}/open_folder`, { which: which }).then(function(data){
      if(data.ok) toast('已打开文件夹', 'success');
      else toast(data.message || '打开失败', 'error');
    }).catch(function(e){ toast('打开失败: ' + e.message, 'error'); });
  }catch(e){ toast('打开失败', 'error'); }
}
function openFolderByPath(name, path){
  // 调用后端 /api/project/{name}/open_folder，传 path 直接打开
  try{
    toast('正在打开: ' + (path || name), 'info');
    api('POST', `/api/project/${encodeURIComponent(name)}/open_folder`, { which: 'path', path: path }).then(function(data){
      if(data.ok) toast('已打开文件夹', 'success');
      else toast(data.message || '打开失败', 'error');
    }).catch(function(e){ toast('打开失败: ' + e.message, 'error'); });
  }catch(e){ toast('打开失败', 'error'); }
}

/* ============ Episode Alert Banner ============ */
var _episodeStatusCache = {};
var _episodeStatusPending = {};

function htm(s){ if(s===undefined||s===null)return ""; return String(s).replace(/[&<>"\'`]/g,function(c){ return { "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","\'":"&#39;","`":"&#96;"}[c]; }); }

function _compactRange(nums) {
    if (!nums.length) return '';
    nums = nums.slice().sort(function(a, b) { return a - b; });
    var parts = [];
    var start = nums[0], prev = nums[0];
    for (var k = 1; k < nums.length; k++) {
      if (nums[k] === prev + 1) {
        prev = nums[k];
      } else {
        parts.push(start === prev ? String(start).padStart(2, '0') : String(start).padStart(2, '0') + '-' + String(prev).padStart(2, '0'));
        start = prev = nums[k];
      }
    }
    parts.push(start === prev ? String(start).padStart(2, '0') : String(start).padStart(2, '0') + '-' + String(prev).padStart(2, '0'));
    return parts.join(', ');
  }

function buildEpSummaryHtml(data, projectName, dbFallback, customStatus) {
    if (!data || !data.ok) {
      if (dbFallback) {
        var total = dbFallback.total_episodes || 0;
        if (total > 0) {
          var cur = dbFallback.current_episodes || 0;
          var plan = {};
          if (dbFallback.episode_plan) {
            try { plan = typeof dbFallback.episode_plan === 'string' ? JSON.parse(dbFallback.episode_plan) : dbFallback.episode_plan; } catch(e) {}
          }
          var personRows = [];
          if (plan && Object.keys(plan).length > 0) {
            var grouped = {};
            for (var k in plan) {
              if (!plan.hasOwnProperty(k)) continue;
              var creator = plan[k];
              if (!creator) continue;
              if (!grouped[creator]) grouped[creator] = [];
              grouped[creator].push(parseInt(k, 10) || k);
            }
            for (var name in grouped) {
              if (!grouped.hasOwnProperty(name)) continue;
              personRows.push('<div class="ep-person-row"><span class="ep-person-name">' + htm(name) + '</span><span class="ep-person-range">负责 ' + _compactRange(grouped[name]) + '</span></div>');
            }
          }
          var html = '<b>' + cur + '/' + total + ' 集</b> · 正在扫描文件确认输出情况...';
          if (personRows.length > 0) html += '<div class="ep-person-grid">' + personRows.join('') + '</div>';
          html += '<div style="margin-top:8px"><button class="ep-detail-btn" data-action="ep-refresh" data-project="' + htm(projectName) + '" data-btn="null">🔄 刷新进度</button><button class="ep-detail-btn ep-deliv-btn" data-action="ep-deliverables" data-project="' + htm(projectName) + '" style="margin-left:6px;background:#0071e3;color:#fff">🎬 成片</button>' + (customStatus === '修改中' ? '<button class="ep-detail-btn ep-deliv-btn" data-action="ep-revising" data-project="' + htm(projectName) + '" style="margin-left:6px;background:#ff9500;color:#fff">📝 修改预览</button>' : '') + ((customStatus === '待交付' || customStatus === '交付中' || customStatus === '已交付' || customStatus === '已完成') ? '<button class="ep-detail-btn ep-deliv-btn" data-action="ep-delivery" data-project="' + htm(projectName) + '" style="margin-left:6px;background:#34c759;color:#fff">📦 交付预览</button>' : '') + '</div>';
          return { className: 'ep-missing-summary', html: html };
        }
      }
      return { className: 'ep-missing-summary', html: '' };
    }
    var total = data.total || 0;
    var missing = data.missing || [];
    var unnamed = data.unnamed || [];
    var plan = data.editor_plan || {};
    var curCount = data.current_count || 0;

    if (total === 0) {
      return { className: 'ep-missing-summary', html: '请先设置「总集数」，再点「统计」识别文件' };
    }
    if (missing.length === 0) {
      var detailHint = ' <div style="margin-top:8px"><button class="ep-detail-btn" data-action="ep-refresh" data-project="' + htm(projectName) + '" data-btn="null">🔄 刷新进度</button><button class="ep-detail-btn ep-deliv-btn" data-action="ep-deliverables" data-project="' + htm(projectName) + '" style="margin-left:6px;background:#0071e3;color:#fff">🎬 成片</button>' + (customStatus === '修改中' ? '<button class="ep-detail-btn ep-deliv-btn" data-action="ep-revising" data-project="' + htm(projectName) + '" style="margin-left:6px;background:#ff9500;color:#fff">📝 修改预览</button>' : '') + ((customStatus === '待交付' || customStatus === '交付中' || customStatus === '已交付' || customStatus === '已完成') ? '<button class="ep-detail-btn ep-deliv-btn" data-action="ep-delivery" data-project="' + htm(projectName) + '" style="margin-left:6px;background:#34c759;color:#fff">📦 交付预览</button>' : '') + '</div>';
      return {
        className: 'ep-missing-summary ok',
        html: '✅ ' + curCount + '/' + total + ' 集 全部输出完成' + detailHint
      };
    }

    // 按剪辑人员分组
    var groups = {};
    var unassigned = [];
    for (var i = 0; i < missing.length; i++) {
      var ep = missing[i];
      var creator = plan[String(ep)] || plan[ep] || null;
      if (creator) {
        if (!groups[creator]) groups[creator] = [];
        groups[creator].push(ep);
      } else {
        unassigned.push(ep);
      }
    }

    // 每人一行：<div class="ep-person-row"><b>人名</b><span class="ep-person-range">01-04, 12</span></div>
    var personRows = [];
    for (var name in groups) {
      if (!groups.hasOwnProperty(name)) continue;
      personRows.push('<div class="ep-person-row"><span class="ep-person-name">' + htm(name) + '</span><span class="ep-person-range">' + _compactRange(groups[name]) + '</span></div>');
    }
    if (unassigned.length > 0) {
      personRows.push('<div class="ep-person-row ep-person-unassigned"><span class="ep-person-name">未分配</span><span class="ep-person-range">' + _compactRange(unassigned) + '</span></div>');
    }

    var tipHtml = '<b>缺 ' + missing.length + '/' + total + ' 集</b>';
    if (unassigned.length > 0) tipHtml += '（<span class="ep-unassigned-count">' + unassigned.length + ' 集未分配</span>）';
    var unnamedHtml = '';
    if (unnamed && unnamed.length > 0) {
      unnamedHtml = '<div class="ep-unnamed-tip">另有 ' + unnamed.length + ' 个文件未识别集号</div>';
    }
    var detailBtn = '<div style="margin-top:8px"><button class="ep-detail-btn" data-action="ep-refresh" data-project="' + htm(projectName) + '" data-btn="null">🔄 刷新进度</button><button class="ep-detail-btn ep-deliv-btn" data-action="ep-deliverables" data-project="' + htm(projectName) + '" style="margin-left:6px;background:#0071e3;color:#fff">🎬 成片</button>' + (customStatus === '修改中' ? '<button class="ep-detail-btn ep-deliv-btn" data-action="ep-revising" data-project="' + htm(projectName) + '" style="margin-left:6px;background:#ff9500;color:#fff">📝 修改预览</button>' : '') + ((customStatus === '待交付' || customStatus === '交付中' || customStatus === '已交付' || customStatus === '已完成') ? '<button class="ep-detail-btn ep-deliv-btn" data-action="ep-delivery" data-project="' + htm(projectName) + '" style="margin-left:6px;background:#34c759;color:#fff">📦 交付预览</button>' : '') + '</div>';

    return {
      className: 'ep-missing-summary has-missing',
      html: tipHtml + '<div class="ep-person-grid">' + personRows.join('') + '</div>' + unnamedHtml + detailBtn
    };
  }

function fetchEpisodeStatus(projectName) {
    if (_episodeStatusPending[projectName]) return _episodeStatusPending[projectName];
    _episodeStatusPending[projectName] = api('GET', '/api/project/' + encodeURIComponent(projectName) + '/episodes_status')
      .then(function(data) {
        if (data && data.ok) _episodeStatusCache[projectName] = data;
        updateCardEpisodeSummary(projectName, data);
        return data;
      }).catch(function() {
        updateCardEpisodeSummary(projectName, { ok: false });
      }).then(function(data) {
        delete _episodeStatusPending[projectName];
        return data;
      });
    return _episodeStatusPending[projectName];
  }

function updateCardEpisodeSummary(projectName, data) {
    var present = (data && data.present) ? data.present : [];
    var missing = (data && data.missing) ? data.missing : [];
    var total = (data && data.total) || 0;
    var current = (data && data.current_count) || present.length;
    
    // 1. 更新文字摘要
    var selector = document.querySelector('.ep-missing-summary[data-ep-summary="' + projectName.replace(/"/g,'&quot;') + '"]');
    if (selector) {
        var _p = (projects||[]).find(function(x){ return x.name===projectName; });
        var _cs = _p ? (_p.custom_status||'') : '';
        var result = buildEpSummaryHtml(data, projectName, null, _cs);
        if (result) {
            selector.className = result.className || selector.className;
            selector.innerHTML = result.html || '';
        }
    }
    
    // 2. 更新进度条（用磁盘扫描的真实数据）
    var progId = 'prog-' + projectName.replace(/[^a-zA-Z0-9_]/g,'_');
    var progEl = document.getElementById(progId);
    if (progEl && total > 0) {
        var pct = Math.round(current / total * 100);
        var fill = progEl.querySelector('.card-progress-fill');
        var textSpans = progEl.querySelectorAll('.card-progress-text span');
        if (fill) {
            fill.style.width = pct + '%';
            fill.className = 'card-progress-fill' + (pct < 100 ? ' missing' : '');
        }
        if (textSpans.length >= 2) {
            textSpans[0].textContent = '输出进度';
            textSpans[1].innerHTML = '<span class="done">' + current + '</span> / ' + total + ' 集 · ' + pct + '%';
        }
    }
    
    // 3. 更新分集展开面板（如果已展开）
    var panelId = 'ep-panel-' + projectName.replace(/[^a-zA-Z0-9_]/g,'_');
    var panelEl = document.getElementById(panelId);
    if (panelEl && panelEl.classList.contains('open')) {
        panelEl.innerHTML = renderEpisodesGrid(projectName, data);
    }
}

function openProjectFolder(name, fullPath) {
    var postData;
    if (fullPath) {
      postData = { which: 'path', path: fullPath };
    } else {
      postData = { which: 'project' };
    }
    api('POST', '/api/project/' + encodeURIComponent(name) + '/open_folder', postData).then(function(data) {
      if (data.ok) toast(data.message || '已打开');
      else toast(data.message || '打开失败');
    }).catch(function() { toast('打开失败'); });
  }

function openEpisodeDetail(projectName) {
    try {
      var title = document.getElementById('modal-title');
      var body = document.getElementById('modal-body');
      var fileList = document.getElementById('file-list');
      // Swap: show body, hide file-list and toolbar/batch-progress
      title.textContent = '集数详情 - ' + projectName;
      body.style.display = '';
      body.innerHTML = '<div class="empty"><div class="loading">加载集数状态...</div></div>';
      if (fileList) fileList.style.display = 'none';
      var tb = document.getElementById('modal-toolbar');
      var bp = document.getElementById('batch-progress');
      var extra = document.getElementById('modal-extra');
      if (tb) tb.style.display = 'none';
      if (bp) bp.style.display = 'none';
      if (extra) extra.style.display = 'none';
      document.getElementById('modal').classList.add('active');

      fetchEpisodeStatus(projectName).then(function(data) {
        if (!data || !data.ok) {
          body.innerHTML = '<div class="empty"><div class="empty-icon">⚠️</div><div>获取失败</div></div>';
          return;
        }
        renderEpisodeDetailBody(projectName, data);
      }).catch(function(err) {
        body.innerHTML = '<div class="empty"><div class="empty-icon">⚠️</div><div>请求失败: ' + htm(String(err)) + '</div></div>';
      });
    } catch (err) {
      alert('打开详情出错: ' + err.message);
    }
  }

function renderEpisodeDetailBody(projectName, data) {
    var body = document.getElementById('modal-body');
    var total = data.total || 0;
    var present = data.present || [];
    var missing = data.missing || [];
    var unnamed = data.unnamed || [];
    var plan = data.editor_plan || {};
    var currentCount = data.current_count || 0;

    // 表头
    var grid = '<div class="ep-detail-grid">'
      + '<div class="ep-col-head">集号</div><div class="ep-col-head">状态</div><div class="ep-col-head">剪辑人员</div>';

    // 完整渲染 1..total；无 total 时仅渲染 present + missing 里的集号
    var nums;
    if (total > 0) {
      nums = [];
      for (var i = 1; i <= total; i++) nums.push(i);
    } else {
      var s = {};
      present.forEach(function(x) { s[x] = true; });
      missing.forEach(function(x) { s[x] = true; });
      nums = Object.keys(s).map(Number).sort(function(a, b) { return a - b; });
    }

    for (var j = 0; j < nums.length; j++) {
      var n = nums[j];
      var isMissing = missing.indexOf(n) >= 0;
      var val = plan[String(n)] || plan[n] || '';
      grid += '<div class="ep-num' + (isMissing ? ' missing-num' : '') + '">第 ' + String(n).padStart(2, '0') + ' 集</div>'
        + '<div class="ep-status ' + (isMissing ? 'missing' : 'ok') + '">' + (isMissing ? '未输出' : '已输出 ✅') + '</div>'
        + '<input class="ep-creator-input' + (isMissing ? ' missing-creator' : '') + '" data-ep="' + n + '" placeholder="' + (isMissing ? '请填剪辑人员' : '可填可不填') + '" value="' + htm(val) + '">';
    }
    grid += '</div>';

    var unnamedHtml = '';
    if (unnamed.length > 0) {
      var list = unnamed.slice(0, 20).map(function(n) { return '<code>' + htm(n) + '</code>'; }).join('<br>');
      var more = unnamed.length > 20 ? '<br>…还有 ' + (unnamed.length - 20) + ' 个' : '';
      unnamedHtml = '<div style="margin-top:12px;font-size:12px;color:#86868b">⚠️ 以下 ' + unnamed.length + ' 个文件未能识别集号：<br>' + list + more + '</div>';
    }

    body.innerHTML =
      '<div class="ep-detail-header">'
        + '<div class="ep-detail-stat">总集数 <b>' + total + '</b></div>'
        + '<div class="ep-detail-stat">已输出 <b style="color:#137333">' + present.length + '</b></div>'
        + '<div class="ep-detail-stat">缺失 <b style="color:#c5221f">' + missing.length + '</b></div>'
        + '<div class="ep-detail-stat">成片文件 <b>' + currentCount + '</b></div>'
      + '</div>'
      + '<div class="ep-batch-bar">'
        + '<button type="button" class="btn btn-secondary btn-sm" id="ep-batch-toggle">📋 批量粘贴分配表</button>'
        + '<span class="ep-batch-hint" style="display:none;color:#86868b;font-size:12px;margin-left:8px">格式：姓名:起始-结束，每行一条（支持中英文冒号、波浪号、逗号混合）</span>'
      + '</div>'
      + '<textarea id="ep-batch-input" class="ep-batch-input" placeholder="任显翔：1-4&#10;陈陆杰：5-9&#10;陈春阳：10-15&#10;程梦：16-21&#10;..."></textarea>'
      + '<div class="ep-batch-actions" style="display:none">'
        + '<button type="button" class="btn btn-primary btn-sm" id="ep-batch-apply">应用到表格</button>'
        + '<span id="ep-batch-apply-result" style="margin-left:8px;font-size:12px"></span>'
      + '</div>'
      + (nums.length === 0 ? '<div class="ep-detail-no-plan-hint">暂无可显示的集号。先在卡片上点「统计」识别成片文件。</div>' : '')
      + grid
      + unnamedHtml
      + '<div class="ep-detail-footer">'
        + '<button class="btn btn-secondary btn-sm" id="ep-detail-close">关闭</button>'
        + '<button class="btn btn-primary btn-sm" id="ep-detail-save">保存剪辑人员</button>'
      + '</div>';

    document.getElementById('ep-detail-close').addEventListener('click', closeModal);
    document.getElementById('ep-detail-save').addEventListener('click', function() {
      saveEpisodePlan(projectName);
    });

    // Toggle batch paste area
    var batchToggle = document.getElementById('ep-batch-toggle');
    var batchInput = document.getElementById('ep-batch-input');
    var batchActions = document.querySelector('.ep-batch-actions');
    var batchHint = document.querySelector('.ep-batch-hint');
    batchToggle.addEventListener('click', function() {
      var show = batchInput.style.display !== 'block';
      batchInput.style.display = show ? 'block' : 'none';
      batchActions.style.display = show ? 'block' : 'none';
      batchHint.style.display = show ? 'inline' : 'none';
    });
    document.getElementById('ep-batch-apply').addEventListener('click', function() {
      var result = parseBatchEditorPlan(batchInput.value);
      applyBatchEditorPlan(result);
    });
  }

function saveEpisodePlan(projectName) {
    var inputs = document.querySelectorAll('#modal-body .ep-creator-input');
    var plan = {};
    for (var i = 0; i < inputs.length; i++) {
      var ep = inputs[i].getAttribute('data-ep');
      var val = (inputs[i].value || '').trim();
      if (val) plan[String(ep)] = val;
    }
    toast('正在保存剪辑人员分配...');
    api('POST', '/api/project/' + encodeURIComponent(projectName) + '/episodes_plan', { plan: plan }).then(function(data) {
      if (data.ok) {
        toast(data.message || '已保存');
        // 清缓存，强制重新拉一次并刷新卡片
        delete _episodeStatusCache[projectName];
        fetchEpisodeStatus(projectName);
      } else {
        toast(data.message || '保存失败');
      }
    }).catch(function() { toast('保存失败，请检查网络'); });
  }

function parseBatchEditorPlan(text) {
    var plan = {};
    var lines = (text || '').split(/\r?\n/);
    var lineRe = /^(.+?)\s*[:：]\s*(.+?)\s*$/;
    lines.forEach(function(raw) {
      var line = raw.trim();
      if (!line) return;
      // Try "name: range" first
      var m = line.match(lineRe);
      var name, rangeStr;
      if (m) {
        name = m[1].trim();
        rangeStr = m[2].trim();
      } else {
        // Fallback: last whitespace-separated token(s) as range, rest as name
        var idx = line.search(/\d/);
        if (idx <= 0) return;
        name = line.substring(0, idx).trim().replace(/[:：]$/, '').trim();
        rangeStr = line.substring(idx).trim();
      }
      if (!name || !rangeStr) return;
      // Expand ranges like "1-4", "5~9", "10,11,13-15"
      var tokens = rangeStr.split(/[，,、\s]+/).filter(Boolean);
      tokens.forEach(function(tok) {
        var rng = tok.match(/^(\d{1,4})\s*[-~到至]\s*(\d{1,4})$/);
        if (rng) {
          var a = parseInt(rng[1], 10), b = parseInt(rng[2], 10);
          if (a > b) { var tmp = a; a = b; b = tmp; }
          for (var n = a; n <= b; n++) plan[String(n)] = name;
        } else {
          var single = tok.match(/^(\d{1,4})$/);
          if (single) plan[String(single[1])] = name;
        }
      });
    });
    return plan;
  }

function applyBatchEditorPlan(plan) {
    var inputs = document.querySelectorAll('#modal-body .ep-creator-input');
    var matched = 0;
    for (var i = 0; i < inputs.length; i++) {
      var ep = inputs[i].getAttribute('data-ep');
      if (plan[String(ep)] !== undefined) {
        inputs[i].value = plan[String(ep)];
        matched++;
      }
    }
    var summary = document.getElementById('ep-batch-apply-result');
    var totalKeys = Object.keys(plan).length;
    summary.textContent = '✅ 已填 ' + matched + ' 集，共解析 ' + totalKeys + ' 条分配；记得点右下角「保存剪辑人员」持久化。';
    summary.style.color = '#137333';
    // flash briefly — scroll to top of grid
    var grid = document.querySelector('.ep-detail-grid');
    if (grid) grid.scrollTop = 0;
  }

async function loadAllEpisodeSummary(){
  await loadInitialEpisodeSummary();
}

// === 手动刷新单个项目 ===
function refreshProjectStatus(name, btn){
  if (btn) { btn.disabled = true; btn.textContent = '⏳ 扫描中...'; }
  fetchEpisodeStatus(name).then(function(data){
    updateCardEpisodeSummary(name, data);
    toast('✅ ' + name + ' 进度已刷新', 'success');
  }).catch(function(err){
    toast('❌ 刷新失败: ' + err.message, 'error');
  }).finally(function(){
    if (btn) { btn.disabled = false; btn.textContent = '🔄 刷新'; }
  });
}

// 判断项目是否"进行中"（有实际制作状态且未完成）
function _isActiveProject(p){
  var s = String(p.custom_status||'').trim();
  return s !== '' && s !== '已完成';
}

// 判断是否为组内NAS进行中 section（本部门当前要用的项目）
function _isGroupActiveSection(sec){
  return sec && (sec.key === 'group_active' || (sec.projects && sec.projects.some(function(p){
    return p.project_type === 'group' && _isActiveProject(p);
  })));
}

// === 页面首次加载：只扫描"组内NAS进行中"的项目，其余按需加载 ===
async function loadInitialEpisodeSummary(){
  // 只扫"组内NAS进行中"且有分集数的项目（本部门当前真正要用的），数量很少、快速完成，
  // 让进度条和预览尽早可用；已完成 / 其他部门项目完全不扫，点开时按需加载
  await runRefreshAllProgress(null, true);
}

// === 全项目进度刷新（自动 + 手动共用）===
async function runRefreshAllProgress(btn, isAuto, opts){
  opts = opts || {};
  if (btn) { btn.disabled = true; btn.textContent = '⏳ 扫描中...'; }
  if (!allSections) { if(btn){btn.disabled=false;btn.textContent='🔄 刷新所有进度';} return; }

  let targets = [];
  for (const sec of allSections) {
    // 自动扫描：只处理"组内NAS进行中"section（本部门项目）
    // 已完成 / 其他部门项目不扫，点开时按需加载
    if (isAuto && !_isGroupActiveSection(sec)) continue;
    for (const p of (sec.projects || [])) {
      const hasEp = Number(p.total_episodes) > 0;
      // 自动扫描：只处理有分集数的项目（无分集数的项目扫描无意义且耗时）
      if (isAuto && !hasEp) continue;
      targets.push(p.name);
    }
  }
  if (targets.length === 0) {
    if (!isAuto) toast('没有需要扫描的项目', 'info');
    if(btn){btn.disabled=false;btn.textContent='🔄 刷新所有进度';}
    return;
  }

  if (isAuto) toast('📡 扫描 ' + targets.length + ' 个进行中项目的成片进度...', 'info');

  // 自动扫描用较低并发（4），避免占满后端线程池阻塞预览视频加载；
  // 手动刷新保持 8 路快速
  const CONCURRENCY = isAuto ? 4 : 8;
  let idx = 0;
  let ok = 0, fail = 0;
  function worker() {
    const i = idx++;
    if (i >= targets.length) return Promise.resolve();
    return fetchEpisodeStatus(targets[i]).then(function(d){
      if(d && d.ok) ok++; else fail++;
      if(btn) btn.textContent = '⏳ ' + (ok+fail) + '/' + targets.length;
      return null;
    }).catch(function(){ fail++; return null; }).then(worker);
  }
  await Promise.all(Array.from({length: Math.min(CONCURRENCY, targets.length)}, worker));

  if(btn){btn.disabled=false;btn.textContent='🔄 刷新所有进度';}
  toast(('✅ 进度扫描完成：' + ok + '/' + targets.length + ' 成功') + (fail>0 ? ('，' + fail + ' 失败') : ''),
        fail>0 ? 'warning' : 'success');
}

function toggleAlertDetail(){
  const el=$('episodeAlertDetail');
  const expanded=el.style.display==='block';
  el.style.display=expanded?'none':'block';
  const btn=document.querySelector('#episodeAlertBanner button');
  if(btn)btn.textContent=expanded?'展开':'收起';
}

/* ============ Paste Episodes Modal ============ */
function showPasteEpisodesModal(){
  $('pasteEpisodesModal').classList.add('active');
}
function closePasteEpisodesModal(){
  $('pasteEpisodesModal').classList.remove('active');
}
async function savePastedEpisodes(){
  const name=$('pasteProjectName').value.trim();
  const text=$('pasteEpisodesText').value.trim();
  if(!name||!text){toast('请填写项目名和分集数据','warning');return;}
  const lines=text.split('\n').map(l=>l.trim()).filter(Boolean);
  const episodes=lines.map(line=>{
    const m=line.match(/第\s*(\d+)\s*集\s*[-:：]\s*(.+)/);
    if(m)return{episode_number:parseInt(m[1]),editor:m[2].trim()};
    const m2=line.match(/^(\d+)\s*[-:：]\s*(.+)/);
    if(m2)return{episode_number:parseInt(m2[1]),editor:m2[2].trim()};
    return null;
  }).filter(Boolean);
  if(episodes.length===0){toast('无法解析任何分集数据，请检查格式','error');return;}
  try{
    toast(`正在保存 ${episodes.length} 集...`,'info');
    const r=await api('POST',`/api/project/${encodeURIComponent(name)}/episodes`,{episodes});
    toast(r.message||`成功保存 ${episodes.length} 集到 ${name}`,'success');
    closePasteEpisodesModal();
    $('pasteEpisodesText').value='';
    await loadProjects();
  }catch(e){toast('保存失败: '+e.message,'error');}
}

