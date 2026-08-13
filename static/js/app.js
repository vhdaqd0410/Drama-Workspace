// DOMContentLoaded 入口
document.addEventListener('DOMContentLoaded',async ()=>{
  try{
    // ===== 分秒帧配置初始化 =====
    try { window._fmConfig = await fetch('/api/fenmiaozhen/config').then(r => r.json()); } catch(_) { window._fmConfig = null; }

    // 0. 先显示页面框架（statsRow 去掉 spinner）
    $('statsRow').innerHTML = '<div class="stat-card"><div class="stat-icon blue">📁</div><div><div class="stat-num">...</div><div class="stat-label">加载中</div></div></div>';

    // 1. 绑定筛选器
    const fd=$('filterDept');const fs=$('filterStatus');const sb=$('sortBy');const so=$('sortOrder');
    if(fd)fd.addEventListener('change',renderDashboard);
    if(fs)fs.addEventListener('change',renderDashboard);
    if(sb)sb.addEventListener('change',renderDashboard);
    if(so)so.addEventListener('change',renderDashboard);
    const gs=$('globalSearch');if(gs)gs.addEventListener('input',renderDashboard);

    // 2. 分集管理 tab 的默认行（可选，失败不阻塞）
    try{
      addAssignRow('张大强','1-10');addAssignRow('李小明','11-20');addAssignRow('王芳','21-40');addAssignRow('赵磊','41-60');addAssignRow('陈思','61-80');
    }catch(e){;}

    // 3. 加载项目数据 — 用 try/catch 包裹每步
    try{
      await loadProjects();
    }catch(e){
      $('statsRow').innerHTML = '<div style="color:#ff3b30;padding:20px;">❌ 加载失败: ' + e.message + '<br><small>' + (e.stack||'') + '</small></div>';
    }

    // 4. 自动刷新已禁用 — 由用户手动点 🔄 刷新 按钮触发
    // pollDashboard=setInterval(loadProjects,30000);
  }catch(e){
    try{$('statsRow').innerHTML='<div style="color:#ff3b30;padding:20px;">❌ 页面初始化失败: '+e.message+'</div>';}catch(_){}
  }
});
