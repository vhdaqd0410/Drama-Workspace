/* ============ 组员协作（打勾 / 进度矩阵 / 通知） ============
 *
 * 身份：window._collabRole = 'lead' | 'member' | 'unknown'
 *   lead   组长主端：可见全部项目 + 协作 Tab（进度矩阵）
 *   member 组员端  ：只见组内项目 + 卡片上直接打勾
 *
 * 打勾阶段（与后端 STATUS_PHASE 对齐）：
 *   cut     剪辑完成  ← 状态 剪辑中 / 待审核
 *   revise  修改完成  ← 状态 审核中 / 修改中
 *   deliver 交付完成  ← 状态 待交付 / 待质检 / 已完成
 */
(function () {
  'use strict';

  // 状态 -> 阶段（与后端一致）
  var STATUS_PHASE = {
    '剪辑中': 'cut', '待审核': 'cut',
    '审核中': 'revise', '修改中': 'revise',
    '待交付': 'deliver', '待质检': 'deliver', '已完成': 'deliver'
  };
  var PHASE_LABEL = { cut: '剪辑完成', revise: '修改完成', deliver: '交付完成' };
  var PHASE_ORDER = ['cut', 'revise', 'deliver'];

  var _summary = null;      // 打勾摘要缓存 {项目名: {...}}
  var _summaryTs = 0;
  var _TTL = 15000;         // 15 秒缓存，避免每次渲染都打请求

  function esc(s) {
    return (typeof escHtml === 'function') ? escHtml(s)
      : String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
          return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
  }

  function phaseOf(status) {
    var s = (typeof normalizeStatus === 'function') ? normalizeStatus(status) : String(status || '');
    return STATUS_PHASE[s] || 'cut';
  }

  // ---------- 身份 ----------

  function initRole() {
    return api('GET', '/api/collab/me').then(function (d) {
      window._collabRole = (d && d.role) || 'unknown';
      window._collabName = (d && d.name) || '';
      applyRoleUI();
      return window._collabRole;
    }).catch(function () {
      window._collabRole = 'unknown';
      return 'unknown';
    });
  }

  function isMember() { return window._collabRole === 'member'; }
  function isLead() { return window._collabRole === 'lead'; }

  // 按身份隐藏组长专属入口（组员看不到这些 Tab）
  function applyRoleUI() {
    if (!isMember()) return;

    // 1) 组长专属 Tab
    var hideTabs = ['qa', 'report', 'editor', 'risk', 'nameplate', 'settings', 'activity', 'fenji', 'collab'];
    hideTabs.forEach(function (name) {
      var el = document.querySelector('.tab[data-tab="' + name + '"]');
      if (el) el.style.display = 'none';
      var panel = document.getElementById('tab-' + name);
      if (panel) panel.classList.add('collab-hidden');
    });

    // 2) 顶部工具栏：批量选择 / 扫描 / 团队 / 命令面板 / 数据洞察 / 数据中心 / 设置
    var hideByTitle = ['批量选择模式', '扫描项目', '团队', '命令面板 (Ctrl+P)',
                       '数据洞察', '数据中心', '设置'];
    hideByTitle.forEach(function (t) {
      var b = document.querySelector('[title="' + t + '"]');
      if (b) b.style.display = 'none';
    });

    // 3) 项目状态选择器（组员无权改状态，显示为静态徽标）
    var style = document.getElementById('collab-member-style');
    if (!style) {
      style = document.createElement('style');
      style.id = 'collab-member-style';
      style.textContent = [
        '.role-member .editable-badge{pointer-events:none;appearance:none;-webkit-appearance:none;',
        '  background-image:none !important;padding-right:8px !important}',
        '.role-member [data-lead-only]{display:none !important}',
        '.role-member .dept-badge[onclick]{pointer-events:none}',
        '.role-member .card-title-name[title]{cursor:default}'
      ].join('');
      document.head.appendChild(style);
    }
    document.body.classList.add('role-member');
  }

  // ---------- 摘要数据 ----------

  function loadSummary(force) {
    var now = Date.now();
    if (!force && _summary && (now - _summaryTs) < _TTL) {
      return Promise.resolve(_summary);
    }
    return api('GET', '/api/collab/summary').then(function (d) {
      _summary = (d && d.projects) || {};
      _summaryTs = Date.now();
      return _summary;
    }).catch(function () {
      _summary = _summary || {};
      return _summary;
    });
  }

  function summaryFor(projectName) {
    return _summary ? _summary[projectName] : null;
  }

  function invalidate() { _summaryTs = 0; }

  // ---------- 卡片打勾条 ----------

  // 返回卡片内嵌的打勾 HTML；无分配或无状态时返回 ''
  function checkBarHTML(project) {
    if (!project || !project.name) return '';
    var info = summaryFor(project.name);
    if (!info) return '';

    var phase = info.phase;
    var mine = info.mine || null;

    // 组员：只显示自己相关的、且未全部完成时显示自己的勾
    if (isMember()) {
      if (!mine || !mine.in_scope) return '';
      var mineDone = !!mine.done;
      return ''
        + '<div class="collab-bar">'
        + '<button class="collab-btn ' + (mineDone ? 'done' : 'todo') + '"'
        + ' data-collab-check="' + esc(project.name) + '"'
        + ' data-collab-phase="' + esc(phase) + '"'
        + ' data-collab-done="' + (mineDone ? '1' : '0') + '"'
        + ' title="' + (mineDone ? '已打勾，点击可取消' : '点击打勾') + '">'
        + (mineDone ? '✅ ' : '⬜ ') + esc(PHASE_LABEL[phase] || phase)
        + (mineDone ? '（已勾）' : '（待打勾）')
        + '</button>'
        + '<span class="collab-progress">'
        + esc(info.done.length + '/' + info.expected.length) + ' 人已勾'
        + '</span>'
        + '</div>';
    }

    // 组长：显示全员进度，可点开进度矩阵
    var dots = PHASE_ORDER.map(function (p) {
      var active = (p === phase);
      var cls = 'collab-dot' + (active ? ' active' : '');
      return '<span class="' + cls + '" title="' + esc(PHASE_LABEL[p]) + '">' + esc(PHASE_LABEL[p].slice(0, 2)) + '</span>';
    }).join('<span class="collab-arrow">›</span>');

    var doneN = info.done.length, allN = info.expected.length;
    var stateCls = info.all_done ? 'all-done' : (doneN ? 'partial' : 'none');
    var stateTxt = info.all_done ? '✅ 全员完成' : (doneN + '/' + allN + ' 已勾');

    return ''
      + '<div class="collab-bar ' + stateCls + '">'
      + '<span class="collab-phases">' + dots + '</span>'
      + '<span class="collab-progress">' + esc(stateTxt) + '</span>'
      + (allN ? '<span class="collab-missing" title="尚未打勾">待勾：' + esc(info.missing.join('、') || '无') + '</span>' : '')
      + '</div>';
  }

  // ---------- 打勾动作 ----------

  function doCheck(projectName, phase, done) {
    return api('POST', '/api/collab/check', {
      project: projectName, phase: phase, done: !!done
    }).then(function (r) {
      if (!r || !r.ok) throw new Error((r && r.message) || '打勾失败');
      invalidate();
      var st = r.state || {};
      if (r.notice === 'all_done') {
        toast('🎉「' + phaseLabelOf(phase) + '」全部完成，已通知组长', 'success');
      } else {
        toast('✅ 已打勾：' + phaseLabelOf(phase), 'success');
      }
      return r;
    });
  }

  function phaseLabelOf(phase) { return PHASE_LABEL[phase] || phase; }

  // 事件委托：卡片上的打勾按钮
  document.addEventListener('click', function (e) {
    var btn = e.target.closest ? e.target.closest('[data-collab-check]') : null;
    if (!btn) return;
    e.preventDefault();
    var name = btn.getAttribute('data-collab-check');
    var phase = btn.getAttribute('data-collab-phase');
    var wasDone = btn.getAttribute('data-collab-done') === '1';
    btn.disabled = true;
    doCheck(name, phase, !wasDone).then(function () {
      if (typeof loadProjects === 'function') loadProjects();
    }).catch(function (err) {
      toast('打勾失败: ' + err.message, 'error');
      btn.disabled = false;
    });
  });

  // ---------- 协作 Tab（组长：进度矩阵） ----------

  function renderProgressInto(el) {
    if (!el) return;
    el.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-sec)">⏳ 加载协作进度...</div>';
    api('GET', '/api/collab/progress').then(function (d) {
      if (!d || !d.ok) {
        el.innerHTML = '<div style="padding:20px;color:var(--red)">' + esc((d && d.message) || '加载失败') + '</div>';
        return;
      }
      var rows = d.rows || [];
      if (!rows.length) {
        el.innerHTML = '<div style="text-align:center;padding:60px;color:var(--text-sec)">📭 暂无进行中的协作项目</div>';
        return;
      }
      var allDone = rows.filter(function (r) { return r.all_done; });
      var pending = rows.filter(function (r) { return !r.all_done; });

      var html = '';
      // 顶部统计
      html += '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:18px">'
        + statCard('⏳ 进行中', rows.length, '#0071e3')
        + statCard('✅ 已齐等待处理', allDone.length, '#34c759')
        + statCard('👥 待打勾项目', pending.length, '#ff9500')
        + '</div>';

      // 未齐的排前面（需要组长关注）
      html += '<div class="collab-matrix">';
      html += '<table style="width:100%;border-collapse:collapse;font-size:13px">'
        + '<thead><tr style="background:#f5f5f7;border-bottom:2px solid #e5e5ea">'
        + '<th style="padding:10px;text-align:left">项目</th>'
        + '<th style="padding:10px;text-align:left">状态</th>'
        + '<th style="padding:10px;text-align:left">当前阶段</th>'
        + '<th style="padding:10px;text-align:left">打勾情况</th>'
        + '<th style="padding:10px;text-align:left">尚未打勾</th>'
        + '</tr></thead><tbody>';

      rows.forEach(function (r) {
        var badge = r.all_done
          ? '<span style="color:#34c759;font-weight:600">✅ 已齐</span>'
          : '<span style="color:#ff9500;font-weight:600">' + r.done.length + '/' + r.expected.length + '</span>';
        var chips = r.expected.map(function (n) {
          var ok = r.done.indexOf(n) >= 0;
          return '<span class="collab-chip ' + (ok ? 'ok' : 'no') + '">'
            + (ok ? '✅ ' : '⬜ ') + esc(n) + '</span>';
        }).join(' ');
        var missing = r.missing.length
          ? r.missing.map(function (n) { return esc(n); }).join('、')
          : '<span style="color:#34c759">—</span>';
        html += '<tr style="border-bottom:1px solid #f0f0f0' + (r.all_done ? '' : ';background:#fffdf5') + '">'
          + '<td style="padding:8px 10px;font-weight:500">'
          + '<a href="javascript:void(0)" onclick="jumpToProject(\'' + jsq(r.project) + '\')" style="color:var(--blue);text-decoration:none">' + esc(r.project) + '</a>'
          + '</td>'
          + '<td style="padding:8px 10px;color:var(--text-sec)">' + esc(r.status) + (r.round > 1 ? '（第' + r.round + '轮）' : '') + '</td>'
          + '<td style="padding:8px 10px">' + esc(r.phase_label) + '</td>'
          + '<td style="padding:8px 10px">' + chips + '</td>'
          + '<td style="padding:8px 10px;color:#c2410c">' + missing + '</td>'
          + '</tr>';
      });
      html += '</tbody></table></div>';
      el.innerHTML = html;
    }).catch(function (err) {
      el.innerHTML = '<div style="padding:20px;color:var(--red)">加载失败: ' + esc(err.message) + '</div>';
    });
  }

  function statCard(label, num, color) {
    return '<div style="background:#fff;border:1px solid var(--border,#e5e5ea);border-radius:12px;padding:14px 16px;min-width:0">'
      + '<div class="collab-stat-label">' + esc(label) + '</div>'
      + '<div class="collab-stat-num" style="color:' + color + '">' + num + '</div>'
      + '</div>';
  }

  window.Collab = {
    initRole: initRole,
    loadSummary: loadSummary,
    invalidate: invalidate,
    checkBarHTML: checkBarHTML,
    renderProgressInto: renderProgressInto,
    isMember: isMember,
    isLead: isLead,
    phaseOf: phaseOf,
    PHASE_LABEL: PHASE_LABEL
  };
})();
