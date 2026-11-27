// 分秒帧窗口内注入的整套界面（工具条 + 分集面板 + 上传监控 + 复制/跳转）
// 由 pywebview 在每次页面加载完成后 evaluate_js 注入，作用域仅限分秒帧窗口。
//
// 为什么独立成文件而不是写在 Python 字符串里：
//   1. 可以 node --check 做语法校验，也能被测试直接读；
//   2. 界面代码长了之后，Python 里的 r"""...""" 几乎无法维护。
//
// 设计要点：
//   - 毛玻璃浮层，右下角常驻，默认半透明、hover 变实，尽量不挡分秒帧自己的控件
//   - 分集按「剪辑师 + 集号区间」聚合展示（第 3-6 集），不是一集一行
//   - 搜索框一个输入口，自动识别：集号 / 人名 / 分秒帧项目ID
//   - 复制链接与跳转都是自建浮层，不用 window.prompt（WebView2 里样式与可用性都不稳）

(function () {
  // node 测试环境：没有 DOM，只导出纯函数供单测，不碰 document
  if (typeof window === 'undefined') {
    if (typeof module !== 'undefined' && module.exports) {
      module.exports = {
        toRanges: toRanges,
        groupByEditor: groupByEditor,
        fmtRanges: fmtRanges
      };
    }
    return;
  }

  if (window.__FM_UI_READY__) { return; }
  window.__FM_UI_READY__ = true;

  // ============ 状态 ============
  var S = {
    data: null,          // 后端返回的分集数据
    q: '',               // 当前搜索词
    loading: false,
    panelOpen: false,
    jumpOpen: false,
    lastFmId: ''         // 上次按项目ID查询的ID（防重复请求）
  };

  // ============ 工具 ============
  function el(id) { return document.getElementById(id); }

  function toast(msg) {
    var tip = el('__fm_tip');
    if (!tip) { return; }
    tip.textContent = msg;
    tip.classList.add('on');
    clearTimeout(window.__fmTipTimer);
    window.__fmTipTimer = setTimeout(function () {
      tip.classList.remove('on');
    }, 3000);
  }

  function currentFmId() {
    // 分秒帧项目页形如 https://app.mediatrack.cn/projects/<id>/files
    var m = String(location.href || '').match(/\/projects\/(\d+)/);
    return m ? m[1] : '';
  }

  // ============ 样式 ============
  function injectStyle() {
    if (el('__fm_style')) { return; }
    var st = document.createElement('style');
    st.id = '__fm_style';
    st.textContent = [
      '#__fm_bar{position:fixed;right:16px;bottom:16px;z-index:2147483647;',
      'display:flex;align-items:center;gap:4px;padding:6px;border-radius:18px;',
      'background:rgba(255,255,255,.62);',
      'backdrop-filter:blur(20px) saturate(180%);-webkit-backdrop-filter:blur(20px) saturate(180%);',
      'border:1px solid rgba(255,255,255,.72);',
      'box-shadow:0 8px 28px rgba(0,0,0,.14);',
      'font:12.5px/1.4 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif;',
      'opacity:.86;transition:opacity .18s,transform .18s}',
      '#__fm_bar:hover{opacity:1}',

      '.__fm_btn{display:flex;align-items:center;gap:5px;padding:6px 11px;border-radius:13px;',
      'border:0;background:transparent;color:#1d1d1f;cursor:pointer;white-space:nowrap;',
      'font:12.5px/1.4 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif;transition:background .15s}',
      '.__fm_btn:hover{background:rgba(0,113,227,.12);color:#0071e3}',
      '.__fm_btn.on{background:rgba(0,113,227,.16);color:#0071e3;font-weight:600}',

      '#__fm_up{display:none;margin:0 4px;padding:4px 10px;border-radius:11px;',
      'background:rgba(0,113,227,.9);color:#fff;font-size:11.5px;font-weight:600;white-space:nowrap}',

      // 面板
      '#__fm_panel{position:fixed;right:16px;bottom:66px;width:392px;max-height:68vh;z-index:2147483647;',
      'display:none;flex-direction:column;border-radius:16px;overflow:hidden;',
      'background:rgba(255,255,255,.72);',
      'backdrop-filter:blur(26px) saturate(180%);-webkit-backdrop-filter:blur(26px) saturate(180%);',
      'border:1px solid rgba(255,255,255,.78);box-shadow:0 14px 44px rgba(0,0,0,.18);',
      'font:13px/1.5 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif;color:#1d1d1f}',
      '#__fm_panel.on{display:flex}',

      '.__fm_head{display:flex;align-items:center;gap:8px;padding:12px 14px 10px;',
      'border-bottom:1px solid rgba(0,0,0,.06)}',
      '.__fm_title{flex:1;min-width:0;font-size:13px;font-weight:600;overflow:hidden;',
      'text-overflow:ellipsis;white-space:nowrap}',
      '.__fm_sub{font-size:11px;color:#6b7280;margin-top:2px;font-weight:400;overflow:hidden;',
      'text-overflow:ellipsis;white-space:nowrap}',
      '.__fm_x{border:0;background:transparent;cursor:pointer;font-size:15px;color:#9ca3af;',
      'padding:2px 4px;border-radius:8px;line-height:1}',
      '.__fm_x:hover{background:rgba(0,0,0,.06);color:#374151}',

      '.__fm_search{padding:9px 12px;border-bottom:1px solid rgba(0,0,0,.06)}',
      '.__fm_input{width:100%;box-sizing:border-box;padding:8px 11px;border-radius:10px;',
      'border:1px solid rgba(0,0,0,.1);background:rgba(255,255,255,.85);',
      'font:12.5px/1.4 inherit;color:#1d1d1f;outline:none;transition:border-color .15s,box-shadow .15s}',
      '.__fm_input:focus{border-color:#0071e3;box-shadow:0 0 0 3px rgba(0,113,227,.13)}',
      '.__fm_hint{padding:6px 12px 0;font-size:10.5px;color:#9ca3af}',

      '.__fm_list{flex:1;overflow:auto;padding:4px 0 6px}',
      '.__fm_row{padding:9px 14px;border-bottom:1px solid rgba(0,0,0,.045);transition:background .12s}',
      '.__fm_row:last-child{border-bottom:0}',
      '.__fm_row:hover{background:rgba(0,113,227,.06)}',
      '.__fm_row.hit{background:rgba(255,214,10,.22)}',
      '.__fm_rowtop{display:flex;align-items:baseline;gap:8px}',
      '.__fm_ed{font-size:13px;font-weight:600;color:#111827;flex:1;min-width:0;',
      'overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
      '.__fm_cnt{font-size:11px;color:#6b7280;background:rgba(0,0,0,.05);padding:1px 7px;',
      'border-radius:9px;white-space:nowrap}',
      '.__fm_ranges{font-size:11.5px;color:#4b5563;margin-top:3px;line-height:1.55;word-break:break-word}',
      '.__fm_row.none .__fm_ed{color:#9ca3af;font-weight:400}',
      '.__fm_empty{padding:26px 16px;text-align:center;font-size:12px;color:#9ca3af;line-height:1.7}',

      // 跳转浮层
      '#__fm_jump{position:fixed;right:16px;bottom:66px;width:392px;z-index:2147483647;',
      'display:none;flex-direction:column;gap:10px;padding:14px;border-radius:16px;',
      'background:rgba(255,255,255,.75);',
      'backdrop-filter:blur(26px) saturate(180%);-webkit-backdrop-filter:blur(26px) saturate(180%);',
      'border:1px solid rgba(255,255,255,.8);box-shadow:0 14px 44px rgba(0,0,0,.18);',
      'font:13px/1.5 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif;color:#1d1d1f}',
      '#__fm_jump.on{display:flex}',
      '.__fm_jrow{display:flex;gap:8px}',
      '.__fm_jbtn{border:0;border-radius:9px;padding:7px 14px;cursor:pointer;font:12.5px inherit;',
      'background:#0071e3;color:#fff;font-weight:600}',
      '.__fm_jbtn.ghost{background:rgba(0,0,0,.06);color:#374151;font-weight:400}',

      // 提示
      '#__fm_tip{position:fixed;right:16px;bottom:96px;z-index:2147483647;max-width:76vw;',
      'padding:9px 13px;border-radius:12px;background:rgba(28,28,32,.9);color:#fff;',
      'font:12.5px/1.5 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif;',
      'box-shadow:0 6px 20px rgba(0,0,0,.26);word-break:break-all;',
      'opacity:0;transform:translateY(6px);pointer-events:none;transition:opacity .18s,transform .18s}',
      '#__fm_tip.on{opacity:1;transform:none}'
    ].join('');
    document.head.appendChild(st);
  }

  // ============ 区间聚合 ============
  // 把同一剪辑师的连续集号压成区间：[1,2,5,6,7] -> [[1,2],[5,7]]
  function toRanges(nums) {
    var out = [];
    nums.forEach(function (n) {
      var last = out[out.length - 1];
      if (last && n === last[1] + 1) { last[1] = n; }
      else { out.push([n, n]); }
    });
    return out;
  }

  function groupByEditor(items) {
    var map = {}, order = [];
    (items || []).forEach(function (it) {
      var ed = String(it.editor || '').trim();
      var key = ed || '未分配';
      if (!map[key]) { map[key] = []; order.push(key); }
      var n = parseInt(it.ep, 10);
      map[key].push(isNaN(n) ? null : n);
    });
    var groups = [];
    order.forEach(function (key) {
      var nums = (map[key] || []).filter(function (x) { return x !== null; })
        .sort(function (a, b) { return a - b; });
      // 去重，防止同一集号重复录入导致区间算错
      nums = nums.filter(function (v, i) { return i === 0 || v !== nums[i - 1]; });
      groups.push({
        editor: key,
        isNone: (key === '未分配'),
        ranges: toRanges(nums),
        count: nums.length
      });
    });
    // 按起始集号排序，方便对着集数进度看
    groups.sort(function (a, b) {
      var ra = a.ranges.length ? a.ranges[0][0] : 999999;
      var rb = b.ranges.length ? b.ranges[0][0] : 999999;
      return ra - rb;
    });
    return groups;
  }

  function fmtRanges(ranges) {
    if (!ranges.length) { return '—'; }
    return ranges.map(function (r) {
      return (r[0] === r[1]) ? ('第 ' + r[0] + ' 集') : ('第 ' + r[0] + '-' + r[1] + ' 集');
    }).join('，');
  }

  // ============ 渲染 ============
  function render() {
    var list = el('__fm_list');
    if (!list) { return; }
    var d = S.data;

    if (!d || !d.ok) {
      list.innerHTML = '<div class="__fm_empty">'
        + (d && d.message ? d.message : '未关联项目')
        + '<br><span style="font-size:11px;opacity:.8">从工作台项目卡片打开分秒帧即可关联</span>'
        + '</div>';
      return;
    }

    var groups = groupByEditor(d.items);
    var q = String(S.q || '').trim();

    if (q) {
      var isEp = /^\d{1,4}$/.test(q);
      groups = groups.filter(function (g) {
        if (isEp) {
          var ep = parseInt(q, 10);
          return g.ranges.some(function (r) { return ep >= r[0] && ep <= r[1]; });
        }
        return g.editor.toLowerCase().indexOf(q.toLowerCase()) >= 0;
      });
    }

    if (!groups.length) {
      list.innerHTML = '<div class="__fm_empty">'
        + (q ? '没有匹配的集号或人名' : '该项目还没有分集分配记录')
        + '</div>';
      return;
    }

    var html = '';
    groups.forEach(function (g) {
      html += '<div class="__fm_row' + (g.isNone ? ' none' : '') + '">'
        +   '<div class="__fm_rowtop">'
        +     '<span class="__fm_ed">' + esc(g.editor) + '</span>'
        +     '<span class="__fm_cnt">' + g.count + ' 集</span>'
        +   '</div>'
        +   '<div class="__fm_ranges">' + esc(fmtRanges(g.ranges)) + '</div>'
        + '</div>';
    });
    list.innerHTML = html;
  }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function setHead(d) {
    var t = el('__fm_title');
    var s = el('__fm_sub');
    if (!t) { return; }
    if (d && d.ok) {
      t.textContent = d.project || '分集';
      t.title = d.project || '';
      var bits = [];
      if (d.count) { bits.push(d.count + ' 集有分配'); }
      if (d.department) { bits.push(d.department.replace('AI漫剧', '')); }
      if (d.custom_status) { bits.push(d.custom_status); }
      if (d.fm_id) { bits.push('ID ' + d.fm_id); }
      if (s) { s.textContent = bits.join(' · '); }
    } else {
      t.textContent = '分集';
      if (s) { s.textContent = ''; }
    }
  }

  // ============ 数据 ============
  function loadEpisodes(fmId) {
    var api = window.pywebview && window.pywebview.api;
    var list = el('__fm_list');
    if (!api || !api.get_episodes) {
      if (list) { list.innerHTML = '<div class="__fm_empty">桥未就绪，请重试</div>'; }
      return;
    }
    if (S.loading) { return; }
    S.loading = true;
    if (list) { list.innerHTML = '<div class="__fm_empty">加载中…</div>'; }

    // 优先用当前页面 URL 里的项目ID，用户跳到别的项目也能对上
    var id = fmId !== undefined ? fmId : currentFmId();

    api.get_episodes('', id || '').then(function (d) {
      S.loading = false;
      S.data = d;
      setHead(d);
      render();
    }).catch(function (e) {
      S.loading = false;
      S.data = { ok: false, message: '加载失败: ' + (e && e.message ? e.message : e) };
      setHead(null);
      render();
    });
  }

  // ============ 分集面板 ============
  function buildPanel() {
    if (el('__fm_panel')) { return; }
    var p = document.createElement('div');
    p.id = '__fm_panel';
    p.innerHTML =
        '<div class="__fm_head">'
      +   '<div style="flex:1;min-width:0">'
      +     '<div class="__fm_title" id="__fm_title">分集</div>'
      +     '<div class="__fm_sub" id="__fm_sub"></div>'
      +   '</div>'
      +   '<button class="__fm_x" id="__fm_close">✕</button>'
      + '</div>'
      + '<div class="__fm_search">'
      +   '<input class="__fm_input" id="__fm_q" placeholder="集号 / 人名 / 分秒帧项目ID">'
      +   '<div class="__fm_hint">输入 12 查集号；输入姓名查该人所有集；输入项目ID（长数字）切换项目</div>'
      + '</div>'
      + '<div class="__fm_list" id="__fm_list"></div>';
    document.body.appendChild(p);

    p.querySelector('#__fm_close').onclick = function () { togglePanel(false); };

    var input = p.querySelector('#__fm_q');
    var timer = null;
    input.oninput = function () {
      var v = this.value;
      S.q = v;
      // 长数字视为分秒帧项目ID：防抖后切换数据源
      if (/^\d{7,}$/.test(String(v).trim())) {
        clearTimeout(timer);
        var id = String(v).trim();
        timer = setTimeout(function () {
          if (S.lastFmId === id) { return; }
          S.lastFmId = id;
          loadEpisodes(id);
        }, 420);
        return;
      }
      render();
    };
    input.onkeydown = function (e) {
      if (e.key === 'Enter' && /^\d{7,}$/.test(String(this.value).trim())) {
        clearTimeout(timer);
        S.lastFmId = String(this.value).trim();
        loadEpisodes(S.lastFmId);
      }
    };
  }

  function togglePanel(force) {
    buildPanel();
    var p = el('__fm_panel');
    var btn = el('__fm_btn_eps');
    if (!p) { return; }
    var willOpen = (force === undefined) ? !p.classList.contains('on') : !!force;
    if (willOpen) {
      p.classList.add('on');
      if (btn) { btn.classList.add('on'); }
      S.panelOpen = true;
      // 每次打开都重新取，跟着当前页面项目走
      S.lastFmId = '';
      var q = el('__fm_q');
      if (q) { q.value = ''; }
      S.q = '';
      loadEpisodes();
    } else {
      p.classList.remove('on');
      if (btn) { btn.classList.remove('on'); }
      S.panelOpen = false;
    }
  }

  // ============ 跳转浮层 ============
  function buildJump() {
    if (el('__fm_jump')) { return; }
    var j = document.createElement('div');
    j.id = '__fm_jump';
    j.innerHTML =
        '<div style="font-size:12.5px;font-weight:600">跳转到分秒帧链接</div>'
      + '<input class="__fm_input" id="__fm_jump_url" placeholder="https://app.mediatrack.cn/projects/…">'
      + '<div class="__fm_jrow">'
      +   '<button class="__fm_jbtn" id="__fm_jump_ok">打开</button>'
      +   '<button class="__fm_jbtn ghost" id="__fm_jump_cancel">取消</button>'
      + '</div>'
      + '<div style="font-size:10.5px;color:#9ca3af">只支持 mediatrack.cn 的地址</div>';
    document.body.appendChild(j);

    var input = j.querySelector('#__fm_jump_url');
    j.querySelector('#__fm_jump_ok').onclick = function () {
      var u = String(input.value || '').trim();
      if (!u) { return; }
      if (!/^https?:\/\/([\w.-]+\.)?mediatrack\.cn(\/|$)/i.test(u)) {
        toast('只支持 mediatrack.cn 的链接');
        return;
      }
      location.href = u;
    };
    j.querySelector('#__fm_jump_cancel').onclick = function () { toggleJump(false); };
    input.onkeydown = function (e) {
      if (e.key === 'Enter') { j.querySelector('#__fm_jump_ok').click(); }
    };
  }

  function toggleJump(force) {
    buildJump();
    var j = el('__fm_jump');
    if (!j) { return; }
    var willOpen = (force === undefined) ? !j.classList.contains('on') : !!force;
    if (willOpen) {
      togglePanel(false);
      j.classList.add('on');
      var input = el('__fm_jump_url');
      if (input) {
        input.value = location.href || '';
        setTimeout(function () { input.focus(); input.select(); }, 30);
      }
      S.jumpOpen = true;
    } else {
      j.classList.remove('on');
      S.jumpOpen = false;
    }
  }

  // ============ 复制链接 ============
  function copyLink() {
    var u = location.href;
    var done = false;
    var timer = setTimeout(function () {
      if (done) { return; }
      done = true;
      fallbackCopy();
    }, 1500);

    function fallbackCopy() {
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(u).then(
            function () { toast('已复制：' + u); },
            function () { manualCopy(); }
          );
        } else { manualCopy(); }
      } catch (e) { manualCopy(); }
    }
    function manualCopy() {
      var ta = document.createElement('textarea');
      ta.value = u;
      ta.style.cssText = 'position:fixed;left:-9999px;top:0';
      document.body.appendChild(ta);
      ta.select();
      var ok = false;
      try { ok = document.execCommand('copy'); } catch (e) {}
      document.body.removeChild(ta);
      toast(ok ? ('已复制：' + u) : '复制失败，请手动选中地址');
    }

    try {
      if (window.pywebview && window.pywebview.api && window.pywebview.api.copy_clipboard) {
        window.pywebview.api.copy_clipboard(u).then(function (r) {
          if (done) { return; }
          done = true;
          clearTimeout(timer);
          if (r && r.ok) { toast('已复制：' + u); }
          else { fallbackCopy(); }
        }).catch(function () {
          if (done) { return; }
          done = true;
          clearTimeout(timer);
          fallbackCopy();
        });
        return;
      }
    } catch (e) {}
    if (!done) { done = true; clearTimeout(timer); }
    fallbackCopy();
  }

  // ============ 工具条 ============
  function buildBar() {
    if (el('__fm_bar')) { return; }
    var bar = document.createElement('div');
    bar.id = '__fm_bar';
    bar.innerHTML =
        '<div id="__fm_up"></div>'
      + '<button class="__fm_btn" id="__fm_btn_eps">📋 分集</button>'
      + '<button class="__fm_btn" id="__fm_btn_copy">🔗 复制</button>'
      + '<button class="__fm_btn" id="__fm_btn_jump">🧭 跳转</button>';
    document.body.appendChild(bar);

    var tip = document.createElement('div');
    tip.id = '__fm_tip';
    document.body.appendChild(tip);

    el('__fm_btn_eps').onclick = function () { togglePanel(); };
    el('__fm_btn_copy').onclick = copyLink;
    el('__fm_btn_jump').onclick = function () { toggleJump(); };
  }

  // ============ 上传进度 ============
  var upState = {};
  var lastUpSent = 0;

  function upSummary() {
    var n = 0, loaded = 0, total = 0;
    for (var k in upState) {
      var a = upState[k];
      n++; loaded += a.loaded || 0; total += a.total || 0;
    }
    return { active: n, loaded: loaded, total: total };
  }

  function upPaint() {
    var el2 = el('__fm_up');
    if (!el2) { return; }
    var s = upSummary();
    if (s.active > 0) {
      el2.style.display = 'block';
      var pct = s.total > 0 ? Math.floor(s.loaded * 100 / s.total) : 0;
      el2.textContent = '⬆ ' + (s.total > 0 ? pct + '%' : (s.loaded / 1048576).toFixed(1) + 'MB');
    } else {
      el2.style.display = 'none';
    }
  }

  function upReport(force) {
    var now = Date.now();
    if (!force && now - lastUpSent < 400) { return; }
    lastUpSent = now;
    var s = upSummary();
    try {
      if (window.pywebview && window.pywebview.api && window.pywebview.api.upload_report) {
        window.pywebview.api.upload_report(JSON.stringify(s)).catch(function () {});
      }
    } catch (e) {}
    upPaint();
  }

  function hookUpload() {
    if (window.__fmUploadHook) { upPaint(); return; }
    window.__fmUploadHook = true;
    var XO = XMLHttpRequest.prototype.open;
    var XS = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function (method, url) {
      this.__fmId = 'u' + Math.random().toString(36).slice(2);
      return XO.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function () {
      var xhr = this, id = xhr.__fmId;
      try {
        if (xhr.upload) {
          xhr.upload.addEventListener('progress', function (e) {
            // 只统计真实文件上传（>1MB），避开保存评论等小接口干扰
            if (e && e.total && e.total > 1048576) {
              upState[id] = { loaded: e.loaded || 0, total: e.total || 0 };
              upReport(false);
            }
          });
        }
        xhr.addEventListener('loadend', function () {
          if (upState[id]) { delete upState[id]; upReport(true); }
        });
      } catch (e) {}
      return XS.apply(this, arguments);
    };
  }

  // ============ 初始化 ============
  injectStyle();
  buildBar();
  hookUpload();
})();