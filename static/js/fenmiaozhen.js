// ===== 分秒帧板块（待办清单）=====
// 业务口径（用户确定）：除二部以外的项目全部要传分秒帧。
//   进行中（active_statuses）→ 列在最上面，未填链接的高亮提示补填。
//   已完成 → 折叠区，默认收起。
//
// 为什么不用 iframe：实测 iframe 里点登录必定跳系统浏览器（跨域 iframe 的 window.open
// 冒泡到顶层 WebView，pywebview 把它交给 webbrowser.open）。全局改掉又会把主窗口 14 处
// window.open 一起带走。所以登录/上传统一走软件内独立窗口（实测可正常登录，cookie 持久）。

(function () {
  var state = {
    active: [],
    completed: [],
    stats: {},
    keyword: '',
    onlyMissing: false,
    showCompleted: false,
    currentUrl: '',
    projectName: ''
  };
  window._fmState = state;

  function el(id) { return document.getElementById(id); }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function isFmUrl(url) {
    try {
      var u = new URL(url);
      return /(^|\.)mediatrack\.cn$/i.test(u.hostname);
    } catch (e) { return false; }
  }

  // 部门是否被排除（与后端 exclude_dept_keywords 一致）
  function deptExcluded(dept) {
    var kw = (window._fmCfg && window._fmCfg.exclude_dept_keywords) || ['二部'];
    var d = String(dept || '');
    if (!d.trim()) return false;
    for (var i = 0; i < kw.length; i++) {
      if (kw[i] && d.indexOf(kw[i]) >= 0) return true;
    }
    return false;
  }
  window.fmDeptExcluded = deptExcluded;

  async function ensureCfg() {
    if (window._fmCfg) return window._fmCfg;
    try {
      var d = await api('GET', '/api/fenmiaozhen/config');
      if (d && d.ok) window._fmCfg = d;
    } catch (e) {}
    return window._fmCfg || {};
  }

  window.fmLoadList = async function () {
    await ensureCfg();
    var wrap = el('fmListWrap');
    if (wrap && !state.active.length && !state.completed.length) {
      wrap.innerHTML = '<div class="fm-empty">正在加载…</div>';
    }
    try {
      var d = await api('GET', '/api/fenmiaozhen/board');
      if (!d || !d.ok) throw new Error((d && d.msg) || '接口返回失败');
      state.active = d.active || [];
      state.completed = d.completed || [];
      state.stats = d.stats || {};
    } catch (e) {
      if (wrap) wrap.innerHTML = '<div class="fm-empty">加载失败: ' + esc(e.message) + '</div>';
      return;
    }
    window.fmRenderList();
  };

  window.fmFilterList = function () {
    var inp = el('fmSearch');
    state.keyword = ((inp && inp.value) || '').trim().toLowerCase();
    window.fmRenderList();
  };

  window.fmToggleOnlyMissing = function (chk) {
    state.onlyMissing = !!(chk && chk.checked);
    window.fmRenderList();
  };

  window.fmToggleCompleted = function () {
    state.showCompleted = !state.showCompleted;
    window.fmRenderList();
  };

  function rowHtml(it, isMissing) {
    var nameArg = esc(JSON.stringify(it.name));
    var cls = isMissing ? 'fm-row fm-row-missing' : 'fm-row';
    var badge = isMissing
      ? '<span class="fm-badge miss">未填链接</span>'
      : '<span class="fm-badge ok">已配置</span>';
    var ep = (it.total_episodes ? (it.current_episodes + '/' + it.total_episodes) : '');
    return '<div class="' + cls + '">'
      +   '<div class="fm-row-name" title="' + esc(it.name) + '">' + esc(it.name) + '</div>'
      +   '<div class="fm-row-dept">' + esc((it.department || '').replace('AI漫剧', '')) + '</div>'
      +   '<div class="fm-row-status">' + esc(it.custom_status || '') + '</div>'
      +   '<div class="fm-row-ep">' + esc(ep) + '</div>'
      +   badge
      +   '<div class="fm-row-acts">'
      +     (isMissing
              ? '<button class="btn btn-sm btn-primary" onclick="fmSetLink(' + nameArg + ')">填写链接</button>'
              : '<button class="btn btn-sm btn-primary" onclick="fmOpenFor(' + nameArg + ')">⧉ 打开</button>'
                + '<button class="btn btn-sm" onclick="fmSetLink(' + nameArg + ')">改</button>')
      +     '<button class="btn btn-sm" onclick="fmRemoveLink(' + nameArg + ')">移除</button>'
      +   '</div>'
      + '</div>';
  }

  window.fmRenderList = function () {
    var wrap = el('fmListWrap');
    if (!wrap) return;

    var kw = state.keyword;
    function match(x) {
      if (!kw) return true;
      return String(x.name).toLowerCase().indexOf(kw) >= 0
          || String(x.department || '').toLowerCase().indexOf(kw) >= 0;
    }

    var act = state.active.filter(match);
    if (state.onlyMissing) act = act.filter(function (x) { return !x.has_link; });
    var done = state.completed.filter(match);

    var st = el('fmStatus');
    var s = state.stats || {};
    if (st) {
      st.textContent = '进行中 ' + (s.active || 0) + ' 个'
        + (s.missing ? '（未填链接 ' + s.missing + ' 个）' : '')
        + ' · 已完成 ' + (s.completed || 0) + ' 个';
    }

    var html = '';

    // 顶部工具条
    html += '<div class="fm-tools">'
      + '<label class="fm-chk"><input type="checkbox" id="fmOnlyMissing" '
      + (state.onlyMissing ? 'checked' : '')
      + ' onchange="fmToggleOnlyMissing(this)"> 只看未填链接</label>'
      + '<span class="fm-tools-tip">除二部以外的项目都要传分秒帧</span>'
      + '</div>';

    // 进行中
    html += '<div class="fm-sec-head">🟢 进行中（需传分秒帧）<span class="fm-sec-count">' + act.length + '</span></div>';
    if (!act.length) {
      html += '<div class="fm-empty-sm">'
        + (state.active.length ? '没有匹配的项目' : '当前没有进行中的项目')
        + '</div>';
    } else {
      act.forEach(function (it) { html += rowHtml(it, !it.has_link); });
    }

    // 已完成（折叠）
    html += '<div class="fm-sec-head fm-sec-fold" onclick="fmToggleCompleted()">'
      + '<span class="fm-fold-arrow">' + (state.showCompleted ? '▼' : '▶') + '</span>'
      + '✅ 已完成<span class="fm-sec-count">' + done.length + '</span>'
      + '<span class="fm-sec-hint">点击' + (state.showCompleted ? '收起' : '展开') + '</span>'
      + '</div>';
    if (state.showCompleted) {
      if (!done.length) {
        html += '<div class="fm-empty-sm">没有已完成项目</div>';
      } else {
        done.forEach(function (it) { html += rowHtml(it, false); });
      }
    }

    wrap.innerHTML = html;
  };

  // 打开某个项目的分秒帧（独立窗口 + 复制成片目录）
  window.fmOpenFor = function (name) {
    var it = state.active.concat(state.completed).filter(function (x) { return x.name === name; })[0];
    if (!it || !it.url) { window.fmSetLink(name); return; }
    state.currentUrl = it.url;
    state.projectName = name;
    var pn = el('fmProjName');
    if (pn) pn.textContent = '· ' + name;
    window.fmOpenWindow(it.url, name);
  };

  window.fmSetLink = async function (name) {
    var all = state.active.concat(state.completed);
    var cur = (all.filter(function (x) { return x.name === name; })[0] || {}).url || '';
    var u = prompt('请输入「' + name + '」在分秒帧的审核链接：\n（打开分秒帧项目页后，复制地址栏网址）',
                   cur || 'https://app.mediatrack.cn/');
    if (!u) return;
    u = u.trim();
    if (!isFmUrl(u)) { toast('只允许分秒帧网址（mediatrack.cn）', 'error'); return; }
    try {
      var r = await api('POST', '/api/fenmiaozhen/link/' + encodeURIComponent(name), { url: u });
      if (r && r.ok) {
        toast('✅ 链接已保存', 'success');
        window.fmLoadList();
      } else {
        toast((r && r.msg) || '保存失败', 'error');
      }
    } catch (e) { toast('保存失败: ' + e.message, 'error'); }
  };

  window.fmRemoveLink = async function (name) {
    if (!confirm('确认移除「' + name + '」的分秒帧链接？')) return;
    try {
      var r = await api('DELETE', '/api/fenmiaozhen/link/' + encodeURIComponent(name));
      if (r && r.ok) { toast('已移除', 'success'); window.fmLoadList(); }
      else toast('移除失败', 'error');
    } catch (e) { toast('移除失败: ' + e.message, 'error'); }
  };

  // 打开软件内独立窗口（桌面版）；浏览器访问时新标签页
  window.fmOpenWindow = function (url, project) {
    var target = url || state.currentUrl || 'https://app.mediatrack.cn/';
    var proj = project || state.projectName || '';
    var title = '分秒帧' + (proj ? ' - ' + proj : '');
    if (!isFmUrl(target)) target = 'https://app.mediatrack.cn/';

    if (!window.__IS_DESKTOP__) {
      window.open(target, '_blank');
      return;
    }
    fetch('/api/_self/fenmiaozhen', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: target, title: title, project: proj })
    }).then(function (r) { return r.json(); }).then(function (d) {
      if (d && d.ok) {
        toast(d.path_copied
          ? '✅ 已打开分秒帧窗口，成片目录路径已复制（上传时 Ctrl+V 定位）'
          : '✅ 已打开分秒帧窗口（未找到成片目录，路径未复制）',
          'success', 5000);
      } else {
        toast((d && d.message) || '打开失败', 'error');
      }
    }).catch(function (e) { toast('打开失败: ' + e.message, 'error'); });
  };

  window.fmOpenInBrowser = function () {
    window.open(state.currentUrl || 'https://app.mediatrack.cn/', '_blank');
  };

  window.fmTabEnter = function () { window.fmLoadList(); };

  // 从项目卡片进来：确保有链接后直接开独立窗口
  window.fmOpenForProject = async function (name) {
    var enc = encodeURIComponent(name);
    var url = '';
    try {
      var d = await api('GET', '/api/fenmiaozhen/link/' + enc);
      if (d && d.ok && d.has_link) url = d.url;
    } catch (e) {}

    if (!url) {
      var entered = prompt('🔗 请输入「' + name + '」在分秒帧的审核链接：', 'https://app.mediatrack.cn/');
      if (!entered) return false;
      entered = entered.trim();
      if (!isFmUrl(entered)) { toast('只允许分秒帧网址', 'error'); return false; }
      try {
        var saved = await api('POST', '/api/fenmiaozhen/link/' + enc, { url: entered });
        if (!(saved && saved.ok)) {
          toast((saved && saved.msg) || '链接保存失败', 'error');
          return false;
        }
        url = saved.url;
      } catch (e) {
        toast('链接保存失败: ' + e.message, 'error');
        return false;
      }
    }

    state.currentUrl = url;
    state.projectName = name;
    if (typeof switchTab === 'function') switchTab('fenmiaozhen');
    window.fmOpenWindow(url, name);
    setTimeout(window.fmLoadList, 800);
    return true;
  };

  // 给其他模块用：确保某项目有分秒帧链接（状态改「审核中」时调用）
  // 返回 true=已有链接，false=用户取消
  window.fmEnsureLink = async function (name) {
    await ensureCfg();
    try {
      var d = await api('GET', '/api/fenmiaozhen/link/' + encodeURIComponent(name));
      if (d && d.ok && d.has_link) return true;
    } catch (e) {}
    var entered = prompt('⚠️ 该项目要传分秒帧，但还没有分秒帧链接。\n\n'
      + '请粘贴「' + name + '」在分秒帧的项目页网址：', 'https://app.mediatrack.cn/');
    if (!entered) return false;
    entered = entered.trim();
    if (!isFmUrl(entered)) {
      toast('只允许分秒帧网址（mediatrack.cn），链接未保存', 'error');
      return false;
    }
    try {
      var r = await api('POST', '/api/fenmiaozhen/link/' + encodeURIComponent(name), { url: entered });
      if (r && r.ok) {
        toast('✅ 分秒帧链接已保存', 'success');
        return true;
      }
      toast((r && r.msg) || '保存失败', 'error');
    } catch (e) { toast('保存失败: ' + e.message, 'error'); }
    return false;
  };
})();