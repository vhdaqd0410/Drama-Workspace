// 分集面板 + 粘贴分集
// === 分集面板展开/收起 ===
function toggleEpisodesPanel(projectName, btn){
  const id = 'ep-panel-' + projectName.replace(/[^a-zA-Z0-9_]/g,'_');
  const panel = document.getElementById(id);
  if (!panel) return;
  
  if (panel.classList.contains('open')) {
    panel.classList.remove('open');
    btn.textContent = '📺 分集';
    return;
  }
  
  panel.classList.add('open');
  btn.textContent = '📺 收起';
  
  // 面板里如果还没内容，拉取并渲染
  if (panel.innerHTML.trim().length < 20) {
    panel.innerHTML = '<div style="text-align:center;padding:20px;color:#86868b;font-size:12px">加载分集数据中...</div>';
    fetchEpisodeStatus(projectName).then(function(data){
      if (data && data.total > 0) {
        panel.innerHTML = renderEpisodesGrid(projectName, data);
      } else {
        panel.innerHTML = '<div style="text-align:center;padding:20px;color:#86868b;font-size:12px">暂无分集数据（未设置总集数）</div>';
      }
    }).catch(function(){
      panel.innerHTML = '<div style="text-align:center;padding:20px;color:#ff3b30;font-size:12px">加载失败</div>';
    });
  }
}

// === 渲染分集 grid（常驻展开用）===

// === 粘贴分集文本 → 解析为 assign ===
function parsePasteEpisodes(text){
  const assign = {};
  const lines = text.split(/\r?\n/);
  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) continue;
    // 匹配 "姓名：集数范围"  — 冒号支持中英文
    const m = line.match(/^([^\s:：,，\-]+(?:\s+[^\s:：,，\-]+)*)\s*[:：]\s*(.+)$/);
    if (!m) continue;
    const name = m[1].trim();
    const ranges = m[2];
    if (!name || !ranges) continue;

    // 解析集数部分：支持 "1-3, 68-70" 或 "1,3,5-7" 等
    const parts = ranges.split(/[,，;；\s]+/).map(s => s.trim()).filter(Boolean);
    for (const part of parts) {
      const range = part.match(/^(\d+)\s*[-~到]\s*(\d+)$/);
      if (range) {
        const a = parseInt(range[1], 10);
        const b = parseInt(range[2], 10);
        const lo = Math.min(a, b), hi = Math.max(a, b);
        for (let ep = lo; ep <= hi; ep++) assign[String(ep)] = name;
      } else {
        const single = part.match(/^(\d+)$/);
        if (single) assign[String(single[1])] = name;
      }
    }
  }
  return assign;
}

// === 打开粘贴分集 modal ===
function openPasteEpisodesModal(projectName, currentTotal){
  const modalId = 'pasteEpModal';
  const existing = document.getElementById(modalId);
  if (existing) existing.remove();

  const defaultText = `陈陆杰：1-3, 68-70
陈春阳：4-8, 66-67
张靖杰：9-15
袁绍杰：16-25
王傲雪：26-35
张淯升：36-45
李钊琦：46-55
陈浩博：56-65`;

  const modal = document.createElement('div');
  modal.id = modalId;
  modal.className = 'modal-overlay active';
  modal.innerHTML = `
    <div class="modal" style="min-width:520px;max-width:600px">
      <div class="modal-head">
        <h3>📋 粘贴分集数据</h3>
        <span class="modal-close" onclick="document.getElementById('${modalId}').remove()">×</span>
      </div>
      <div class="modal-body" style="padding:16px">
        <div style="font-size:12px;color:var(--text-sec);margin-bottom:8px">
          格式：<code>姓名：集数范围</code>，每行一个人。支持范围写法：<code>1-3</code>、<code>1,5</code>、<code>1-3, 6-8</code>
        </div>
        <textarea id="pasteEpInput" rows="10" style="width:100%;padding:10px;border:1px solid var(--border);border-radius:6px;font-family:monospace;font-size:13px;resize:vertical" placeholder="粘贴分集数据...">${defaultText}</textarea>
        <div id="pasteEpPreview" style="margin-top:10px;padding:10px;background:#f5f5f7;border-radius:6px;font-size:12px;color:#333;max-height:180px;overflow-y:auto"></div>
        <div style="margin-top:10px;display:flex;gap:8px;align-items:center">
          <label style="font-size:12px;color:var(--text-sec)">总集数:</label>
          <input type="number" id="pasteEpTotal" value="${currentTotal || ''}" style="width:80px;padding:5px 8px;border:1px solid var(--border);border-radius:4px;font-size:13px" placeholder="必填">
          <button class="btn btn-sm" onclick="pasteEpPreview()" style="margin-left:auto">👀 预览</button>
        </div>
      </div>
      <div class="modal-foot" style="padding:12px 16px;border-top:1px solid var(--border);display:flex;gap:8px;justify-content:flex-end">
        <button class="btn btn-sm" onclick="document.getElementById('${modalId}').remove()">取消</button>
        <button class="btn btn-sm btn-primary" onclick="pasteEpSave('${htm(projectName)}', '${modalId}')">💾 保存并应用</button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);

  // 实时预览
  const ta = modal.querySelector('#pasteEpInput');
  if (ta) ta.addEventListener('input', pasteEpPreview);
  pasteEpPreview();
}

function pasteEpPreview(){
  const el = document.getElementById('pasteEpInput');
  const pv = document.getElementById('pasteEpPreview');
  if (!el || !pv) return;
  const assign = parsePasteEpisodes(el.value);
  const total = Object.keys(assign).length;
  if (total === 0) {
    pv.innerHTML = '<span style="color:#86868b">⚠️ 暂未解析到有效分集</span>';
    return;
  }
  // 按人名分组展示
  const byName = {};
  for (const [ep, name] of Object.entries(assign)) {
    if (!byName[name]) byName[name] = [];
    byName[name].push(parseInt(ep, 10));
  }
  const lines = Object.entries(byName).map(([name, eps]) => {
    eps.sort((a, b) => a - b);
    // 合并连续集数
    const ranges = [];
    let start = eps[0], prev = eps[0];
    for (let i = 1; i < eps.length; i++) {
      if (eps[i] === prev + 1) prev = eps[i];
      else { ranges.push(start === prev ? `${start}` : `${start}-${prev}`); start = prev = eps[i]; }
    }
    ranges.push(start === prev ? `${start}` : `${start}-${prev}`);
    return `<div style="margin:2px 0"><b>${htm(name)}</b>：${ranges.join(', ')} <span style="color:#86868b">(${eps.length}集)</span></div>`;
  });
  pv.innerHTML = `<div style="margin-bottom:4px;color:#34c759">✅ 共解析 ${total} 集，分配给 ${Object.keys(byName).length} 人</div>` + lines.join('');
}

async function pasteEpSave(projectName, modalId){
  const el = document.getElementById('pasteEpInput');
  const totalEl = document.getElementById('pasteEpTotal');
  if (!el) return;
  const assign = parsePasteEpisodes(el.value);
  if (Object.keys(assign).length === 0) {
    toast('❌ 未解析到有效分集数据', 'error');
    return;
  }
  let total = parseInt((totalEl && totalEl.value) || '0', 10) || 0;
  if (!total) {
    total = Math.max(...Object.keys(assign).map(k => parseInt(k, 10)));
    if (confirm(`未填写总集数，自动设为 ${total}，是否继续？`)) {
      // ok
    } else { return; }
  }

  try {
    toast('⏳ 正在保存分集...', 'info');
    await api('POST', '/api/bulk/import_episodes', {
      project_name: projectName,
      total_episodes: total,
      assign: assign,
    });
    toast(`✅ 已保存 ${Object.keys(assign).length} 集分集数据`, 'success');
    document.getElementById(modalId).remove();
    // 刷新分集面板
    delete _episodeStatusCache[projectName];
    refreshProjectStatus(projectName, null);
  } catch(e) {
    toast('❌ 保存失败: ' + (e.message || e), 'error');
  }
}

function renderEpisodesGrid(projectName, data){
  const total = data.total || 0;
  const present = data.present || [];
  const missing = data.missing || [];
  const editorPlan = data.editor_plan || {};
  
  const presentSet = new Set(present);
  const cells = [];
  
  for (let i = 1; i <= total; i++) {
    const isPresent = presentSet.has(i);
    const creator = editorPlan[String(i)] || editorPlan[i] || '';
    const cls = isPresent ? 'card-ep-cell present' : 'card-ep-cell missing';
    const title = isPresent ? '已输出' : '未输出';
    const creatorHtml = creator ? `<div class="card-ep-creator" title="${htm(creator)}">${htm(creator)}</div>` : '';
    cells.push(`
      <div class="${cls}" title="${i}集 ${title}${creator ? ' · ' + htm(creator) : ''}" 
           onclick="openEpisodeFile('${htm(projectName)}', ${i}, '${isPresent ? 'present' : 'missing'}')">
        ${i}${creatorHtml}
      </div>`);
  }
  
  const missingCount = missing.length;
  const header = `<div style="font-size:11px;color:#86868b;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap">
    <span>📺 ${total} 集 · 已输出 <b style="color:#34c759">${present.length}</b> · 缺 <b style="color:#ff3b30">${missingCount}</b></span>
    <span style="display:flex;gap:6px;align-items:center">
      <button class="btn btn-sm" style="padding:2px 8px;font-size:11px;background:#f0f7ff;border:1px solid #007aff;color:#007aff;border-radius:4px;cursor:pointer" onclick="openPasteEpisodesModal('${htm(projectName)}', ${total})">📋 粘贴分集</button>
      <span style="cursor:pointer;color:#007aff" onclick="refreshProjectStatus('${htm(projectName)}', null)">🔄 刷新进度</span>
    </span>
  </div>`;
  
  return header + '<div class="card-episodes-grid">' + cells.join('') + '</div>';
}

// === 点击单集 → 打开文件或文件夹 ===
function openEpisodeFile(projectName, epNum, status){
  if (status === 'present') {
    // 已输出 → 打开制作部 dest 目录（那里应该有 01上映单集版/第X集）
    openSmart(projectName, 'dest');
  } else {
    // 未输出 → 打开修改文件夹或 source
    openSmart(projectName, 'source');
  }
}

