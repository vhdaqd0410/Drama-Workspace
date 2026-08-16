// DOMContentLoaded 入口
document.addEventListener('DOMContentLoaded',async ()=>{
  try{
    // 清理可能残留的快捷键录制监听器（防止拦截所有快捷键）
    try{
      if(window._keyRecorder){
        window.removeEventListener('keydown', window._keyRecorder);
        window._keyRecorder = null;
      }
      window._keyRecording = null;
    }catch(_){}

    // 加载用户设置（快捷键配置等），失败不阻塞
    try{
      const _set = await fetch('/api/settings').then(r=>r.json());
      if(_set && _set.ok && _set.settings){
        if(_set.settings.search_shortcut) window._shortcutConfig = { search: _set.settings.search_shortcut };
      }
    }catch(_){}

    // ===== 分秒帧配置初始化 =====
    try { window._fmConfig = await fetch('/api/fenmiaozhen/config').then(r => r.json()); } catch(_) { window._fmConfig = null; }

    // 0. 先显示页面框架（statsRow 去掉 spinner）
    $('statsRow').innerHTML = '<div class="stat-card"><div class="stat-icon blue">📁</div><div><div class="stat-num">...</div><div class="stat-label">加载中</div></div></div>';

    // 1. 绑定筛选器
    const fd=$('filterDept');const fs=$('filterStatus');const fm=$('filterMonth');const sb=$('sortBy');const so=$('sortOrder');
    if(fd)fd.addEventListener('change',renderDashboard);
    if(fs)fs.addEventListener('change',renderDashboard);
    if(fm)fm.addEventListener('change',renderDashboard);
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

    // 3.5 自动扫描所有项目的成片进度（后台执行）
    try{ loadAllEpisodeSummary(); } catch(e){}

    // 3.6 桌面版：建立 SSE 实时事件连接（任务完成通知）
    if(window.__IS_DESKTOP__){
      try{ initDesktopSSE(); } catch(e){ console.warn('SSE init failed', e); }
    }

    // 3.7 全局快捷键
    try{ bindShortcuts(); } catch(e){ console.warn('shortcuts init failed', e); }

    // 3.8 剪辑完成自动扫描提醒
    try{ if(typeof initEditCompleteWatcher==='function') initEditCompleteWatcher(); }catch(_){}

    // 3.9 通知中心角标（加载交付/待办提醒）
    try{ if(typeof loadNotifications==='function') loadNotifications(); }catch(_){}

    // 4. 自动刷新已禁用 — 由用户手动点 🔄 刷新 按钮触发
    // pollDashboard=setInterval(loadProjects,30000);
  }catch(e){
    try{$('statsRow').innerHTML='<div style="color:#ff3b30;padding:20px;">❌ 页面初始化失败: '+e.message+'</div>';}catch(_){}
  }
});
