/* wb-shared.js — 全局共享工具与命名空间（唯一事实来源）
 *
 * 目的：
 *   1. 收敛分散在各文件里的 escHtml / htm / jsq 等转义工具，避免"三处定义不一致"漂移。
 *   2. 提供 window.WB 命名空间，新功能（排期看板 / 剪辑师视图 / 离线缓存）挂在其下，
 *      减少污染全局作用域。
 *   3. 兼容：仍把常用函数挂到 window 上（全局），让既有内联 onclick 不受影响。
 *
 * 加载顺序：必须位于所有其它 static/js 之前（index.html 顶部）。
 */
(function(){
  var WB = window.WB || (window.WB = {});

  // ===== 转义工具（统一口径） =====
  function escHtml(s){
    if(s === undefined || s === null) return '';
    return String(s)
      .replace(/&/g,'&amp;')
      .replace(/</g,'&lt;')
      .replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;')
      .replace(/'/g,'&#39;');
  }
  function htm(s){ return escHtml(s); }

  // 安全地把任意字符串嵌入 JS 单引号字符串（用于 onclick 属性等）
  function jsq(s){
    if(s === undefined || s === null) return '';
    return String(s)
      .replace(/\\/g,'\\\\')
      .replace(/'/g,"\\'")
      .replace(/"/g,'&quot;')
      .replace(/\r/g,'\\r')
      .replace(/\n/g,'\\n')
      .replace(/</g,'\\u003C')
      .replace(/>/g,'\\u003E');
  }

  // 统一 fetch 封装（兼容既有 api() 全局）
  function api(method, path, body){
    var opts = { method: method, headers: {} };
    if(body !== undefined){
      if(body instanceof FormData){ opts.body = body; }
      else {
        opts.headers['Content-Type'] = 'application/json';
        opts.body = JSON.stringify(body);
      }
    }
    return fetch(path, opts).then(function(r){
      if(!r.ok) throw new Error(r.status + ' ' + r.statusText);
      var ct = r.headers.get('content-type') || '';
      return ct.indexOf('application/json') >= 0 ? r.json() : r.text();
    });
  }

  // 轻提示（兼容既有 toast() 全局）
  function toast(msg, type){
    type = type || 'info';
    var container = document.getElementById('toastContainer');
    if(!container) return;
    var icons = { success:'✅', error:'❌', warning:'⚠️', info:'ℹ️' };
    var t = document.createElement('div');
    t.className = 'toast ' + type;
    t.innerHTML = '<span class="toast-icon">' + (icons[type]||'ℹ️') + '</span>'
      + '<span class="toast-msg"></span>';
    t.querySelector('.toast-msg').textContent = msg;
    var c = document.createElement('span');
    c.className = 'toast-close';
    c.textContent = '×';
    c.onclick = function(){ t.remove(); };
    t.appendChild(c);
    container.appendChild(t);
    setTimeout(function(){ t.style.opacity='0'; t.style.transition='all .3s'; setTimeout(function(){ t.remove(); },300); }, 3500);
  }

  // 挂到命名空间
  WB.escHtml = escHtml;
  WB.htm = htm;
  WB.jsq = jsq;
  WB.api = api;
  WB.toast = toast;

  // 兼容：挂到全局（供既有内联 onclick / 老代码使用）
  if(typeof window.escHtml !== 'function') window.escHtml = escHtml;
  if(typeof window.htm !== 'function') window.htm = htm;
  if(typeof window.jsq !== 'function') window.jsq = jsq;
  if(typeof window.api !== 'function') window.api = api;
  if(typeof window.toast !== 'function') window.toast = toast;

  // 版本信息，便于排障
  WB.version = '1.0';
  window.WB = WB;
})();
