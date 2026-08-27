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
    // 数据 Tab 提成缓存（30 秒内不重复请求）
    _statsCache: { data: null, ts: 0 },

    // 是否处于手机模式：窄屏 + 触摸设备（或 WebView App）。
    // 避免桌面浏览器缩小窗口误入手机模式。
    isMobile: function(){
      if(window.innerWidth > MOBILE_BREAKPOINT) return false;
      if(window.__IS_APP__) return true;  // WebView 壳 App 注入的标志
      // 真移动设备：支持触摸（maxTouchPoints>0）
      return (typeof navigator.maxTouchPoints === 'number' && navigator.maxTouchPoints > 0)
        || /Android|iPhone|iPad|Mobile/i.test(navigator.userAgent || '');
    },

    // 初始化：检测宽度 + 监听变化
    init: function(){
      var self = this;
      this.applyMode();
      this._bindPullRefresh();
      this._bindSwipeActions();
      this._startNotifPolling();
      // 深色模式初始化（跟随系统/浅色/深色）
      this.applyTheme();
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

    // ---- 左滑快捷操作：事件委托绑定到内容区（卡片动态生成也生效） ----
    _bindSwipeActions: function(){
      var self = this;
      var el = document.getElementById('m-content');
      if(!el) return;
      var startX = 0, startY = 0, tracking = false, isHorizontal = null, swipeCard = null;

      el.addEventListener('touchstart', function(e){
        if(e.touches.length !== 1) return;
        var card = e.target.closest('.m-swipe-card');
        if(!card) return;
        startX = e.touches[0].clientX;
        startY = e.touches[0].clientY;
        swipeCard = card; // 记录起始卡片，避免 touchend 时 target 变化
        tracking = true;
        isHorizontal = null;
      }, { passive: true });

      el.addEventListener('touchmove', function(e){
        if(!tracking) return;
        var dx = e.touches[0].clientX - startX;
        var dy = e.touches[0].clientY - startY;
        // 判断滑动方向：横向为主才算横向
        if(isHorizontal === null && (Math.abs(dx) > 8 || Math.abs(dy) > 8)){
          isHorizontal = Math.abs(dx) > Math.abs(dy);
        }
        if(isHorizontal && swipeCard && Math.abs(dx) > 20){
          // 横向滑动时阻止纵向滚动，避免与下拉刷新冲突
          e.preventDefault();
        }
      }, { passive: false });

      el.addEventListener('touchend', function(e){
        if(!tracking) return;
        tracking = false;
        if(isHorizontal !== true || !swipeCard) return;
        var dx = e.changedTouches[0].clientX - startX;
        // 未同步项目用 swiped-single（左滑距离更小），否则用 swiped
        var single = swipeCard.getAttribute('data-sync-only') === '1';
        var openCls = single ? 'swiped-single' : 'swiped';
        // 左滑：露出操作区；右滑：收回
        if(dx < -50){
          self._closeAllSwipe();
          swipeCard.classList.add(openCls);
        } else if(dx > 50){
          swipeCard.classList.remove('swiped', 'swiped-single');
        }
        swipeCard = null;
      }, { passive: true });
    },

    // 关闭所有已滑开的卡片（点击其他地方/进详情前调用）
    _closeAllSwipe: function(){
      document.querySelectorAll('.m-swipe-card.swiped, .m-swipe-card.swiped-single').forEach(function(c){
        c.classList.remove('swiped', 'swiped-single');
      });
    },

    // 点击卡片：若已滑开则收回，否则进详情
    onCardTap: function(name){
      var card = document.querySelector('.m-swipe-card.swiped, .m-swipe-card.swiped-single');
      if(card){
        card.classList.remove('swiped', 'swiped-single');
        return; // 收回操作区，不进入详情
      }
      this.openDetail(name);
    },

    // 左滑快捷操作：改状态（弹出状态选择）
    swipeStatus: function(name){
      this._closeAllSwipe();
      var st = prompt('输入新状态（分集中/剪辑中/审核中/修改中/交付中/待交付/待质检/质检中/已完成）：', '');
      if(st === null) return;
      st = st.trim();
      if(!st) return;
      // 调用状态更新接口
      var self = this;
      api('POST','/api/project/'+encodeURIComponent(name)+'/custom_status', { custom_status: st }).then(function(d){
        if(d && d.ok){
          toast('✅ 状态已更新为 '+st, 'success');
          self._lastStatusChanged = name;   // 重排后高亮该项目
          self.load(); // 刷新列表
        }
        else { toast('❌ ' + ((d&&d.message)||'更新失败'), 'error'); }
      }).catch(function(e){ toast('❌ 更新失败: '+e.message, 'error'); });
    },

    // 左滑快捷操作：回传（打开成片预览以选择回传）
    swipeDeliver: function(name){
      this._closeAllSwipe();
      this.openChengPreview(name);
    },

    // 左滑快捷操作：缺集详情（打开项目详情，顶部即显示逐集缺集网格）
    swipeMissing: function(name){
      this._closeAllSwipe();
      this.openDetail(name);
    },

    // ---- 深色模式（system / light / dark）----
    applyTheme: function(){
      var mode = localStorage.getItem('wb_m_theme') || 'system';
      var app = document.getElementById('mobile-app');
      if(app){
        if(mode === 'dark' || mode === 'light'){
          app.setAttribute('data-theme', mode);
        } else {
          app.removeAttribute('data-theme'); // system：跟随系统 prefers-color-scheme
        }
      }
      this._themeMode = mode;
    },
    setTheme: function(mode){
      try{ localStorage.setItem('wb_m_theme', mode); }catch(_){}
      this.applyTheme();
      // 若在"我的"页，重渲染以更新按钮选中态
      if(this._curTab === 'mine'){
        var content = document.getElementById('m-content');
        if(content) this.renderMine(content);
      }
    },
    getTheme: function(){ return this._themeMode || 'system'; },

    // 下拉刷新手势：内容区顶部下拉超过阈值刷新当前页
    _bindPullRefresh: function(){
      var self = this;
      var el = document.getElementById('m-content');
      if(!el) return;
      var startY = 0, startX = 0, pulling = false, isScrollTop = true;
      el.addEventListener('touchstart', function(e){
        if(e.touches.length !== 1) return;
        // 只在滚动容器在顶部时允许下拉
        if(el.scrollTop <= 0){
          startY = e.touches[0].clientY;
          startX = e.touches[0].clientX;
          pulling = true;
        }
      }, { passive: true });
      el.addEventListener('touchmove', function(e){
        if(!pulling) return;
        var dy = e.touches[0].clientY - startY;
        var dx = Math.abs(e.touches[0].clientX - startX);
        // 下拉且横向位移不大（避免与左滑冲突）
        if(dy > 0 && dx < 30 && dy > 40){
          e.preventDefault();
        }
      }, { passive: false });
      el.addEventListener('touchend', function(e){
        if(!pulling) return;
        var dy = e.changedTouches[0].clientY - startY;
        var dx = Math.abs(e.changedTouches[0].clientX - startX);
        pulling = false;
        // 下拉超过 80px 且非横向滑动 → 刷新
        if(dy > 80 && dx < 30){
          self.refresh();
          toast('🔄 已刷新','info');
        }
      }, { passive: true });
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

    // 加载数据（用精简接口，大幅减小传输量，加快手机加载）
    async load(){
      // 数据未就绪时显示骨架屏
      if(!this._data.projects.length && this.isMobile()){
        this._renderSkeleton();
      }
      try{
        // 优先用手机端精简接口（只含卡片字段，约减小 5-10 倍）
        var d = await api('GET','/api/projects/mobile');
        if(!d || !d.ok){
          // 回退到完整接口
          d = await api('GET','/api/projects');
          d = d || {};
        }
        if(d && (d.sections || d.ok)){
          this._data.sections = d.sections || [];
          this._data.overview = d.overview_stats || null;
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
      // 顶部标题随 Tab 联动，明确当前所在页
      var title = document.getElementById('m-page-title');
      if(title){
        var titles = { home: '🎬 视频工作台', fenji: '📑 分集管理', stats: '📊 数据', mine: '👤 我的' };
        title.textContent = titles[tab] || '🎬 视频工作台';
      }
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
        // 默认折叠：除「组内进行中」外，其他分组折叠，且折叠时不渲染卡片 DOM（性能优化）
        var isGroupActive = sec.key === 'group_active';
        var secId = 'm-sec-' + String(sec.key||'').replace(/[^a-zA-Z0-9_]/g,'_');
        html += '<div style="font-size:13px;font-weight:700;color:var(--m-text-sec);margin:14px 2px 8px;display:flex;align-items:center;gap:6px;cursor:pointer" '
          + 'onclick="WB.mobile.toggleGroup(\''+secId+'\',\''+sec.key+'\',this)">'
          + '<span style="font-size:10px;color:var(--m-text-sec)">'+(isGroupActive?'▼':'▶')+'</span>'
          + escHtml(sec.name||'项目') + ' <span style="font-weight:400;font-size:11px">('+projects.length+')</span></div>';
        if(isGroupActive){
          // 组内进行中：直接渲染卡片
          html += '<div id="'+secId+'">';
          projects.forEach(function(p){ html += self._projectCard(p); });
          html += '</div>';
        } else {
          // 折叠部门：不渲染卡片 DOM，仅放空容器，展开时动态填充
          html += '<div id="'+secId+'" style="display:none" data-key="'+String(sec.key||'').replace(/[^a-zA-Z0-9_]/g,'_')+'" data-loaded="0"></div>';
        }
      });

      if(!html){
        html = '<div class="m-empty">📭 暂无项目</div>';
      }
      el.innerHTML = html;

      // 状态变更后重排：高亮刚修改状态的项目（若在首页列表）
      if(this._lastStatusChanged && this._curTab === 'home'){
        var _name = this._lastStatusChanged;
        this._lastStatusChanged = null;
        var self = this;
        setTimeout(function(){ self.highlightProject(_name); }, 120);
      }
    },

    // 定位并高亮项目卡片（状态变更后重排用；橙色脉冲动画）
    highlightProject: function(name){
      // 若该分组当前折叠，先展开
      var card = null;
      var cards = document.querySelectorAll('.m-swipe-card');
      for(var i=0;i<cards.length;i++){
        var tn = cards[i].querySelector('.m-card-name');
        if(tn && (tn.getAttribute('data-project-name') === name || tn.textContent === name)){
          card = cards[i];
          break;
        }
      }
      if(!card) return;
      // 滚动到卡片
      card.scrollIntoView({ behavior: 'smooth', block: 'center' });
      // 高亮动画
      card.classList.add('m-highlight');
      document.querySelectorAll('.m-swipe-card.m-highlight').forEach(function(c){ if(c!==card) c.classList.remove('m-highlight'); });
      setTimeout(function(){ card.classList.remove('m-highlight'); }, 3000);
    },

    // 展开/折叠部门分组；展开时按需渲染该部门卡片（懒加载，减少 DOM）
    toggleGroup: function(secId, key, titleEl){
      var box = document.getElementById(secId);
      if(!box) return;
      var isHidden = box.style.display === 'none';
      if(isHidden){
        box.style.display = '';
        // 未加载过则填充该部门卡片
        if(box.getAttribute('data-loaded') !== '1'){
          var q = (this._filter.q||'').toLowerCase();
          var sec = (this._data.sections||[]).find(function(s){ return s.key === key; });
          if(sec){
            var self = this;
            var projects = (sec.projects||[]).filter(function(p){
              if(q && String(p.name||'').toLowerCase().indexOf(q)<0) return false;
              if(self._filter.status && (p.custom_status||'')!==self._filter.status) return false;
              return true;
            });
            projects.sort(function(a,b){
              var ao = _workflowOrder(a.custom_status), bo = _workflowOrder(b.custom_status);
              if(ao!==bo) return ao-bo;
              return String(a.name||'').localeCompare(String(b.name||''));
            });
            var html = projects.map(function(p){ return self._projectCard(p); }).join('');
            box.innerHTML = html;
            box.setAttribute('data-loaded', '1');
          }
        }
        // 更新箭头
        var arrow = titleEl ? titleEl.querySelector('span') : null;
        if(arrow) arrow.textContent = '▼';
      } else {
        box.style.display = 'none';
        var arrow2 = titleEl ? titleEl.querySelector('span') : null;
        if(arrow2) arrow2.textContent = '▶';
      }
    },

    // 单个项目卡片（支持左滑露出快捷操作）
    _projectCard: function(p){
      var self = this;
      var st = p.custom_status || '';
      var total = p.total_episodes || 0;
      var cur = p.current_episodes || 0;
      var pct = total>0 ? Math.round(cur/total*100) : 0;
      var badge = this._statusBadge(st);
      var safeId = String(p.name||'').replace(/[^a-zA-Z0-9_]/g,'_');
      var progId = 'mprog-' + safeId;
      var nameAttr = String(p.name||'').replace(/'/g,"\\'");

      // 判断是否未同步项目（制作部有、组NAS没有）→ 左滑只显示"同步素材"
      var isUnsynced = p.on_group === false;
      var swipeActions = '';
      if(isUnsynced){
        // 未同步：只显示"同步素材"一个操作，且按钮更宽
        swipeActions = '<button class="sa-deliver sa-wide" onclick="WB.mobile.mobileSyncMaterial(\''+nameAttr+'\')"><span class="m-ico">📦</span>同步素材</button>';
      } else {
        // 已同步/组内：显示改状态/回传/缺集
        swipeActions = '<button class="sa-status" onclick="WB.mobile.swipeStatus(\''+nameAttr+'\')"><span class="m-ico">📋</span>改状态</button>'
          + '<button class="sa-deliver" onclick="WB.mobile.swipeDeliver(\''+nameAttr+'\')"><span class="m-ico">📤</span>回传</button>'
          + '<button class="sa-folder" onclick="WB.mobile.swipeMissing(\''+nameAttr+'\')"><span class="m-ico">🧩</span>缺集</button>';
      }

      // 左滑容器：下层操作区 + 上层卡片内容
      var html = '<div class="m-swipe-wrap">'
        // 下层：快捷操作按钮
        + '<div class="m-swipe-actions">'
        + swipeActions
        + '</div>'
        // 上层：卡片内容
        + '<div class="m-swipe-card"'+(isUnsynced?' data-sync-only="1"':'')+' data-swipe-name="'+nameAttr+'" onclick="WB.mobile.onCardTap(\''+nameAttr+'\')">'
        + '<div class="m-card-head">'
          + '<div class="m-card-name" data-project-name="'+nameAttr+'">'+escHtml(p.name)+'</div>'
          + '<span class="m-card-badge" style="background:'+badge.bg+';color:'+badge.fg+'">'+escHtml(badge.text)+'</span>'
        + '</div>'
        + '<div class="m-card-meta">'
          + (p.department?'<span class="m-chip">'+escHtml(p.department)+'</span>':'')
          + (p.project_month?'<span class="m-chip">📅 '+escHtml(p.project_month)+'</span>':'')
          + '<span class="m-chip">'+cur+'/'+total+' 集</span>'
          + (p.due_date?'<span class="m-chip">⏰ '+escHtml(p.due_date)+'</span>':'')
        + '</div>'
        + (total>0 ? '<div class="m-prog"><div class="m-prog-bar"><div class="m-prog-fill '+(pct<50?'warn':'')+'" id="'+progId+'" style="width:'+pct+'%"></div></div><div class="m-prog-text"><span>输出进度</span><span>'+pct+'%</span></div></div>' : '')
        // 卡片操作按钮：分集 / 详情（与桌面端一致）
        + '<div class="m-card-actions" style="margin-top:8px">'
        + '<button class="m-act ghost" style="flex:1" onclick="event.stopPropagation();WB.mobile.goFenji(\''+nameAttr+'\')">📑 分集</button>'
        + '<button class="m-act ghost" style="flex:1" onclick="event.stopPropagation();WB.mobile.openDetail(\''+nameAttr+'\')">📋 详情</button>'
        + '</div>'
        + '</div>'
        + '</div>';
      return html;
    },

    // 卡片"分集"按钮：切到分集 Tab 并选中该项目
    goFenji: function(name){
      var self = this;
      this._closeAllSwipe();
      // 切换到分集 Tab
      this._curTab = 'fenji';
      document.querySelectorAll('.m-tabbar .m-tab').forEach(function(b){
        b.classList.toggle('active', b.getAttribute('data-mtab')==='fenji');
      });
      var title = document.getElementById('m-page-title');
      if(title) title.textContent = '📑 分集管理';
      // 设置选中项目并渲染分集页
      this._fj.project = name || '';
      var p = this._findProject(name);
      if(p && p.total_episodes) this._fj.total = p.total_episodes;
      var content = document.getElementById('m-content');
      if(content) this.renderFenji(content);
    },

    // 状态徽标颜色
    _statusBadge: function(st){
      st = String(st||'');
      if(!st) return { bg:'#f2f3f5', fg:'#86868b', text:'未设置' };
      if(st.indexOf('完成')>=0) return { bg:'#d1f4e0', fg:'#1d8f4c', text:st };
      if(st.indexOf('待提交')>=0) return { bg:'#e8f2fd', fg:'#0071e3', text:st };   // 待提交审核
      if(st.indexOf('质检')>=0) return { bg:'#e8f2fd', fg:'#0071e3', text:st };
      if(st.indexOf('交付')>=0) return { bg:'#fff3cd', fg:'#856404', text:st };
      if(st.indexOf('修改')>=0) return { bg:'#ffe8d9', fg:'#c2410c', text:st };
      if(st.indexOf('审中')>=0 || st.indexOf('审核')>=0) return { bg:'#f3e8ff', fg:'#9333ea', text:st };  // 审核中/N审中
      if(st.indexOf('剪辑')>=0) return { bg:'#fde8e8', fg:'#dc2626', text:st };
      if(st.indexOf('分集')>=0) return { bg:'#f2f3f5', fg:'#4a4a4a', text:st };
      return { bg:'#f2f3f5', fg:'#4a4a4a', text:st };
    },

    // 搜索（只更新列表，不重建输入框，避免焦点丢失）
    // 300ms 防抖：输入停顿后才刷新，避免每敲一个字符全量渲染导致卡顿
    setSearch: function(v){
      var self = this;
      this._filter.q = v;
      if(this._searchTimer) clearTimeout(this._searchTimer);
      this._searchTimer = setTimeout(function(){ self._renderHomeList(); }, 300);
    },
    // 状态筛选（立即生效）
    setStatus: function(v){ this._filter.status = v; this._renderHomeList(); },

    /* ---------- 项目详情全屏弹窗 ---------- */
    openDetail: function(name){
      var p = this._findProject(name);
      if(!p){ toast('项目不存在','warning'); return; }
      var self = this;
      // 精简接口不含 group_path/production_path（同步/打开目录需要），进入详情时异步补全
      if(!p.group_path && !p.production_path){
        api('GET','/api/project/'+encodeURIComponent(name)).then(function(d){
          var full = d && (d.project || d);
          if(full && typeof full === 'object'){
            ['group_path','production_path','source_root','episode_plan','on_group','has_production_match'].forEach(function(k){
              if(full[k] !== undefined) p[k] = full[k];
            });
          }
        }).catch(function(){});
      }
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
          + ['','分集中','剪辑中','待提交审核','审核中','修改中','二审中','三审中','交付中','待交付','待质检','质检中','已完成'].map(function(s){
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
          // 项目时间线
          + '<div class="m-section"><h4>⏱ 项目时间线</h4><div id="m-timeline">加载中...</div></div>'
        + '</div></div>';
      document.getElementById('m-detail-root').innerHTML = html;
      this._bindSwipeBack();
      // 加载该项目的缺集信息
      this.loadEpisodeInfo(name);
      // 加载该项目的待办
      this.loadTodo(name);
      // 加载项目时间线（状态变更/事件历史）
      this.loadMobileTimeline(name);
      // 绑定左滑返回
      this._bindSwipeBack();
      // 更新状态变化时不保存，点"保存状态"才保存
    },

    // 加载项目时间线（复用 /api/project/<name>/timeline，展示状态变更/事件历史）
    async loadMobileTimeline(name){
      var box = document.getElementById('m-timeline');
      if(!box) return;
      try{
        var d = await api('GET','/api/project/'+encodeURIComponent(name)+'/timeline');
        var events = (d && d.events) || [];
        if(!events.length){
          box.innerHTML = '<div style="color:var(--m-text-sec);font-size:13px;padding:6px 0">暂无事件</div>';
          return;
        }
        // 取最近 30 条，按时间倒序（最新在上）
        var sorted = events.slice().sort(function(a,b){ return String(b.time||'').localeCompare(String(a.time||'')); }).slice(0,30);
        var html = '<div style="max-height:280px;overflow-y:auto">';
        sorted.forEach(function(ev){
          var color = ev.color || '#0071e3';
          html += '<div style="display:flex;gap:8px;padding:6px 0;position:relative;padding-left:14px">'
            + '<span style="position:absolute;left:0;top:10px;width:8px;height:8px;border-radius:50%;background:'+color+'"></span>'
            + '<div style="flex:1;min-width:0">'
            + '<div style="font-size:12px;font-weight:600;color:var(--m-text)">'+escHtml(ev.title||'')+'</div>'
            + '<div style="font-size:11px;color:var(--m-text-sec);word-break:break-all">'+escHtml(ev.detail||'')+'</div>'
            + '<div style="font-size:10px;color:var(--m-text-ter);opacity:.8">'+escHtml(ev.time||'')+'</div>'
            + '</div></div>';
        });
        html += '</div>';
        box.innerHTML = html;
      }catch(e){
        box.innerHTML = '<div style="color:var(--m-text-sec);font-size:13px;padding:6px 0">时间线加载失败</div>';
      }
    },

    // 加载缺集信息（/episodes_status）—— 与桌面端一致，显示逐集网格
    async loadEpisodeInfo(name){
      var box = document.getElementById('m-epinfo');
      if(!box) return;
      try{
        var d = await api('GET','/api/project/'+encodeURIComponent(name)+'/episodes_status');
        if(!d || !d.ok){ box.innerHTML = '<div style="color:var(--m-text-sec);font-size:13px">无法获取缺集信息</div>'; return; }
        var total = d.total || 0;
        var present = d.present || [];
        var missing = d.missing || [];
        var editorPlan = d.editor_plan || {};
        var cur = d.current_count || 0;
        var pct = total>0 ? Math.round(cur/total*100) : 0;

        var html = '<div class="m-prog"><div class="m-prog-bar"><div class="m-prog-fill '+(pct<50?'warn':'')+'" style="width:'+pct+'%"></div></div>'
          + '<div class="m-prog-text"><span>已输出 '+cur+'/'+total+' 集</span><span>'+pct+'%</span></div></div>';

        // 逐集网格（与桌面端一致）：每集一格，已输出绿 / 缺失红，标注剪辑师
        var presentSet = {};
        present.forEach(function(n){ presentSet[n]=true; });
        if(total>0){
          var cells = '';
          for(var i=1;i<=total;i++){
            var isPresent = !!presentSet[i];
            var creator = editorPlan[String(i)] || editorPlan[i] || '';
            var cellCls = isPresent ? 'm-ep-cell present' : 'm-ep-cell missing';
            var bg = isPresent ? '#34c759' : '#ff3b30';
            cells += '<div class="'+cellCls+'" title="'+i+'集'+(isPresent?' 已输出':' 未输出')+(creator?' · '+creator:'')+'">'
              + '<div class="m-ep-cell-num">'+i+'</div>'
              + (creator ? '<div class="m-ep-cell-ed">'+escHtml(creator)+'</div>' : '')
              + '</div>';
          }
          html += '<div style="margin-top:8px">'
            + '<div style="font-size:11px;color:var(--m-text-sec);margin-bottom:6px;display:flex;justify-content:space-between">'
            + '<span>📺 '+total+' 集 · 已输出 <b style="color:#34c759">'+present.length+'</b> · 缺 <b style="color:#ff3b30">'+missing.length+'</b></span>'
            + '</div>'
            + '<div class="m-ep-grid">'+cells+'</div>'
            + '</div>';
        } else {
          html += '<div style="font-size:12px;color:var(--m-text-sec);margin-top:6px">未设总集数，无法统计缺集</div>';
        }
        box.innerHTML = html;
      }catch(e){
        box.innerHTML = '<div style="color:var(--m-text-sec);font-size:13px">缺集信息加载失败</div>';
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
      var isFenji = st.indexOf('分集') >= 0;
      var isJianji = st.indexOf('剪辑') >= 0;
      var isDaiTijiao = st.indexOf('待提交') >= 0;
      var isShenhe = st.indexOf('审核') >= 0 || st.indexOf('审中') >= 0;
      var isXiugai = st.indexOf('修改') >= 0;
      var isZhiJian = st.indexOf('质检') >= 0;
      // 分集中：分集 + 一键同步到工作台
      if(isFenji){
        html += '<button class="m-act primary" onclick="WB.mobile.goFenji(\''+pname+'\')">📋 分集</button>'
          + '<button class="m-act success" onclick="WB.mobile.mSyncToWorkbench(\''+pname+'\')">⚡ 同步到工作台</button>';
      }
      // 待提交审核：进入审核
      if(isDaiTijiao){
        html += '<button class="m-act primary" onclick="WB.mobile.mSubmitReview(\''+pname+'\')">📤 进入审核</button>';
      }
      // 质检中/待质检：质检审批入口
      if(isZhiJian){
        html += '<button class="m-act primary" onclick="WB.mobile.openQAApproval(\''+pname+'\')">🔍 质检审批</button>';
      }
      // 剪辑中：刷新进度 + 成片预览
      if(isJianji){
        html += '<button class="m-act primary" onclick="WB.mobile.refreshDetailProgress(\''+pname+'\')">🔄 刷新进度</button>'
          + '<button class="m-act success" onclick="WB.mobile.openChengPreview(\''+pname+'\')">🎬 成片</button>';
      }
      // 审核中/N审中：分秒帧 + 标记修改
      if(isShenhe){
        html += '<button class="m-act primary" onclick="WB.mobile.openFenmiaozhenBtn(\''+pname+'\')">🔗 分秒帧</button>'
          + '<button class="m-act warn" onclick="WB.mobile.mMarkRevision(\''+pname+'\')">✏️ 标记修改</button>';
      }
      // 修改中：修改预览 + 修改完毕（提交下一轮审核）+ 终审完毕（进入待交付）
      if(isXiugai){
        html += '<button class="m-act primary" onclick="WB.mobile.openFenmiaozhenBtn(\''+pname+'\')">🔗 分秒帧</button>'
          + '<button class="m-act warn" onclick="WB.mobile.openRevisePreview(\''+pname+'\')">📝 修改预览</button>'
          + '<button class="m-act ghost" onclick="WB.mobile.mSubmitRevision(\''+pname+'\')">✅ 修改完毕</button>'
          + '<button class="m-act success" onclick="WB.mobile.mFinalReviewComplete(\''+pname+'\')">🏁 终审完毕</button>';
      }
      // 通用：保存状态
      html += '<button class="m-act ghost" onclick="WB.mobile.saveStatus(\''+pname+'\')">保存状态</button>';
      // 同步素材：仅当项目"制作部有但组NAS没有"（未同步，on_group=false）时显示，与电脑端一致
      if(p.on_group === false){
        html += '<button class="m-act primary" onclick="WB.mobile.mobileSyncMaterial(\''+pname+'\')">📦 同步素材</button>';
      }
      html += '</div></div>';
      return html;
    },

    // 移动端专用同步素材（与电脑端一致：先查是否已在组盘 → 确认 → 同步 → 轮询进度）
    async mobileSyncMaterial(name){
      var self = this;
      var pname = String(name||'').replace(/'/g,"\\'");
      // 先检查是否已在组盘（用户可能手动复制了）
      try{
        var check = await api('POST','/api/project/'+encodeURIComponent(name)+'/check_on_group');
        if(check && check.on_group){
          toast('✅ "'+name+'" 已在组盘上，状态已刷新','success');
          this.load();
          return;
        }
      }catch(_){}
      if(!confirm('确认要将「'+name+'」从制作部 NAS 同步到组内 NAS 吗？\n（首次同步可能耗时较长）')) return;
      toast('📤 正在同步 '+name+'...','info');
      // 打开同步进度面板
      var html = '<div class="m-detail" id="m-detail">'
        + '<div class="m-detail-bar"><button class="m-back" onclick="WB.mobile.closeDetail()">✕</button><div class="m-dt">📦 同步素材</div></div>'
        + '<div class="m-detail-body">'
        + '<div style="text-align:center;padding:20px 0">'
        + '<div style="font-size:13px;color:var(--m-text-sec)" id="msync-status">正在同步 '+escHtml(name)+'...</div>'
        + '<div style="background:var(--m-chip-bg);border-radius:8px;height:12px;margin:14px 8px;overflow:hidden">'
        + '<div id="msync-bar" style="height:100%;width:0%;background:linear-gradient(90deg,#2e7d32,#34c759);border-radius:8px;transition:width .3s"></div></div>'
        + '<div style="font-size:20px;font-weight:700;color:#2e7d32" id="msync-pct">0%</div>'
        + '</div></div></div>';
      document.getElementById('m-detail-root').innerHTML = html;
      this._bindSwipeBack();
      try{
        var r = await api('POST','/api/sync/'+encodeURIComponent(name));
        if(!r || !r.ok){ toast('❌ 同步启动失败: '+((r&&r.message)||'未知'),'error'); return; }
        // 轮询进度
        var bar = document.getElementById('msync-bar');
        var pctEl = document.getElementById('msync-pct');
        var statusEl = document.getElementById('msync-status');
        var pollCount = 0;
        this._msyncPoll = setInterval(async function(){
          pollCount++;
          if(pollCount > 200){ clearInterval(self._msyncPoll); if(statusEl) statusEl.textContent = '⏱ 耗时较长，可稍后刷新查看'; return; }
          try{
            var dd = await api('GET','/api/project/'+encodeURIComponent(name));
            var proj = (dd && dd.project) || {};
            var sp = proj.sync_progress || '';
            var m = sp.match(/(\d+)%/);
            if(bar && m) bar.style.width = m[1] + '%';
            if(pctEl && m) pctEl.textContent = m[1] + '%';
            if(statusEl && sp) statusEl.textContent = sp;
            // 同步完成：sync_status 不再是 syncing
            if(proj.sync_status && proj.sync_status !== 'syncing'){
              clearInterval(self._msyncPoll);
              self._msyncPoll = null;
              if(statusEl) statusEl.textContent = '✅ 同步完成';
              if(pctEl) pctEl.textContent = '100%';
              toast('✅ 同步完成：'+name,'success');
              self.load();
            }
          }catch(_){}
        }, 800);
      }catch(e){ toast('❌ 同步失败: '+e.message,'error'); }
    },

    // 质检审批：查看报告摘要 + 通过/打回
    async openQAApproval(name){
      var self = this;
      var pname = String(name||'').replace(/'/g,"\\'");
      var html = '<div class="m-detail" id="m-detail">'
        + '<div class="m-detail-bar"><button class="m-back" onclick="WB.mobile.closeDetail()">✕</button><div class="m-dt">🔍 质检审批</div></div>'
        + '<div class="m-detail-body"><div style="color:var(--m-text-sec);text-align:center;padding:40px">加载质检结果...</div></div></div>';
      document.getElementById('m-detail-root').innerHTML = html;
      this._bindSwipeBack();
      var body = document.querySelector('#m-detail .m-detail-body');
      try{
        var d = await api('GET','/api/project/'+encodeURIComponent(name)+'/qa_lastresult');
        if(!d || !d.ok){ if(body) body.innerHTML = '<div class="m-empty">暂无质检结果缓存</div>'; return; }
        var s = d.summary || {};
        var results = d.results || [];
        var h = '<div class="m-sum-card">'
          + '<div class="m-sum-label">质检结果（'+escHtml(d.timestamp||'')+'）</div>'
          + '<div class="m-sum-row">'
          + '<div class="m-sum-item"><div class="m-num" style="color:#34c759">'+(s.passed||0)+'</div><div class="m-lab">通过</div></div>'
          + '<div class="m-sum-item"><div class="m-num" style="color:#ff9500">'+(s.warnings||0)+'</div><div class="m-lab">警告</div></div>'
          + '<div class="m-sum-item"><div class="m-num" style="color:#ff3b30">'+(s.failed||0)+'</div><div class="m-lab">失败</div></div>'
          + '<div class="m-sum-item"><div class="m-num">'+(s.total||0)+'</div><div class="m-lab">总计</div></div>'
          + '</div></div>';
        // 问题项列表
        var issues = results.filter(function(r){ return r.status === 'fail' || r.status === 'warn'; });
        h += '<div class="m-section"><h4>'+(issues.length ? ('⚠️ 问题项（'+issues.length+'）') : '✅ 无问题项')+'</h4>';
        if(issues.length){
          h += issues.slice(0, 20).map(function(r){
            var isFail = r.status === 'fail';
            var color = isFail ? '#ff3b30' : '#ff9500';
            var issuesTxt = '';
            if(r.issues && Array.isArray(r.issues)){
              issuesTxt = r.issues.slice(0,2).map(function(it){ return ' · '+String(it); }).join('');
            }
            return '<div style="display:flex;gap:8px;align-items:flex-start;padding:8px 0;border-bottom:1px solid var(--m-border-light)">'
              + '<span style="width:34px;flex-shrink:0;font-size:11px;color:'+color+';font-weight:700;padding:2px 0">'+(isFail?'失败':'警告')+'</span>'
              + '<div style="flex:1;font-size:13px;min-width:0"><div style="word-break:break-word">'+escHtml(r.video||'')+'</div>'
              + (issuesTxt?'<div style="font-size:11px;color:var(--m-text-sec)">'+escHtml(issuesTxt)+'</div>':'')+'</div></div>';
          }).join('');
        } else {
          h += '<div style="color:#34c759;font-size:14px;padding:8px 0">所有文件通过质检</div>';
        }
        h += '</div>';
        // 审批操作
        h += '<div class="m-section"><h4>审批操作</h4>'
          + '<div class="m-card-actions">'
          + '<button class="m-act success" style="flex:1" onclick="WB.mobile.qaApprove(\''+pname+'\',\'交付中\')">✅ 通过</button>'
          + '<button class="m-act danger" style="flex:1" onclick="WB.mobile.qaApprove(\''+pname+'\',\'修改中\')">↩️ 打回修改</button>'
          + '</div>'
          + '<div style="font-size:11px;color:#c7c7cc;margin-top:8px">通过 → 状态变「交付中」；打回 → 状态变「修改中」</div>'
          + '</div>';
        if(body) body.innerHTML = h;
      }catch(e){
        if(body) body.innerHTML = '<div class="m-empty">加载失败: '+escHtml(e.message)+'</div>';
      }
    },

    // 质检审批：通过/打回 → 更新状态
    async qaApprove(name, targetStatus){
      var self = this;
      var action = targetStatus === '交付中' ? '通过质检' : '打回修改';
      if(!confirm('确认「'+action+'」项目「'+name+'」？状态将变为「'+targetStatus+'」')) return;
      try{
        var d = await api('POST','/api/project/'+encodeURIComponent(name)+'/custom_status', { custom_status: targetStatus });
        if(d && d.ok){
          toast('✅ 已'+action+'，状态为「'+targetStatus+'」','success');
          self.load(); // 刷新
          this.closeDetail();
        } else {
          toast('❌ ' + ((d&&d.message)||'操作失败'),'error');
        }
      }catch(e){ toast('❌ 操作失败: '+e.message,'error'); }
    },

    // ===== 移动端流程操作（与桌面端重构同步）=====

    // 分集中 → 跳转分集 Tab 选中项目
    mSyncToWorkbench: function(name){
      this._curTab = 'fenji';
      document.querySelectorAll('.m-tabbar .m-tab').forEach(function(b){
        b.classList.toggle('active', b.getAttribute('data-mtab')==='fenji');
      });
      var title = document.getElementById('m-page-title');
      if(title) title.textContent = '📑 分集管理';
      this._fj.project = name || '';
      var p = this._findProject(name);
      if(p && p.total_episodes) this._fj.total = p.total_episodes;
      var content = document.getElementById('m-content');
      if(content) this.renderFenji(content);
      toast('📑 已进入分集页，确认分集后点「同步到工作台」','info');
    },

    // 移动端：一键同步分集到工作台（保存分集 + 同步统计 + 改状态剪辑中）
    async mFenjiSyncToWorkbench(){
      var self = this;
      var name = this._fj.project;
      if(!name){ toast('请先选择项目','warning'); return; }
      if(!this._fj.ranges || !Object.keys(this._fj.ranges).length){ toast('请先分配集数','warning'); return; }
      if(!confirm('一键同步「'+name+'」分集到工作台？（保存分集+同步统计，状态改为剪辑中）')) return;
      try{
        // 1) 保存分集（复用 fjSave 逻辑）
        await this.fjSave();
        // 2) 同步工作台统计
        try{ await this.fjSync(); }catch(_){}
        // 3) 改状态为剪辑中
        await this._setStatus(name, '剪辑中');
        // 4) 返回首页并定位
        this._curTab = 'home';
        document.querySelectorAll('.m-tabbar .m-tab').forEach(function(b){
          b.classList.toggle('active', b.getAttribute('data-mtab')==='home');
        });
        if(title = document.getElementById('m-page-title')) title.textContent = '🎬 视频工作台';
        this.render();
        toast('✅ 复制成功 · 同步成功','success');
      }catch(e){ toast('同步失败: '+e.message,'error'); }
    },

    // 待提交审核 → 进入审核（二部批量回传 / 其他部门分秒帧确认）
    async mSubmitReview(name){
      var self = this;
      var p = this._findProject(name);
      var dept = p ? (p.department||'') : '';
      if(dept.indexOf('二部') >= 0){
        // 二部项目：打开成片预览，用户手动批量回传（移动端自动全选触发）
        if(!confirm('项目「'+name+'」为二部项目，将打开成片预览，全选后批量回传审核。继续？')) return;
        this._mAutoDeliver = { name: name, mode: 'editing', status: '审核中' };
        this.openChengPreview(name);
        return;
      }
      // 其他部门：打开分秒帧（若有）+ 确认已上传
      this.openFenmiaozhenBtn(name);
      if(confirm('请确认成片是否已经上传至分秒帧并提交审核？')){
        await this._setStatus(name, '审核中');
        toast('✅ 上传成功，项目进入审核中','success');
      }
    },

    // 审核中 → 标记修改
    async mMarkRevision(name){
      if(!confirm('确认将「'+name+'」标记为修改中？（将创建日期修改文件夹）')) return;
      await this._setStatus(name, '修改中');
    },

    // 修改中 → 提交下一轮审核（N审递增）
    async mSubmitRevision(name){
      var self = this;
      var p = this._findProject(name);
      var dept = p ? (p.department||'') : '';
      if(!confirm('项目「'+name+'」修改完成，提交下一轮审核？（将进入二审/三审...）')) return;
      if(dept.indexOf('二部') >= 0){
        // 二部项目：打开修改预览，全选后修改回传 → N审递增
        this._mAutoDeliver = { name: name, mode: 'revising', status: 'next_review' };
        this.openRevisePreview(name);
        return;
      }
      // 其他部门：分秒帧确认
      this.openFenmiaozhenBtn(name);
      if(confirm('请确认修改内容是否已经上传至分秒帧并提交审核？')){
        var next = this._nextReviewStatus(name);
        await this._setStatus(name, next);
        toast('✅ 修改上传成功，项目进入'+next,'success');
      }
    },

    // 终审完毕：所有审核通过，直接进入待交付（自动创建 000交付）
    async mFinalReviewComplete(name){
      var self = this;
      if(!confirm('项目「'+name+'」全部审核通过，标记为待交付？\n（将自动创建 000交付 文件夹）')) return;
      await this._setStatus(name, '待交付');
      toast('✅ 终审完毕，项目进入待交付，已创建 000交付','success');
    },

    // 计算下一轮审核状态
    _nextReviewStatus: function(name){
      var p = this._findProject(name);
      var cur = p ? (p.custom_status||'') : '';
      var cn = ['零','一','二','三','四','五','六','七','八','九','十'];
      if(cur.indexOf('修改中') >= 0) return '审核中';
      var m = String(cur||'').match(/^([二三四五六七八九十])审中$/);
      if(m){
        var idx = cn.indexOf(m[1]);
        return (idx >= 0 && idx < cn.length-1) ? cn[idx+1]+'审中' : '审核中';
      }
      return '审核中';
    },

    // 统一状态更新 + 刷新
    async _setStatus(name, status){
      try{
        var d = await api('POST','/api/project/'+encodeURIComponent(name)+'/custom_status', { custom_status: status });
        if(d && d.ok){ toast('✅ 状态已更新为「'+status+'」','success'); this._lastStatusChanged = name; this.load(); }
        else toast('❌ ' + ((d&&d.message)||'更新失败'),'error');
      }catch(e){ toast('❌ 更新失败: '+e.message,'error'); }
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
        + '<div class="m-detail-body"><div style="color:var(--m-text-sec);text-align:center;padding:40px">加载成片文件...</div></div></div>';
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
        var html2 = '<div style="margin-bottom:10px;font-size:13px;color:var(--m-text-sec)">共 '+files.length+' 个文件，点击可预览，亦可回传到制作部</div>'
          + '<div style="display:flex;gap:8px;margin-bottom:12px">'
          + '<button class="m-act primary" style="flex:1" onclick="WB.mobile.deliverAll(\''+pname+'\')">📤 全部回传</button>'
          + '</div>';
        files.forEach(function(f, i){
          var fname = String(f.name||'').replace(/'/g,"\\'");
          var isVideo = ['.mp4','.mov','.mkv','.avi','.webm'].indexOf(String(f.ext||'').toLowerCase())>=0;
          html2 += '<div style="display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid var(--m-border-light)">'
            + '<span style="font-size:16px">'+(isVideo?'🎥':'📄')+'</span>'
            + '<div style="flex:1;min-width:0"><div style="font-size:13px;word-break:break-word">'+escHtml(f.name)+'</div>'
            + '<div style="font-size:11px;color:var(--m-text-sec)">'+(f.editor?'👤 '+escHtml(f.editor):'')+' '+(f.size_mb?f.size_mb+'MB':'')+'</div></div>'
            + (isVideo?'<button class="m-act ghost" style="min-width:auto;padding:6px 12px" onclick="WB.mobile.playVideo(\''+pname+'\',\''+fname+'\',\''+encodeURIComponent(f.name)+'\')">▶ 播放</button>':'')
            + '<button class="m-act success" style="min-width:auto;padding:6px 12px" onclick="WB.mobile.deliverOne(\''+pname+'\',\''+encodeURIComponent(f.name)+'\')">📤</button>'
            + '</div>';
        });
        body.innerHTML = html2;
        // 审核流程：二部项目 待提交审核/修改回传 → 自动全选并批量回传
        if(this._mAutoDeliver && this._mAutoDeliver.name === name){
          var auto = this._mAutoDeliver;
          this._mAutoDeliver = null;
          var self = this;
          var allNames = files.map(function(f){ return f.name; });
          if(auto.status === '审核中'){
            this._doDeliver(pname, allNames, function(){
              self._setStatus(name, '审核中');
              toast('✅ 批量回传完成，项目进入审核中','success');
            });
          } else if(auto.status === 'next_review'){
            this._doDeliver(pname, allNames, function(){
              var next = self._nextReviewStatus(name);
              self._setStatus(name, next);
              toast('✅ 修改回传完成，项目进入'+next,'success');
            });
          }
        }
      }catch(e){
        var body2 = document.querySelector('#m-detail .m-detail-body');
        if(body2) body2.innerHTML = '<div class="m-empty">加载失败: '+escHtml(e.message)+'</div>';
      }
    },

    // M4: 回传单个成片文件到制作部
    async deliverOne(name, encodedName){
      var pname = String(name||'').replace(/'/g,"\\'");
      var fname = decodeURIComponent(encodedName||'');
      if(!confirm('回传「'+fname+'」到制作部？')) return;
      this._doDeliver(pname, [fname]);
    },

    // M4: 全部成片回传到制作部
    async deliverAll(name){
      var pname = String(name||'').replace(/'/g,"\\'");
      var self = this;
      try{
        var d = await api('GET','/api/output_files/'+encodeURIComponent(name)+'?mode=editing');
        var files = Array.isArray(d) ? d : (d.files || []);
        if(!files.length){ toast('没有可回传的文件','warning'); return; }
        if(!confirm('回传全部 '+files.length+' 个成片文件到制作部？（在桌面执行复制）')) return;
        this._doDeliver(pname, files.map(function(f){ return f.name; }));
      }catch(e){ toast('获取文件失败: '+e.message,'error'); }
    },

    // 执行批量回传（复用 /api/deliver_batch），发起后展示进度面板并轮询 sync_progress
    async _doDeliver(pname, fileNames, onDone){
      if(!fileNames || !fileNames.length){ toast('未选择文件','warning'); return; }
      toast('📤 正在发起回传 ' + fileNames.length + ' 个文件...','info');
      var self = this;
      this._deliverOnDone = onDone || null;   // 回传完成回调（审核流程用）
      try{
        var d = await api('POST','/api/deliver_batch/'+encodeURIComponent(pname), { file_names: fileNames, mode: 'editing' });
        if(d && d.ok){
          toast('✅ ' + (d.message || '回传已启动'), 'success');
          // 打开回传进度面板，轮询 sync_progress 显示进度
          this._showDeliverProgress(pname);
        } else {
          toast('❌ ' + ((d && d.message) || '回传失败'), 'error');
        }
      }catch(e){ toast('❌ 回传失败: ' + e.message, 'error'); }
    },

    // 展示回传进度面板（全屏弹窗），轮询 /api/project/<name> 读 sync_progress
    _showDeliverProgress: function(name){
      var self = this;
      var pname = String(name||'').replace(/'/g,"\\'");
      var html = '<div class="m-detail" id="m-detail">'
        + '<div class="m-detail-bar"><button class="m-back" onclick="WB.mobile.closeDetail()">✕</button><div class="m-dt">📤 回传进度</div></div>'
        + '<div class="m-detail-body">'
        + '<div style="text-align:center;padding:20px 0">'
        + '<div style="font-size:13px;color:var(--m-text-sec)" id="mdp-status">正在执行回传...</div>'
        + '<div style="background:var(--m-chip-bg);border-radius:8px;height:12px;margin:14px 8px;overflow:hidden">'
        + '<div id="mdp-bar" style="height:100%;width:0%;background:linear-gradient(90deg,#0071e3,#5ac8fa);border-radius:8px;transition:width .3s"></div></div>'
        + '<div style="font-size:20px;font-weight:700;color:#0071e3" id="mdp-pct">0%</div>'
        + '</div>'
        + '<div style="text-align:center;color:#c7c7cc;font-size:12px">回传在电脑上执行系统复制，此进度自动刷新</div>'
        + '</div></div>';
      document.getElementById('m-detail-root').innerHTML = html;
      this._bindSwipeBack();

      var startTs = Date.now();
      var pollCount = 0, maxPolls = 200; // 最多约 100 秒（500ms 一次）
      var bar = document.getElementById('mdp-bar');
      var pctEl = document.getElementById('mdp-pct');
      var statusEl = document.getElementById('mdp-status');
      this._deliverPoll = setInterval(async function(){
        pollCount++;
        if(pollCount > maxPolls){
          clearInterval(self._deliverPoll);
          if(statusEl) statusEl.textContent = '⏱ 轮询超时，请到桌面端查看进度';
          return;
        }
        try{
          var dd = await api('GET','/api/project/'+encodeURIComponent(name));
          var proj = (dd && dd.project) || {};
          var sp = proj.sync_progress || '';
          // 解析 "回传 X/Y 文件"
          var m = sp.match(/回传\s*(\d+)\s*\/\s*(\d+)/);
          var pct = 0, label = sp;
          if(m){
            var cur = parseInt(m[1]), tot = parseInt(m[2]);
            pct = tot>0 ? Math.round(cur*100/tot) : 0;
            label = '已回传 ' + cur + '/' + tot + ' 文件';
            if(pct >= 100){ label = '✅ 回传完成'; }
          } else if(sp && sp.indexOf('正在复制')>=0){
            var es = (Date.now()-startTs)/1000;
            pct = Math.min(95, Math.round(3 + 95*(1-Math.exp(-es/240))));
            label = '📋 正在复制（查看电脑系统进度窗口）';
          } else if(sp && sp.indexOf('完成')>=0){
            pct = 100; label = '✅ 回传完成';
          } else if(sp){
            pct = 0; label = sp;
          }
          // 更新 UI
          if(bar) bar.style.width = pct + '%';
          if(pctEl) pctEl.textContent = pct + '%';
          if(statusEl) statusEl.textContent = label;
          // 完成或状态不再是回传中则停止
          if(pct >= 100 || !sp || sp.indexOf('回传')<0 && sp.indexOf('正在复制')<0 && sp.indexOf('完成')<0){
            clearInterval(self._deliverPoll);
            self._deliverPoll = null;
            // 回传完成回调（审核流程：改状态等）
            if(self._deliverOnDone){
              var cb = self._deliverOnDone;
              self._deliverOnDone = null;
              try{ cb(); }catch(_){}
            }
          }
        }catch(e){}
      }, 500);
    },

    // 修改预览：列出修改文件夹（revising）并可播放
    async openRevisePreview(name){
      var pname = String(name||'').replace(/'/g,"\\'");
      var html = '<div class="m-detail" id="m-detail">'
        + '<div class="m-detail-bar"><button class="m-back" onclick="WB.mobile.closeDetail()">✕</button><div class="m-dt">📝 修改预览</div></div>'
        + '<div class="m-detail-body"><div style="color:var(--m-text-sec);text-align:center;padding:40px">加载修改文件夹...</div></div></div>';
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
          html2 += '<div style="display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid var(--m-border-light)">'
            + '<span style="font-size:16px">📁</span>'
            + '<div style="flex:1"><div style="font-size:13px">'+escHtml(f.name)+'</div>'
            + '<div style="font-size:11px;color:var(--m-text-sec)">'+(f.file_count?f.file_count+' 个文件':'')+'</div></div>'
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
        + '<div class="m-detail-body"><div style="color:var(--m-text-sec);text-align:center;padding:40px">加载中...</div></div></div>';
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
          html2 += '<div style="display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid var(--m-border-light)">'
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
      // 关闭时清理回传/同步进度轮询，避免后台持续请求
      if(this._deliverPoll){ clearInterval(this._deliverPoll); this._deliverPoll = null; }
      if(this._msyncPoll){ clearInterval(this._msyncPoll); this._msyncPoll = null; }
      this._deliverOnDone = null;
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
          // 状态变更后回到首页并高亮该项目
          self._lastStatusChanged = name;
          self._curTab = 'home';
          document.querySelectorAll('.m-tabbar .m-tab').forEach(function(b){
            b.classList.toggle('active', b.getAttribute('data-mtab')==='home');
          });
          var title = document.getElementById('m-page-title');
          if(title) title.textContent = '🎬 视频工作台';
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

    // 打开目录（打开成片目录 01上映单集版）
    openGroup: function(name){
      if(typeof openSmart === 'function'){ openSmart(name, 'group_output'); }
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
          box.innerHTML = '<div style="color:var(--m-text-sec);text-align:center;padding:14px;font-size:13px">暂无待办</div>';
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
        var html = '<div style="margin-bottom:12px;font-size:13px;color:var(--m-text-sec)">📌 进行中的待办（'+todos.length+'）</div>';
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

      // M2 增强：产能趋势 + 部门统计 + 个人年度工作量（并行加载，追加到概览下方）
      var base = (ov.this_month ? String(ov.this_month) : '');
      if(base && base.length === 7){
        // 产能趋势
        api('GET','/api/stats/dashboard?month='+encodeURIComponent(base)).then(function(dd){
          if(!dd || !dd.ok) return;
          self._renderTrend(content, dd.trend);
          self._renderDept(content, dd.dept_stats);
        }).catch(function(){});
        // 个人年度工作量
        var year = base.slice(0,4);
        api('GET','/api/commission/person_cards?year='+year).then(function(pd){
          if(!pd || !pd.ok || !pd.cards) return;
          self._renderPersonCards(content, pd.cards, year);
        }).catch(function(){});
      }

      // 提成数据：30 秒缓存，避免重复请求
      var now = Date.now();
      if(this._statsCache.data && (now - this._statsCache.ts) < 30000){
        this._renderStatsBody(content, this._statsCache.data);
        return;
      }
      api('GET','/api/commission/monthly').then(function(d){
        if(!d || !d.ok) return;
        self._statsCache = { data: d, ts: Date.now() };
        self._renderStatsBody(content, d);
      }).catch(function(){});
    },

    // M2: 产能趋势（近6个月）—— 简单柱状
    _renderTrend: function(content, trend){
      if(!trend || !trend.length) return;
      var max = Math.max.apply(null, trend.map(function(t){ return Math.max(t.total||0, t.done||0); }).concat([1]));
      var h = '<div class="m-section"><h4>📈 产能趋势（近6月）</h4>';
      h += '<div style="display:flex;align-items:flex-end;gap:6px;height:110px;padding:8px 0">';
      trend.forEach(function(t){
        var tot = t.total||0, done = t.done||0;
        var hTot = Math.round(tot/max*90), hDone = Math.round(done/max*90);
        h += '<div style="flex:1;display:flex;flex-direction:column;justify-content:flex-end;align-items:center">'
          + '<div style="width:60%;background:#dbeafe;border-radius:3px;height:'+Math.max(3,hDone)+'px"></div>'
          + '<div style="width:100%;background:#5c6bc0;border-radius:3px;height:'+Math.max(3,hTot)+'px;margin-top:2px"></div>'
          + '<div style="font-size:9px;color:var(--m-text-sec);margin-top:4px">'+String(t.month||'').slice(5)+'</div>'
          + '</div>';
      });
      h += '</div><div style="font-size:10px;color:var(--m-text-sec);display:flex;gap:12px">'
        + '<span><i style="display:inline-block;width:8px;height:8px;background:#5c6bc0;border-radius:2px"></i> 立项</span>'
        + '<span><i style="display:inline-block;width:8px;height:8px;background:#dbeafe;border-radius:2px"></i> 完成</span>'
        + '</div></div>';
      var tmp = document.createElement('div'); tmp.innerHTML = h;
      while(tmp.firstChild) content.appendChild(tmp.firstChild);
    },

    // M2: 部门统计
    _renderDept: function(content, deptStats){
      if(!deptStats || !deptStats.length) return;
      var h = '<div class="m-section"><h4>🏢 部门统计</h4>';
      deptStats.slice(0, 8).forEach(function(d){
        if(!d.department) return;
        var pct = d.total ? Math.round((d.completed||0)/d.total*100) : 0;
        h += '<div style="display:flex;align-items:center;gap:8px;padding:6px 0">'
          + '<div style="width:52px;font-size:12px;color:var(--m-text);font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+escHtml(d.department)+'</div>'
          + '<div style="flex:1;background:var(--m-chip-bg);border-radius:6px;height:14px;overflow:hidden">'
          + '<div style="height:100%;width:'+pct+'%;background:linear-gradient(90deg,#34c759,#30d158)"></div></div>'
          + '<div style="font-size:11px;color:var(--m-text-sec);min-width:52px;text-align:right">'+(d.completed||0)+'/'+(d.total||0)+'</div>'
          + '</div>';
      });
      h += '</div>';
      var tmp = document.createElement('div'); tmp.innerHTML = h;
      while(tmp.firstChild) content.appendChild(tmp.firstChild);
    },

    // M2: 个人年度工作量卡片（逐月集数）
    _renderPersonCards: function(content, cards, year){
      if(!cards || !cards.length) return;
      var h = '<div class="m-section"><h4>👥 个人年度工作量（'+year+'）</h4>';
      cards.slice(0, 10).forEach(function(c){
        if(!c.name) return;
        var monthly = c.monthly || {};
        var months = [];
        for(var m=1; m<=12; m++){
          var k = year + '-' + (m<10?'0':'') + m;
          months.push({ m: m, v: monthly[k] || 0 });
        }
        var maxV = Math.max.apply(null, months.map(function(x){return x.v;}).concat([1]));
        h += '<div style="background:var(--m-card-bg);border-radius:10px;padding:10px 12px;margin-bottom:8px;box-shadow:0 1px 3px rgba(0,0,0,.04)">'
          + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">'
          + '<span style="font-size:13px;font-weight:600">'+escHtml(c.name)+'</span>'
          + '<span style="font-size:11px;color:var(--m-text-sec)">全年 '+c.annual_total+' 集'+(c.role?' · '+escHtml(c.role):'')+'</span></div>'
          + '<div style="display:flex;align-items:flex-end;gap:2px;height:36px">';
        months.forEach(function(x){
          var hh = Math.round(x.v/maxV*32);
          h += '<div style="flex:1;display:flex;flex-direction:column;justify-content:flex-end;align-items:center">'
            + '<div style="width:90%;background:'+(x.v>0?'#0071e3':'#e8e8ed')+';border-radius:2px;height:'+Math.max(2,hh)+'px"></div></div>';
        });
        h += '</div><div style="font-size:9px;color:#c7c7cc;display:flex;gap:2px;margin-top:2px">';
        months.forEach(function(x){ h += '<div style="flex:1;text-align:center">'+(x.v?'':'')+'</div>'; });
        h += '</div></div>';
      });
      h += '</div>';
      var tmp = document.createElement('div'); tmp.innerHTML = h;
      while(tmp.firstChild) content.appendChild(tmp.firstChild);
    },

    // 渲染提成明细（汇总卡 + 每人卡）
    _renderStatsBody: function(content, d){
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
        var pct = quota>0 ? Math.min(100, Math.round(episodes/quota*100)) : (episodes>0?100:0);
        var barColor = r.is_complete ? '#34c759' : '#ff9500';
        var avatar = String(r.name||'?').charAt(0);
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
      while(tmp.firstChild) content.appendChild(tmp.firstChild);
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
          html += '<div style="background:var(--m-card-bg);border-radius:10px;padding:10px 12px;margin-bottom:8px;box-shadow:0 1px 3px rgba(0,0,0,.04)">'
            + '<div style="display:flex;justify-content:space-between;align-items:center">'
            + '<span style="font-size:14px;font-weight:600">'+escHtml(r.name)
            + (r.role?' <span style="font-size:10px;color:var(--m-text-sec);font-weight:400">'+escHtml(r.role)+'</span>':'')
            + '</span>'
            + '<span style="font-weight:700;color:'+color+'">¥'+(r.commission||0)+'</span>'
            + '</div>'
            + '<div style="font-size:11px;color:var(--m-text-sec);margin-top:6px">'+detail.join(' · ')+'</div>'
            + '<div style="font-size:10px;color:var(--m-text-sec);margin-top:3px">'+daBiao+'</div>'
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
      var self = this;
      var curTheme = this.getTheme();
      var themeLabel = { system: '跟随系统', light: '浅色', dark: '深色' }[curTheme] || '跟随系统';

      var html = '<div class="m-section"><h4>关于</h4>'
        + '<div class="m-row"><span class="m-k">视频工作台</span><span class="m-v">手机版</span></div>'
        + '<div class="m-row"><span class="m-k">项目总数</span><span class="m-v">'+this._data.projects.length+'</span></div>'
        + '</div>';

      // 主题切换（⭐4）
      html += '<div class="m-section"><h4>外观</h4>'
        + '<div class="m-row"><span class="m-k">深色模式</span><span class="m-v">'+themeLabel+'</span></div>'
        + '<div style="display:flex;gap:8px;margin-top:8px">'
        + '<button class="m-act '+(curTheme==='system'?'primary':'ghost')+'" style="min-width:auto" onclick="WB.mobile.setTheme(\'system\')">跟随系统</button>'
        + '<button class="m-act '+(curTheme==='light'?'primary':'ghost')+'" style="min-width:auto" onclick="WB.mobile.setTheme(\'light\')">☀️ 浅色</button>'
        + '<button class="m-act '+(curTheme==='dark'?'primary':'ghost')+'" style="min-width:auto" onclick="WB.mobile.setTheme(\'dark\')">🌙 深色</button>'
        + '</div></div>';

      // 快捷操作（⭐5）
      html += '<div class="m-section"><h4>快捷操作</h4>'
        + '<div style="display:flex;gap:8px;flex-wrap:wrap">'
        + '<button class="m-act ghost" style="min-width:auto" onclick="WB.mobile.openSync()">📤 同步素材</button>'
        + '<button class="m-act ghost" style="min-width:auto" onclick="WB.mobile.changeServer()">🌐 修改地址</button>'
        + '<button class="m-act ghost" style="min-width:auto" onclick="WB.mobile.reloadPage()">🔄 刷新页面</button>'
        + '<button class="m-act ghost" style="min-width:auto" onclick="WB.mobile.refresh()">🔄 刷新数据</button>'
        + '<button class="m-act ghost" style="min-width:auto" onclick="WB.mobile.openNotifications()">🔔 通知</button>'
        + '<button class="m-act ghost" style="min-width:auto" onclick="WB.mobile.openStats()">📊 我的数据</button>'
        + '</div></div>';

      content.innerHTML = html;
    },

    // 修改服务器地址：跳转到新地址（WebView 会拦截并加载）
    changeServer: function(){
      var cur = location.href;
      var url = prompt('请输入新的服务器地址：\n（当前：'+cur+'）', cur);
      if(!url) return;
      url = url.trim();
      if(!url) return;
      if(!/^https?:\/\//i.test(url)) url = 'http://' + url;
      // 保存到 localStorage，便于下次（虽然原生壳用自己存的地址）
      try{ localStorage.setItem('wb_server_url', url); }catch(_){}
      toast('正在切换到 '+url, 'info');
      setTimeout(function(){ location.href = url; }, 300);
    },

    // 刷新页面（重新加载当前 URL）
    reloadPage: function(){
      toast('🔄 正在刷新页面...', 'info');
      setTimeout(function(){ location.reload(); }, 300);
    },

    // 新建项目（扫描NAS → 发现未同步项目 → 同步到组内NAS）
    // 同步单个项目到组内NAS（带进度）
    async syncNewProject(name){
      var self = this;
      if(!confirm('将「'+name+'」从制作部 NAS 同步到组内 NAS（完成新建）？')) return;
      toast('📤 正在同步 '+name+' ...','info');
      try{
        var d = await api('POST','/api/sync/'+encodeURIComponent(name));
        if(!d || !d.ok){ toast('❌ 同步启动失败: '+((d&&d.message)||'未知'),'error'); return; }
        // 轮询进度
        var box = document.querySelector('.m-sync-prog');
        var bar = box ? box.querySelector('div div') : null;
        if(box) box.style.display = '';
        var pollCount = 0;
        var timer = setInterval(async function(){
          pollCount++;
          if(pollCount > 200){ clearInterval(timer); toast('⏱ 同步耗时较长，可稍后刷新查看','warning'); return; }
          try{
            var dd = await api('GET','/api/project/'+encodeURIComponent(name));
            var proj = (dd && dd.project) || {};
            var sp = proj.sync_progress || '';
            var m = sp.match(/(\d+)%/);
            if(bar && m){ bar.style.width = m[1] + '%'; }
            if(sp && sp.indexOf('完成') >= 0){
              clearInterval(timer);
              toast('✅ 「'+name+'」同步完成','success');
              self.load();
            }
          }catch(_){}
        }, 800);
      }catch(e){ toast('❌ 同步失败: '+e.message,'error'); }
    },

    // 同步素材入口（对已有项目）
    openSync: function(){
      var self = this;
      var html = '<div class="m-detail" id="m-detail">'
        + '<div class="m-detail-bar"><button class="m-back" onclick="WB.mobile.closeDetail()">✕</button><div class="m-dt">📤 同步素材</div></div>'
        + '<div class="m-detail-body">'
        + '<div class="m-section"><h4>选择项目同步到组内 NAS</h4>'
        + '<input id="m-sync-search" type="text" placeholder="🔍 搜索项目..." style="width:100%;padding:9px 12px;border:1px solid var(--border,#e5e5ea);border-radius:10px;font-size:14px;margin-bottom:10px" oninput="WB.mobile.renderSyncList(this.value)">'
        + '<div id="m-sync-list"></div>'
        + '</div></div></div>';
      document.getElementById('m-detail-root').innerHTML = html;
      this._bindSwipeBack();
      this.renderSyncList('');
    },

    renderSyncList: function(q){
      var box = document.getElementById('m-sync-list');
      if(!box) return;
      var self = this;
      var ql = (q||'').toLowerCase();
      var needSync = this._data.projects.filter(function(p){
        return p.need_sync && (!ql || String(p.name||'').toLowerCase().indexOf(ql) >= 0);
      });
      if(!needSync.length){
        box.innerHTML = '<div class="m-empty">'+(ql?'没有匹配的项目':'✅ 没有待同步的项目')+'</div>';
        return;
      }
      var html = '';
      needSync.forEach(function(p){
        var name = String(p.name||'').replace(/'/g,"\\'");
        html += '<div style="background:var(--m-card-bg);border-radius:10px;padding:10px 12px;margin-bottom:8px;box-shadow:0 1px 3px rgba(0,0,0,.04);display:flex;justify-content:space-between;align-items:center;gap:8px">'
          + '<div style="flex:1;min-width:0;font-size:13px;font-weight:600;word-break:break-word">'+escHtml(p.name)+'</div>'
          + '<button class="m-act success" style="min-width:auto;flex-shrink:0" onclick="WB.mobile.syncNewProject(\''+name+'\')">📤 同步</button>'
          + '</div>';
      });
      box.innerHTML = html;
    },

    // ⭐5: 打开"我的数据"（个人年度工作量 + 本月我的提成/集数）
    openStats: function(){
      var self = this;
      var html = '<div class="m-detail" id="m-detail">'
        + '<div class="m-detail-bar"><button class="m-back" onclick="WB.mobile.closeDetail()">✕</button><div class="m-dt">📊 我的数据</div></div>'
        + '<div class="m-detail-body"><div style="color:var(--m-text-sec);text-align:center;padding:40px">加载中...</div></div></div>';
      document.getElementById('m-detail-root').innerHTML = html;
      this._bindSwipeBack();
      var body = document.querySelector('#m-detail .m-detail-body');
      var year = new Date().getFullYear();
      api('GET','/api/commission/person_cards?year='+year).then(function(d){
        if(!d || !d.ok){ if(body) body.innerHTML = '<div class="m-empty">暂无数据</div>'; return; }
        var h = '<div class="m-section"><h4>👥 全部剪辑师年度工作量（'+year+'）</h4>';
        (d.cards||[]).forEach(function(c){
          if(!c.name) return;
          var monthly = c.monthly || {};
          var months = [];
          for(var m=1;m<=12;m++){ var k=year+'-'+(m<10?'0':'')+m; months.push(monthly[k]||0); }
          var maxV = Math.max.apply(null, months.concat([1]));
          h += '<div style="background:var(--m-card-bg);border-radius:10px;padding:10px 12px;margin-bottom:8px;box-shadow:0 1px 3px rgba(0,0,0,.04)">'
            + '<div style="display:flex;justify-content:space-between;margin-bottom:6px"><span style="font-size:13px;font-weight:600">'+escHtml(c.name)+'</span><span style="font-size:11px;color:var(--m-text-sec)">全年 '+c.annual_total+' 集'+(c.role?' · '+escHtml(c.role):'')+'</span></div>'
            + '<div style="display:flex;align-items:flex-end;gap:2px;height:34px">';
          months.forEach(function(v){
            var hh = Math.round(v/maxV*30);
            h += '<div style="flex:1;display:flex;flex-direction:column;justify-content:flex-end;align-items:center"><div style="width:90%;background:'+(v>0?'#0071e3':'#e8e8ed')+';border-radius:2px;height:'+Math.max(2,hh)+'px"></div></div>';
          });
          h += '</div></div>';
        });
        h += '</div>';
        if(body) body.innerHTML = h;
      }).catch(function(){ if(body) body.innerHTML = '<div class="m-empty">加载失败</div>'; });
    },

    refresh: function(){ this.load(); },

    // 顶部刷新按钮
    openScan: function(){
      if(typeof scanProjects === 'function'){ scanProjects(); }
      else { toast('扫描不可用','warning'); }
    },

    // 移动端专属通知中心（全屏弹窗，展示逾期/今日交付/待办提醒）
    async openNotifications(){
      var self = this;
      var html = '<div class="m-detail" id="m-detail">'
        + '<div class="m-detail-bar"><button class="m-back" onclick="WB.mobile.closeDetail()">✕</button><div class="m-dt">🔔 通知中心</div></div>'
        + '<div class="m-detail-body"><div style="color:var(--m-text-sec);text-align:center;padding:40px">加载中...</div></div></div>';
      document.getElementById('m-detail-root').innerHTML = html;
      this._bindSwipeBack();
      try{
        // 并行加载：通知 + 审核/质检超时
        var notifP = api('GET','/api/notifications').then(function(d){ return d||{}; }).catch(function(){ return {}; });
        var auditP = api('GET','/api/audit/alerts').then(function(d){ return d||{}; }).catch(function(){ return {}; });
        var results = await Promise.all([notifP, auditP]);
        var d = results[0], audit = results[1];
        var body = document.querySelector('#m-detail .m-detail-body');
        if(!body) return;
        var overdue = d.overdue || [];
        var today = d.today_deliver || [];
        var upcoming = d.upcoming || [];
        var todos = d.todo_reminders || [];
        var alerts = (audit.alerts) || [];   // 审核/质检超时项目
        var qaPending = alerts.filter(function(a){ return (a.status||'').indexOf('质检') >= 0; });
        var auditStuck = alerts.filter(function(a){ return (a.status||'').indexOf('质检') < 0; });
        var h = '';

        // 质检待审批（优先展示，可点击进入审批）
        if(qaPending.length){
          h += '<div class="m-section"><h4>🔍 质检待审批（'+qaPending.length+'）</h4>';
          qaPending.forEach(function(x){
            var name = String(x.name||'').replace(/'/g,"\\'");
            h += '<div class="m-row" style="cursor:pointer" onclick="WB.mobile.openQAApproval(\''+name+'\')">'
              + '<span class="m-k">🟣 '+escHtml(x.name)+'</span><span class="m-v" style="color:#ff9500">'+escHtml(x.status||'')+' '+escHtml(x.days_stuck||0)+'天</span></div>';
          });
          h += '</div>';
        }
        // 审核/修改超时
        if(auditStuck.length){
          h += '<div class="m-section"><h4>⏰ 审核/修改超时（'+auditStuck.length+'）</h4>';
          auditStuck.forEach(function(x){
            var name = String(x.name||'').replace(/'/g,"\\'");
            h += '<div class="m-row" style="cursor:pointer" onclick="WB.mobile.openDetail(\''+name+'\')">'
              + '<span class="m-k">'+escHtml(x.name)+'</span><span class="m-v" style="color:#ff9500">'+escHtml(x.status||'')+' '+escHtml(x.days_stuck||0)+'天</span></div>';
          });
          h += '</div>';
        }

        var totalItems = overdue.length + today.length + upcoming.length + todos.length + qaPending.length + auditStuck.length;
        if(totalItems === 0){
          h = '<div class="m-empty">🎉 没有待处理通知</div>';
        } else {
          if(!h) h = ''; // h 已含超时/质检区块
          h += '<div class="m-section"><h4>⏰ 逾期交付（'+overdue.length+'）</h4>';
          if(!overdue.length) h += '<div style="color:var(--m-text-sec);font-size:13px;padding:6px 0">无</div>';
          overdue.forEach(function(x){ var name=String(x.name||'').replace(/'/g,"\\'"); h += '<div class="m-row" style="cursor:pointer" onclick="WB.mobile.openDetail(\''+name+'\')"><span class="m-k">🔴 '+escHtml(x.name)+'</span><span class="m-v" style="color:#ff3b30">'+escHtml(x.date||'')+'</span></div>'; });
          h += '</div>';
          h += '<div class="m-section"><h4>📦 今日交付（'+today.length+'）</h4>';
          if(!today.length) h += '<div style="color:var(--m-text-sec);font-size:13px;padding:6px 0">无</div>';
          today.forEach(function(x){ var name=String(x.name||'').replace(/'/g,"\\'"); h += '<div class="m-row" style="cursor:pointer" onclick="WB.mobile.openDetail(\''+name+'\')"><span class="m-k">'+escHtml(x.name)+'</span><span class="m-v" style="color:#0071e3">今日</span></div>'; });
          h += '</div>';
          h += '<div class="m-section"><h4>📅 即将交付（'+upcoming.length+'）</h4>';
          if(!upcoming.length) h += '<div style="color:var(--m-text-sec);font-size:13px;padding:6px 0">无</div>';
          upcoming.forEach(function(x){ var name=String(x.name||'').replace(/'/g,"\\'"); h += '<div class="m-row" style="cursor:pointer" onclick="WB.mobile.openDetail(\''+name+'\')"><span class="m-k">'+escHtml(x.name)+'</span><span class="m-v">'+escHtml(x.date||'')+'</span></div>'; });
          h += '</div>';
          h += '<div class="m-section"><h4>📌 待办提醒（'+todos.length+'）</h4>';
          if(!todos.length) h += '<div style="color:var(--m-text-sec);font-size:13px;padding:6px 0">无</div>';
          todos.forEach(function(x){ h += '<div class="m-row"><span class="m-k">'+escHtml(x.project||'')+'</span><span class="m-v">'+escHtml(x.text||'')+'</span></div>'; });
          h += '</div>';
        }
        body.innerHTML = h;
        // 已查看，清角标
        this._notifCount = 0;
        this._updateNotifBadge();
      }catch(e){
        var b2 = document.querySelector('#m-detail .m-detail-body');
        if(b2) b2.innerHTML = '<div class="m-empty">加载失败: '+escHtml(e.message)+'</div>';
      }
    },

    // 更新顶部铃铛角标
    _updateNotifBadge: function(){
      var badge = document.getElementById('m-notif-badge');
      if(!badge) return;
      var n = this._notifCount || 0;
      if(n > 0){
        badge.style.display = '';
        badge.textContent = n > 99 ? '99+' : n;
      } else {
        badge.style.display = 'none';
      }
    },

    // 定期检查通知（每 5 分钟）：新通知弹浏览器通知 + 更新角标
    _startNotifPolling: function(){
      var self = this;
      if(this._notifPolling) return;
      this._notifPolling = true;
      this._notifCount = 0;
      var lastCount = -1;
      var check = async function(){
        try{
          // 并行：通知 + 审核/质检超时，角标计数两者之和
          var notifP = api('GET','/api/notifications').then(function(d){ return d||{}; }).catch(function(){ return {}; });
          var auditP = api('GET','/api/audit/alerts').then(function(d){ return d||{}; }).catch(function(){ return {}; });
          var res = await Promise.all([notifP, auditP]);
          var d = res[0], audit = res[1];
          var count = ((d && d.count) || 0) + ((audit && audit.alerts && audit.alerts.length) || 0);
          if(count > lastCount){
            self._notifCount = count;
            self._updateNotifBadge();
            // 浏览器通知（需授权）
            if(count > 0 && 'Notification' in window && Notification.permission === 'granted'){
              var over = (d.overdue||[]).length;
              var today = (d.today_deliver||[]).length;
              var stuck = (audit.alerts||[]).length;
              try{
                new Notification('🎬 视频工作台提醒', {
                  body: (over?('逾期 '+over+' 个')+' ':'') + (today?('今日交付 '+today+' 个')+' ':'') + (stuck?('审核超时 '+stuck+' 个'):'') || ('共 '+count+' 条通知'),
                });
              }catch(_){}
            }
          }
          lastCount = count;
        }catch(_){}
      };
      // 首次请求通知权限
      if('Notification' in window && Notification.permission === 'default'){
        Notification.requestPermission().catch(function(){});
      }
      check();
      setInterval(check, 5*60*1000);
    },

    renderError: function(msg){
      var content = document.getElementById('m-content');
      if(content) content.innerHTML = '<div class="m-empty">'+escHtml(msg)+'</div>';
    },

    // 首页骨架屏：数据加载时显示灰色占位卡
    _renderSkeleton: function(){
      var content = document.getElementById('m-content');
      if(!content || this._curTab !== 'home') return;
      var cards = '';
      for(var i=0; i<4; i++){
        cards += '<div class="m-skel-card">'
          + '<div class="m-skeleton m-skel-line" style="width:70%"></div>'
          + '<div class="m-skeleton m-skel-chip"></div>'
          + '<div class="m-skeleton m-skel-chip"></div>'
          + '<div class="m-skeleton m-skel-chip"></div>'
          + '<div class="m-skeleton m-skel-line" style="margin-top:12px"></div>'
          + '</div>';
      }
      content.innerHTML = '<div class="m-stats">'
        + ['','','',''].map(function(){ return '<div class="m-stat"><div class="m-skeleton" style="width:70%;height:20px;margin:0 auto"></div><div class="m-skeleton" style="width:50%;height:10px;margin:6px auto 0"></div></div>'; }).join('')
        + '</div>' + cards;
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

      // ===== 顶部 Hero 卡片：项目选择 + 总集数 =====
      var html = '<div class="m-fj-hero">'
        + '<div class="m-fj-hero-title">📑 分集分配</div>'
        // 项目选择器
        + '<div class="m-fj-picker" onclick="WB.mobile.openFjProjectPicker()">'
        + (fj.project
            ? '<span>'+escHtml(fj.project)+'</span>'
            : '<span class="m-fj-picker-empty">— 点击选择项目 —</span>')
        + '<span style="font-size:13px;opacity:.8">▾</span>'
        + '</div>'
        // 总集数
        + '<div class="m-fj-hero-row">'
        + '<span class="m-fj-label">总集数</span>'
        + '<input id="m-fj-total" class="m-fj-total-input" type="number" value="'+(fj.total||'')+'" oninput="WB.mobile.fjSetTotal(this.value)">'
        + '<span class="m-fj-total-suffix">集</span>'
        + '</div>'
        + '</div>';

      // ===== 剪辑师选择（chip 选择器）=====
      html += '<div class="m-section"><h4>👥 选择剪辑师 <span id="m-fj-selected-count" style="font-weight:400;color:#5c6bc0"></span></h4>'
        + '<div class="m-filter" style="margin-bottom:8px"><select id="m-fj-tpl" onchange="WB.mobile.fjApplyTpl(this.value)">'
        + '<option value="">— 应用人员模板 —</option>'
        + '</select></div>'
        + '<div id="m-fj-persons" class="m-fj-persons-wrap"><div style="color:var(--m-text-sec);font-size:13px;padding:8px 0">加载剪辑师...</div></div>'
        + '<div class="m-card-actions" style="margin-top:10px">'
        + '<button class="m-act ghost" style="flex:1" onclick="WB.mobile.fjSaveTpl()">💾 存为模板</button>'
        + '<button class="m-act ghost" style="flex:1" onclick="WB.mobile.fjDelTpl()">🗑 删除模板</button>'
        + '</div></div>';

      // ===== 操作按钮 =====
      html += '<div class="m-section"><h4>操作</h4><div class="m-card-actions">'
        + '<button class="m-act primary" style="flex:1" onclick="WB.mobile.fjAssign()">⚡ 自动分配</button>'
        + '<button class="m-act ghost" style="flex:1" onclick="WB.mobile.fjSave()">💾 保存</button>'
        + '<button class="m-act ghost" style="flex:1" onclick="WB.mobile.fjCopy()">📋 复制</button>'
        + '<button class="m-act warn" style="flex:1" onclick="WB.mobile.fjSync()">🔄 同步</button>'
        + '</div>'
        + '<button class="m-act success" style="width:100%;margin-top:8px" onclick="WB.mobile.mFenjiSyncToWorkbench()">⚡ 一键同步到工作台（保存+同步+剪辑中）</button>'
        + '</div>';

      // ===== 分配结果 =====
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
        var sel = (p.name === self._fj.project);
        return '<div style="background:var(--m-card-bg);border-radius:10px;padding:12px 14px;margin-bottom:8px;box-shadow:0 1px 3px rgba(0,0,0,.05);cursor:pointer;display:flex;justify-content:space-between;align-items:center;gap:8px;'+(sel?'border:1.5px solid #5c6bc0;':'')+'"'
          + ' onclick="WB.mobile.fjPickProject(\''+pn+'\')">'
          + '<div style="flex:1;min-width:0"><div style="font-size:14px;font-weight:600;color:var(--m-text);word-break:break-word">'+escHtml(p.name)+'</div>'
          + (p.custom_status?'<div style="font-size:11px;color:var(--m-text-sec);margin-top:2px">'+escHtml(p.custom_status)+'</div>':'')+'</div>'
          + (sel?'<span style="font-size:12px;color:#5c6bc0;font-weight:600;flex-shrink:0">✓ 已选</span>':'')
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
      if(!names.length) return '<div style="color:var(--m-text-sec);font-size:13px;padding:12px 0">尚未分配，点「⚡ 自动分配」或手动填写</div>';
      var self = this;
      return names.map(function(n){
        var pn = String(n).replace(/'/g,"\\'");
        var avatar = String(n||'?').charAt(0);
        return '<div class="m-fj-result-card">'
          + '<div class="m-fj-avatar">'+escHtml(avatar)+'</div>'
          + '<div class="m-fj-result-name">'+escHtml(n)+'</div>'
          + '<input type="text" class="m-fj-range-input" value="'+escHtml(ranges[n])+'" '
          + 'oninput="WB.mobile.fjUpdateRange(\''+pn+'\',this.value)" '
          + 'placeholder="如 1-10 或 1-5,11-15"></div>';
      }).join('');
    },

    // 更新某个剪辑师的分集范围（支持逗号分隔多段，如 "1-5,11-15"）
    fjUpdateRange: function(name, value){
      if(!this._fj.ranges) this._fj.ranges = {};
      this._fj.ranges[name] = value;
    },

    // 解析 "1-5,11-15" 等多段范围为 {集号: 剪辑师}（供保存用）
    _parseRangeToAssign: function(rangeStr, person){
      // 复用公共分集工具（支持逗号分隔多段）
      return window.FenjiCore ? FenjiCore.rangeToAssign(rangeStr, person) : {};
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
          var pn = String(n).replace(/'/g,"\\'");
          return '<div class="m-fj-person-chip'+(checked?' selected':'')+'" onclick="WB.mobile.fjTogglePerson(\''+pn+'\')">'+escHtml(n)+'</div>';
        }).join('');
      }
      this._updateFjSelectedCount();
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
            var pn = String(n).replace(/'/g,"\\'");
            return '<div class="m-fj-person-chip'+(checked?' selected':'')+'" onclick="WB.mobile.fjTogglePerson(\''+pn+'\')">'+escHtml(n)+'</div>';
          }).join('');
          self._updateFjSelectedCount();
        }
      }catch(e){
        var el2 = document.getElementById('m-fj-persons');
        if(el2) el2.innerHTML = '<div style="color:var(--m-text-sec);font-size:13px">加载失败</div>';
      }
    },

    // 更新"已选 N 人"统计
    _updateFjSelectedCount: function(){
      var el = document.getElementById('m-fj-selected-count');
      if(!el) return;
      var n = (this._fj.selected || []).length;
      el.textContent = n ? '（已选 '+n+' 人）' : '';
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
          var pn = String(n).replace(/'/g,"\\'");
          return '<div class="m-fj-person-chip'+(checked?' selected':'')+'" onclick="WB.mobile.fjTogglePerson(\''+pn+'\')">'+escHtml(n)+'</div>';
        }).join('');
      }
      this._updateFjSelectedCount();
    },

    fjAssign: function(){
      var total = this._fj.total;
      var selected = this._fj.selected;
      if(total<=0){ toast('请设置总集数','warning'); return; }
      if(!selected.length){ toast('请选择剪辑师','warning'); return; }
      // 复用公共分集工具（与桌面端同源，避免算法漂移）
      var ranges = window.FenjiCore ? FenjiCore.splitEpisodes(total, selected.slice()) : this._fj.ranges;
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
    if(s.indexOf('待提交')>=0) return 2;
    if(s.indexOf('审中')>=0 || s.indexOf('审核')>=0) return 3;   // 审核中 / N审中
    if(s.indexOf('修改')>=0) return 4;
    if(s.indexOf('交付')>=0) return 5;
    if(s.indexOf('质检')>=0) return 6;
    if(s.indexOf('完成')>=0) return 7;
    return -1;
  }

  window.WB = WB;
})();
