/* wb-mobile.js — 手机端专属界面
 * 响应式双端自动切换：屏幕 ≤768px 时进入手机模式，桌面端不受影响。
 * 手机端形态：底部导航（首页/待办/数据/我的）+ 卡片式项目列表 + 全屏详情弹窗。
 */
(function(){
  var WB = window.WB || (window.WB = {});
  var escHtml = WB.escHtml || function(s){ return String(s==null?'':s); };
  var api = WB.api || function(){ throw new Error('api not ready'); };
  var toast = WB.toast || function(){};

  var MOBILE_BREAKPOINT = 768;
  var mobile = {
    _data: { sections: [], projects: [], overview: null },
    _curTab: 'home',
    _filter: { q: '', status: '' },
    // 手机端分集 Tab 状态（total 默认 70）
    _fj: { project:'', total:70, selected:[], ranges:{} },

    // 是否处于手机模式
    isMobile: function(){ return window.innerWidth <= MOBILE_BREAKPOINT; },

    // 初始化：检测宽度 + 监听变化
    init: function(){
      var self = this;
      this.applyMode();
      // 注意：输入法弹出会触发 resize（高度变化），此时不能重渲染否则丢失焦点。
      // 只在跨越手机/桌面宽度断点时切换模式，高度变化（输入法）忽略。
      var _lastMobile = this.isMobile();
      window.addEventListener('resize', function(){
        var nowMobile = self.isMobile();
        if(nowMobile !== _lastMobile){
          _lastMobile = nowMobile;
          self.applyMode();
        }
      });
    },

    // 根据宽度应用手机/桌面模式（只在断点切换时调用）
    applyMode: function(){
      if(this.isMobile()){
        document.body.classList.add('mobile-mode');
        // 首次进入手机模式且内容为空则加载
        if(!this._data.projects.length){
          this.load();
        }
        this.render();
      } else {
        document.body.classList.remove('mobile-mode');
      }
    },

    // 加载数据
    async load(){
      try{
        var d = await api('GET','/api/projects');
        if(d && d.ok){
          this._data.sections = d.sections || [];
          this._data.overview = d.overview_stats || null;
          // 平铺所有项目
          var flat = [];
          (d.sections||[]).forEach(function(s){ (s.projects||[]).forEach(function(p){ flat.push(p); }); });
          this._data.projects = flat;
          if(this.isMobile()) this.render();
        }
      }catch(e){
        if(this.isMobile()) this.renderError('加载失败: '+e.message);
      }
    },

    // 切换底部导航 Tab
    switchTab: function(tab){
      this._curTab = tab;
      document.querySelectorAll('.m-tabbar .m-tab').forEach(function(b){
        b.classList.toggle('active', b.getAttribute('data-mtab')===tab);
      });
      this.render();
    },

    // 主导渲染
    render: function(){
      if(!this.isMobile()) return;
      var content = document.getElementById('m-content');
      if(!content) return;
      if(this._curTab === 'home') this.renderHome(content);
      else if(this._curTab === 'fenji') this.renderFenji(content);
      else if(this._curTab === 'stats') this.renderStats(content);
      else if(this._curTab === 'mine') this.renderMine(content);
    },

    /* ---------- 首页：统计 + 按部门分组的项目卡片列表 ---------- */
    renderHome: function(content){
      var ov = this._data.overview || {};
      var self = this;
      var html = '';

      // 统计卡
      html += '<div class="m-stats">'
        + '<div class="m-stat"><div class="m-num">'+(ov.total||0)+'</div><div class="m-lab">总项目</div></div>'
        + '<div class="m-stat"><div class="m-num">'+(ov.this_month||0)+'</div><div class="m-lab">本月</div></div>'
        + '<div class="m-stat"><div class="m-num" style="color:#34c759">'+(ov.this_month_done||0)+'</div><div class="m-lab">已完成</div></div>'
        + '<div class="m-stat"><div class="m-num" style="color:#ff9500">'+(ov.producing||0)+'</div><div class="m-lab">制作中</div></div>'
        + '</div>';

      // 搜索 + 状态筛选（输入框只渲染一次，搜索时用 _renderHomeList 局部刷新）
      html += '<div class="m-filter">'
        + '<input type="text" placeholder="🔍 搜索项目..." value="'+escHtml(this._filter.q)+'" oninput="WB.mobile.setSearch(this.value)">'
        + '<select onchange="WB.mobile.setStatus(this.value)"><option value="">全部状态</option>'
        + ['分集中','剪辑中','审核中','修改中','交付中','待交付','待质检','质检中','已完成'].map(function(s){
            return '<option value="'+s+'"'+(self._filter.status===s?' selected':'')+'>'+s+'</option>';
          }).join('')
        + '</select></div>';

      // 列表容器（可局部刷新，不重建输入框）
      html += '<div id="m-home-list"></div>';
      content.innerHTML = html;
      this._renderHomeList();
    },

    // 渲染/刷新首页分组列表（搜索/筛选时调用，保留输入框焦点）
    _renderHomeList: function(){
      var el = document.getElementById('m-home-list');
      if(!el) return;
      var self = this;
      var q = this._filter.q.toLowerCase();

      // 用桌面端相同的 sections 分组结构（组内进行中 / 各部门 / 已完成）
      var sections = this._data.sections || [];
      var html = '';
      sections.forEach(function(sec){
        // 按搜索/状态筛选项目
        var projects = (sec.projects||[]).filter(function(p){
          if(q && String(p.name||'').toLowerCase().indexOf(q)<0) return false;
          if(self._filter.status && (p.custom_status||'')!==self._filter.status) return false;
          return true;
        });
        if(projects.length === 0) return;
        // 组内按状态排序（未完成在前，按交付流程顺序）
        projects.sort(function(a,b){
          var ao = _workflowOrder(a.custom_status), bo = _workflowOrder(b.custom_status);
          if(ao!==bo) return ao-bo;
          return String(a.name||'').localeCompare(String(b.name||''));
        });
        // 默认折叠：除「组内进行中」外，其他分组折叠
        var isGroupActive = sec.key === 'group_active';
        var secId = 'm-sec-' + String(sec.key||'').replace(/[^a-zA-Z0-9_]/g,'_');
        html += '<div style="font-size:13px;font-weight:700;color:#86868b;margin:14px 2px 8px;display:flex;align-items:center;gap:6px;cursor:pointer" onclick="var d=document.getElementById(\''+secId+'\');if(d){d.style.display=d.style.display===\'none\'?\'\':\'none\'}">'
          + '<span style="font-size:10px;color:#86868b">'+(isGroupActive?'▼':'▶')+'</span>'
          + escHtml(sec.name||'项目') + ' <span style="font-weight:400;font-size:11px">('+projects.length+')</span></div>'
          + '<div id="'+secId+'"'+(isGroupActive?'':' style="display:none"')+'>';
        projects.forEach(function(p){
          html += self._projectCard(p);
        });
        html += '</div>';
      });

      if(!html){
        html = '<div class="m-empty">📭 暂无项目</div>';
      }
      el.innerHTML = html;
    },

    // 单个项目卡片
    _projectCard: function(p){
      var self = this;
      var st = p.custom_status || '';
      var total = p.total_episodes || 0;
      var cur = p.current_episodes || 0;
      var pct = total>0 ? Math.round(cur/total*100) : 0;
      var badge = this._statusBadge(st);
      var safeId = String(p.name||'').replace(/[^a-zA-Z0-9_]/g,'_');
      var progId = 'mprog-' + safeId;

      var html = '<div class="m-card" onclick="WB.mobile.openDetail(\''+String(p.name||'').replace(/'/g,"\\'")+'\')">'
        + '<div class="m-card-head">'
          + '<div class="m-card-name">'+escHtml(p.name)+'</div>'
          + '<span class="m-card-badge" style="background:'+badge.bg+';color:'+badge.fg+'">'+escHtml(badge.text)+'</span>'
        + '</div>'
        + '<div class="m-card-meta">'
          + (p.department?'<span class="m-chip">'+escHtml(p.department)+'</span>':'')
          + (p.project_month?'<span class="m-chip">📅 '+escHtml(p.project_month)+'</span>':'')
          + '<span class="m-chip">'+cur+'/'+total+' 集</span>'
          + (p.due_date?'<span class="m-chip">⏰ '+escHtml(p.due_date)+'</span>':'')
        + '</div>'
        + (total>0 ? '<div class="m-prog"><div class="m-prog-bar"><div class="m-prog-fill '+(pct<50?'warn':'')+'" id="'+progId+'" style="width:'+pct+'%"></div></div><div class="m-prog-text"><span>输出进度</span><span>'+pct+'%</span></div></div>' : '')
        + '</div>';
      return html;
    },

    // 状态徽标颜色
    _statusBadge: function(st){
      st = String(st||'');
      if(!st) return { bg:'#f2f3f5', fg:'#86868b', text:'未设置' };
      if(st.indexOf('完成')>=0) return { bg:'#d1f4e0', fg:'#1d8f4c', text:st };
      if(st.indexOf('质检')>=0) return { bg:'#e8f2fd', fg:'#0071e3', text:st };
      if(st.indexOf('交付')>=0) return { bg:'#fff3cd', fg:'#856404', text:st };
      if(st.indexOf('修改')>=0) return { bg:'#ffe8d9', fg:'#c2410c', text:st };
      if(st.indexOf('审核')>=0) return { bg:'#f3e8ff', fg:'#9333ea', text:st };
      if(st.indexOf('剪辑')>=0) return { bg:'#fde8e8', fg:'#dc2626', text:st };
      if(st.indexOf('分集')>=0) return { bg:'#f2f3f5', fg:'#4a4a4a', text:st };
      return { bg:'#f2f3f5', fg:'#4a4a4a', text:st };
    },

    // 搜索（只更新列表，不重建输入框，避免焦点丢失）
    setSearch: function(v){ this._filter.q = v; this._renderHomeList(); },
    // 状态筛选
    setStatus: function(v){ this._filter.status = v; this._renderHomeList(); },

    /* ---------- 项目详情全屏弹窗 ---------- */
    openDetail: function(name){
      var p = this._findProject(name);
      if(!p){ toast('项目不存在','warning'); return; }
      var self = this;
      var st = p.custom_status || '';
      var badge = this._statusBadge(st);
      var total = p.total_episodes || 0;
      var cur = p.current_episodes || 0;
      var pname = String(name||'').replace(/'/g,"\\'");

      var html = '<div class="m-detail" id="m-detail">'
        + '<div class="m-detail-bar"><button class="m-back" onclick="WB.mobile.closeDetail()">✕</button><div class="m-dt">'+escHtml(name)+'</div></div>'
        + '<div class="m-detail-body">'
          // 状态
          + '<div class="m-section"><h4>项目状态</h4>'
          + '<select class="m-status-select" id="m-status-select">'
          + ['','分集中','剪辑中','审核中','修改中','交付中','待交付','待质检','质检中','已完成'].map(function(s){
              return '<option value="'+s+'"'+(st===s?' selected':'')+'>'+(s||'未设置')+'</option>';
            }).join('')
          + '</select></div>'
          // 基本信息
          + '<div class="m-section"><h4>基本信息</h4>'
          + '<div class="m-row"><span class="m-k">部门</span><span class="m-v">'+escHtml(p.department||'—')+'</span></div>'
          + '<div class="m-row"><span class="m-k">集数</span><span class="m-v">'+cur+'/'+total+'</span></div>'
          + '<div class="m-row"><span class="m-k">月份</span><span class="m-v">'+escHtml(p.project_month||'—')+'</span></div>'
          + (p.due_date?'<div class="m-row"><span class="m-k">截止</span><span class="m-v">'+escHtml(p.due_date)+'</span></div>':'')
          + '</div>'
          // 缺集信息
          + '<div class="m-section"><h4>缺集情况</h4><div id="m-epinfo">加载中...</div></div>'
          // 操作按钮（按状态动态显示）
          + this._detailActionButtons(p, pname, st)
          // 各版本回传
          + '<div class="m-section"><h4>各版本回传</h4>'
          + '<div class="m-card-actions">'
          + '<button class="m-act success" onclick="WB.mobile.deliverVersion(\''+pname+'\',\'cheng\')">成片</button>'
          + '<button class="m-act success" onclick="WB.mobile.deliverVersion(\''+pname+'\',\'yinyue\')">有音乐</button>'
          + '<button class="m-act success" onclick="WB.mobile.deliverVersion(\''+pname+'\',\'wuyinyue\')">无音乐</button>'
          + '<button class="m-act success" onclick="WB.mobile.deliverVersion(\''+pname+'\',\'zimu\')">字幕</button>'
          + '</div></div>'
          // 待办
          + '<div class="m-section"><h4>待办</h4><div id="m-todo-list">加载中...</div>'
          + '<div class="m-todo-add"><input id="m-todo-input" placeholder="添加待办..." onkeydown="if(event.key===\'Enter\')WB.mobile.addTodo(\''+pname+'\')"><button onclick="WB.mobile.addTodo(\''+pname+'\')">添加</button></div></div>'
        + '</div></div>';
      document.getElementById('m-detail-root').innerHTML = html;
      this._bindSwipeBack();
      // 加载该项目的缺集信息
      this.loadEpisodeInfo(name);
      // 加载该项目的待办
      this.loadTodo(name);
      // 绑定左滑返回
      this._bindSwipeBack();
      // 更新状态变化时不保存，点"保存状态"才保存
    },

    // 加载缺集信息（/episodes_status）
    async loadEpisodeInfo(name){
      var box = document.getElementById('m-epinfo');
      if(!box) return;
      try{
        var d = await api('GET','/api/project/'+encodeURIComponent(name)+'/episodes_status');
        if(!d || !d.ok){ box.innerHTML = '<div style="color:#86868b;font-size:13px">无法获取缺集信息</div>'; return; }
        var total = d.total || 0;
        var present = d.present || [];
        var missing = d.missing || [];
        var cur = d.current_count || 0;
        var pct = total>0 ? Math.round(cur/total*100) : 0;
        var html = '<div class="m-prog"><div class="m-prog-bar"><div class="m-prog-fill '+(pct<50?'warn':'')+'" style="width:'+pct+'%"></div></div>'
          + '<div class="m-prog-text"><span>已输出 '+cur+'/'+total+' 集</span><span>'+pct+'%</span></div></div>';
        if(missing && missing.length){
          // 显示缺集（压缩成区间）
          var ranges = [];
          var s = missing[0], prev = missing[0];
          for(var i=1;i<missing.length;i++){
            if(missing[i]===prev+1){ prev=missing[i]; }
            else { ranges.push(s===prev?String(s):s+'-'+prev); s=prev=missing[i]; }
          }
          ranges.push(s===prev?String(s):s+'-'+prev);
          html += '<div style="font-size:12px;color:#dc2626;margin-top:6px">⚠️ 缺 ' + missing.length + ' 集：'
            + '<div style="font-size:12px;color:#1d1d1f;margin-top:4px;word-break:break-word">'+escHtml(ranges.join('、'))+'</div></div>';
        } else if(total>0){
          html += '<div style="font-size:12px;color:#1d8f4c;margin-top:6px">✅ 全部输出完成</div>';
        } else {
          html += '<div style="font-size:12px;color:#86868b;margin-top:6px">未设总集数，无法统计缺集</div>';
        }
        box.innerHTML = html;
      }catch(e){
        box.innerHTML = '<div style="color:#86868b;font-size:13px">缺集信息加载失败</div>';
      }
    },

    // 各版本回传（成片/有音乐/无音乐/字幕）— 触发对应版本文件批量回传
    deliverVersion: function(name, version){
      var label = {cheng:'成片', yinyue:'有音乐无字幕版本', wuyinyue:'无音乐无bgm版本', zimu:'字幕文件'}[version] || version;
      if(!confirm('确认回传「'+label+'」吗？\n将把该项目对应的 '+label+' 文件回传到制作部。\n\n确认继续？')) return;
      toast('正在回传 '+label+'...','info');
      // 回传逻辑：对成片用 deliver_batch 整目录；其他版本较复杂，此处用打开交付目录辅助
      // 这里先实现成片回传（最常用），其他版本提示用桌面端
      var self = this;
      if(version === 'cheng'){
        // 成片回传：批量回传成片目录全部文件
        api('POST','/api/deliver_batch/'+encodeURIComponent(name), { file_names:[], mode:'editing' }).then(function(r){
          if(r && r.ok){ toast('✅ 成片回传已启动','success'); }
          else toast((r&&r.message)||'回传启动失败','error');
        }).catch(function(e){ toast('回传失败: '+e.message,'error'); });
      } else {
        // 其他版本：回传 000交付 下对应版本子文件夹
        var folderMap = { yinyue:'有音乐无字幕版本', wuyinyue:'无音乐无bgm版本', zimu:'字幕' };
        var folderName = folderMap[version];
        api('POST','/api/deliver_folder/'+encodeURIComponent(name), { folder_names:[folderName], mode:'delivery' }).then(function(r){
          if(r && r.ok){ toast('✅ '+label+' 回传已启动','success'); }
          else toast((r&&r.message)||'回传启动失败','error');
        }).catch(function(e){ toast('回传失败: '+e.message,'error'); });
      }
    },

    // 按项目状态动态生成详情操作按钮
    _detailActionButtons: function(p, pname, st){
      var html = '<div class="m-section"><h4>操作</h4><div class="m-card-actions">';
      var isJianji = st.indexOf('剪辑') >= 0;
      var isShenhe = st.indexOf('审核') >= 0;
      var isXiugai = st.indexOf('修改') >= 0;
      // 剪辑中：刷新进度 + 成片预览
      if(isJianji){
        html += '<button class="m-act primary" onclick="WB.mobile.refreshDetailProgress(\''+pname+'\')">🔄 刷新进度</button>'
          + '<button class="m-act success" onclick="WB.mobile.openChengPreview(\''+pname+'\')">🎬 成片</button>';
      }
      // 审核中/修改中：分秒帧 + 修改预览
      if(isShenhe || isXiugai){
        html += '<button class="m-act primary" onclick="WB.mobile.openFenmiaozhenBtn(\''+pname+'\')">🔗 分秒帧</button>';
        if(isXiugai){
          html += '<button class="m-act warn" onclick="WB.mobile.openRevisePreview(\''+pname+'\')">📝 修改预览</button>';
        }
      }
      // 通用：保存状态 / 同步素材
      html += '<button class="m-act ghost" onclick="WB.mobile.saveStatus(\''+pname+'\')">保存状态</button>'
        + '<button class="m-act ghost" onclick="WB.mobile.doSync(\''+pname+'\')">同步素材</button>';
      html += '</div></div>';
      return html;
    },

    // 刷新进度（剪辑中）— 刷新并重新加载缺集
    async refreshDetailProgress(name){
      var self = this;
      toast('刷新进度中...','info');
      try{
        // 复用桌面端 refreshProjectStatus
        if(typeof refreshProjectStatus === 'function'){
          refreshProjectStatus(name, null);
        }
        // 重新加载缺集信息
        setTimeout(function(){ self.loadEpisodeInfo(name); }, 1500);
      }catch(e){ toast('刷新失败: '+e.message,'error'); }
    },

    // 成片预览：列出成片文件（editing）并可内嵌播放
    async openChengPreview(name){
      var pname = String(name||'').replace(/'/g,"\\'");
      var html = '<div class="m-detail" id="m-detail">'
        + '<div class="m-detail-bar"><button class="m-back" onclick="WB.mobile.closeDetail()">✕</button><div class="m-dt">🎬 成片</div></div>'
        + '<div class="m-detail-body"><div style="color:#86868b;text-align:center;padding:40px">加载成片文件...</div></div></div>';
      document.getElementById('m-detail-root').innerHTML = html;
      this._bindSwipeBack();
      try{
        var d = await api('GET','/api/output_files/'+encodeURIComponent(name)+'?mode=editing');
        var files = Array.isArray(d) ? d : (d.files || []);
        var body = document.querySelector('#m-detail .m-detail-body');
        if(!body) return;
        if(!files.length){
          body.innerHTML = '<div class="m-empty">📭 该项目暂无成片文件</div>';
          return;
        }
        var html2 = '<div style="margin-bottom:10px;font-size:13px;color:#86868b">共 '+files.length+' 个文件，点击可预览</div>';
        files.forEach(function(f, i){
          var fname = String(f.name||'').replace(/'/g,"\\'");
          var isVideo = ['.mp4','.mov','.mkv','.avi','.webm'].indexOf(String(f.ext||'').toLowerCase())>=0;
          html2 += '<div style="display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid #f0f0f0">'
            + '<span style="font-size:16px">'+(isVideo?'🎥':'📄')+'</span>'
            + '<div style="flex:1;min-width:0"><div style="font-size:13px;word-break:break-word">'+escHtml(f.name)+'</div>'
            + '<div style="font-size:11px;color:#86868b">'+(f.editor?'👤 '+escHtml(f.editor):'')+' '+(f.size_mb?f.size_mb+'MB':'')+'</div></div>'
            + (isVideo?'<button class="m-act ghost" style="min-width:auto;padding:6px 12px" onclick="WB.mobile.playVideo(\''+pname+'\',\''+fname+'\',\''+encodeURIComponent(f.name)+'\')">▶ 播放</button>':'')
            + '</div>';
        });
        body.innerHTML = html2;
      }catch(e){
        var body2 = document.querySelector('#m-detail .m-detail-body');
        if(body2) body2.innerHTML = '<div class="m-empty">加载失败: '+escHtml(e.message)+'</div>';
      }
    },

    // 修改预览：列出修改文件夹（revising）并可播放
    async openRevisePreview(name){
      var pname = String(name||'').replace(/'/g,"\\'");
      var html = '<div class="m-detail" id="m-detail">'
        + '<div class="m-detail-bar"><button class="m-back" onclick="WB.mobile.closeDetail()">✕</button><div class="m-dt">📝 修改预览</div></div>'
        + '<div class="m-detail-body"><div style="color:#86868b;text-align:center;padding:40px">加载修改文件夹...</div></div></div>';
      document.getElementById('m-detail-root').innerHTML = html;
      this._bindSwipeBack();
      try{
        var d = await api('GET','/api/output_files/'+encodeURIComponent(name)+'?mode=revising');
        var folders = (d && d.folders) || [];
        var body = document.querySelector('#m-detail .m-detail-body');
        if(!body) return;
        if(!folders.length){
          body.innerHTML = '<div class="m-empty">📭 该项目暂无修改文件夹</div>';
          return;
        }
        var html2 = '';
        folders.forEach(function(f, i){
          var fname = String(f.name||'').replace(/'/g,"\\'");
          var subpath = String(f.path||f.name||'').replace(/'/g,"\\'");
          html2 += '<div style="display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid #f0f0f0">'
            + '<span style="font-size:16px">📁</span>'
            + '<div style="flex:1"><div style="font-size:13px">'+escHtml(f.name)+'</div>'
            + '<div style="font-size:11px;color:#86868b">'+(f.file_count?f.file_count+' 个文件':'')+'</div></div>'
            + '<button class="m-act ghost" style="min-width:auto;padding:6px 12px" onclick="WB.mobile.openReviseFolder(\''+pname+'\',\''+subpath+'\',\''+fname+'\')">打开</button>'
            + '</div>';
        });
        body.innerHTML = html2;
      }catch(e){
        var body2 = document.querySelector('#m-detail .m-detail-body');
        if(body2) body2.innerHTML = '<div class="m-empty">加载失败: '+escHtml(e.message)+'</div>';
      }
    },

    // 打开某个修改文件夹里的文件列表
    async openReviseFolder(name, subpath, folderName){
      var pname = String(name||'').replace(/'/g,"\\'");
      var sp = String(subpath||'').replace(/'/g,"\\'");
      var html = '<div class="m-detail" id="m-detail">'
        + '<div class="m-detail-bar"><button class="m-back" onclick="WB.mobile.closeDetail()">✕</button><div class="m-dt">'+escHtml(folderName)+'</div></div>'
        + '<div class="m-detail-body"><div style="color:#86868b;text-align:center;padding:40px">加载中...</div></div></div>';
      document.getElementById('m-detail-root').innerHTML = html;
      this._bindSwipeBack();
      try{
        var d = await api('GET','/api/output_files/'+encodeURIComponent(name)+'?mode=revising&subpath='+encodeURIComponent(subpath));
        var files = (d && d.files) || [];
        var body = document.querySelector('#m-detail .m-detail-body');
        if(!body) return;
        if(!files.length){ body.innerHTML = '<div class="m-empty">📭 该修改文件夹暂无文件</div>'; return; }
        var html2 = '';
        files.forEach(function(f){
          var fname = String(f.name||'').replace(/'/g,"\\'");
          var isVideo = ['.mp4','.mov','.mkv','.avi','.webm'].indexOf(String(f.ext||'').toLowerCase())>=0;
          html2 += '<div style="display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid #f0f0f0">'
            + '<span>'+escHtml(f.name)+'</span>'
            + (isVideo?'<button class="m-act ghost" style="min-width:auto;padding:6px 12px;margin-left:auto" onclick="WB.mobile.playVideo(\''+pname+'\',\''+fname+'\',\''+encodeURIComponent(f.name)+'\',\'revising\',\''+sp+'\')">▶ 播放</button>':'')
            + '</div>';
        });
        body.innerHTML = html2;
      }catch(e){
        var body2 = document.querySelector('#m-detail .m-detail-body');
        if(body2) body2.innerHTML = '<div class="m-empty">加载失败: '+escHtml(e.message)+'</div>';
      }
    },

    // 分秒帧按钮：打开该项目的分秒帧链接
    async openFenmiaozhenBtn(name){
      var pname = String(name||'').replace(/'/g,"\\'");
      try{
        var d = await api('GET','/api/fenmiaozhen/link/'+encodeURIComponent(name));
        if(d && d.ok && d.has_link){
          window.open(d.url, '_blank');
          return;
        }
        // 无链接，提示设置（与桌面端一致）
        var url = prompt('该项目暂无分秒帧链接，请输入：', 'https://www.mediatrack.cn/');
        if(!url) return;
        var saved = await api('POST','/api/fenmiaozhen/link/'+encodeURIComponent(name), { url:url });
        if(saved && saved.ok){ window.open(saved.url, '_blank'); toast('✅ 分秒帧链接已保存','success'); }
        else toast((saved&&saved.msg)||'保存失败','error');
      }catch(e){ toast('操作失败: '+e.message,'error'); }
    },

    // 内嵌播放视频
    playVideo: function(name, displayName, encodedName, mode, subpath){
      var pname = String(name||'').replace(/'/g,"\\'");
      // 构建视频 URL（用后端流式接口）
      var base = '/api/preview/' + encodeURIComponent(name) + '/' + encodedName;
      if(mode === 'revising' && subpath){
        base += '?subpath=' + encodeURIComponent(subpath);
      }
      var html = '<div class="m-detail" id="m-detail">'
        + '<div class="m-detail-bar"><button class="m-back" onclick="WB.mobile.closeDetail()">✕</button><div class="m-dt">▶ '+escHtml(displayName)+'</div></div>'
        + '<div class="m-detail-body" style="display:flex;align-items:center;justify-content:center;background:#000">'
        + '<video controls autoplay style="width:100%;max-height:60vh;background:#000" src="'+base+'"></video>'
        + '</div></div>';
      document.getElementById('m-detail-root').innerHTML = html;
      this._bindSwipeBack();
    },

    // 绑定左滑返回手势（从屏幕左缘向左滑关闭详情）
    _bindSwipeBack: function(){
      var root = document.getElementById('m-detail');
      if(!root) return;
      var startX = 0, startY = 0;
      var self = this;
      root.addEventListener('touchstart', function(e){
        startX = e.touches[0].clientX;
        startY = e.touches[0].clientY;
      }, { passive: true });
      root.addEventListener('touchend', function(e){
        var dx = e.changedTouches[0].clientX - startX;
        var dy = e.changedTouches[0].clientY - startY;
        // 从屏幕左缘开始 + 左滑（dx<0）且超过阈值，竖直位移不大
        if(startX < 40 && dx < -60 && Math.abs(dy) < 80){
          self.closeDetail();
        }
      }, { passive: true });
    },

    closeDetail: function(){
      document.getElementById('m-detail-root').innerHTML = '';
    },

    _findProject: function(name){
      return this._data.projects.find(function(p){ return p.name===name; });
    },

    // 保存状态（复用全局 onStatusChange 逻辑）
    saveStatus: function(name){
      var sel = document.getElementById('m-status-select');
      if(!sel) return;
      var newStatus = sel.value;
      var self = this;
      api('POST','/api/project/'+encodeURIComponent(name)+'/custom_status', { custom_status: newStatus }).then(function(r){
        if(r && r.ok){
          toast('✅ 状态已更新为 '+(newStatus||'未设置'),'success');
          // 更新本地数据
          var p = self._findProject(name);
          if(p) p.custom_status = newStatus;
          self.closeDetail();
          self.render();
        } else {
          toast((r&&r.message)||'更新失败','error');
        }
      }).catch(function(e){ toast('❌ 更新失败: '+e.message,'error'); });
    },

    // 同步素材
    doSync: function(name){
      if(typeof syncMaterial === 'function'){ syncMaterial(name); }
      else toast('同步功能不可用','warning');
    },

    // 打开目录
    openGroup: function(name){
      if(typeof openSmart === 'function'){ openSmart(name, 'group'); }
      else toast('打开目录不可用','warning');
    },

    // 加载项目待办
    async loadTodo(name){
      var box = document.getElementById('m-todo-list');
      if(!box) return;
      try{
        var d = await api('GET','/api/project/'+encodeURIComponent(name)+'/todos');
        var todos = (d && d.todos) || [];
        if(!todos.length){
          box.innerHTML = '<div style="color:#86868b;text-align:center;padding:14px;font-size:13px">暂无待办</div>';
          return;
        }
        var pname = String(name||'').replace(/'/g,"\\'");
        box.innerHTML = todos.map(function(t){
          return '<div class="m-todo-item">'
            + '<div class="m-td-check'+(t.done?' done':'')+'" onclick="WB.mobile.toggleTodo(\''+pname+'\','+t.id+','+(t.done?0:1)+')">'+(t.done?'✓':'')+'</div>'
            + '<div class="m-td-text'+(t.done?' done':'')+'">'+escHtml(t.text)+'</div>'
            + '</div>';
        }).join('');
      }catch(e){
        box.innerHTML = '<div style="color:#ff3b30;text-align:center;padding:14px">加载失败</div>';
      }
    },

    // 添加待办
    async addTodo(name){
      var input = document.getElementById('m-todo-input');
      var text = input ? input.value.trim() : '';
      if(!text){ toast('请输入待办内容','warning'); return; }
      try{
        var d = await api('POST','/api/project/'+encodeURIComponent(name)+'/todos', { text:text });
        if(d && d.ok){
          if(input) input.value='';
          this.loadTodo(name);
          toast('已添加待办','success');
        } else toast((d&&d.message)||'添加失败','error');
      }catch(e){ toast('添加失败: '+e.message,'error'); }
    },

    // 切换待办完成
    async toggleTodo(name, id, done){
      try{
        await api('PUT','/api/project/'+encodeURIComponent(name)+'/todos/'+id, { done: !!done });
        this.loadTodo(name);
      }catch(e){ toast('更新失败: '+e.message,'error'); }
    },

    /* ---------- 待办 Tab：全局待办 ---------- */
    renderGlobalTodo: function(content){
      var self = this;
      api('GET','/api/todos/global?done=0').then(function(d){
        var todos = (d && d.todos) || [];
        // 按项目分组
        var groups = {};
        todos.forEach(function(t){ (groups[t.project_name||'(独立待办)']=groups[t.project_name||'(独立待办)']||[]).push(t); });
        var html = '<div style="margin-bottom:12px;font-size:13px;color:#86868b">📌 进行中的待办（'+todos.length+'）</div>';
        if(!todos.length){ html += '<div class="m-empty">🎉 没有待办</div>'; content.innerHTML=html; return; }
        Object.keys(groups).forEach(function(proj){
          html += '<div class="m-section"><h4>'+escHtml(proj)+'</h4>';
          groups[proj].forEach(function(t){
            var pn = String(t.project_name||'').replace(/'/g,"\\'");
            html += '<div class="m-todo-item">'
              + '<div class="m-td-check'+(t.done?' done':'')+'" onclick="WB.mobile.toggleGlobalTodo(\''+pn+'\','+t.id+','+(t.done?0:1)+')">'+(t.done?'✓':'')+'</div>'
              + '<div class="m-td-text'+(t.done?' done':'')+'">'+escHtml(t.text)+'</div>'
              + '</div>';
          });
          html += '</div>';
        });
        content.innerHTML = html;
      }).catch(function(e){ content.innerHTML = '<div class="m-empty">加载失败: '+escHtml(e.message)+'</div>'; });
    },

    async toggleGlobalTodo(pname, id, done){
      try{
        await api('PUT','/api/project/'+encodeURIComponent(pname)+'/todos/'+id, { done: !!done });
        this.render();
      }catch(e){ toast('更新失败: '+e.message,'error'); }
    },

    /* ---------- 数据 Tab：每个剪辑师的工作量 + 提成详情（美观版）---------- */
    renderStats: function(content){
      var self = this;
      var ov = this._data.overview || {};
      // 概览统计卡
      var html = '<div class="m-section"><h4>概览</h4>'
        + '<div class="m-stats">'
        + '<div class="m-stat"><div class="m-num">'+(ov.total||0)+'</div><div class="m-lab">总项目</div></div>'
        + '<div class="m-stat"><div class="m-num">'+(ov.this_month||0)+'</div><div class="m-lab">本月</div></div>'
        + '<div class="m-stat"><div class="m-num" style="color:#34c759">'+(ov.this_month_done||0)+'</div><div class="m-lab">已完成</div></div>'
        + '<div class="m-stat"><div class="m-num" style="color:#ff9500">'+(ov.producing||0)+'</div><div class="m-lab">制作中</div></div>'
        + '</div></div>';
      content.innerHTML = html;
      // 加载剪辑师工作量和提成
      api('GET','/api/commission/monthly').then(function(d){
        if(!d || !d.ok) return;
        var rows = (d.rows || []).slice().sort(function(a,b){ return (b.commission||0)-(a.commission||0); });
        var summary = d.summary || {};
        var totalComm = summary.total_commission || 0;
        var met = summary.met_quota || 0;
        var all = summary.total_people || 0;
        var totalEp = summary.total_episodes || 0;

        // 顶部汇总卡（深色）
        var h2 = '<div class="m-sum-card">'
          + '<div class="m-sum-label">本月总提成（'+escHtml(d.month||'')+'）</div>'
          + '<div class="m-sum-main">¥'+(totalComm<0?'-':'')+Math.abs(totalComm).toLocaleString()+'</div>'
          + '<div class="m-sum-row">'
          + '<div class="m-sum-item"><div class="m-num" style="color:#34c759">'+met+'/'+all+'</div><div class="m-lab">达标</div></div>'
          + '<div class="m-sum-item"><div class="m-num">'+totalEp+'</div><div class="m-lab">总集数</div></div>'
          + '<div class="m-sum-item"><div class="m-num" style="color:#ffd60a">'+(all-met)+'</div><div class="m-lab">未达标</div></div>'
          + '</div></div>';

        // 每人明细卡
        rows.forEach(function(r){
          var isPos = (r.commission||0) >= 0;
          var commColor = isPos ? '#34c759' : '#ff3b30';
          var commSign = isPos ? '' : '-';
          var episodes = r.episodes || 0;
          var quota = r.quota || 0;
          // 进度条百分比（集数/基准）
          var pct = quota>0 ? Math.min(100, Math.round(episodes/quota*100)) : (episodes>0?100:0);
          var barColor = r.is_complete ? '#34c759' : '#ff9500';
          // 头像首字
          var avatar = String(r.name||'?').charAt(0);
          // 标签
          var tags = [];
          tags.push('<span class="m-ed-tag">集数 <b>'+episodes+'</b></span>');
          if(quota) tags.push('<span class="m-ed-tag">基准 <b>'+quota+'</b></span>');
          tags.push(r.is_complete ? '<span class="m-ed-tag ok">✔ 达标</span>' : '<span class="m-ed-tag warn">✘ 未达标</span>');
          if(r.overtime_bonus) tags.push('<span class="m-ed-tag money">超额 +'+r.overtime_bonus+'</span>');
          if(r.shortage_penalty) tags.push('<span class="m-ed-tag warn">缺集 -'+r.shortage_penalty+'</span>');
          if(r.group_bonus) tags.push('<span class="m-ed-tag money2">组奖 +'+r.group_bonus+'</span>');

          h2 += '<div class="m-ed-card">'
            + '<div class="m-ed-head">'
            + '<div class="m-ed-avatar">'+escHtml(avatar)+'</div>'
            + '<div class="m-ed-info"><div class="m-ed-name">'+escHtml(r.name)+'</div>'
            + (r.role?'<div class="m-ed-role">'+escHtml(r.role)+'</div>':'')
            + '</div>'
            + '<div class="m-ed-comm"><div class="m-ed-comm-val" style="color:'+commColor+'">'+commSign+'¥'+Math.abs(r.commission||0)+'</div>'
            + '<div class="m-ed-comm-lab">提成</div></div>'
            + '</div>'
            + '<div class="m-ed-bar">'
            + '<div class="m-ed-bar-track"><div class="m-ed-bar-fill" style="width:'+pct+'%;background:'+barColor+'"></div></div>'
            + '<div class="m-ed-bar-text">'+episodes+'/'+quota+' 集</div>'
            + '</div>'
            + '<div class="m-ed-tags">'+tags.join('')+'</div>'
            + '</div>';
        });
        h2 += '</div>';
        var tmp = document.createElement('div');
        tmp.innerHTML = h2;
        // 追加全部子节点（h2 含汇总卡 + 多个剪辑师卡片，不能只取 firstChild）
        while(tmp.firstChild) content.appendChild(tmp.firstChild);
      }).catch(function(){});
    },

    // 当月提成表（复用 /api/commission/monthly）
    _renderCommission: function(content){
      var self = this;
      api('GET','/api/commission/monthly').then(function(d){
        if(!d || !d.ok || !d.rows) return;
        var rows = d.rows || [];
        var summary = d.summary || {};
        var html = '<div class="m-section"><h4>💰 提成/绩效（'+escHtml(d.month||'')+'）</h4>'
          + '<div class="m-row"><span class="m-k">总提成</span><span class="m-v" style="color:#af52de;font-weight:700">¥'+(summary.total_commission||0)+'</span></div>'
          + '<div class="m-row"><span class="m-k">达标</span><span class="m-v">'+(summary.met_quota||0)+'/'+(summary.total_people||0)+'</span></div>'
          + '<div class="m-row"><span class="m-k">总集数</span><span class="m-v">'+(summary.total_episodes||0)+'</span></div>'
          + '</div>';
        // 每人明细（与桌面月度报告对齐全部列）
        rows.forEach(function(r){
          var color = (r.commission||0) >= 0 ? '#0071e3' : '#c5221f';
          var daBiao = r.is_complete ? '<span style="color:#34c759">✔ 达标</span>' : '<span style="color:#ff3b30">✘ 未达标</span>';
          var detail = [];
          detail.push('集数 <b>'+(r.episodes||0)+'</b>');
          if(r.quota) detail.push('基准 <b>'+(r.quota)+'</b>');
          if(r.overtime_bonus) detail.push('超额 <span style="color:#34c759">+'+r.overtime_bonus+'</span>');
          if(r.shortage_penalty) detail.push('缺集扣 <span style="color:#ff3b30">-'+r.shortage_penalty+'</span>');
          if(r.group_bonus) detail.push('组奖 +'+r.group_bonus);
          html += '<div style="background:#fff;border-radius:10px;padding:10px 12px;margin-bottom:8px;box-shadow:0 1px 3px rgba(0,0,0,.04)">'
            + '<div style="display:flex;justify-content:space-between;align-items:center">'
            + '<span style="font-size:14px;font-weight:600">'+escHtml(r.name)
            + (r.role?' <span style="font-size:10px;color:#86868b;font-weight:400">'+escHtml(r.role)+'</span>':'')
            + '</span>'
            + '<span style="font-weight:700;color:'+color+'">¥'+(r.commission||0)+'</span>'
            + '</div>'
            + '<div style="font-size:11px;color:#86868b;margin-top:6px">'+detail.join(' · ')+'</div>'
            + '<div style="font-size:10px;color:#86868b;margin-top:3px">'+daBiao+'</div>'
            + '</div>';
        });
        // 追加到内容末尾
        var tmp = document.createElement('div');
        tmp.innerHTML = html;
        while(tmp.firstChild) content.appendChild(tmp.firstChild);
      }).catch(function(){});
    },

    /* ---------- 我的 Tab ---------- */
    renderMine: function(content){
      var html = '<div class="m-section"><h4>关于</h4>'
        + '<div class="m-row"><span class="m-k">视频工作台</span><span class="m-v">手机版</span></div>'
        + '<div class="m-row"><span class="m-k">项目总数</span><span class="m-v">'+this._data.projects.length+'</span></div>'
        + '</div>'
        + '<div style="margin-top:16px"><button class="m-act ghost" style="width:100%" onclick="WB.mobile.refresh()">🔄 刷新数据</button></div>';
      content.innerHTML = html;
    },

    refresh: function(){ this.load(); },

    // 顶部刷新按钮
    openScan: function(){
      if(typeof scanProjects === 'function'){ scanProjects(); }
      else { toast('扫描不可用','warning'); }
    },
    openNotifications: function(){
      if(typeof openNotifications === 'function'){ openNotifications(); }
      else toast('通知不可用','warning');
    },

    renderError: function(msg){
      var content = document.getElementById('m-content');
      if(content) content.innerHTML = '<div class="m-empty">'+escHtml(msg)+'</div>';
    },

    /* ============ 手机端分集 Tab ============ */
    renderFenji: function(content){
      var self = this;
      var fj = this._fj;
      var projects = this._data.projects;
      // 项目搜索过滤
      var fjq = (this._fjSearch||'').toLowerCase();
      var filtered = projects.filter(function(p){
        if(!fjq) return true;
        return String(p.name||'').toLowerCase().indexOf(fjq) >= 0;
      });
      var html = '<div class="m-section"><h4>📑 分集分配</h4>'
        // 项目选择器：点击弹出项目列表
        + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">'
        + '<div id="m-fj-project-display" style="flex:1;padding:12px;border:1px solid #e5e5ea;border-radius:12px;font-size:14px;background:#fff;cursor:pointer;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" onclick="WB.mobile.openFjProjectPicker()">'
        + (fj.project ? escHtml(fj.project) : '<span style="color:#86868b">— 点击选择项目 —</span>')
        + '</div></div>'
        + '<div class="m-row"><span class="m-k">总集数</span><span class="m-v"><input id="m-fj-total" type="number" value="'+(fj.total||'')+'" style="width:80px;padding:6px;border:1px solid #e5e5ea;border-radius:8px;text-align:right" oninput="WB.mobile.fjSetTotal(this.value)"></span></div>'
        + '</div>';
      // 人员模板区
      html += '<div class="m-section"><h4>👥 人员模板</h4>'
        + '<div class="m-filter" style="margin-bottom:8px"><select id="m-fj-tpl" onchange="WB.mobile.fjApplyTpl(this.value)">'
        + '<option value="">— 选择模板 —</option>'
        + '</select></div>'
        + '<div class="m-card-actions">'
        + '<button class="m-act ghost" style="flex:1" onclick="WB.mobile.fjSaveTpl()">💾 存为模板</button>'
        + '<button class="m-act danger" style="flex:1" onclick="WB.mobile.fjDelTpl()">🗑 删除模板</button>'
        + '</div></div>';
      html += '<div class="m-section"><h4>选择剪辑师</h4><div id="m-fj-persons"><div style="color:#86868b;font-size:13px">加载剪辑师...</div></div></div>';
      html += '<div class="m-section"><h4>操作</h4><div class="m-card-actions">'
        + '<button class="m-act primary" onclick="WB.mobile.fjAssign()">⚡ 分配</button>'
        + '<button class="m-act ghost" onclick="WB.mobile.fjSave()">💾 保存</button>'
        + '<button class="m-act ghost" onclick="WB.mobile.fjCopy()">📋 复制</button>'
        + '<button class="m-act warn" onclick="WB.mobile.fjSync()">🔄 同步</button>'
        + '</div></div>';
      html += '<div class="m-section"><h4>分配结果</h4><div id="m-fj-result">'+this._fjResultHTML()+'</div></div>';
      content.innerHTML = html;
      this.fjLoadPersons();
      this.fjLoadTpls();
    },

    // 分集项目搜索（只更新下拉，不重建搜索框）
    // 打开项目选择弹窗（半屏列表 + 搜索）
    openFjProjectPicker: function(){
      var self = this;
      // 复用 m-detail-root 做全屏选择器
      var html = '<div class="m-detail" id="m-detail">'
        + '<div class="m-detail-bar"><button class="m-back" onclick="WB.mobile.closeDetail()">✕</button><div class="m-dt">选择项目</div></div>'
        + '<div class="m-detail-body">'
        + '<div class="m-filter" style="margin-bottom:10px"><input type="text" id="m-fj-picker-search" placeholder="🔍 搜索项目..." oninput="WB.mobile.fjPickerSearch(this.value)"></div>'
        + '<div id="m-fj-picker-list">加载中...</div>'
        + '</div></div>';
      document.getElementById('m-detail-root').innerHTML = html;
      this._bindSwipeBack();
      this.fjPickerSearch('');
      // 聚焦搜索框
      var si = document.getElementById('m-fj-picker-search');
      if(si) setTimeout(function(){ si.focus(); }, 100);
    },

    // 项目选择弹窗内搜索
    fjPickerSearch: function(v){
      var list = document.getElementById('m-fj-picker-list');
      if(!list) return;
      var self = this;
      var q = (v||'').toLowerCase();
      var filtered = this._data.projects.filter(function(p){
        if(!q) return true;
        return String(p.name||'').toLowerCase().indexOf(q) >= 0;
      });
      if(!filtered.length){
        list.innerHTML = '<div class="m-empty">没有匹配的项目</div>';
        return;
      }
      list.innerHTML = filtered.map(function(p){
        var pn = String(p.name||'').replace(/'/g,"\\'");
        var sel = (p.name === self._fj.project) ? ' style="background:#e8f4fd"' : '';
        return '<div style="padding:12px 4px;border-bottom:1px solid #f0f0f0;font-size:14px;cursor:pointer;word-break:break-word"'+sel
          + ' onclick="WB.mobile.fjPickProject(\''+pn+'\')">'
          + escHtml(p.name)
          + (p.custom_status?' <span style="font-size:10px;color:#86868b">['+escHtml(p.custom_status)+']</span>':'')
          + '</div>';
      }).join('');
    },

    // 选中项目
    fjPickProject: function(name){
      this._fj.project = name || '';
      this._fj.total = 70;
      this._fj.ranges = {};
      var p = this._findProject(name);
      if(p && p.total_episodes) this._fj.total = p.total_episodes;
      this.closeDetail();
      this.render();
    },

    _fjResultHTML: function(){
      var ranges = this._fj.ranges || {};
      var names = Object.keys(ranges);
      if(!names.length) return '<div style="color:#86868b;font-size:13px">尚未分配</div>';
      var self = this;
      return names.map(function(n){
        var pn = String(n).replace(/'/g,"\\'");
        return '<div class="m-row"><span class="m-k">'+escHtml(n)+'</span>'
          + '<span class="m-v"><input type="text" value="'+escHtml(ranges[n])+'" '
          + 'oninput="WB.mobile.fjUpdateRange(\''+pn+'\',this.value)" '
          + 'style="width:110px;padding:6px;border:1px solid #e5e5ea;border-radius:8px;text-align:right;font-size:13px" '
          + 'placeholder="如 1-10 或 1-5,11-15"></span></div>';
      }).join('');
    },

    // 更新某个剪辑师的分集范围（支持逗号分隔多段，如 "1-5,11-15"）
    fjUpdateRange: function(name, value){
      if(!this._fj.ranges) this._fj.ranges = {};
      this._fj.ranges[name] = value;
    },

    // 解析 "1-5,11-15" 等多段范围为 {集号: 剪辑师}（供保存用）
    _parseRangeToAssign: function(rangeStr, person){
      var assign = {};
      var segs = String(rangeStr||'').split(',');
      segs.forEach(function(seg){
        seg = seg.trim();
        if(!seg) return;
        var parts = seg.split('-');
        var start = parseInt(parts[0]);
        var end = parseInt(parts[1] || parts[0]);
        if(isNaN(start)) return;
        if(isNaN(end)) end = start;
        for(var ep=start; ep<=end; ep++) assign[ep] = person;
      });
      return assign;
    },

    fjSelectProject: function(name){
      this._fj.project = name || '';
      this._fj.total = 70;
      this._fj.ranges = {};
      var p = this._findProject(name);
      if(p && p.total_episodes) this._fj.total = p.total_episodes;
      this.render();
    },

    fjSetTotal: function(v){ this._fj.total = parseInt(v) || 70; },

    // 加载人员模板到下拉
    async fjLoadTpls(){
      var self = this;
      try{
        var d = await api('GET','/api/fenji/person_templates');
        var tpls = (d && d.templates) || {};
        var sel = document.getElementById('m-fj-tpl');
        if(!sel) return;
        var names = Object.keys(tpls);
        sel.innerHTML = '<option value="">— 选择模板 —</option>'
          + names.map(function(n){ return '<option value="'+escHtml(n)+'">'+escHtml(n)+' ('+(tpls[n]||[]).length+'人)</option>'; }).join('');
        self._fjTpls = tpls;
      }catch(e){}
    },

    // 应用模板：勾选模板中的人员
    fjApplyTpl: function(name){
      var tpls = this._fjTpls || {};
      var persons = tpls[name] || [];
      if(!persons.length){ toast('模板为空','warning'); return; }
      this._fj.selected = persons.slice();
      var el = document.getElementById('m-fj-persons');
      var fj = this._fj;
      if(el && this._fjPersons){
        el.innerHTML = this._fjPersons.map(function(n){
          var checked = fj.selected.indexOf(n)>=0;
          return '<div class="m-todo-item"><div class="m-td-check'+(checked?' done':'')+'" onclick="WB.mobile.fjTogglePerson(\''+String(n).replace(/'/g,"\\'")+'\')">'+(checked?'✓':'')+'</div><div class="m-td-text">'+escHtml(n)+'</div></div>';
        }).join('');
      }
      toast('✅ 已应用模板：'+persons.length+' 人','success');
    },

    // 保存当前勾选为模板
    async fjSaveTpl(){
      var selected = this._fj.selected || [];
      if(!selected.length){ toast('请先选择剪辑师','warning'); return; }
      var name = window.prompt('模板名称：', '我的模板');
      if(!name) return;
      try{
        var d = await api('POST','/api/fenji/person_templates', { name:name.trim(), persons:selected });
        if(d && d.ok){ toast('✅ 模板已保存','success'); this.fjLoadTpls(); }
        else toast((d&&d.msg)||'保存失败','error');
      }catch(e){ toast('保存失败: '+e.message,'error'); }
    },

    // 删除选中模板
    async fjDelTpl(){
      var sel = document.getElementById('m-fj-tpl');
      var name = sel ? sel.value : '';
      if(!name){ toast('请先选择要删除的模板','warning'); return; }
      if(!confirm('确认删除模板「'+name+'」？')) return;
      try{
        var d = await api('DELETE','/api/fenji/person_templates', { name:name });
        if(d && d.ok){ toast('✅ 模板已删除','success'); this.fjLoadTpls(); }
        else toast((d&&d.msg)||'删除失败','error');
      }catch(e){ toast('删除失败: '+e.message,'error'); }
    },

    async fjLoadPersons(){
      var self = this;
      try{
        var d = await api('GET','/api/commission/monthly');
        var names = (d && d.rows || []).map(function(r){ return r.name; });
        try{
          var t = await api('GET','/api/team/members');
          (t && t.members||[]).forEach(function(m){ if(m.name && names.indexOf(m.name)<0) names.push(m.name); });
        }catch(_){}
        self._fjPersons = names;
        var el = document.getElementById('m-fj-persons');
        if(el && names.length){
          var fj = self._fj;
          el.innerHTML = names.map(function(n){
            var checked = fj.selected.indexOf(n)>=0;
            return '<div class="m-todo-item"><div class="m-td-check'+(checked?' done':'')+'" onclick="WB.mobile.fjTogglePerson(\''+String(n).replace(/'/g,"\\'")+'\')">'+(checked?'✓':'')+'</div><div class="m-td-text">'+escHtml(n)+'</div></div>';
          }).join('');
        }
      }catch(e){
        var el2 = document.getElementById('m-fj-persons');
        if(el2) el2.innerHTML = '<div style="color:#86868b;font-size:13px">加载失败</div>';
      }
    },

    fjTogglePerson: function(name){
      var idx = this._fj.selected.indexOf(name);
      if(idx>=0) this._fj.selected.splice(idx,1);
      else this._fj.selected.push(name);
      var el = document.getElementById('m-fj-persons');
      var fj = this._fj;
      if(el && this._fjPersons){
        el.innerHTML = this._fjPersons.map(function(n){
          var checked = fj.selected.indexOf(n)>=0;
          return '<div class="m-todo-item"><div class="m-td-check'+(checked?' done':'')+'" onclick="WB.mobile.fjTogglePerson(\''+String(n).replace(/'/g,"\\'")+'\')">'+(checked?'✓':'')+'</div><div class="m-td-text">'+escHtml(n)+'</div></div>';
        }).join('');
      }
    },

    fjAssign: function(){
      var total = this._fj.total;
      var selected = this._fj.selected;
      if(total<=0){ toast('请设置总集数','warning'); return; }
      if(!selected.length){ toast('请选择剪辑师','warning'); return; }
      var persons = selected.slice();
      var segLen = total;
      var per = Math.floor(segLen/persons.length);
      var rem = segLen % persons.length;
      var cur = 1;
      var ranges = {};
      persons.forEach(function(p, i){
        var sz = per + (i < rem ? 1 : 0);
        ranges[p] = cur + '-' + (cur+sz-1);
        cur += sz;
      });
      this._fj.ranges = ranges;
      var el = document.getElementById('m-fj-result');
      if(el) el.innerHTML = this._fjResultHTML();
      toast('⚡ 分配完成','success');
    },

    async fjSave(){
      var name = this._fj.project;
      var total = this._fj.total;
      var ranges = this._fj.ranges;
      if(!name){ toast('请选择项目','warning'); return; }
      if(!total || !Object.keys(ranges).length){ toast('请先分配','warning'); return; }
      var self = this;
      var assign = {};
      Object.keys(ranges).forEach(function(p){
        // 支持逗号分隔多段（如 "1-5,11-15"）
        var segAssign = self._parseRangeToAssign(ranges[p], p);
        Object.keys(segAssign).forEach(function(ep){ assign[ep] = segAssign[ep]; });
      });
      if(!Object.keys(assign).length){ toast('分集范围格式有误，请检查','warning'); return; }
      try{
        var d = await api('POST','/api/bulk/import_episodes', { project_name:name, total_episodes:total, assign:assign });
        if(d && d.ok){ toast('✅ 分集已保存 ('+(d.count||Object.keys(assign).length)+' 集)','success'); }
        else toast((d&&d.message)||'保存失败','error');
      }catch(e){ toast('保存失败: '+e.message,'error'); }
    },

    fjCopy: function(){
      var name = this._fj.project;
      var ranges = this._fj.ranges;
      var names = Object.keys(ranges);
      if(!names.length){ toast('没有可复制的结果','warning'); return; }
      var text = (name ? ('项目：'+name+'\n') : '') + names.map(function(n){ return n + ':' + ranges[n]; }).join('\n');
      if(navigator.clipboard && navigator.clipboard.writeText){
        navigator.clipboard.writeText(text).then(function(){ toast('✅ 已复制分集结果','success'); });
      } else {
        var ta = document.createElement('textarea');
        ta.value = text; document.body.appendChild(ta); ta.select();
        document.execCommand('copy'); document.body.removeChild(ta);
        toast('✅ 已复制分集结果','success');
      }
    },

    async fjSync(){
      if(!confirm('确认同步工作台吗？\n将把当前项目的分集数据同步到全工作台统计。\n\n确认继续？')) return;
      try{
        var d = await api('POST','/api/fenji/sync_episode_plan', {});
        if(d && d.ok){ toast('✅ '+(d.message||'同步完成'),'success'); }
        else toast((d&&d.message)||'同步失败','error');
      }catch(e){ toast('同步失败: '+e.message,'error'); }
    }
  };

  WB.mobile = mobile;
  // 初始化
  document.addEventListener('DOMContentLoaded', function(){ mobile.init(); });
  // 兜底：如果 DOMContentLoaded 已过，立即初始化
  if(document.readyState !== 'loading') mobile.init();

  // 交付流程顺序（分集→剪辑→审核→修改→交付→质检→已完成），未设置在前
  function _workflowOrder(status){
    var s = String(status||'').trim();
    if(!s) return -1;
    if(s.indexOf('分集')>=0) return 0;
    if(s.indexOf('剪辑')>=0) return 1;
    if(s.indexOf('审核')>=0) return 2;
    if(s.indexOf('修改')>=0) return 3;
    if(s.indexOf('交付')>=0) return 4;
    if(s.indexOf('质检')>=0) return 5;
    if(s.indexOf('完成')>=0) return 6;
    return -1;
  }

  window.WB = WB;
})();
