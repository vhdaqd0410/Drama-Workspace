// 项目级操作: batchRefresh, openFolder, syncMaterial
// === 批量刷新某个 section 下所有项目的输出进度 ===
async function batchRefreshSection(sectionKey, btn){
  const sec = (allSections || []).find(s => s.key === sectionKey);
  if (!sec) return;
  const names = (sec.projects || []).map(p => p.name);
  if (names.length === 0) { toast('没有可刷新的项目', 'warning'); return; }

  const oldText = btn.textContent;
  btn.disabled = true;
  const CONCURRENCY = 6;
  let done = 0;
  let idx = 0;
  let success = 0;

  function updateBtn(){
    btn.textContent = `⏳ ${done}/${names.length}`;
  }
  updateBtn();

  async function worker(){
    const i = idx++;
    if (i >= names.length) return;
    const name = names[i];
    try {
      const data = await fetchEpisodeStatus(name);
      updateCardEpisodeSummary(name, data);
      if (data && data.ok) success++;
    } catch(e) {}
    done++;
    updateBtn();
    await worker();
  }

  await Promise.all(Array.from({length: Math.min(CONCURRENCY, names.length)}, worker));

  btn.disabled = false;
  btn.textContent = oldText;
  toast(`✅ 批量刷新完成：${success}/${names.length} 个项目成功`, success === names.length ? 'success' : 'info');
}

let _projectsLoading = false;
async function loadProjects(){
  if(_projectsLoading) return;
  _projectsLoading = true;
  try{
    const d = await api('GET','/api/projects');
    allSections=d.sections||[];
    let flat=[];
    if(d.sections)d.sections.forEach(s=>flat=flat.concat(s.projects||[]));
    if(flat.length===0&&Array.isArray(d))flat=d;
    if(flat.length===0&&d.projects)flat=d.projects;
    if(flat.length===0&&d.data)flat=d.data;
    projects=flat;
    allSections=d.sections||[];
    allProjects={production:d.production||[],group_all:d.group_all||[],group_completed:d.group_completed||[]};
    updateDepartmentFilter();
    renderDashboard();
    updateLightLists();
    await loadAllEpisodeSummary();
  }catch(e){
    $('statsRow').innerHTML='<div style="color:var(--red);padding:20px;">加载失败: '+e.message+'</div>';
  }finally{ _projectsLoading = false; }
}
async function scanProjects(){try{toast('正在扫描...','info');const r=await api('POST','/api/scan');toast((r&&r.message)||'扫描完成','success');await loadProjects()}catch(e){toast('扫描失败: '+e.message,'error')}}
async function onStatusChange(pname, sel){
  const newStatus = sel.value;
  const pnameEsc = pname.replace(/'/g,"\\'");
  sel.disabled = true;
  sel.title = '保存中...';
  try{
    const r = await api('POST', `/api/project/${encodeURIComponent(pname)}/custom_status`, {custom_status: newStatus});
    if(r.ok){
      toast('✅ 状态已更新为: ' + (newStatus||'未设置'), 'success');
      const newCls = getBadge(newStatus).cls;
      sel.className = 'badge editable-badge ' + newCls;
      sel.disabled = (newStatus === '已完成') ? true : false;
      sel.title = '点击修改项目状态';
      // 同步更新内存中的状态值，然后重渲染（自动排序）
      const target = (projects||[]).find(x => x.name === pname);
      if(target) target.custom_status = newStatus;
      (allSections||[]).forEach(sec => (sec.projects||[]).forEach(p => { if(p.name===pname) p.custom_status=newStatus; }));
      renderDashboard();
    }else{
      toast('❌ 更新失败: ' + (r.message||''), 'error');
      // 失败回滚
      sel.value = (sel.querySelectorAll('option')[0].value);
    }
  }catch(e){
    toast('❌ 网络错误: ' + e.message, 'error');
    sel.disabled = false;
    sel.title = '点击修改项目状态';
  }
}
async function updateStatus(name,status){try{await api('POST',`/api/project/${encodeURIComponent(name)}/custom_status`,{custom_status:status});toast(`已更新 ${name} → ${status}`,'success');await loadProjects()}catch(e){toast('更新失败: '+e.message,'error')}}
async function syncMaterial(name){
    // 先检查项目是否已经在组盘（用户可能手动复制了）
  try {
    const check = await api('POST', `/api/project/${encodeURIComponent(name)}/check_on_group`);
    if (check && check.on_group) {
      toast(`✅ "${name}" 已在组盘上，状态已刷新`, 'success');
      await loadProjects();
      return;
    }
  } catch(e) {}
if(!confirm(`确认要将 "${name}" 从制作部NAS同步到组内NAS吗？\n（首次同步可能耗时较长）`))return;
  toast(`正在同步: ${name}...`,'info');
  try{
    const r = await api('POST', `/api/sync/${encodeURIComponent(name)}`);
    if(r.ok){
      toast('同步已启动，请关注进度','success');
      await loadProjects();
      const syncProgId = 'sync-prog-' + name.replace(/[^a-zA-Z0-9_]/g,'_');
      const poll = setInterval(async () => {
        try {
          const d = await api('GET', '/api/projects');
          const flat = (d.production || []).concat(d.group_all || []);
          const target = flat.find(x => x.name === name);
          if(!target) return;

          // 实时更新进度条
          const sp = target.sync_progress || '';
          const m = sp.match(/^(\d+)%\s*(.*)$/);
          const pct = m ? parseInt(m[1]) : 0;
          const label = m ? m[2] : sp;
          const bar = document.getElementById(syncProgId);
          if (bar) {
            const fill = bar.querySelector('.sync-fill');
            const pctEl = bar.querySelector('.sync-pct');
            const lblEl = bar.querySelector('.card-progress-text span');
            if (fill) fill.style.width = pct + '%';
            if (pctEl) pctEl.textContent = pct + '%';
            if (lblEl) lblEl.textContent = '📦 ' + (label || '同步中...');
          }

          if(target.sync_status && target.sync_status !== 'syncing'){
            clearInterval(poll);
            toast(`✅ 同步完成: ${name}，自动进入分集`,'success');
            await loadProjects();
            setTimeout(() => openFenjiFor(name), 300);
          }
        } catch(e){}
      }, 2000);
      setTimeout(() => clearInterval(poll), 300000);
    } else {
      toast('同步失败: ' + (r.message || ''),'error');
    }
  } catch(e){
    toast('同步请求失败: '+e.message,'error');
  }
}
async function openFenmiaozhen(name){
  const enc = encodeURIComponent(name);
  const setBtn = (txt, disabled) => {
    const b = document.querySelector(`button[onclick*="openFenmiaozhen('${name.replace(/'/g,'\\')}')"]`);
    if(b){ b.textContent = txt; b.disabled = disabled; }
  };
  setBtn('⏳ 读取中...', true);
  try {
    let d = await fetch(`/api/fenmiaozhen/link/${enc}`).then(r => r.json());
    if (d.ok && d.has_link) {
      window.open(d.url, '_blank');
      setBtn('🔗 分秒帧', false);
      toast('✅ 已打开分秒帧链接', 'success');
      return;
    }
    const entered = prompt('🔗 请输入该项目的分秒帧审核链接：', 'https://www.mediatrack.cn/');
    if (!entered) { setBtn('🔗 分秒帧', false); return; }
    setBtn('⏳ 保存中...', true);
    const saved = await fetch(`/api/fenmiaozhen/link/${enc}`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({url: entered})
    }).then(r => r.json());
    if (saved.ok) {
      window.open(saved.url, '_blank');
      setBtn('🔗 分秒帧', false);
      toast('✅ 链接已保存，已打开分秒帧', 'success', 4000);
    } else {
      setBtn('🔗 分秒帧', false);
      toast('❌ 保存失败: ' + (saved.msg || ''), 'error');
    }
  } catch (e) {
    setBtn('🔗 分秒帧', false);
    toast('❌ 操作失败: ' + e.message, 'error');
  }
}

async function openFenjiFor(name){switchTab('fenji');await loadFenjiProjects();$('fjProject').value=name;readFromProject()}
async function qaStartFor(name){switchTab('qa');await loadQAProjects();$('qaProject').value=name;qaStart()}
async function editFenmiaozhenLink(name){
  const enc = encodeURIComponent(name);
  try {
    const d = await fetch(`/api/fenmiaozhen/link/${enc}`).then(r => r.json());
    const curUrl = (d.ok && d.url) ? d.url : '';
    const entered = prompt('🔗 修改分秒帧审核链接：', curUrl || 'https://www.mediatrack.cn/');
    if(!entered) return;
    const saved = await fetch(`/api/fenmiaozhen/link/${enc}`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({url: entered})
    }).then(r => r.json());
    if(saved.ok){
      toast('✅ 链接已更新', 'success');
    } else {
      toast('❌ 保存失败: '+(saved.msg||''), 'error');
    }
  } catch(e){
    toast('❌ 操作失败: '+e.message, 'error');
  }
}

function updateLightLists(){
  const fj=$('fjProject'),qa=$('qaProject');
  const opts='<option value="">— 选择项目 —</option>'+projects.map(p=>`<option value="${p.name}">${p.name}</option>`).join('');
  fj.innerHTML=opts;qa.innerHTML=opts;
}

/* ============ Project Detail Modal ============ */
