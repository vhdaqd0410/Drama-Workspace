// 风险预警中心（D2）
// 聚合审核超时 / 交付逾期 / 今日与即将交付 / 待办提醒，形成统一的风险视图。
// 数据源：/api/audit/alerts、/api/notifications
(function () {
  'use strict';
  window.loadRiskCenter = loadRiskCenter;

  function loadRiskCenter() {
    var box = document.getElementById('riskContent');
    if (!box) return;
    box.innerHTML = '<div style="text-align:center;padding:40px;color:#86868b">⏳ 正在汇总风险...</div>';

    var auditP = api('GET', '/api/audit/alerts').then(function (d) { return d || {}; }).catch(function () { return {}; });
    var notifP = api('GET', '/api/notifications').then(function (d) { return d || {}; }).catch(function () { return {}; });

    Promise.all([auditP, notifP]).then(function (res) {
      var audit = res[0] || {};
      var notif = res[1] || {};
      var alerts = (audit.alerts) || [];
      var overdue = (notif.overdue) || [];
      var today = (notif.today_deliver) || [];
      var upcoming = (notif.upcoming) || [];
      var todoReminders = (notif.todo_reminders) || [];

      var html = '';

      // 风险概览统计条
      var totalRisk = alerts.length + overdue.length;
      html += '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:20px">'
        + statCard('🔴 逾期交付', overdue.length, overdue.length ? '#ff3b30' : '#34c759')
        + statCard('⏰ 审核超时', alerts.length, alerts.length ? '#ff9500' : '#34c759')
        + statCard('📦 今日交付', today.length, '#0071e3')
        + statCard('📅 即将交付', upcoming.length, '#5c6bc0')
        + statCard('📌 待办提醒', todoReminders.length, '#af52de')
        + '</div>';

      if (totalRisk === 0 && todoReminders.length === 0) {
        box.innerHTML = html + '<div style="text-align:center;padding:50px;color:#34c759;font-size:16px">🎉 当前没有风险项</div>';
        return;
      }

      // 逾期交付
      html += section('🔴 逾期交付', overdue.length, function () {
        return overdue.map(function (x) {
          return rowItem(x.name, x.department, '逾期 ' + x.date, '#ff3b30');
        }).join('');
      });

      // 审核超时
      html += section('⏰ 审核/质检超时（卡 > 3 天）', alerts.length, function () {
        return alerts.map(function (a) {
          return rowItem(a.name, (a.owner ? '👤 ' + a.owner : '') + (a.department ? ' · ' + a.department : ''), a.status + ' 已 ' + a.days_stuck + ' 天', '#ff9500');
        }).join('');
      });

      // 今日交付
      html += section('📦 今日交付', today.length, function () {
        return today.map(function (x) {
          return rowItem(x.name, x.department, '今日交付', '#0071e3');
        }).join('');
      });

      // 即将交付
      html += section('📅 即将交付（未来 3 天）', upcoming.length, function () {
        return upcoming.map(function (x) {
          return rowItem(x.name, x.department, '截止 ' + x.date, '#5c6bc0');
        }).join('');
      });

      // 待办提醒
      html += section('📌 待办提醒', todoReminders.length, function () {
        return todoReminders.map(function (t) {
          var items = (t.items || []).slice(0, 3).map(function (it) { return it.text; });
          return rowItem(t.project || '独立待办', (t.count || 0) + ' 条待办', items.join(' / '), '#af52de');
        }).join('');
      });

      box.innerHTML = html;
    }).catch(function (e) {
      box.innerHTML = '<div style="text-align:center;padding:40px;color:#ff3b30">加载失败: ' + escHtml(e.message) + '</div>';
    });
  }

  function statCard(label, num, color) {
    return '<div style="background:#fff;border-radius:12px;padding:16px;box-shadow:var(--shadow);text-align:center">'
      + '<div style="font-size:26px;font-weight:700;color:' + color + '">' + num + '</div>'
      + '<div style="font-size:12px;color:#86868b;margin-top:4px">' + label + '</div></div>';
  }

  function section(title, count, renderRows) {
    var rows = renderRows() || '';
    if (!rows) return '<div style="margin-bottom:16px"><h3 style="font-size:15px;color:#1d1d1f;margin-bottom:8px">' + title + '（0）</h3></div>';
    return '<div style="margin-bottom:20px"><h3 style="font-size:15px;color:#1d1d1f;margin-bottom:10px">' + title + '（' + count + '）</h3>'
      + '<div style="background:#fff;border-radius:12px;box-shadow:var(--shadow);overflow:hidden">' + rows + '</div></div>';
  }

  function rowItem(name, sub, right, color) {
    return '<div style="display:flex;align-items:center;justify-content:space-between;padding:12px 16px;border-bottom:1px solid #f0f0f2;cursor:pointer" onclick="loadRiskGoProject(\'' + escJs(name) + '\')">'
      + '<div style="flex:1;min-width:0"><div style="font-weight:600;font-size:13px;color:#1d1d1f">' + escHtml(name) + '</div>'
      + '<div style="font-size:11px;color:#86868b;margin-top:2px">' + escHtml(sub || '') + '</div></div>'
      + '<div style="font-size:12px;font-weight:600;color:' + color + ';white-space:nowrap">' + escHtml(right || '') + '</div>'
      + '</div>';
  }

  // 点击风险项定位到项目看板
  window.loadRiskGoProject = function (name) {
    try {
      switchTab('dashboard');
      if (typeof jumpToProject === 'function') { jumpToProject(name); }
    } catch (e) {}
  };

  function escJs(s) {
    return String(s || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
  }
})();
