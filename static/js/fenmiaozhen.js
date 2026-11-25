// ===== 分秒帧板块 =====
// 设计要点：
//   1. tab 里用 iframe 内嵌分秒帧网页，点项目卡片的「🔗 分秒帧」会切到这里并定位。
//   2. iframe 属于第三方上下文，登录可能被浏览器 cookie 策略挡住。所以同时保留
//      「独立窗口」通道（pywebview 独立 WebView 窗口，第一方，登录态稳），
//      一条路走不通还有另一条，不让用户卡死。
//   3. 懒加载：首次进 tab 才给 iframe 设 src，避免启动就去拉外部网页拖慢首屏。

(function () {
  var state = {
    loaded: false,       // iframe 是否已设过 src
    currentUrl: '',      // 当前加载的地址
    projectName: '',     // 当前关联的项目名
    timer: null
  };
  window._fmState = state;

  function el(id) { return document.getElementById(id); }

  function setStatus(text, kind) {
    var s = el('fmStatus');
    if (s) s.textContent = text;
    var d = el('fmDot');
    if (d) {
      d.className = 'fm-dot' + (kind ? ' ' + kind : '');
    }
  }

  function setProjectName(name) {
    var p = el('fmProjName');
    if (p) p.textContent = name ? '· ' + name : '';
    state.projectName = name || '';
  }

  function showTip(html) {
    var t = el('fmTip');
    if (!t) return;
    if (!html) { t.style.display = 'none'; t.innerHTML = ''; return; }
    t.innerHTML = html;
    t.style.display = 'block';
  }

  function hideEmpty() {
    var e = el('fmEmpty');
    if (e) e.style.display = 'none';
    var f = el('fmFrame');
    if (f) f.style.display = '';
  }

  // 加载指定地址到 iframe
  window.fmLoad = function (url, projectName) {
    url = (url || '').trim();
    if (!url) url = 'https://www.mediatrack.cn/';
    // 只允许分秒帧域名，防止被塞进任意网址
    var okHost = false;
    try {
      var u = new URL(url);
      okHost = /(^|\.)mediatrack\.cn$/i.test(u.hostname);
    } catch (e) { okHost = false; }
    if (!okHost) {
      toast('只允许加载分秒帧网址', 'error');
      return;
    }

    var f = el('fmFrame');
    if (!f) return;
    var inp = el('fmUrlInput');
    if (inp) inp.value = url;

    setProjectName(projectName || '');
    hideEmpty();
    setStatus('加载中…', 'warn');
    showTip('');

    state.currentUrl = url;
    state.loaded = true;
    state.loadTimerAt = Date.now();

    // 先清掉旧监听，避免多次绑定累积
    f.onload = function () {
      setStatus('已加载', 'on');
      if (state.timer) { clearTimeout(state.timer); state.timer = null; }
      // 首次加载后提示一次可能的登录问题（不打扰，只在顶部黄条）
      if (!state.tipShown) {
        state.tipShown = true;
        showTip('如果页面里登录不上 / 登录后一刷新就掉，是浏览器对 iframe 的跨站 cookie 限制导致的。'
              + '点右上角 <b>⧉ 独立窗口</b> 用独立窗口打开，登录态不会丢。');
      }
    };

    f.src = url;

    // 超时兜底：iframe 被拦时 onload 可能不触发
    if (state.timer) clearTimeout(state.timer);
    state.timer = setTimeout(function () {
      if (f.getAttribute('src') === url) {
        // 这里无法读取跨域内容，只能提示排查方向
        setStatus('加载超时（可能被拦截）', 'warn');
        showTip('页面 15 秒内没加载出来，通常是被站点或浏览器策略拦了。'
              + '点右上角 <b>⧉ 独立窗口</b> 打开，成功率更高。');
      }
    }, 15000);
  };

  window.fmLoadFromInput = function () {
    var inp = el('fmUrlInput');
    window.fmLoad((inp && inp.value) || 'https://www.mediatrack.cn/', '');
  };

  window.fmReload = function () {
    var f = el('fmFrame');
    if (!f || !state.loaded) {
      window.fmLoad((el('fmUrlInput') || {}).value || 'https://www.mediatrack.cn/', '');
      return;
    }
    // 用 src 赋值而非 location.reload，跨域下更可控
    var cur = state.currentUrl;
    setStatus('刷新中…', 'warn');
    f.src = 'about:blank';
    setTimeout(function () { f.src = cur; }, 60);
  };

  // 在软件内开独立窗口（桌面版）
  window.fmOpenWindow = function () {
    var url = state.currentUrl || ((el('fmUrlInput') || {}).value) || 'https://www.mediatrack.cn/';
    var title = '分秒帧' + (state.projectName ? ' - ' + state.projectName : '');
    if (!window.__IS_DESKTOP__) {
      window.open(url, '_blank');
      return;
    }
    fetch('/api/_self/fenmiaozhen', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: url, title: title, project: state.projectName || '' })
    }).then(function (r) { return r.json(); }).then(function (d) {
      if (d && d.ok) {
        toast(d.path_copied ? '✅ 已打开独立窗口，成片目录路径已复制' : '✅ 已在软件内打开独立窗口', 'success', 4000);
      } else {
        toast((d && d.message) || '打开失败', 'error');
      }
    }).catch(function (e) { toast('打开失败: ' + e.message, 'error'); });
  };

  window.fmOpenInBrowser = function () {
    var url = state.currentUrl || ((el('fmUrlInput') || {}).value) || 'https://www.mediatrack.cn/';
    window.open(url, '_blank');
  };

  // 切到分秒帧 tab 时调用
  window.fmTabEnter = function () {
    if (!state.loaded) {
      setStatus('未加载', '');
      return;
    }
    setStatus('已加载', 'on');
  };

  // 从项目卡片进来：查该项目链接，切 tab 并加载
  window.fmOpenForProject = async function (name) {
    var enc = encodeURIComponent(name);
    var url = '';
    try {
      var d = await api('GET', '/api/fenmiaozhen/link/' + enc);
      if (d && d.ok && d.has_link) url = d.url;
    } catch (e) {}

    if (!url) {
      // 没有链接 → 让用户填（与卡片按钮行为一致）
      var entered = prompt('🔗 请输入该项目在分秒帧的审核链接：', 'https://www.mediatrack.cn/');
      if (!entered) return false;
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

    if (typeof switchTab === 'function') switchTab('fenmiaozhen');
    window.fmLoad(url, name);
    toast('✅ 已定位到分秒帧（成片目录路径已复制，上传时可直接粘贴）', 'success', 4000);

    // 顺手把该项目成片目录复制到剪贴板，方便上传时定位
    try {
      fetch('/api/_self/fenmiaozhen', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url, title: '分秒帧 - ' + name, project: name, _no_window: true })
      });
    } catch (e) {}
    return true;
  };
})();