// 视频预览播放器
// === 视频预览（从 nas-bridge 移植）===
function _openPreview(projectName, fileName){
  const overlay = document.getElementById('preview-overlay');
  const video = document.getElementById('preview-video');
  const title = document.getElementById('preview-title');
  const loading = document.getElementById('preview-loading');
  const toolbar = document.getElementById('preview-toolbar');
  
  if (!overlay) { toast('预览组件未加载', 'error'); return; }
  
  const proj = projectName || (window.currentProject || '');
  const mode = window.__previewMode || window.currentMode || 'source';
  let url = '/api/preview/' + encodeURIComponent(proj) + '/' + encodeURIComponent(fileName) + '?mode=' + mode;
  var subpath = window.__previewSubpath || '';
  if(subpath) url += '&subpath=' + encodeURIComponent(subpath);
  
  // Update navigation index
  if (window.__previewList && window.__previewList.length > 0) {
    const idx = window.__previewList.findIndex(f => f.name === fileName);
    window.__previewIdx = idx >= 0 ? idx : 0;
    const label = document.getElementById('preview-idx-label');
    if (label) label.textContent = `${idx + 1} / ${window.__previewList.length}`;
    if (toolbar) toolbar.style.display = 'flex';
  } else {
    if (toolbar) toolbar.style.display = 'none';
  }
  
  title.textContent = fileName;
  overlay.classList.add('active');
  video.style.display = '';
  if (loading) { loading.style.display = 'block'; loading.textContent = '⏳ 加载中...'; }
  
  video.src = url;
  video.playbackRate = 1;
  _updateSpeedButtons(1);
  video.onloadeddata = function(){
    if (loading) loading.style.display = 'none';
  };
  video.onerror = function(){
    if (loading) loading.textContent = '⚠️ 无法加载视频';
  };
}

function previewFile(fileName, subpath, projectName){
  window.__previewMode = window.currentMode || 'source';
  _openPreview(projectName, fileName);
}

function closePreview(){
  const overlay = document.getElementById('preview-overlay');
  const video = document.getElementById('preview-video');
  if (video) { video.pause(); video.removeAttribute('src'); video.load(); }
  if (overlay) overlay.classList.remove('active');
}

function previewNav(delta){
  if (!window.__previewList || window.__previewList.length < 2) return;
  let idx = (window.__previewIdx || 0) + delta;
  if (idx < 0) idx = window.__previewList.length - 1;
  if (idx >= window.__previewList.length) idx = 0;
  window.__previewIdx = idx;
  const next = window.__previewList[idx];
  if (next && next.name) _openPreview(window.__previewListProject, next.name);
}

function previewSetSpeed(rate){
  const video = document.getElementById('preview-video');
  if (video) video.playbackRate = rate;
  _updateSpeedButtons(rate);
}

function _updateSpeedButtons(rate){
  document.querySelectorAll('#preview-toolbar button').forEach(b => b.classList.remove('active'));
  const btns = document.querySelectorAll('#preview-toolbar button[onclick]');
  btns.forEach(b => { if (b.getAttribute('onclick') && b.getAttribute('onclick').includes(String(rate))) b.classList.add('active'); });
}

// Global keyboard shortcuts for preview
document.addEventListener('keydown', function(e){
  const overlay = document.getElementById('preview-overlay');
  if (!overlay || !overlay.classList.contains('active')) return;
  if (e.key === 'Escape') closePreview();
  else if (e.key === 'ArrowLeft') previewNav(-1);
  else if (e.key === 'ArrowRight') previewNav(1);
  else if (e.key === ' ') { e.preventDefault(); const v = document.getElementById('preview-video'); if (v) v.paused ? v.play() : v.pause(); }
});

