// ===== 分秒帧板块（项目清单）=====
// 为什么不用 iframe 内嵌：
//   实测 iframe 里点登录必定跳系统浏览器 —— 跨域 iframe 的 window.open 会冒泡到顶层 WebView，
//   而 pywebview 的处理是把新窗口交给系统浏览器。全局关掉该行为又会把主窗口 14 处
//   window.open（质检报告下载等）一起带走。所以登录/上传统一走软件内的独立窗口
//   （实测可正常登录，登录态持久化在 data/webview_profile）。
//
// 本板块的职责：把「哪个项目对应哪个分秒帧链接」列成清单，
// 一键打开独立窗口，并自动把成片目录复制到剪贴板，减少上传时的找路径成本。

(function () {
  var state = {
    items: [],        // [{name, url}]
    keyword: '',
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

  // 只允许分秒帧域名
  function isFmUrl(url) {
    try {
      var u = new URL(url);
      return /(^|\.)mediatrack\.cn$/i.test(u.hostname);
    } catch (e) { return false; }
  }

  window.fmLoadList = async function () {
    var wrap = el('fmListWrap');
    if (wrap && !state.items.length) wrap.innerHTML = '<div class="fm-empty">正在加载…</div>';
    try {
      var d = await api('GET', '/api/fenmiaozhen/links');
      state.items = (d && d.items) || [];
    } catch (e) {
      state.items = [];
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

  window.fmRenderList = function () {
    var wrap = el('fmListWrap');
    if (!wrap) return;

    var kw = state.keyword;
    var list = state.items.filter(function (x) {
      return !kw || String(x.name).toLowerCase().indexOf(kw) >= 0;
    });

    var st = el('fmStatus');
    if (st) st.textContent = '已配置 ' + state.items.length + ' 个项目' + (kw ? '（筛选 ' + list.length + '）' : '');

    if (!list.length) {
      wrap.innerHTML = '<div class="fm-empty">'
        + '<div style="font-size:32px;margin-bottom:10px">🔗</div>'
        + (state.items.length ? '没有匹配的项目' :
           '还没有项目配置分秒帧链接<br><span style="opacity:.75">在项目卡片上点「🔗 分秒帧」即可设置</span>')
        + '</div>';
      return;
    }

    var html = '';
    list.forEach(function (it) {
      var nameEsc = esc(it.name);
      var nameArg = esc(JSON.stringify(it.name));
      html += '<div class="fm-row">'
        +   '<div class="fm-row-name" title="' + nameEsc + '">' + nameEsc + '</div>'
        +   '<div class="fm-row-url" title="' + esc(it.url) + '">' + esc(it.url) + '</div>'
        +   '<div class="fm-row-acts">'
        +     '<button class="btn btn-sm btn-primary" onclick="fmOpenFor(' + nameArg + ')">⧉ 打开</button>'
        +     '<button class="btn btn-sm" onclick="fmSetLink(' + nameArg + ')">改链接</button>'
        +     '<button class="btn btn-sm" onclick="fmRemoveLink(' + nameArg + ')">移除</button>'
        +   '</div>'
        + '</div>';
    });
    wrap.innerHTML = html;
  };

  // 打开某个项目的分秒帧（独立窗口 + 复制成片目录）
  window.fmOpenFor = function (name) {
    var it = state.items.filter(function (x) { return x.name === name; })[0];
    if (!it) { toast('没有该项目的分秒帧链接', 'error'); return; }
    state.currentUrl = it.url;
    state.projectName = name;
    var pn = el('fmProjName');
    if (pn) pn.textContent = '· ' + name;
    window.fmOpenWindow(it.url, name);
  };

  window.fmSetLink = async function (name) {
    var it = state.items.filter(function (x) { return x.name === name; })[0];
    var cur = it ? it.url : '';
    var u = prompt('分秒帧链接（' + name + '）：', cur || 'https://app.mediatrack.cn/');
    if (!u) return;
    u = u.trim();
    if (!isFmUrl(u)) { toast('只允许分秒帧网址', 'error'); return; }
    try {
      var r = await api('POST', '/api/fenmiaozhen/link/' + encodeURIComponent(name), { url: u });
      if (r && r.ok) { toast('✅ 链接已保存', 'success'); window.fmLoadList(); }
      else toast((r && r.msg) || '保存失败', 'error');
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

  // 打开软件内独立窗口（桌面版）；浏览器访问时直接新标签页
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
    var u = state.currentUrl || 'https://app.mediatrack.cn/';
    window.open(u, '_blank');
  };

  // 切到本 tab 时刷新清单
  window.fmTabEnter = function () {
    window.fmLoadList();
  };

  // 从项目卡片进来：确保有链接后直接开独立窗口
  window.fmOpenForProject = async function (name) {
    var enc = encodeURIComponent(name);
    var url = '';
    try {
      var d = await api('GET', '/api/fenmiaozhen/link/' + enc);
      if (d && d.ok && d.has_link) url = d.url;
    } catch (e) {}

    if (!url) {
      var entered = prompt('🔗 请输入该项目在分秒帧的审核链接：', 'https://app.mediatrack.cn/');
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
    if (typeof window.fmLoadList === 'function') setTimeout(window.fmLoadList, 600);
    return true;
  };
})();