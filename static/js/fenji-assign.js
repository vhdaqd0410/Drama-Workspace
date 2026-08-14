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
    const escaped = name.replace(/'/g,"\\'");
    return `<div class="fj-row">
      <div class="idx">${i+1}</div>
      <div>${name}</div>
      <input class="range-input" value="${rng}" data-person="${escaped}"
             oninput="fjOnRangeLive('${escaped}', this.value)"
             onblur="fjOnRangeBlur('${escaped}')">
      <input type="number" value="${len}" min="0" data-person="${escaped}"
             oninput="fjOnLenLive('${escaped}', this.value)"
             onblur="fjOnLenBlur('${escaped}')">
      <div class="row-actions">
        <button onclick="fjOpenSegModal('${escaped}')" title="多段编辑">⛓</button>
        <button onclick="fjAutoAlignFrom('${escaped}')" title="从此人起自动连续对齐">🔗</button>
        <button class="danger" onclick="fjRemovePerson('${escaped}')">✕</button>
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
// ===== 范围/长度 编辑 —— 实时更新数据但不重绘 DOM，避免焦点丢失 =====
function fjOnRangeLive(person, val){
  fjRanges[person] = val;
  // 找到当前行（通过包含这个 input 的 row 元素），只更新同一行的"长度"数字，不重建 DOM
  fjUpdateRowLen(val);
  fjUpdateValidation();
  fjRenderPreview();
}
function fjUpdateRowLen(val){
  // 从事件对象获取当前焦点行 —— 用 document.activeElement 定位
  const el = document.activeElement;
  if(!el || !el.classList || !el.classList.contains('range-input')) return;
  const row = el.closest('.fj-row');
  if(!row) return;
  const numInput = row.querySelector('input[type="number"]');
  if(numInput) numInput.value = fjRangeToCount(val);
}
function fjOnRangeBlur(person){
  // 智能顺延：如果这个人是单段连续，自动把后面人的集数重新排成连续
  if(fjIsSingleSegment(fjRanges[person])){
    fjAutoAlignFrom(person);
    return;  // fjAutoAlignFrom 里已经做了 render + save
  }
  // 多段：不顺延，只保存重绘
  fjSaveSession();
  fjRenderTable();
}
function fjOnLenLive(person, lenStr){
  const len = parseInt(lenStr) || 0;
  const curStart = fjGetStartEpisode(fjRanges[person]);
  fjRanges[person] = `${curStart}-${curStart + len - 1}`;
  fjUpdateValidation();
  fjRenderPreview();
}
function fjOnLenBlur(person){
  // 长度编辑必然是单段 → 自动顺延后面人
  fjAutoAlignFrom(person);
}
function fjIsSingleSegment(rangeStr){
  const s = (rangeStr||'').trim();
  return /^(\d+-\d+|\d+)$/.test(s);
}
function fjRemovePerson(person){
  if(!confirm(`删除 ${person} 的分配？`)) return;
  delete fjRanges[person];
  // 删除后自动对齐后面所有人，保证连续
  fjAutoAlignAll();
  toast(`已删除 ${person}`, 'info');
}

// ===== 手动/自动对齐：保留前面人的原样，只对齐指定人+后面的人为连续 =====
function fjAutoAlignFrom(person){
  const ordered = fjOrderedPersons();
  const idx = ordered.indexOf(person);
  if(idx < 0) return;
  // 这个人自己保留原样，从他后面那个人开始对齐
  fjAutoAlignImpl(ordered, idx + 1);
}
function fjAutoAlignAll(){
  const ordered = fjOrderedPersons();
  if(ordered.length === 0) return;
  const total = parseInt($('fjTotal').value) || 0;
  let nextStart = 1;
  for(let i = 0; i < ordered.length; i++){
    const p = ordered[i];
    const len = fjRangeToCount(fjRanges[p]);
    if(len <= 0) continue;
    if(nextStart + len - 1 > total){
      toast(`对齐时 ${p} 超出总集数`, 'warning');
      break;
    }
    fjRanges[p] = `${nextStart}-${nextStart + len - 1}`;
    nextStart += len;
  }
  fjRenderTable();
  fjUpdateValidation();
  fjSaveSession();
  toast('🔗 全部已对齐为连续', 'success');
}
function fjAutoAlignImpl(ordered, startIdx){
  if(startIdx <= 0 || startIdx >= ordered.length) return;
  const total = parseInt($('fjTotal').value) || 0;
  // 前面人的最后一集 + 1 就是第一个要对齐人的起点
  let nextStart = fjGetEndEpisode(fjRanges[ordered[startIdx - 1]]) + 1;
  for(let i = startIdx; i < ordered.length; i++){
    const p = ordered[i];
    const len = fjRangeToCount(fjRanges[p]);
    if(len <= 0) continue;
    if(nextStart + len - 1 > total){
      toast(`对齐时 ${p} 超出总集数`, 'warning');
      break;
    }
    fjRanges[p] = `${nextStart}-${nextStart + len - 1}`;
    nextStart += len;
  }
  fjRenderTable();
  fjUpdateValidation();
  fjSaveSession();
}
function fjGetEndEpisode(rangeStr){
  const eps = fjParseRange(rangeStr).sort((a,b)=>a-b);
  return eps[eps.length - 1] || 1;
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
  fjUpdateTplBadge();
}
function fjUpdateTplBadge(){
  const b = document.getElementById('fjTplBadge');
  if(!b) return;
  const t = fjExportState.selectedTemplate || localStorage.getItem('fj_selected_template') || '';
  b.textContent = t ? t : '未选';
}

// ===== 模板管理 + 导出到 Excel =====
let fjExportState = {
  templates: [],
  selectedTemplate: localStorage.getItem('fj_selected_template') || '',
  templateB64: '',          // 如果前端直接 base64 上传了模板
  previewBlob: null,
  previewB64: '',
  previewFileName: '',
  previewProjectPath: '',
  lastBackup: null,
};

async function fjLoadTemplates(){
  try{
    const data = await api('GET', '/api/fenji/templates');
    fjExportState.templates = data.templates || [];
  }catch(e){ fjExportState.templates = []; }
}

async function fjPickTemplate(){
  // 小弹窗：列出已有模板 + 上传新模板
  await fjLoadTemplates();
  const existing = fjExportState.templates.length
    ? `<div class="fj-tpl-row"><select id="fjTplSelect" style="flex:1">${
        fjExportState.templates.map(n => `<option value="${n}" ${n===fjExportState.selectedTemplate?'selected':''}>${n}</option>`).join('')
      }</select><button class="btn btn-sm danger" onclick="fjDeleteTemplate()" title="删除">✕</button></div>`
    : '<div style="color:var(--text-sec);padding:12px 0">还没有上传过模板</div>';
  const html = `
    <div class="fj-tpl-picker" style="display:flex;gap:10px;flex-direction:column">
      ${existing}
      <div class="fj-tpl-row"><input type="file" id="fjTplFile" accept=".xlsx,.xlsm"><button class="btn btn-sm" onclick="fjUploadTemplate()">📤 上传</button></div>
      <div class="fj-tpl-row">
        <button class="btn btn-sm btn-primary" onclick="fjConfirmTemplate()" style="flex:1">✓ 使用选中模板</button>
      </div>
    </div>`;
  fjModalBody(html, () => {
    if(fjExportState.selectedTemplate){
      toast('📄 当前模板: ' + fjExportState.selectedTemplate, 'info');
    }
  });
}
function fjModalBody(html, onClose){
  let modal = document.getElementById('fjTplModal');
  if(!modal){
    modal = document.createElement('div');
    modal.id = 'fjTplModal';
    modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center;z-index:1000';
    document.body.appendChild(modal);
  }
  modal.innerHTML = `<div style="background:var(--bg-elev);padding:20px;border-radius:10px;min-width:420px;max-width:90vw;border:1px solid var(--border)">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
      <h3 style="margin:0">📄 选择模板</h3>
      <button class="btn btn-sm danger" onclick="document.getElementById('fjTplModal').remove()">✕</button>
    </div>${html}</div>`;
  modal.addEventListener('click', e => { if(e.target===modal) { modal.remove(); onClose && onClose(); } });
  modal.style.display = 'flex';
}

async function fjUploadTemplate(){
  const input = document.getElementById('fjTplFile');
  if(!input || !input.files[0]){ toast('请先选择文件','warning'); return; }
  const fd = new FormData();
  fd.append('file', input.files[0]);
  try{
    const data = await api('POST', '/api/fenji/upload_template', fd);
    toast(`✅ 已上传 ${data.name}`, 'success');
    fjExportState.selectedTemplate = data.name;
    localStorage.setItem('fj_selected_template', data.name);
    await fjLoadTemplates();
    // 刷新 modal 内容
    fjPickTemplate();
  }catch(e){ toast('上传失败: '+e.message,'error'); }
}
function fjDeleteTemplate(){
  const sel = document.getElementById('fjTplSelect');
  if(!sel || !sel.value) return;
  if(!confirm(`删除模板 ${sel.value}？`)) return;
  const templates = fjExportState.templates.filter(t => t !== sel.value);
  fjExportState.templates = templates;
  if(fjExportState.selectedTemplate === sel.value){
    fjExportState.selectedTemplate = templates[0] || '';
    localStorage.setItem('fj_selected_template', fjExportState.selectedTemplate);
  }
  fjPickTemplate(); // 刷新
  toast('已删除', 'info');
}
function fjConfirmTemplate(){
  const sel = document.getElementById('fjTplSelect');
  if(!sel || !sel.value){ toast('请先选择模板','warning'); return; }
  fjExportState.selectedTemplate = sel.value;
  localStorage.setItem('fj_selected_template', sel.value);
  document.getElementById('fjTplModal')?.remove();
  fjUpdateTplBadge();
  toast('📄 已选模板: ' + sel.value, 'success');
}

// 点击"📊 导出到模板"按钮
async function fjExportExcel(){
  // 1. 检查有分配
  const assignList = fjGetAssignList();
  if(!assignList.length){ toast('请先完成分集分配','warning'); return; }
  // 2. 检查模板
  await fjLoadTemplates();
  if(!fjExportState.selectedTemplate){
    toast('请先点「📄 模板」选择一个模板','warning');
    fjPickTemplate();
    return;
  }
  // 3. 打开交片时间 Modal
  fjOpenTimeModal(assignList);
}

function fjOpenTimeModal(assignList){
  const tmr = new Date(Date.now() + 24*3600*1000);
  const m = tmr.getMonth()+1, d = tmr.getDate();
  const html = `
    <div style="display:flex;flex-direction:column;gap:14px;min-width:360px">
      <div id="fjTimeHint" style="color:var(--text-sec);font-size:13px">交片日期自动设为明天：${m}.${d}</div>
      <div style="display:flex;gap:12px;align-items:center">
        <label style="min-width:60px">交片日期</label>
        <input type="date" id="fjTimeDate" value="${tmr.toISOString().slice(0,10)}" style="flex:1;padding:6px;border-radius:4px;border:1px solid var(--bg-border);background:var(--bg)">
      </div>
      <div style="display:flex;gap:12px;align-items:center">
        <label style="min-width:60px">上午/下午</label>
        <select id="fjTimePeriod" style="flex:1;padding:6px;border-radius:4px;border:1px solid var(--bg-border);background:var(--bg)">
          <option value="上午">上午</option>
          <option value="下午" selected>下午</option>
          <option value="晚上">晚上</option>
        </select>
      </div>
      <div style="display:flex;gap:12px;align-items:center">
        <label style="min-width:60px">几点</label>
        <select id="fjTimeHour" style="flex:1;padding:6px;border-radius:4px;border:1px solid var(--bg-border);background:var(--bg)">
          ${Array.from({length:24},(_,i)=>`<option value="${i}" ${i===18?'selected':''}>${i}点</option>`).join('')}
        </select>
      </div>
      <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:8px">
        <button class="btn btn-sm" onclick="document.getElementById('fjTimeModal')?.remove()">取消</button>
        <button class="btn btn-sm btn-primary" onclick="fjDoExport()">确定并导出</button>
      </div>
    </div>`;
  let modal = document.getElementById('fjTimeModal');
  if(!modal){
    modal = document.createElement('div');
    modal.id = 'fjTimeModal';
    modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center;z-index:1000';
    document.body.appendChild(modal);
  }
  modal.innerHTML = `<div style="background:var(--bg-elev);padding:20px;border-radius:10px;min-width:420px;border:1px solid var(--border)">
    <div style="margin-bottom:14px"><h3 style="margin:0">⏰ 设置交片时间</h3></div>${html}</div>`;
  modal.style.display = 'flex';
  modal._assignList = assignList;
  modal.onclick = e => { if(e.target === modal) modal.remove(); };
}

async function fjDoExport(){
  const modal = document.getElementById('fjTimeModal');
  const assignList = modal._assignList || fjGetAssignList();
  modal.remove();

  const dateStr = $('fjTimeDate').value;
  const period = $('fjTimePeriod').value;
  const hour = $('fjTimeHour').value;
  const dt = new Date(dateStr);
  const timeText = `${dt.getMonth()+1}.${dt.getDate()}${period}${hour}点交`;

  const project = $('fjProject').value || '未命名项目';
  let projectPath = project;
  // 从项目路径下拉框里读路径（如果有的话）
  const pOpt = $('fjProject')?.selectedOptions?.[0];
  if(pOpt && pOpt.value){
    try{
      const pdata = await api('GET', `/api/project/${encodeURIComponent(pOpt.value)}`);
      projectPath = pdata.path || project;
    }catch(e){}
  }

  toast('⏳ 正在生成模板...');
  try{
    const res = await api('POST', '/api/fenji/export_excel', {
      template_name: fjExportState.selectedTemplate,
      originalTemplateName: fjExportState.selectedTemplate,
      projectName: project,
      path: projectPath,
      timeText: timeText,
      statusText: '已分集',
      assign: assignList,
    });
    // 生成 Blob
    const binary = atob(res.file_b64);
    const bytes = new Uint8Array(binary.length);
    for(let i=0;i<binary.length;i++) bytes[i]=binary.charCodeAt(i);
    fjExportState.previewBlob = new Blob([bytes],{type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});
    fjExportState.previewB64 = res.file_b64;
    fjExportState.previewFileName = res.fileName;
    fjExportState.previewProjectPath = projectPath;
    fjExportState.lastBackup = res.backup || null;
    fjBuildPreview(assignList, projectPath, timeText);
  }catch(e){ toast('导出失败: '+e.message,'error'); }
}

function fjBuildPreview(assignList, path, timeText){
  const projectName = path.split(/[\\\/]/).pop() || '未命名项目';
  const scroll = document.getElementById('fjPreviewScroll');
  if(!scroll){ toast('预览区域找不到','error'); return; }
  let html = `<table class="preview-table" style="border-collapse:collapse;width:100%;font-size:13px">`;
  html += `<tr><td class="pt-title" colspan="5" style="background:#4472C4;color:#fff;padding:12px;text-align:center;font-size:16px;font-weight:bold">八月份</td></tr>`;
  // 新项目
  const first = assignList[0] || {person:'',range:''};
  html += `<tr>
    <td class="pt-block" style="background:#DDEBF7;color:#1F4E79;font-weight:bold;border:1px solid #BFBFBF;padding:8px;text-align:center">${escHtml(projectName)}</td>
    <td class="pt-block" style="background:#DDEBF7;color:#1F4E79;font-weight:bold;border:1px solid #BFBFBF;padding:8px;text-align:center">${escHtml(path)}</td>
    <td class="pt-body" style="border:1px solid #BFBFBF;padding:8px;text-align:center">${escHtml(first.person)}：${escHtml(first.range)}</td>
    <td class="pt-block" style="background:#DDEBF7;color:#1F4E79;font-weight:bold;border:1px solid #BFBFBF;padding:8px;text-align:center">${escHtml(timeText)}</td>
    <td class="pt-done" style="background:#E2EFDA;color:#006100;font-weight:bold;border:1px solid #BFBFBF;padding:8px;text-align:center">已分集</td>
  </tr>`;
  assignList.slice(1).forEach(d=>{
    html += `<tr>
      <td class="pt-empty" style="background:#DDEBF7;border:1px solid #BFBFBF"></td>
      <td class="pt-empty" style="background:#DDEBF7;border:1px solid #BFBFBF"></td>
      <td class="pt-body" style="border:1px solid #BFBFBF;padding:8px;text-align:center">${escHtml(d.person)}：${escHtml(d.range)}</td>
      <td class="pt-empty" style="background:#DDEBF7;border:1px solid #BFBFBF"></td>
      <td class="pt-empty" style="background:#DDEBF7;border:1px solid #BFBFBF"></td>
    </tr>`;
  });
  html += '</table>';
  scroll.innerHTML = html;

  // 备份提示
  const bk = document.getElementById('fjBackupNote');
  if(bk){
    if(fjExportState.lastBackup && fjExportState.lastBackup.name){
      bk.style.display = 'block';
      bk.innerHTML = '🛡️ 已自动备份原模板：<b>' + escHtml(fjExportState.lastBackup.name) + '</b>';
    } else {
      bk.style.display = 'none';
    }
  }

  // 显示预览 Modal
  let modal = document.getElementById('fjPreviewModal');
  if(!modal){
    modal = document.createElement('div');
    modal.id = 'fjPreviewModal';
    modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center;z-index:1000';
    document.body.appendChild(modal);
  }
  modal.innerHTML = `<div style="background:var(--bg-elev);border-radius:10px;min-width:680px;max-width:92vw;max-height:88vh;border:1px solid var(--border);display:flex;flex-direction:column">
    <div style="padding:12px 16px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border)">
      <h3 style="margin:0">📊 导出预览（可直接保存）</h3>
      <button class="btn btn-sm danger" onclick="document.getElementById('fjPreviewModal').remove()">✕</button>
    </div>
    <div id="fjPreviewScroll" style="overflow:auto;padding:16px;flex:1"></div>
    <div id="fjBackupNote" style="padding:8px 16px;color:var(--text-sec);font-size:13px"></div>
    <div style="padding:12px 16px;display:flex;gap:8px;justify-content:flex-end;border-top:1px solid var(--border)">
      <button class="btn btn-sm" onclick="document.getElementById('fjPreviewModal').remove()">取消</button>
      <button class="btn btn-sm" onclick="fjSaveToProjectFolder()">📁 保存到项目文件夹</button>
      <button class="btn btn-sm btn-primary" onclick="fjDownloadPreview()">💾 下载 Excel 文件</button>
    </div>
  </div>`;
  modal.style.display = 'flex';
  modal.onclick = e => { if(e.target === modal) modal.remove(); };
  // 重建 scroll 引用（innerHTML 后）
  setTimeout(() => fjBuildPreview._scroll = document.getElementById('fjPreviewScroll'), 0);
}

function fjDownloadPreview(){
  if(!fjExportState.previewBlob){ toast('没有可保存的文件','warning'); return; }
  const url = URL.createObjectURL(fjExportState.previewBlob);
  const a = document.createElement('a');
  a.href = url; a.download = fjExportState.previewFileName;
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  URL.revokeObjectURL(url);
  document.getElementById('fjPreviewModal')?.remove();
  toast('✅ 文件已下载', 'success');
}

async function fjSaveToProjectFolder(){
  if(!fjExportState.previewB64){ toast('没有可保存的文件','warning'); return; }
  const folder = fjExportState.previewProjectPath.replace(/[\\\/][^\\\/]*$/, '');
  if(!folder || folder === fjExportState.previewProjectPath){
    toast('无法识别项目文件夹路径','warning'); return;
  }
  try{
    const res = await api('POST', '/api/fenji/save_to_folder', {
      fileB64: fjExportState.previewB64,
      fileName: fjExportState.previewFileName,
      folder: folder,
      open: true,
    });
    toast(`✅ 已保存到 ${res.saved}，正在用 Excel 打开...`, 'success');
    document.getElementById('fjPreviewModal')?.remove();
  }catch(e){ toast('保存失败: '+e.message,'error'); }
}

// 返回 [{person, range}] —— 后端 /api/fenji/export_excel 需要的格式
function fjGetAssignList(){
  const ordered = fjOrderedPersons();
  return ordered.map(name => ({ person: name, range: fjRanges[name] || '' }))
               .filter(d => d.range && fjRangeToCount(d.range) > 0);
}

function escHtml(s){ const d=document.createElement('div'); d.textContent=s; return d.innerHTML; }
/* ============ QA Center ============ */
