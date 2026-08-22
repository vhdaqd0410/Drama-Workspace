/* wb-features.js — 新增功能模块：排期看板 / 剪辑师视图 / 离线只读缓存
 * 全部挂在 window.WB 命名空间下，避免污染全局。
 * 依赖：wb-shared.js 先加载（提供 WB.api / WB.escHtml / WB.htm / WB.toast）。
 */
(function(){
  var WB = window.WB || (window.WB = {});
  var escHtml = WB.escHtml || function(s){ return String(s==null?'':s); };
  var htm = escHtml;
  var api = WB.api || function(){ throw new Error('api not ready'); };
  var toast = WB.toast || function(){};

  /* ============================================================
   * 离线只读缓存
   * ============================================================ */
  var OFFLINE_KEY = 'wb_offline_cache_v1';
  var OFFLINE_BADGE_ID = 'wbOfflineBadge';

  var offline = {
    _data: null,
    _enabled: false,

    // 拉取并缓存离线数据（项目+待办+分集）
    async refresh(){
      try{
        var d = await api('GET','/api/offline/cache');
        if(d && d.ok){
          this._data = d;
          localStorage.setItem(OFFLINE_KEY, JSON.stringify(d));
          return true;
        }
      }catch(e){}
      return false;
    },

    // 启用离线模式：若有缓存则用缓存，否则先尝试拉取
    async enable(){
      var cached = localStorage.getItem(OFFLINE_KEY);
      if(cached){
        try{ this._data = JSON.parse(cached); }catch(_){}
      }
      if(!this._data){
        var ok = await this.refresh();
        if(!ok){ toast('离线模式：无法获取数据缓存','warning'); return false; }
      }
      this._enabled = true;
      this._showBadge(true);
      toast('离线只读模式已启用','info');
      // 切换到项目看板展示缓存
      if(typeof WB.offlineRender === 'function') WB.offlineRender();
      return true;
    },

    disable(){
      this._enabled = false;
      this._showBadge(false);
      // 退出离线后恢复实时看板
      if(typeof loadProjects === 'function'){
        try{ loadProjects(); }catch(_){}
      }
      toast('已退出离线模式','info');
    },

    isEnabled(){ return this._enabled; },
    getData(){ return this._data; },

    _showBadge(on){
      var el = document.getElementById(OFFLINE_BADGE_ID);
      if(on && !el){
        var b = document.createElement('div');
        b.id = OFFLINE_BADGE_ID;
        b.style.cssText = 'position:fixed;left:12px;bottom:12px;z-index:23000;background:#1d1d1f;color:#fff;padding:8px 12px;border-radius:8px;font-size:12px;box-shadow:0 4px 14px rgba(0,0,0,.25);display:flex;align-items:center;gap:8px';
        b.innerHTML = '📴 离线只读'
          + '<button onclick="WB.offline.disable()" style="background:none;border:none;color:#ffd60a;cursor:pointer;font-size:11px">退出</button>';
        document.body.appendChild(b);
      } else if(!on && el){
        el.remove();
      }
    }
  };

  // 离线模式：渲染项目看板（只读，从缓存）
  WB.offlineRender = function(){
    var data = offline.getData();
    var target = document.getElementById('dashboardContent') || document.querySelector('#tab-dashboard');
    if(!data) return;
    var projects = data.projects || [];
    var html = '<div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;padding:10px 14px;background:#1d1d1f;color:#fff;border-radius:10px">'
      + '<span>📴 离线只读模式 · 缓存于 ' + escHtml(data.cached_at||'') + '</span>'
      + '<span style="margin-left:auto;font-size:12px;opacity:.8">' + projects.length + ' 个项目 · 仅可查看</span></div>';
    html += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px">';
    projects.forEach(function(p){
      var plan = p.episode_plan || {};
      var edCount = Object.keys(plan).length;
      html += '<div style="background:#fff;border:1px solid #e5e5ea;border-radius:12px;padding:14px">'
        + '<div style="font-weight:600;font-size:14px">' + escHtml(p.name) + '</div>'
        + '<div style="font-size:12px;color:#86868b;margin-top:4px">'
        + '状态：' + escHtml(p.custom_status||'未设置')
        + ' · 集数：' + (p.current_episodes||0) + '/' + (p.total_episodes||0)
        + ' · 分集：' + edCount + ' 集</div>'
        + (p.due_date ? '<div style="font-size:12px;color:#b58100;margin-top:4px">📅 截止 ' + escHtml(p.due_date) + '</div>' : '')
        + '</div>';
    });
    html += '</div>';
    target.innerHTML = html;
    // 切到 dashboard tab
    if(typeof switchTab === 'function') switchTab('dashboard');
  };

  // 离线入口（可从设置或命令面板调用）
  WB.offline = offline;
  WB.toggleOffline = function(){
    if(offline.isEnabled()) offline.disable();
    else offline.enable();
  };

  /* ============================================================
   * 排期看板（甘特图）
   * ============================================================ */
  /* ============================================================
   * 剪辑师个人视图
   * ============================================================ */
  var editor = {
    _data: [],
    _selected: '',
    _search: '',          // 项目名搜索关键词

    async load(){
      var el = document.getElementById('editorContent');
      if(!el) return;
      el.innerHTML = '<div style="text-align:center;padding:60px;color:#86868b">⏳ 加载剪辑师视图...</div>';
      try{
        var d = await api('GET','/api/editor/view');
        if(!d || !d.ok){ el.innerHTML = '<div style="color:#ff3b30">加载失败</div>'; return; }
        this._data = d.editors || [];
        this._render(el);
      }catch(e){
        el.innerHTML = '<div style="color:#ff3b30">加载失败: '+escHtml(e.message)+'</div>';
      }
    },

    select(name){
      this._selected = name || '';
      this._render(document.getElementById('editorContent'));
    },

    setSearch(value){
      this._search = (value||'').trim();
      this._render(document.getElementById('editorContent'));
    },

    async backfillCompleted(){
      if(!confirm('确认执行？\n\n将把已移入「00已完成」目录、但状态尚未设置（未设置）的项目，\n批量补写状态为「已完成」，使首页/剪辑师/看板口径一致。\n\n确认继续？')) return;
      try{
        var d = await api('POST','/api/editor/backfill_completed');
        if(d && d.ok){
          toast('✅ ' + (d.message || ('已补齐 ' + (d.updated||0) + ' 个项目状态')), 'success');
          this.load();
        } else {
          toast((d&&d.message)||'补齐失败','error');
        }
      }catch(e){
        toast('❌ 补齐失败: '+e.message,'error');
      }
    },

    _render(el){
      var editors = this._data;
      var sel = this._selected;
      // 侧边选择器
      var html = '<div style="display:flex;gap:12px;margin-bottom:14px;align-items:center">'
        + '<h3 style="margin:0;font-size:16px">✂️ 剪辑师个人视图</h3>'
        + '<span style="font-size:12px;color:#86868b">按剪辑师查看其负责项目的集数进度</span>'
        + '<div style="flex:1"></div>'
        + '<select onchange="WB.editor.select(this.value)" style="padding:6px 10px;border:1px solid #e5e5ea;border-radius:6px;font-size:13px">'
        + '<option value="">— 选择剪辑师 —</option>'
        + editors.map(function(ed){ return '<option value="'+escHtml(ed.name)+'"'+(ed.name===sel?' selected':'')+'>'+escHtml(ed.name)+'（'+ed.project_count+'项目/'+ed.episode_count+'集）</option>'; }).join('')
        + '</select>'
        + '<button class="btn btn-sm" onclick="WB.editor.load()">🔄 刷新</button>'
        + '<button class="btn btn-sm" title="把已移入 00已完成 目录但状态未设置的项目，一键补写为已完成" onclick="WB.editor.backfillCompleted()">✅ 补齐已完成状态</button></div>';

      if(!sel){
        // 汇总卡片
        html += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px">';
        editors.forEach(function(ed){
          var pct = ed.episode_count ? Math.round(ed.done_count*100/ed.episode_count) : 0;
          html += '<div onclick="WB.editor.select(\''+String(ed.name).replace(/'/g,"\\'")+'\')" style="background:#fff;border:1px solid #e5e5ea;border-radius:12px;padding:14px;cursor:pointer">'
            + '<div style="font-size:15px;font-weight:600">👤 '+escHtml(ed.name)+'</div>'
            + '<div style="font-size:12px;color:#86868b;margin-top:6px">'+ed.project_count+' 项目 · '+ed.episode_count+' 集</div>'
            + '<div style="font-size:12px;margin-top:4px">已完成 <b style="color:#34c759">'+ed.done_count+'</b> 集 ('+pct+'%)</div>'
            + '</div>';
        });
        html += '</div>';
        el.innerHTML = html;
        return;
      }

      var ed = editors.find(function(e){ return e.name === sel; });
      if(!ed){ el.innerHTML = '<div style="color:#86868b;padding:40px;text-align:center">未找到该剪辑师</div>'; return; }

      // 搜索过滤
      var kw = (this._search||'').toLowerCase();
      var list = ed.projects.filter(function(p){
        if(!kw) return true;
        return String(p.project||'').toLowerCase().indexOf(kw) >= 0;
      });
      // 排序：未完成在前，按交付流程顺序（分集→剪辑→审核→修改→交付→质检），已完成放最后。
      // 未设置(-1)视为流程最前，已完成(6)放最后。
      list.sort(function(a,b){
        var ao = _workflowOrder(a.status), bo = _workflowOrder(b.status);
        if(ao!==bo) return ao-bo;
        return String(a.project||'').localeCompare(String(b.project||''));
      });

      // 该剪辑师项目列表
      html += '<div style="margin-bottom:10px;display:flex;align-items:center;gap:8px;flex-wrap:wrap">'
        + '<button class="btn btn-sm" onclick="WB.editor.select(\'\')">⬅ 返回列表</button>'
        + '<div style="flex:1;min-width:160px"></div>'
        + '<input type="text" placeholder="🔍 搜索项目名..." value="'+escHtml(this._search)+'" oninput="WB.editor.setSearch(this.value)" style="padding:6px 10px;border:1px solid #e5e5ea;border-radius:6px;font-size:12px;min-width:160px">'
        + '</div>'
        + '<div style="font-size:11px;color:#86868b;margin:0 0 8px 2px">共 ' + list.length + ' 个项目，按流程排序（未完成在前）' + (kw ? '（匹配「'+escHtml(this._search)+'」）' : '') + '</div>';
      html += '<div style="background:#fff;border:1px solid #e5e5ea;border-radius:12px;overflow:hidden">';
      if(list.length === 0){
        html += '<div style="padding:30px;text-align:center;color:#86868b">没有匹配的项目</div>';
      }
      list.forEach(function(p, i){
        html += '<div style="border-bottom:1px solid #f0f0f0;padding:12px 14px">'
          + '<div style="display:flex;align-items:center;gap:10px;cursor:pointer" onclick="var d=document.getElementById(\'ed-det-\'+this.dataset.i);if(d)d.style.display=d.style.display===\'none\'?\'\':\'none\'" data-i="'+i+'">'
          + '<span style="font-size:14px;font-weight:600;flex:1">'+escHtml(p.project)+'</span>'
          + '<span class="badge '+_statusCls(p.status).cls+'" style="font-size:10px">'+escHtml(_statusCls(p.status).text)+'</span>'
          + '<span style="font-size:12px;color:#86868b">'+p.done_count+'/'+p.total_count+' 集</span>'
          + '<span style="color:#86868b">▾</span></div>'
          + '<div id="ed-det-'+i+'" style="display:none;margin-top:8px;padding-left:8px">'
          + '<div style="font-size:11px;color:#86868b;margin-bottom:4px">负责集号（共 '+p.total_count+' 集）：</div>'
          + '<div style="font-size:12px;line-height:1.8">'
          + (p.episodes||[]).map(function(ep){
              var done = (p.done||[]).indexOf(ep) >= 0;
              return '<span style="display:inline-block;margin:0 3px 3px 0;padding:1px 6px;border-radius:6px;'+(done?'background:#e2efda;color:#006100':'background:#fde2e2;color:#c5221f')+'">'+(done?'✅':'❌')+' 第'+ep+'集</span>';
            }).join('')
          + '</div></div></div>';
      });
      html += '</div>';
      el.innerHTML = html;
    }
  };
  WB.editor = editor;

  /* ===== 内部工具 ===== */
  // 交付流程顺序：分集(0)→剪辑(1)→审核(2)→修改(3)→交付(4)→质检(5)→已完成(6)
  // 未设置/未知返回 -1（视为流程最前）；已完成返回 6（放最后）。
  function _workflowOrder(status){
    var s = String(status||'').trim();
    if(!s) return -1;
    var map = { '分集':0,'分集中':0, '剪辑':1,'剪辑中':1, '审核':2,'审核中':2,
                '修改':3,'修改中':3, '交付':4,'交付中':4,'待交付':4,
                '质检':5,'待质检':5,'质检中':5, '完成':6,'已完成':6 };
    if(map[s] !== undefined) return map[s];
    if(s.indexOf('分集')>=0) return 0;
    if(s.indexOf('剪辑')>=0) return 1;
    if(s.indexOf('审核')>=0) return 2;
    if(s.indexOf('修改')>=0) return 3;
    if(s.indexOf('交付')>=0) return 4;
    if(s.indexOf('质检')>=0) return 5;
    if(s.indexOf('完成')>=0) return 6;
    return -1;
  }
  function _statusCls(status){
    var s = String(status||'').trim();
    if(!s) return { cls:'default', color:'#c0c0c5', text:'—' };
    if(s.indexOf('完成')>=0) return { cls:'completed', color:'#34c759', text:s };
    if(s.indexOf('质检')>=0) return { cls:'zhijian', color:'#0071e3', text:s };
    if(s.indexOf('交付')>=0) return { cls:'jiaofu', color:'#b58100', text:s };
    if(s.indexOf('修改')>=0) return { cls:'xiugai', color:'#ff9500', text:s };
    if(s.indexOf('审核')>=0) return { cls:'shenhe', color:'#af52de', text:s };
    if(s.indexOf('剪辑')>=0) return { cls:'jianji', color:'#ff3b30', text:s };
    if(s.indexOf('分集')>=0) return { cls:'fenji', color:'#86868b', text:s };
    return { cls:'default', color:'#86868b', text:s };
  }

  window.WB = WB;
})();
