// 视频预览播放器
function _openPreview(projectName, fileName){
  const overlay = document.getElementById('preview-overlay');
  const video = document.getElementById('preview-video');
  const title = document.getElementById('preview-title');
  const loading = document.getElementById('preview-loading');
  const toolbar = document.getElementById('preview-toolbar');

  if (!overlay) { toast('预览组件未加载', 'error'); return; }

  const proj = projectName || (window.currentProject || '');
  const mode = window.__previewMode || window.currentMode || 'source';
  const subpath = window.__previewSubpath || '';
  let url = '/api/preview/' + encodeURIComponent(proj) + '/' + encodeURIComponent(fileName) + '?mode=' + mode;
  if(subpath) url += '&subpath=' + encodeURIComponent(subpath);

  if (window.__previewList && window.__previewList.length > 0) {
    const idx = window.__previewList.findIndex(f => f.name === fileName);
    window.__previewIdx = idx >= 0 ? idx : 0;
    const label = document.getElementById('preview-idx-label');
    if (label) label.textContent = `${window.__previewIdx + 1} / ${window.__previewList.length}`;
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
    _updateTimeLabel();
  };
  video.ontimeupdate = _updateTimeLabel;
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
  if (next && next.name) {
    window.__previewSubpath = next.subpath || '';
    _openPreview(window.__previewListProject, next.name);
  }
}

function previewSetSpeed(rate){
  const video = document.getElementById('preview-video');
  if (video) video.playbackRate = rate;
  _updateSpeedButtons(rate);
}

function previewStep(delta){
  const video = document.getElementById('preview-video');
  if (!video || !video.duration) return;
  video.pause();
  video.currentTime = Math.max(0, Math.min(video.duration, video.currentTime + delta));
  video.addEventListener('seeked', function once(){ video.play(); video.removeEventListener('seeked', once); });
}

function previewOpenLocal(){
  const video = document.getElementById('preview-video');
  const title = document.getElementById('preview-title');
  if (!video || !title) return;
  const fileName = title.textContent;
  const proj = window.__previewListProject || window.currentProject || '';
  const mode = window.__previewMode || 'source';
  const subpath = window.__previewSubpath || '';
  api('POST', '/api/preview/open_local', {
    project_name: proj, filename: fileName, mode: mode, subpath: subpath
  }).then(r => {
    if (r.ok) toast('🎬 已用本地播放器打开', 'success');
    else toast('⚠️ ' + (r.message || '打开失败'), 'warning');
  }).catch(e => toast('❌ ' + e.message, 'error'));
}

function _updateSpeedButtons(rate){
  document.querySelectorAll('#preview-toolbar button[data-speed]').forEach(b => {
    b.classList.toggle('active', parseFloat(b.dataset.speed) === rate);
  });
}

function _fmtTime(s){
  if (!isFinite(s) || s < 0) return '--:--';
  s = Math.floor(s);
  const h = Math.floor(s/3600), m = Math.floor((s%3600)/60), sec = s%60;
  const mm = h > 0 ? String(m).padStart(2,'0') : String(m).padStart(2,'0');
  const ss = String(sec).padStart(2,'0');
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

function _updateTimeLabel(){
  const video = document.getElementById('preview-video');
  const el = document.getElementById('preview-time');
  if (!video || !el) return;
  el.textContent = _fmtTime(video.currentTime) + ' / ' + _fmtTime(video.duration);
}

document.addEventListener('keydown', function(e){
  const overlay = document.getElementById('preview-overlay');
  if (!overlay || !overlay.classList.contains('active')) return;
  const k = e.key;
  const video = document.getElementById('preview-video');
  if (k === 'Escape') closePreview();
  else if (k === 'ArrowLeft' && e.shiftKey) { e.preventDefault(); previewStep(-1); }
  else if (k === 'ArrowRight' && e.shiftKey) { e.preventDefault(); previewStep(1); }
  else if (k === 'ArrowLeft') { e.preventDefault(); previewNav(-1); }
  else if (k === 'ArrowRight') { e.preventDefault(); previewNav(1); }
  else if (k === ' ') { e.preventDefault(); if (video) video.paused ? video.play() : video.pause(); }
  else if (k === '[') previewSetSpeed(Math.max(0.25, (video?.playbackRate || 1) - 0.25));
  else if (k === ']') previewSetSpeed(Math.min(4, (video?.playbackRate || 1) + 0.25));
  else if (k.toLowerCase() === 'o') { e.preventDefault(); previewOpenLocal(); }
});
