// Config + Team 管理
async function loadConfig(){
  try{
    const cfg=await api('GET','/api/config');
    $('cfgGroupRoot').value=cfg.group_root||'';
    $('cfgProdRoots').value=(cfg.production_roots||[]).join('\n');
    $('cfgWorkers').value=cfg.qa_workers||cfg.workers||4;
    $('cfgFfmpeg').value=cfg.ffmpeg_path||cfg.ffmpeg||'';
    $('cfgFfprobe').value=cfg.ffprobe_path||cfg.ffprobe||'';
    $('cfgNames').value=(cfg.suggested_names||cfg.fenji_names||[]).join('\n');
  }catch(e){}
  // 加载快捷键配置
  try{
    const d = await api('GET', '/api/settings');
    if(d && d.ok && d.settings && d.settings.search_shortcut){
      const sel = document.getElementById('cfgSearchShortcut');
      if(sel) sel.value = d.settings.search_shortcut;
    }
    if(d && d.ok && d.settings && d.settings.wakeup_shortcut){
      const sel2 = document.getElementById('cfgWakeupShortcut');
      if(sel2) sel2.value = d.settings.wakeup_shortcut;
    }
  }catch(_){}
}
async function saveConfig(){
  const cfg={
    group_root:$('cfgGroupRoot').value,
    production_roots:$('cfgProdRoots').value.split('\n').map(s=>s.trim()).filter(Boolean),
    qa_workers:parseInt($('cfgWorkers').value)||4,
    ffmpeg_path:$('cfgFfmpeg').value,
    ffprobe_path:$('cfgFfprobe').value,
    suggested_names:$('cfgNames').value.split('\n').map(s=>s.trim()).filter(Boolean)
  };
  try{await api('POST','/api/config',cfg);toast('设置已保存','success')}catch(e){toast('保存失败: '+e.message,'error')}
}
async function saveShortcut(){
  const sel = document.getElementById('cfgSearchShortcut');
  if(!sel) return;
  const val = sel.value;
  try{
    await api('PUT', '/api/settings', { search_shortcut: val });
    window._shortcutConfig = { search: val };
    toast('⚡ 快捷键已更新' + (val ? ': ' + val : '（默认 Ctrl+K/F）'), 'success');
  }catch(e){ toast('保存失败: '+e.message,'error'); }
}
async function saveWakeupShortcut(){
  const sel = document.getElementById('cfgWakeupShortcut');
  if(!sel) return;
  const val = sel.value;
  try{
    await api('PUT', '/api/settings', { wakeup_shortcut: val });
    toast('⚡ 全局唤醒快捷键已保存' + (val ? ': ' + val : '（默认自动选择）') + '，重启软件生效', 'info');
  }catch(e){ toast('保存失败: '+e.message,'error'); }
}
async function migrateOld(){
  try{toast('正在迁移...','info');const r=await api('POST','/api/migrate');toast((r&&r.message)||'迁移完成','success')}catch(e){toast('迁移失败: '+e.message,'error')}
}

/* ============ Team Modal ============ */
async function showTeam(){
  $('teamModal').classList.add('active');
  $('teamModalBody').innerHTML = '<div style="text-align:center;padding:30px;color:var(--text-sec)">加载中...</div>';
  loadTeamList();
}

async function loadTeamList(){
  let members = [];
  try{
    const data = await api('GET','/api/team/members');
    members = (data && data.members) || (Array.isArray(data) ? data : []);
  }catch(e){}
  renderTeamList(members);
}

function renderTeamList(members){
  const body = $('teamModalBody');
  if(!members || members.length === 0){
    body.innerHTML = `
      <div style="text-align:center;padding:30px;color:var(--text-sec)">暂无成员，点击下方按钮添加</div>
      <div style="text-align:center;margin-top:10px">
        <button class="btn btn-sm btn-primary" onclick="teamOpenAdd()">＋ 添加成员</button>
      </div>`;
    return;
  }

  const roleMap = {editor:'剪辑师', reviewer:'审核师', pm:'项目经理'};
  const roleColor = {editor:'#0071e3', reviewer:'#af52de', pm:'#ff9f0a'};

  const titleOrder = {'组长':0,'小组长':1,'卡前':2,'卡后':3,'助理':4};
  const sorted = [...members].sort((a,b) => {
    const ta = titleOrder[a.title] !== undefined ? titleOrder[a.title] : 99;
    const tb = titleOrder[b.title] !== undefined ? titleOrder[b.title] : 99;
    if(ta !== tb) return ta - tb;
    return (a.name||'').localeCompare(b.name||'', 'zh-Hans-CN');
  });
  body.innerHTML = `
    <div style="margin-bottom:12px;display:flex;gap:8px;align-items:center">
      <input type="text" id="teamSearch" placeholder="🔍 搜索姓名/称号..." style="flex:1;padding:8px 12px;border:1px solid var(--border);border-radius:6px;font-size:13px" oninput="teamFilterMembers(this.value)">
      <button class="btn btn-sm btn-primary" onclick="teamOpenAdd()">＋ 添加</button>
    </div>
    <div id="teamGrid" style="display:grid;grid-template-columns:repeat(2,1fr);gap:10px">
      ${sorted.map(m => teamCardHTML(m, roleMap, roleColor)).join('')}
    </div>
  `;
  window._teamMembers = members;
}

function teamCardHTML(m, roleMap, roleColor){
  const role = m.role || 'editor';
  const initial = (m.name||'?').charAt(0);
  const title = m.title || '';
  const dept = m.department || '';
  const titleBadge = title ? `<span style="background:var(--blue);color:#fff;padding:1px 8px;border-radius:10px;font-size:10px;margin-left:6px">${title}</span>` : '';
  const deptBadge = dept ? `<span style="background:#f0f1f3;color:var(--text-sec);padding:1px 8px;border-radius:10px;font-size:10px;margin-left:4px">${dept}</span>` : '';
  return `<div style="display:flex;align-items:center;gap:10px;padding:12px;background:#fafafa;border-radius:10px;border:1px solid #f0f0f0;transition:all .15s" class="team-card" data-name="${m.name}">
    <div style="width:38px;height:38px;border-radius:50%;background:linear-gradient(135deg,var(--blue),#5ac8fa);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:600;font-size:15px;flex-shrink:0">${initial}</div>
    <div style="flex:1;min-width:0">
      <div style="font-weight:600;font-size:14px;display:flex;align-items:center;gap:2px;flex-wrap:wrap">
        <span>${m.name}</span>${titleBadge}${deptBadge}
      </div>
      <div style="font-size:11px;color:${roleColor[role]||'var(--text-sec)'};margin-top:2px">${roleMap[role]||role}${m.skills && m.skills.length ? ' · ' + (Array.isArray(m.skills)?m.skills.join('/'):m.skills) : ''}</div>
    </div>
    <div style="display:flex;flex-direction:column;gap:4px">
      <button class="btn btn-sm" onclick="teamOpenEdit(${m.id})" title="编辑" style="padding:2px 8px;font-size:11px">✏️</button>
      <button class="btn btn-sm" onclick="teamConfirmDelete(${m.id},'${m.name.replace(/'/g,"\\'")}')" title="删除" style="padding:2px 8px;font-size:11px;color:#c5221f">🗑</button>
    </div>
  </div>`;
}

function teamFilterMembers(q){
  const all = window._teamMembers || [];
  if(!q){ renderTeamList(all); return; }
  const filtered = all.filter(m =>
    (m.name||'').includes(q) ||
    (m.title||'').includes(q) ||
    (m.department||'').includes(q)
  );
  // Re-render just the grid
  const body = $('teamModalBody');
  const roleMap = {editor:'剪辑师', reviewer:'审核师', pm:'项目经理'};
  const roleColor = {editor:'#0071e3', reviewer:'#af52de', pm:'#ff9f0a'};
  const grid = body.querySelector('#teamGrid');
  if(grid){
    const titleOrder = {'组长':0,'小组长':1,'卡前':2,'卡后':3,'助理':4};
    const sortedF = [...filtered].sort((a,b) => {
      const ta = titleOrder[a.title] !== undefined ? titleOrder[a.title] : 99;
      const tb = titleOrder[b.title] !== undefined ? titleOrder[b.title] : 99;
      if(ta !== tb) return ta - tb;
      return (a.name||'').localeCompare(b.name||'', 'zh-Hans-CN');
    });
    if(sortedF.length === 0){
      grid.innerHTML = '<div style="grid-column:span 2;text-align:center;padding:30px;color:var(--text-sec)">没有匹配的成员</div>';
    } else {
      grid.innerHTML = sortedF.map(m => teamCardHTML(m, roleMap, roleColor)).join('');
    }
  }
}

function teamOpenAdd(){ teamOpenEdit(null); }

function teamOpenEdit(id){
  const m = id ? (window._teamMembers||[]).find(x => x.id === id) : null;
  const isEdit = !!m;
  const modalId = 'teamEditModal';
  const existing = document.getElementById(modalId);
  if(existing) existing.remove();

  const modal = document.createElement('div');
  modal.id = modalId;
  modal.className = 'modal-overlay active';
  modal.innerHTML = `
    <div class="modal" style="min-width:400px">
      <div class="modal-head"><h3>${isEdit ? '✏️ 编辑成员' : '＋ 添加成员'}</h3><span class="modal-close" onclick="document.getElementById('${modalId}').remove()">×</span></div>
      <div class="modal-body" style="padding:16px">
        <div style="display:grid;grid-template-columns:100px 1fr;gap:10px;align-items:center">
          <label style="font-size:13px;color:var(--text-sec)">姓名 *</label>
          <input type="text" id="te_name" value="${m?m.name:''}" placeholder="输入姓名" style="padding:7px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px">
          <label style="font-size:13px;color:var(--text-sec)">角色</label>
          <select id="te_role" style="padding:7px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px;background:#fff">
            <option value="editor" ${(!m||m.role==='editor')?'selected':''}>🎬 剪辑师</option>
            <option value="reviewer" ${m&&m.role==='reviewer'?'selected':''}>🔍 审核师</option>
            <option value="pm" ${m&&m.role==='pm'?'selected':''}>📋 项目经理</option>
          </select>
          <label style="font-size:13px;color:var(--text-sec)">称号</label>
          <select id="te_title" style="padding:7px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px;background:#fff">
            <option value="" ${(!m||!m.title)?'selected':''}>— 请选择 —</option>
            <option value="组长" ${m&&m.title==='组长'?'selected':''}>组长</option>
            <option value="小组长" ${m&&m.title==='小组长'?'selected':''}>小组长</option>
            <option value="卡前" ${m&&m.title==='卡前'?'selected':''}>卡前</option>
            <option value="卡后" ${m&&m.title==='卡后'?'selected':''}>卡后</option>
            <option value="助理" ${m&&m.title==='助理'?'selected':''}>助理</option>
          </select>
          <label style="font-size:13px;color:var(--text-sec)">部门</label>
          <input type="text" id="te_dept" value="${m?(m.department||'').replace(/"/g,'&quot;'):''}" placeholder="如：AI漫剧一部 / 海外组" style="padding:7px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px">
        </div>
      </div>
      <div class="modal-foot" style="padding:12px 16px;border-top:1px solid var(--border);display:flex;gap:8px;justify-content:flex-end">
        <button class="btn btn-sm" onclick="document.getElementById('${modalId}').remove()">取消</button>
        <button class="btn btn-sm btn-primary" onclick="teamSaveMember(${id||'null'})">保存</button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);
}

async function teamSaveMember(id){
  const name = $('te_name').value.trim();
  const role = $('te_role').value;
  const title = $('te_title').value.trim();
  const dept = $('te_dept').value.trim();
  if(!name){ toast('请填写姓名','warning'); return; }

  try{
    if(id){
      await api('PUT', `/api/team/members/${id}`, { name, role, title, department: dept });
      toast(`✅ 已更新 ${name}`, 'success');
    } else {
      await api('POST', '/api/team/members', { name, role, title, department: dept });
      toast(`✅ 已添加 ${name}`, 'success');
    }
    document.getElementById('teamEditModal').remove();
    await loadTeamList();
  } catch(e){
    toast('保存失败: '+ (e.message||e),'error');
  }
}

function teamConfirmDelete(id, name){
  if(!confirm(`确定要删除 "${name}" 吗？`)) return;
  teamDeleteMember(id);
}

async function teamDeleteMember(id){
  try{
    await api('DELETE', `/api/team/members/${id}`);
    toast('🗑 已删除','success');
    await loadTeamList();
  } catch(e){
    toast('删除失败: '+(e.message||e),'error');
  }
}

/* ============ Init ============ */
