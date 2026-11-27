// ===== 状态按钮右键菜单：按项目状态精确跳到该状态关心的目录 =====
// 背景（用户需求）：
//   同一项目在不同阶段，文件在不同位置。只给一个“项目根”等于让用户自己找。
//   待交付 → 交付目录（000交付）；审核中 → 成片目录 + 分秒帧；
//   修改中 → 所有修改目录（MMDD修改）。所以右键按状态给具体路径。
//
// 实现要点：
//   1. 后端 /api/project/<name>/state_paths 负责「状态 → 路径清单」的映射，
//      前端只管渲染，不重复业务判断。
//   2. 复制路径优先走后端剪贴板（navigator.clipboard 在 WebView2 里不可靠）。
//   3. 菜单全局只建一个，点空白/Esc/执行动作后关闭。

(function () {
  var state = {
    el: null,
    name: '',
    status: '',
    sections: [],
    dept: '',
    busy: false
  };

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function closeMenu() {
    if (state.el && state.el.parentNode) state.el.parentNode.removeChild(state.el);
    state.el = null;
  }

  function ensureEl() {
    if (state.el) return state.el;
    var el = document.createElement('div');
    el.className = 'st-menu';
    el.addEventListener('contextmenu', function (e) { e.preventDefault(); });
    document.body.appendChild(el);
    state.el = el;
    return el;
  }

  // 把菜单放到鼠标附近，并防止超出视口
  function position(el, x, y) {
    el.style.left = '0px';
    el.style.top = '0px';
    var rect = el.getBoundingClientRect();
    var vw = window.innerWidth, vh = window.innerHeight;
    var left = x, top = y;
    if (left + rect.width > vw - 8) left = Math.max(8, vw - rect.width - 8);
    if (top + rect.height > vh - 8) top = Math.max(8, vh - rect.height - 8);
    el.style.left = left + 'px';
    el.style.top = top + 'px';
  }

  // 复制文本：优先后端（可靠），退到浏览器 API
  function copyText(text) {
    if (!text) return;
    if (window.__IS_DESKTOP__) {
      fetch('/api/_self/clipboard', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text })
      }).then(function (r) { return r.json(); }).then(function (d) {
        if (d && d.ok) toast('已复制：' + text, 'success', 4000);
        else fallbackCopy(text);
      }).catch(function () { fallbackCopy(text); });
      return;
    }
    fallbackCopy(text);

    function fallbackCopy(t) {
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(t).then(function () {
            toast('已复制：' + t, 'success', 4000);
          }, function () { toast('复制失败，请手动选中', 'error'); });
        } else {
          toast('复制失败，请手动选中', 'error');
        }
      } catch (e) { toast('复制失败: ' + e.message, 'error'); }
    }
  }

  function openPath(name, path) {
    api('POST', '/api/project/' + encodeURIComponent(name) + '/open_folder',
        { which: 'path', path: path }).then(function (d) {
      if (d && d.ok) toast('已打开', 'success');
      else toast((d && d.message) || '打开失败', 'error');
    }).catch(function (e) { toast('打开失败: ' + e.message, 'error'); });
  }

  function render() {
    var el = ensureEl();
    var html = '';
    html += '<div class="st-menu-head">'
      + '<div class="st-menu-title">' + esc(state.name) + '</div>'
      + '<div class="st-menu-sub">' + esc(state.status || '未设置') + ' · 右键菜单</div>'
      + '</div>';

    // 审核类状态且非二部 → 分秒帧动作
    if (state.status && state.status.indexOf('审') >= 0 && !isDept2()) {
      html += '<div class="st-menu-act" onclick="statusMenuFmOpen()">🔗 打开分秒帧窗口</div>'
            + '<div class="st-menu-act" onclick="statusMenuFmLink()">✎ 修改分秒帧链接</div>';
    }

    if (!state.sections.length) {
      html += '<div class="st-menu-empty">该项目没有可定位的目录记录</div>';
    } else {
      state.sections.forEach(function (sec, si) {
        html += '<div class="st-menu-sec">' + esc(sec.title) + '</div>';
        (sec.items || []).forEach(function (it, ii) {
          var flag = it.exists
            ? '<span class="st-mi-flag ok">存在</span>'
            : '<span class="st-mi-flag miss">不存在</span>';
          html += '<div class="st-menu-item">'
            +   '<div class="st-mi-top">'
            +     '<span class="st-mi-label">' + esc(it.label || '目录') + '</span>' + flag
            +   '</div>'
            +   '<div class="st-mi-path">' + esc(it.path) + '</div>'
            +   '<div class="st-mi-btns">'
            +     '<button onclick="statusMenuOpen(' + si + ',' + ii + ')">打开</button>'
            +     '<button onclick="statusMenuCopy(' + si + ',' + ii + ')">复制路径</button>'
            +   '</div>'
            + '</div>';
        });
      });
    }
    el.innerHTML = html;
  }

  function isDept2() {
    try {
      if (typeof fmDeptExcluded === 'function') return fmDeptExcluded(state.dept);
      return String(state.dept || '').indexOf('二部') >= 0;
    } catch (e) { return String(state.dept || '').indexOf('二部') >= 0; }
  }

  function findProject(name) {
    var pools = [];
    try {
      if (window.allProjects) {
        pools = pools.concat(window.allProjects.production || [],
                             window.allProjects.group_all || [],
                             window.allProjects.group_completed || []);
      }
    } catch (e) {}
    try {
      if (window.__projectsCache) pools = pools.concat(window.__projectsCache);
    } catch (e) {}
    for (var i = 0; i < pools.length; i++) {
      if (pools[i] && pools[i].name === name) return pools[i];
    }
    return null;
  }

  // 主入口：状态 select 右键
  window.statusContextMenu = function (ev, selEl, name) {
    ev.preventDefault();
    ev.stopPropagation();
    var status = (selEl && selEl.value) || '';
    var p = findProject(name);
    state.name = name;
    state.status = status;
    state.dept = (p && p.department) || '';
    state.sections = [];

    var el = ensureEl();
    el.innerHTML = '<div class="st-menu-head"><div class="st-menu-title">' + esc(name)
      + '</div><div class="st-menu-sub">' + esc(status || '未设置') + ' · 正在读取目录…</div></div>';
    position(el, ev.clientX, ev.clientY);

    api('POST', '/api/project/' + encodeURIComponent(name) + '/state_paths',
        { status: status }).then(function (d) {
      if (state.name !== name) return;    // 期间切到别的项目了
      if (!d || !d.ok) {
        state.sections = [];
        toast((d && d.msg) || '读取目录失败', 'error');
      } else {
        state.sections = d.sections || [];
      }
      render();
    }).catch(function (e) {
      state.sections = [];
      render();
      toast('读取目录失败: ' + e.message, 'error');
    });
    return false;
  };

  window.statusMenuOpen = function (si, ii) {
    var it = ((state.sections[si] || {}).items || [])[ii];
    if (!it) return;
    if (!it.exists) { toast('目录不存在: ' + it.path, 'error'); return; }
    openPath(state.name, it.path);
    closeMenu();
  };

  window.statusMenuCopy = function (si, ii) {
    var it = ((state.sections[si] || {}).items || [])[ii];
    if (!it) return;
    copyText(it.path);
    closeMenu();
  };

  window.statusMenuFmOpen = function () {
    var name = state.name;
    closeMenu();
    if (typeof fmOpenForProject === 'function') fmOpenForProject(name);
    else toast('分秒帧功能不可用', 'warning');
  };

  window.statusMenuFmLink = function () {
    var name = state.name;
    closeMenu();
    if (typeof fmSetLink === 'function') {
      // 板块清单没加载时 state 里没有条目，fmSetLink 会用空当前值，仍可输入
      fmSetLink(name);
    } else {
      toast('分秒帧功能不可用', 'warning');
    }
  };

  // 关闭时机
  document.addEventListener('click', function (e) {
    if (!state.el) return;
    if (state.el.contains(e.target)) return;
    closeMenu();
  }, true);
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeMenu();
  });
  window.addEventListener('blur', closeMenu);
  window.addEventListener('resize', closeMenu);
})();