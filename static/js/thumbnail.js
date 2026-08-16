/* 视频缩略图悬停预览（融合自「项目档案管理器」）
 * 对带 data-thumb="绝对路径" 的元素悬停，加载 /api/thumbnail 缩略图浮动显示。
 * 使用事件委托，任何动态渲染的列表元素都会自动生效。
 */
(function() {
  'use strict';

  let _float = null, _req = 0, _timer = null;

  function ensureFloat() {
    if (_float) return;
    _float = document.createElement('div');
    _float.id = 'thumbFloat';
    _float.style.cssText = 'position:fixed;z-index:40000;pointer-events:none;display:none;border-radius:8px;overflow:hidden;box-shadow:0 8px 24px rgba(0,0,0,.35);background:#000';
    document.body.appendChild(_float);
  }

  function showThumb(path, el) {
    ensureFloat();
    const reqId = ++_req;
    _float.style.display = 'none';
    _float.innerHTML = '<div style="padding:12px 16px;color:#f59e0b;font-size:12px">🎬 生成缩略图中…</div>';
    const url = '/api/thumbnail?path=' + encodeURIComponent(path);
    const img = new Image();
    img.onload = function() {
      if (reqId !== _req) return;
      _float.innerHTML = '';
      _float.appendChild(img);
      _float.style.display = 'block';
      // 定位在元素右侧
      const r = el.getBoundingClientRect();
      let left = r.right + 8, top = r.top;
      const w = Math.min(320, r.height ? r.height * 1.78 : 320);
      if (left + w > window.innerWidth) left = r.left - w - 8;
      _float.style.left = left + 'px';
      _float.style.top = (top + window.scrollY) + 'px';
      img.style.cssText = 'max-width:320px;max-height:180px;display:block';
    };
    img.onerror = function() {
      if (reqId !== _req) return;
      _float.innerHTML = '<div style="padding:10px 14px;color:#f59e0b;font-size:12px">🎬 无缩略图（需 ffmpeg）</div>';
      const r = el.getBoundingClientRect();
      _float.style.left = (r.right + 8) + 'px';
      _float.style.top = (r.top + window.scrollY) + 'px';
      _float.style.display = 'block';
    };
    img.src = url;
  }

  function hideThumb() {
    _req++;
    if (_float) _float.style.display = 'none';
  }

  // 事件委托：悬停带 data-thumb 的元素
  document.addEventListener('mouseover', function(e) {
    const el = e.target.closest('[data-thumb]');
    if (!el || !el.dataset.thumb) return;
    if (_timer) { clearTimeout(_timer); _timer = null; }
    _timer = setTimeout(function() { showThumb(el.dataset.thumb, el); }, 350);
  });
  document.addEventListener('mouseout', function(e) {
    if (e.target.closest && e.target.closest('[data-thumb]')) {
      if (_timer) { clearTimeout(_timer); _timer = null; }
      hideThumb();
    }
  });
})();
