/* 视频缩略图悬停预览（融合自「项目档案管理器」v2，优化版）
 * 对带 data-thumb="绝对路径" 的元素悬停，加载 /api/thumbnail 缩略图。
 * - 悬停不显示黑窗/加载占位，图片就绪后直接浮现
 * - 缩略图更大、跟随鼠标位置、带明显边框阴影更显眼
 * 使用事件委托，动态渲染的列表元素自动生效。
 */
(function() {
  'use strict';

  let _float = null, _req = 0, _timer = null;

  function ensureFloat() {
    if (_float) return;
    _float = document.createElement('div');
    _float.id = 'thumbFloat';
    _float.style.cssText = 'position:fixed;z-index:40000;pointer-events:none;display:none;border-radius:12px;overflow:hidden;box-shadow:0 14px 40px rgba(0,0,0,.45);border:2px solid rgba(255,255,255,.9);background:#000';
    document.body.appendChild(_float);
  }

  function positionAt(clientX, clientY) {
    const W = 480, H = 270; // 期望尺寸
    let left = clientX + 18, top = clientY + 18;
    if (left + W > window.innerWidth - 8) left = clientX - W - 18;
    if (top + H > window.innerHeight - 8) top = clientY - H - 18;
    left = Math.max(8, left); top = Math.max(8, top);
    _float.style.left = left + 'px';
    _float.style.top = top + 'px';
  }

  function showThumb(path, clientX, clientY) {
    ensureFloat();
    const reqId = ++_req;
    // 悬停不显示黑窗/加载占位，直接隐藏直到就绪
    _float.style.display = 'none';
    _float.innerHTML = '';
    const img = new Image();
    img.onload = function() {
      if (reqId !== _req) return;
      _float.innerHTML = '';
      img.style.cssText = 'max-width:480px;max-height:270px;width:auto;height:auto;display:block';
      _float.appendChild(img);
      _float.style.display = 'block';
      positionAt(clientX, clientY);
    };
    img.onerror = function() {
      if (reqId !== _req) return;
      _float.innerHTML = '<div style="padding:16px 20px;color:#fff;font-size:13px">🎬 无缩略图（需 ffmpeg）</div>';
      _float.style.display = 'block';
      positionAt(clientX, clientY);
    };
    img.src = '/api/thumbnail?path=' + encodeURIComponent(path);
  }

  function hideThumb() {
    _req++;
    if (_float) _float.style.display = 'none';
  }

  // 事件委托：悬停带 data-thumb 的元素（延迟极短，就绪后显示）
  document.addEventListener('mouseover', function(e) {
    const el = e.target.closest ? e.target.closest('[data-thumb]') : null;
    if (!el || !el.dataset.thumb) return;
    if (_timer) { clearTimeout(_timer); _timer = null; }
    const x = e.clientX, y = e.clientY;
    _timer = setTimeout(function() { showThumb(el.dataset.thumb, x, y); }, 120);
  });
  document.addEventListener('mousemove', function(e) {
    // 图片已显示时跟随鼠标
    if (_float && _float.style.display === 'block' && e.target.closest && e.target.closest('[data-thumb]')) {
      const W = 480, H = 270;
      let left = e.clientX + 18, top = e.clientY + 18;
      if (left + W > window.innerWidth - 8) left = e.clientX - W - 18;
      if (top + H > window.innerHeight - 8) top = e.clientY - H - 18;
      _float.style.left = Math.max(8, left) + 'px';
      _float.style.top = Math.max(8, top) + 'px';
    }
  });
  document.addEventListener('mouseout', function(e) {
    if (e.target.closest && e.target.closest('[data-thumb]')) {
      if (_timer) { clearTimeout(_timer); _timer = null; }
      hideThumb();
    }
  });
})();
