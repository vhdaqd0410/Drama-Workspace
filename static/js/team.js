// Config + Team 管理

// ===== NAS 路径列表管理 =====
async function loadNasPaths(){
  try{
    const d = await api('GET', '/api/config/paths');
    if(!d || !d.ok) return;
    // 组内路径
    const gr = document.getElementById('cfgGroupRoot');
    if(gr) gr.value = d.group_root || '';
    const grStatus = document.getElementById('groupRootStatus');
    if(grStatus){
      const exists = await _pathExists(d.group_root);
      grStatus.innerHTML = d.group_root
        ? (exists ? '<span style="color:#2E7D32">✅ 路径可用</span>' : '<span style="color:#c5221f">⚠️ 路径不存在或不可访问</span>')
        : '';
    }
    // 制作部路径列表
    const list = document.getElementById('prodRootsList');
    if(list){
      const roots = d.production_roots || [];
      const labels = d.production_labels || {};
      if(roots.length === 0){
        list.innerHTML = '<div style="color:#86868b;font-size:12px;padding:4px">暂无制作部路径</div>';
      } else {
        list.innerHTML = roots.map(function(path){
          const label = labels[path] || '';
          const safe = String(path).replace(/"/g,'&quot;').replace(/'/g,"&#39;");
          return `<div style="display:flex;align-items:center;gap:6px;background:#f8fafc;border:1px solid #e5e8ee;border-radius:6px;padding:6px 8px">
            <span style="flex:1;font-size:12px;font-family:monospace;word-break:break-all">${htm(path)}</span>
            ${label ? `<span style="font-size:11px;color:#666;background:#eef2ff;padding:1px 6px;border-radius:4px">${htm(label)}</span>` : ''}
            <button class="btn btn-sm danger" onclick="delProdRoot('${safe}')" title="删除">✕</button>
          </div>`;
        }).join('');
      }
    }
  }catch(_){}
}
async function _pathExists(path){
  if(!path) return false;
  // 前端无法直接检测网络路径，用后端接口检测
  try{
    const d = await api('POST', '/api/config/path_check', { path: path });
    return !!(d && d.ok && d.exists);
  }catch(_){ return true; }
}
async function saveGroupRoot(){
  const input = document.getElementById('cfgGroupRoot');
  const path = (input.value||'').trim();
  if(!path){ toast('请输入组内NAS路径','warning'); return; }
  try{
    const d = await api('POST', '/api/config/paths', { type: 'group', path: path });
    toast(d.message || '已保存', d.ok ? 'success' : 'error');
    if(d.ok){ loadNasPaths(); loadConfig(); }
  }catch(e){ toast('保存失败: '+e.message,'error'); }
}
async function addProdRoot(){
  const input = document.getElementById('newProdRoot');
  const labelInput = document.getElementById('newProdLabel');
  const path = (input.value||'').trim();
  if(!path){ toast('请输入制作部路径','warning'); return; }
  try{
    const d = await api('POST', '/api/config/paths', { type: 'production', path: path, label: (labelInput.value||'').trim() });
    toast(d.message || '已添加', d.ok ? 'success' : 'error');
    if(d.ok){ input.value=''; labelInput.value=''; loadNasPaths(); loadConfig(); }
  }catch(e){ toast('添加失败: '+e.message,'error'); }
}
async function delProdRoot(path){
  if(!confirm('删除制作部路径 ' + path + '？')) return;
  try{
    const d = await api('DELETE', '/api/config/paths', { type: 'production', path: path });
    toast(d.message || '已删除', d.ok ? 'success' : 'error');
    if(d.ok){ loadNasPaths(); loadConfig(); }
  }catch(e){ toast('删除失败: '+e.message,'error'); }
}
// 快捷键显示格式化：'ctrl+alt+z' → 'Ctrl+Alt+Z'
function _fmtShortcut(s){
  if(!s) return '';
  return String(s).toLowerCase().split('+').map(function(p){
    p = p.trim();
    if(p==='ctrl') return 'Ctrl';
    if(p==='control') return 'Ctrl';
    if(p==='alt') return 'Alt';
    if(p==='shift') return 'Shift';
    if(p==='meta') return 'Win';
    if(p==='space') return 'Space';
    return p.toUpperCase();
  }).join('+');
}
// 当前录制状态
var _keyRecording = null;  // 'global' | 'page' | 'wakeup'

function startKeyRecord(type){
  if(_keyRecording){
    toast('请先完成当前录制', 'warning');
    return;
  }
  _keyRecording = type;
  var inputId = type === 'global' ? 'cfgGlobalSearchShortcut'
    : type === 'wakeup' ? 'cfgWakeupShortcut' : 'cfgSearchShortcut';
  var input = document.getElementById(inputId);
  if(input){
    input.value = '按下组合键...';
    input.style.color = '#0071e3';
    input.style.fontWeight = '600';
  }
  toast('🎹 按下你想要的组合键（如 Ctrl+Alt+Z）', 'info');

  // 一次性监听 keydown
  window._keyRecorder = function(e){
    e.preventDefault();
    e.stopPropagation();
    // Esc 取消录制
    if(e.key === 'Escape'){
      _cancelKeyRecord(type);
      return;
    }
    var mods = [];
    if(e.ctrlKey||e.metaKey) mods.push('ctrl');
    if(e.altKey) mods.push('alt');
    if(e.shiftKey) mods.push('shift');
    // 主键
    var key = (e.key||'').toLowerCase();
    if(key==='control'||key==='alt'||key==='shift'||key==='meta') return; // 只按修饰键不记录
    if(key===' ') key='space';
    // 数字键/字母键/功能键
    var valid = /^[a-z0-9]$/.test(key) || /^f\d{1,2}$/.test(key) || key==='space' || key==='enter' || key==='tab';
    if(!valid){
      toast('请使用字母/数字/功能键组合，Esc 取消', 'warning');
      return;
    }
    if(mods.length === 0){
      toast('请至少包含一个修饰键（Ctrl/Alt/Shift），Esc 取消', 'warning');
      return;
    }
    var shortcut = mods.concat([key]).join('+');
    _finishKeyRecord(type, shortcut);
  };
  window.addEventListener('keydown', window._keyRecorder);
}

// 结束录制并保存
function _finishKeyRecord(type, shortcut){
  if(window._keyRecorder){
    window.removeEventListener('keydown', window._keyRecorder);
    window._keyRecorder = null;
  }
  _keyRecording = null;
  _saveRecordedShortcut(type, shortcut);
}

// 取消录制（Esc 或超时）
function _cancelKeyRecord(type){
  if(window._keyRecorder){
    window.removeEventListener('keydown', window._keyRecorder);
    window._keyRecorder = null;
  }
  _keyRecording = null;
  var inputId = type === 'global' ? 'cfgGlobalSearchShortcut'
    : type === 'wakeup' ? 'cfgWakeupShortcut' : 'cfgSearchShortcut';
  var input = document.getElementById(inputId);
  if(input){
    input.value = '';
    input.style.color = '';
    input.style.fontWeight = '';
  }
  toast('已取消录制', 'info');
}

function _saveRecordedShortcut(type, shortcut){
  var inputId = type === 'global' ? 'cfgGlobalSearchShortcut'
    : type === 'wakeup' ? 'cfgWakeupShortcut' : 'cfgSearchShortcut';
  var input = document.getElementById(inputId);
  var settingKey = type === 'global' ? 'global_search_shortcut'
    : type === 'wakeup' ? 'wakeup_shortcut' : 'search_shortcut';
  var label = type === 'global' ? '全局搜索' : type === 'wakeup' ? '全局唤醒' : '页面内搜索';

  if(input){
    input.value = _fmtShortcut(shortcut);
    input.style.color = '';
    input.style.fontWeight = '';
  }

  // 保存到后端
  var body = {}; body[settingKey] = shortcut;
  api('PUT', '/api/settings', body).then(function(){
    // 更新前端生效的配置
    if(type === 'global'){
      // 页面内也支持全局搜索快捷键（作为补充）
    } else if(type === 'page'){
      window._shortcutConfig = window._shortcutConfig || {};
      window._shortcutConfig.search = shortcut;
    }
    toast('✅ ' + label + '快捷键已设置: ' + _fmtShortcut(shortcut) + (type==='page' ? '（已生效）' : '（重启软件生效）'),
      type==='page' ? 'success' : 'info');
  }).catch(function(){
    toast('保存失败', 'error');
  });
}

function clearKeyRecord(type){
  var inputId = type === 'global' ? 'cfgGlobalSearchShortcut'
    : type === 'wakeup' ? 'cfgWakeupShortcut' : 'cfgSearchShortcut';
  var settingKey = type === 'global' ? 'global_search_shortcut'
    : type === 'wakeup' ? 'wakeup_shortcut' : 'search_shortcut';
  var label = type === 'global' ? '全局搜索' : type === 'wakeup' ? '全局唤醒' : '页面内搜索';
  var input = document.getElementById(inputId);
  if(input) input.value = '';
  var body = {}; body[settingKey] = '';
  api('PUT', '/api/settings', body).then(function(){
    if(type === 'page'){
      window._shortcutConfig = window._shortcutConfig || {};
      window._shortcutConfig.search = '';
    }
    toast(label + '快捷键已恢复默认', 'info');
  }).catch(function(){});
}

async function loadConfig(){
  try{
    const cfg=await api('GET','/api/config');
    $('cfgGroupRoot').value=cfg.group_root||'';
    $('cfgWorkers').value=cfg.qa_workers||cfg.workers||4;
    $('cfgFfmpeg').value=cfg.ffmpeg_path||cfg.ffmpeg||'';
    $('cfgFfprobe').value=cfg.ffprobe_path||cfg.ffprobe||'';
    $('cfgNames').value=(cfg.suggested_names||cfg.fenji_names||[]).join('\n');
  }catch(e){}
  // 加载 NAS 路径列表（组内 + 制作部）
  try{ await loadNasPaths(); }catch(_){}
  // 加载快捷键配置
  try{
    const d = await api('GET', '/api/settings');
    if(d && d.ok && d.settings){
      var cfg = d.settings;
      if(cfg.search_shortcut){
        var s1 = document.getElementById('cfgSearchShortcut');
        if(s1) s1.value = _fmtShortcut(cfg.search_shortcut);
      }
      if(cfg.wakeup_shortcut){
        var s2 = document.getElementById('cfgWakeupShortcut');
        if(s2) s2.value = _fmtShortcut(cfg.wakeup_shortcut);
      }
      if(cfg.global_search_shortcut){
        var s3 = document.getElementById('cfgGlobalSearchShortcut');
        if(s3) s3.value = _fmtShortcut(cfg.global_search_shortcut);
      }
    }
  }catch(_){}
}
async function saveConfig(){
  const cfg={
    group_root:$('cfgGroupRoot').value,
    qa_workers:parseInt($('cfgWorkers').value)||4,
    ffmpeg_path:$('cfgFfmpeg').value,
    ffprobe_path:$('cfgFfprobe').value,
    suggested_names:$('cfgNames').value.split('\n').map(s=>s.trim()).filter(Boolean)
  };
  try{await api('POST','/api/config',cfg);toast('设置已保存','success')}catch(e){toast('保存失败: '+e.message,'error')}
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
