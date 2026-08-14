// 分集分配器 30+ fj* 函数
// ===== Chips =====
function fjRenderChips(){
  const wrap = $('fjChipWrap');
  if(!wrap) return;
  if(fjPersons.length === 0){
    wrap.innerHTML = '<div style="color:var(--text-sec);font-size:12px">暂无人员，在下方添加</div>';
  } else {
    wrap.innerHTML = fjPersons.map(p => {
      const sel = fjSelected.includes(p) ? 'selected' : '';
      return `<div class="fj-chip ${sel}" onclick="fjToggle('${p.replace(/'/g,"\\'")}')">${p}</div>`;
    }).join('');
  }
  $('fjSelCount').textContent = `(已选 ${fjSelected.length} 人)`;
}
function fjToggle(p){
  const i = fjSelected.indexOf(p);
  if(i >= 0) fjSelected.splice(i,1); else fjSelected.push(p);
  fjPersons = fjPersons.slice();
  fjSave(FJ_KEY_PERSONS, fjPersons);
  // Remove deselected from ranges
  Object.keys(fjRanges).forEach(k => {
    if(!fjSelected.includes(k)) delete fjRanges[k];
  });
  fjRenderChips();
  fjRenderHeadTail();
  fjRenderTable();
  fjSaveSession();
}
function fjSelectAll(){ fjSelected = fjPersons.slice(); fjRenderChips(); fjRenderHeadTail(); fjRenderTable(); fjSaveSession(); }
function fjClearAll(){
  fjSelected = [];
  fjRanges = {};
  fjRenderChips();
  fjRenderTable();
  $('fjValidation').style.display='none';
  $('fjPreview').innerHTML = '<div style="color:var(--text-sec);text-align:center;padding:40px">完成分配后将在此显示预览</div>';
  $('fjStats').innerHTML = '';
  fjSaveSession();
}
function fjAddPerson(){
  const input = $('fjNewPerson');
  const v = (input.value||'').trim();
  if(!v) return;
  if(fjPersons.includes(v)){ toast('已存在','warning'); input.value=''; return; }
  fjPersons.push(v);
  fjSave(FJ_KEY_PERSONS, fjPersons);
  input.value = '';
  fjRenderChips();
  fjRenderHeadTail();
}

// ===== Head/Tail =====
function fjRenderHeadTail(){
  const on = $('fjHeadTailOn').checked;
  $('fjHeadTailPerson').style.display = on ? '' : 'none';
  $('fjHeadTailNum').style.display = on ? '' : 'none';
  const sel = $('fjHeadTailPerson');
  if(sel){
    const cur = sel.value;
    sel.innerHTML = '<option value="">选一位...</option>' + fjSelected.map(p => `<option value="${p}">${p}</option>`).join('');
    if(cur) sel.value = cur;
  }
}

// ===== Assign =====
function fjAssign(){
  const total = parseInt($('fjTotal').value) || 0;
  if(total <= 0){ toast('请填写总集数','warning'); return; }
  if(fjSelected.length === 0){ toast('请先选择剪辑师','warning'); return; }

  const htOn = $('fjHeadTailOn').checked;
  const htPerson = $('fjHeadTailPerson').value;
  const htNum = parseInt($('fjHeadTailNum').value) || 3;

  if(htOn && !htPerson){ toast('请选择头尾分的剪辑师','warning'); return; }

  let persons = fjSelected.slice();
  let startEp = 1, endEp = total;

  if(htOn){
    // Head + tail go to htPerson
    fjRanges[htPerson] = `${startEp}-${htNum},${total-htNum+1}-${total}`;
    persons = persons.filter(p => p !== htPerson);
    startEp = htNum + 1;
    endEp = total - htNum;
    if(startEp > endEp){ toast('头尾集数过多，中间没有空间','error'); return; }
  } else {
    fjRanges = {};
  }

  // Remaining persons split middle
  if(persons.length > 0){
    const segLen = endEp - startEp + 1;
    const per = Math.floor(segLen / persons.length);
    const rem = segLen % persons.length;
    let cur = startEp;
    persons.forEach((p, i) => {
      const sz = per + (i < rem ? 1 : 0);
      fjRanges[p] = `${cur}-${cur + sz - 1}`;
      cur += sz;
    });
  }

  fjRenderTable();
  fjUpdateValidation();
  toast('⚡ 分配完成','success');
  fjSaveSession();
  fjMaybeSaveHist();
}

// ===== Table =====
function fjRenderTable(){
  const body = $('fjAllocBody');
  const empty = $('fjTableEmpty');
  const names = Object.keys(fjRanges).filter(k => fjSelected.includes(k));
  if(names.length === 0){
    body.innerHTML = '';
    empty.style.display = '';
    $('fjPreview').innerHTML = '<div style="color:var(--text-sec);text-align:center;padding:40px">完成分配后将在此显示预览</div>';
    $('fjStats').innerHTML = '';
    return;
  }
  empty.style.display = 'none';
  body.innerHTML = names.map((name, i) => {
    const rng = fjRanges[name] || '';
    const len = fjRangeToCount(rng);
    return `<div class="fj-row">
      <div class="idx">${i+1}</div>
      <div>${name}</div>
      <input class="range-input" value="${rng}" data-person="${name}" oninput="fjOnRangeEdit('${name.replace(/'/g,"\\'")}', this.value)">
      <input type="number" value="${len}" min="0" data-person="${name}" oninput="fjOnLenEdit('${name.replace(/'/g,"\\'")}', this.value)">
      <div class="row-actions">
        <button onclick="fjOpenSegModal('${name.replace(/'/g,"\\'")}')" title="分段">⛓</button>
        <button class="danger" onclick="fjRemovePerson('${name.replace(/'/g,"\\'")}')">✕</button>
      </div>
    </div>`;
  }).join('');
  fjRenderPreview();
}
function fjRangeToCount(rng){
  let n = 0;
  (rng||'').split(',').forEach(part => {
    const m = part.trim().match(/^(\d+)\s*-\s*(\d+)$/);
    if(m) n += parseInt(m[2]) - parseInt(m[1]) + 1;
    else if(/^\d+$/.test(part.trim())) n += 1;
  });
  return n;
}
function fjOnRangeEdit(person, val){
  const oldStart = fjGetStartEpisode(fjRanges[person]);
  const oldLen = fjRangeToCount(fjRanges[person]);
  fjRanges[person] = val;
  const newLen = fjRangeToCount(val);

  if (oldLen !== newLen) {
    // 长度变了 —— 保持起点，重新分配范围 + 后面顺延
    fjRanges[person] = `${oldStart}-${oldStart + newLen - 1}`;
    fjShiftAllAfter(person);
  } else if (fjGetStartEpisode(val) !== oldStart) {
    // 起点变了但长度没变 —— 整体偏移后面的人
    fjRanges[person] = `${oldStart}-${oldStart + newLen - 1}`;
    fjShiftAllAfter(person);
  }
  fjRenderTable();
  fjUpdateValidation();
  fjSaveSession();
}
function fjOnLenEdit(person, lenStr){
  const total = parseInt($('fjTotal').value) || 0;
  const len = parseInt(lenStr) || 0;
  const curStart = fjGetStartEpisode(fjRanges[person]);
  if (curStart + len - 1 > total) {
    toast('超出总集数','warning');
    return;
  }
  fjRanges[person] = `${curStart}-${curStart + len - 1}`;
  fjShiftAllAfter(person);
  fjRenderTable();
  fjUpdateValidation();
  fjSaveSession();
}
function fjRemovePerson(person){
  delete fjRanges[person];
  // 重排所有人
  const ordered = fjOrderedPersons();
  let next = 1;
  ordered.forEach(p => {
    const l = fjRangeToCount(fjRanges[p]);
    fjRanges[p] = `${next}-${next + l - 1}`;
    next += l;
  });
  fjRenderTable();
  fjUpdateValidation();
  fjSaveSession();
}
function fjGetStartEpisode(rangeStr){
  const eps = fjParseRange(rangeStr).sort((a,b)=>a-b);
  return eps[0] || 1;
}
function fjOrderedPersons(){
  return Object.entries(fjRanges)
    .map(([p,r]) => [p, fjGetStartEpisode(r)])
    .sort((a,b) => a[1] - b[1])
    .map(e => e[0]);
}
function fjShiftAllAfter(person){
  const ordered = fjOrderedPersons();
  const idx = ordered.indexOf(person);
  if (idx < 0) return;
  let nextStart = fjGetStartEpisode(fjRanges[person]);
  for (let i = idx; i < ordered.length; i++) {
    const p = ordered[i];
    const len = fjRangeToCount(fjRanges[p]);
    if (len <= 0) continue;
    fjRanges[p] = `${nextStart}-${nextStart + len - 1}`;
    nextStart += len;
  }
}
function fjParseRange(s){
  s = (s||'').trim(); if(!s) return [];
  const out = [];
  for(const part of s.split(',')){
    const m = part.match(/^(\d+)\s*-\s*(\d+)$/);
    if(m){ for(let i=parseInt(m[1]);i<=parseInt(m[2]);i++) out.push(i); continue; }
    if(/^\d+$/.test(part.trim())) out.push(parseInt(part.trim()));
  }
  return out;
}

// ===== Validation =====
function fjUpdateValidation(){
  const total = parseInt($('fjTotal').value) || 0;
  const all = {};
  Object.entries(fjRanges).forEach(([p,r]) => fjParseRange(r).forEach(ep => { all[ep] = p; }));
  const assigned = Object.keys(all).map(Number).sort((a,b)=>a-b);
  const covered = new Set(assigned);
  const missing = [];
  for(let i=1;i<=total;i++) if(!covered.has(i)) missing.push(i);
  const dup = assigned.length - covered.size;
  const box = $('fjValidation');
  if(total === 0 || Object.keys(fjRanges).length === 0){ box.style.display='none'; return; }
  box.style.display = 'block';
  if(missing.length === 0 && dup === 0){
    box.className = 'validation-box ok';
    box.innerHTML = `✅ 覆盖 ${covered.size}/${total} 集 (100%)，无缺失无重叠`;
  } else {
    box.className = 'validation-box err';
    let msg = `覆盖 ${covered.size}/${total} 集，缺失 ${missing.length} 集`;
    if(dup > 0) msg += `，重叠 ${dup} 处`;
    if(missing.length <= 20) msg += ` (缺失: ${missing.join(',')})`;
    box.innerHTML = '❌ ' + msg;
  }
}

// ===== Preview =====
function fjRenderPreview(){
  const byEditor = {};
  Object.entries(fjRanges).forEach(([p,r]) => {
    fjParseRange(r).forEach(ep => {
      if(!byEditor[p]) byEditor[p] = [];
      byEditor[p].push(ep);
    });
  });
  const names = Object.keys(byEditor);
  if(names.length === 0){ $('fjPreview').innerHTML = '<div style="color:var(--text-sec);text-align:center;padding:40px">完成分配后将在此显示预览</div>'; return; }

  let html = '<div style="display:grid;grid-template-columns:100px 1fr 60px;gap:10px;padding:8px;background:#f5f5f7;border-radius:6px;font-size:12px;font-weight:600;color:var(--text-sec);margin-bottom:6px">';
  html += '<div>剪辑师</div><div>集数</div><div>数量</div></div>';

  const total = parseInt($('fjTotal').value) || 0;
  const maxPer = Math.max(...names.map(n => byEditor[n].length), 1);
  const colors = ['#0071e3','#34c759','#ff9f0a','#af52de','#ff2d55','#5ac8fa','#ffcc00','#ff3b30'];

  names.forEach((name, idx) => {
    const eps = byEditor[name].slice().sort((a,b)=>a-b);
    const ranges = []; let s = eps[0], prev = eps[0];
    for(let i=1;i<eps.length;i++){ if(eps[i]===prev+1) prev=eps[i]; else { ranges.push(s===prev?`${s}`:`${s}-${prev}`); s=prev=eps[i]; } }
    ranges.push(s===prev?`${s}`:`${s}-${prev}`);
    const pct = total > 0 ? (eps.length / total * 100) : 0;
    const color = colors[idx % colors.length];

    html += `<div style="display:grid;grid-template-columns:100px 1fr 60px;gap:10px;align-items:center;padding:8px 10px;border-bottom:1px solid #f0f0f0;font-size:13px">`;
    html += `<div style="font-weight:600;color:${color}">${name}</div>`;
    html += `<div style="font-family:Menlo,Consolas,monospace;color:var(--text-sec)">${ranges.join(', ')}</div>`;
    html += `<div style="text-align:right;font-weight:600">${eps.length}</div></div>`;

    // Stat bar
    const barW = Math.max(4, eps.length / total * 100);
  });

  $('fjPreview').innerHTML = html;

  // Stats bars
  let stats = '<div style="font-size:12px;font-weight:600;color:var(--text-sec);margin-bottom:6px">📊 工作量分布</div>';
  names.forEach((name, idx) => {
    const n = byEditor[name].length;
    const pct = total > 0 ? n / total * 100 : 0;
    const color = colors[idx % colors.length];
    stats += `<div class="fj-stat-bar"><div class="bar-label">${name}</div><div class="bar-track"><div class="bar-fill" style="width:${pct}%;background:${color}"></div></div><div class="bar-count">${n}集</div></div>`;
  });
  $('fjStats').innerHTML = stats;
}

function fjCopyResult(){
  const byEditor = {};
  Object.entries(fjRanges).forEach(([p,r]) => {
    fjParseRange(r).forEach(ep => {
      if(!byEditor[p]) byEditor[p] = [];
      byEditor[p].push(ep);
    });
  });
  let txt = '';
  Object.entries(byEditor).forEach(([name, eps]) => {
    eps.sort((a,b)=>a-b);
    const ranges = []; let s = eps[0], prev = eps[0];
    for(let i=1;i<eps.length;i++){ if(eps[i]===prev+1) prev=eps[i]; else { ranges.push(s===prev?`${s}`:`${s}-${prev}`); s=prev=eps[i]; } }
    ranges.push(s===prev?`${s}`:`${s}-${prev}`);
    txt += `${name}: ${ranges.join(', ')}\n`;
  });
  if(!txt){ toast('没有可复制的内容','warning'); return; }
  navigator.clipboard.writeText(txt.trim()).then(() => toast('📋 已复制到剪贴板','success')).catch(() => {
    const ta = document.createElement('textarea'); ta.value = txt; document.body.appendChild(ta); ta.select();
    document.execCommand('copy'); document.body.removeChild(ta); toast('📋 已复制','success');
  });
}

// ===== Seg Modal =====
let fjSegState = { person: '', ranges: [] };
function fjOpenSegModal(person){
  fjSegState.person = person;
  fjSegState.ranges = (fjRanges[person]||'').split(',').map(s => s.trim()).filter(Boolean);
  if(fjSegState.ranges.length === 0) fjSegState.ranges.push('');
  $('fjSegPerson').textContent = person;
  fjRenderSegList();
  $('fjSegModal').style.display = 'flex';
}
function fjCloseSegModal(){ $('fjSegModal').style.display = 'none'; }
function fjRenderSegList(){
  $('fjSegList').innerHTML = fjSegState.ranges.map((r,i) => `<div class="fj-seg-row">
    <input placeholder="如 1-10" value="${r}" oninput="fjSegState.ranges[${i}]=this.value">
    <button onclick="fjDelSegRow(${i})">✕</button>
  </div>`).join('');
}
function fjAddSegRow(){ fjSegState.ranges.push(''); fjRenderSegList(); }
function fjDelSegRow(i){ fjSegState.ranges.splice(i,1); if(fjSegState.ranges.length===0) fjSegState.ranges.push(''); fjRenderSegList(); }
function fjConfirmSeg(){
  const clean = fjSegState.ranges.map(s => s.trim()).filter(Boolean);
  // Validate
  const all = [];
  for(const r of clean){
    if(!/^\d+-\d+$/.test(r)){ toast('分段格式应为 起始-结束，如 1-10','error'); return; }
    const [a,b] = r.split('-').map(Number);
    if(a > b){ toast(`段 ${r} 起始大于结束`,'error'); return; }
    for(let i=a;i<=b;i++) all.push(i);
  }
  if(new Set(all).size !== all.length){ toast('分段之间有重叠','error'); return; }
  fjRanges[fjSegState.person] = clean.join(',');
  fjCloseSegModal();
  fjRenderTable();
  fjUpdateValidation();
  fjSaveSession();
}

// ===== History =====
function fjRenderHistSelect(){
  const sel = $('fjHistSelect');
  if(!sel) return;
  sel.innerHTML = '<option value="">— 从历史载入 —</option>' +
    fjHist.slice(0,20).map((h,i) => {
      const label = (h.name || h.path || h.time || '?').substring(0,30);
      return `<option value="${i}">${label} (${h.total||'?'}集)</option>`;
    }).join('');
  const list = $('fjHistList');
  if(list) fjRenderHistList();
  const count = $('fjHistCount');
  if(count) count.textContent = `共 ${fjHist.length} 条记录`;
}
function fjOpenHistList(){ fjRenderHistList(); $('fjHistModal').style.display = 'flex'; }
function fjRenderHistList(){
  const q = ($('fjHistSearch')?.value || '').toLowerCase();
  const list = $('fjHistList');
  if(!list) return;
  const items = fjHist.map((h,i) => ({h,i})).filter(({h}) => {
    if(!q) return true;
    return (h.name||'').toLowerCase().includes(q) || (h.path||'').toLowerCase().includes(q);
  });
  list.innerHTML = items.length === 0
    ? '<div style="padding:30px;text-align:center;color:var(--text-sec)">暂无历史记录</div>'
    : items.map(({h,i}) => {
        const assignStr = Object.entries(h.assign||{}).map(([p,r]) => `${p}(${r})`).join(', ');
        return `<div class="fj-hist-item">
          <div class="hi-time">${h.time||''}</div>
          <div class="hi-name" onclick="document.getElementById('fjHistModal').style.display='none';fjRestoreHistEntry(fjHist[${i}])">
            ${h.name||h.path||'未命名'} <span style="color:var(--text-sec);font-size:11px">· ${h.total||'?'}集 · ${assignStr.substring(0,40)}</span>
          </div>
          <button class="hi-del" onclick="fjDelHist(${i})">✕</button>
        </div>`;
      }).join('');
}
function fjRestoreHist(idx){
  const h = fjHist[parseInt(idx)];
  if(!h) return;
  fjRestoreHistEntry(h);
  fjHistSelect = h;
}
function fjRestoreHistEntry(h){
  // Extract persons & ranges from assign
  const ranges = h.assign || {};
  fjPersons = Object.keys(ranges);
  fjSelected = fjPersons.slice();
  fjRanges = {};
  Object.entries(ranges).forEach(([p, r]) => fjRanges[p] = r);
  fjSave(FJ_KEY_PERSONS, fjPersons);
  const projSel = $('fjProject');
  if(projSel && h.path){
    // Try to match by name in select options
    for(const opt of projSel.options){
      if(opt.value === h.path || opt.value === h.name){ projSel.value = opt.value; break; }
    }
  }
  if(h.total) $('fjTotal').value = h.total;
  fjRenderChips();
  fjRenderHeadTail();
  fjRenderTable();
  fjUpdateValidation();
  toast(`📖 已载入历史记录: ${h.name||h.path}`,'success');
}
function fjDelHist(i){
  fjHist.splice(i,1);
  fjSave(FJ_KEY_HISTORY, fjHist);
  fjRenderHistSelect();
  fjRenderHistList();
}
function fjClearAllHist(){
  if(!confirm('确定要清空所有历史记录吗？')) return;
  fjHist = [];
  fjSave(FJ_KEY_HISTORY, fjHist);
  fjRenderHistSelect();
  fjRenderHistList();
}
function fjMaybeSaveHist(){
  if(fjSuppressSaveHist) return;
  const name = $('fjProject').value;
  const total = parseInt($('fjTotal').value) || 0;
  if(!name || total === 0) return;
  const rangesCopy = {};
  Object.entries(fjRanges).forEach(([p,r]) => rangesCopy[p] = r);
  const entry = {
    time: new Date().toLocaleString('zh-CN'),
    name: name,
    path: name,
    total: total,
    assign: rangesCopy
  };
  // Remove duplicate for same project
  fjHist = fjHist.filter(h => !(h.path === name || h.name === name));
  fjHist.unshift(entry);
  // Keep max 200 entries
  if(fjHist.length > 200) fjHist = fjHist.slice(0,200);
  fjSave(FJ_KEY_HISTORY, fjHist);
  fjRenderHistSelect();
}

// ===== Session =====
function fjSaveSession(){
  try{
    const sess = {
      path: $('fjProject').value,
      total: parseInt($('fjTotal').value)||0,
      selected: fjSelected,
      ranges: fjRanges,
      htOn: $('fjHeadTailOn')?.checked || false,
      htPerson: $('fjHeadTailPerson')?.value || '',
      htNum: parseInt($('fjHeadTailNum')?.value)||3,
    };
    localStorage.setItem(FJ_KEY_SESSION, JSON.stringify(sess));
  }catch(e){}
}
function fjRestoreSession(){
  try{
    const raw = localStorage.getItem(FJ_KEY_SESSION);
    if(!raw) return;
    const s = JSON.parse(raw);
    if(s.path){
      const sel = $('fjProject');
      if(sel){
        // Try to match after options are loaded
        setTimeout(() => { sel.value = s.path; }, 50);
      }
    }
    if(s.total) $('fjTotal').value = s.total;
    if(Array.isArray(s.selected)) fjSelected = s.selected.filter(p => fjPersons.includes(p));
    if(s.ranges && typeof s.ranges === 'object') fjRanges = {};
    if(s.htOn){ $('fjHeadTailOn').checked = true; fjRenderHeadTail(); }
    if(s.htPerson) setTimeout(() => { $('fjHeadTailPerson').value = s.htPerson; }, 50);
    if(s.htNum) $('fjHeadTailNum').value = s.htNum;
  }catch(e){}
}

// ===== buildAssignObj / parseRange kept from old =====
function parseRange(s){
  s=(s||'').trim();if(!s)return[];const out=[];
  for(const part of s.split(',')){
    const m=part.match(/^(\d+)\s*-\s*(\d+)$/);if(m){for(let i=parseInt(m[1]);i<=parseInt(m[2]);i++)out.push(i);continue}
    const n=part.match(/^\d+$/);if(n)out.push(parseInt(part));
  }
  return out;
}
function buildAssignObj(){
  const plan={};
  for(const [p,r] of Object.entries(fjRanges)){
    fjParseRange(r).forEach(ep => { plan[String(ep)] = p; });
  }
  return plan;
}
async function readFromProject(){
  const project=$('fjProject').value;if(!project){toast('请先选择项目','warning');return}
  try{
    const data=await api('GET',`/api/project/${encodeURIComponent(project)}/episodes_plan`);
    const plan=data.plan||data||{};const summary=data.summary||{};
    const byEditor={};
    Object.entries(plan).forEach(([ep,name])=>{if(!name)return;if(!byEditor[name])byEditor[name]=[];byEditor[name].push(parseInt(ep))});
    fjRanges = {};
    fjPersons = [];
    Object.entries(byEditor).forEach(([name,eps]) => {
      if(!fjPersons.includes(name)) fjPersons.push(name);
      eps.sort((a,b)=>a-b);
      let s=eps[0],prev=eps[0],parts=[];
      for(let i=1;i<eps.length;i++){ if(eps[i]===prev+1)prev=eps[i]; else{ parts.push(s===prev?`${s}`:`${s}-${prev}`); s=prev=eps[i]; } }
      parts.push(s===prev?`${s}`:`${s}-${prev}`);
      fjRanges[name] = parts.join(',');
    });
    fjSelected = Object.keys(fjRanges);
    fjSave(FJ_KEY_PERSONS, fjPersons);
    if(data.total_episodes)$('fjTotal').value=data.total_episodes;
    fjRenderChips(); fjRenderHeadTail(); fjRenderTable(); fjUpdateValidation();
    toast(`📥 已从 ${project} 读取分配`,'success');
  }catch(e){toast('读取失败: '+e.message,'error')}
}
async function syncAssign(){
  const project=$('fjProject').value;const total=parseInt($('fjTotal').value)||0;
  if(!project){toast('请先选择项目','warning');return}
  const assign=buildAssignObj();
  if(Object.keys(assign).length===0){toast('请先分配集数','warning');return}
  try{
    toast('正在同步...','info');
    await api('POST','/api/bulk/import_episodes',{project_name:project,total_episodes:total,assign});
    toast(`已同步 ${Object.keys(assign).length} 集到 ${project}`,'success');
    await loadProjects();
    fjMaybeSaveHist();
  }catch(e){toast('同步失败: '+e.message,'error')}
}
async function openFenjiFor(name){
  switchTab('fenji');
  await loadFenjiProjects();
  $('fjProject').value = name;
  fjOnProjectChange();
}
/* ============ QA Center ============ */
