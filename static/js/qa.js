/* ============================================================
   新版 QA JavaScript（完全对齐独立视频质检工具 UI/交互）
   ============================================================ */

// ---------- 全局状态 ----------
var qa2State = {
    running: false,
    pollTimer: null,
    startTime: 0,
    layout: null,          // /api/qa/scan_dir 返回的 layout
    recentDirs: [],        // 最近目录（localStorage）
    subRegions: {},        // {"1920x1080": [x,y,w,h], ...} 按分辨率记忆
    currentSubRegion: null,// 当前匹配的 [x,y,w,h]
    firstVideoPath: null,  // 用于 /api/qa/preview_frame
    firstVideoInfo: null,  // {width,height,fps,...}
    hardsubVars: {},       // {folderName: bool}
    lastReportReady: false,// 是否有可下载的报告
    tmpProjectName: '',    // 临时存，方便导出时用
    tmpProjectPath: '',
};

var QA2_RECENT_KEY = 'qa_recent_dirs_v2';
var QA2_SUBREGION_KEY = 'qa_sub_regions_v2';

// ---------- 初始化 ----------
document.addEventListener('DOMContentLoaded', function () {
    qa2LoadPersisted();
    qa2RefreshRecentSelect();
    qa2UpdateButtons();
});

function qa2LoadPersisted() {
    try {
        var r = localStorage.getItem(QA2_RECENT_KEY);
        if (r) qa2State.recentDirs = JSON.parse(r) || [];
    } catch (e) { }
    try {
        var s = localStorage.getItem(QA2_SUBREGION_KEY);
        if (s) qa2State.subRegions = JSON.parse(s) || {};
    } catch (e) { }
}
function qa2SaveRecent() {
    try { localStorage.setItem(QA2_RECENT_KEY, JSON.stringify(qa2State.recentDirs.slice(0, 10))); } catch (e) { }
}
function qa2SaveSubRegions() {
    try { localStorage.setItem(QA2_SUBREGION_KEY, JSON.stringify(qa2State.subRegions)); } catch (e) { }
}

// ---------- 工具 ----------
function $(id) { return document.getElementById(id); }
function qa2Log(text) {
    var box = $('qa2Log');
    if (!box) return;
    var ts = new Date();
    var pad = function (n) { return n < 10 ? '0' + n : '' + n; };
    var tstr = pad(ts.getHours()) + ':' + pad(ts.getMinutes()) + ':' + pad(ts.getSeconds());
    var div = document.createElement('div');
    div.className = 'log-l';
    div.textContent = '[' + tstr + '] ' + text;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
}
function qa2ClearLog() {
    var box = $('qa2Log');
    if (box) box.innerHTML = '';
}

// ---------- 浏览目录 + 最近 ----------
function qa2BrowseDir() {
    // 弹出目录选择模态框，从 NAS 根目录列出项目文件夹
    var modal = $('qa2BrowseModal');
    if (!modal) return;
    modal.classList.add('active');
    var list = $('qa2BrowseList');
    if (list) list.innerHTML = '<div style="text-align:center;padding:20px;color:var(--text-sec)">加载中...</div>';
    // 默认加载组内NAS
    qa2LoadBrowseDirs('group');
}

function qa2LoadBrowseDirs(rootType) {
    var list = $('qa2BrowseList');
    if (!list) return;
    list.innerHTML = '<div style="text-align:center;padding:20px;color:var(--text-sec)">加载中...</div>';
    api('GET', '/api/qa/browse_dirs?root=' + (rootType || 'group')).then(function (resp) {
        if (!resp || !resp.ok || !resp.dirs) {
            list.innerHTML = '<div style="text-align:center;padding:20px;color:var(--text-sec)">无可用目录</div>';
            return;
        }
        if (resp.dirs.length === 0) {
            list.innerHTML = '<div style="text-align:center;padding:20px;color:var(--text-sec)">未找到项目文件夹</div>';
            return;
        }
        list.innerHTML = '';
        resp.dirs.forEach(function (d) {
            var item = document.createElement('div');
            item.className = 'qa-browse-item';
            var badge = d.has_delivery ? '<span style="color:var(--green);font-size:12px;margin-left:6px">📦 000交付</span>' : '';
            item.innerHTML = '<span class="qa-browse-name">' + escHtml(d.name) + '</span>' + badge +
                '<span class="qa-browse-path">' + escHtml(d.path) + '</span>';
            item.addEventListener('click', function () {
                qa2CloseBrowse();
                qa2SetDir(d.path);
            });
            list.appendChild(item);
        });
    }).catch(function (e) {
        list.innerHTML = '<div style="text-align:center;padding:20px;color:var(--red)">加载失败: ' + escHtml(e.message) + '</div>';
    });
}

function qa2CloseBrowse() {
    var modal = $('qa2BrowseModal');
    if (modal) modal.classList.remove('active');
}

function qa2PickRecent(sel) {
    var v = sel.value;
    if (!v) return;
    qa2SetDir(v);
    sel.value = '';
}

function qa2RefreshRecentSelect() {
    var sel = $('qa2Recent');
    if (!sel) return;
    sel.innerHTML = '<option value="">最近目录</option>';
    qa2State.recentDirs.forEach(function (d) {
        var opt = document.createElement('option');
        opt.value = d;
        var label = d.length > 40 ? '...' + d.slice(-38) : d;
        opt.textContent = label;
        sel.appendChild(opt);
    });
}

function qa2AddRecent(dir) {
    var list = qa2State.recentDirs.filter(function (x) { return x !== dir; });
    list.unshift(dir);
    qa2State.recentDirs = list.slice(0, 10);
    qa2SaveRecent();
    qa2RefreshRecentSelect();
}

// ---------- 设置目录 → 自动扫描 ----------
function qa2SetDir(dir) {
    if (!dir) return;
    $('qa2Dir').value = dir;
    qa2AddRecent(dir);
    qa2ScanDir(dir);
}

function qa2ScanDir(dir) {
    qa2Log('扫描目录: ' + dir);
    api('POST', '/api/qa/scan_dir', { project_path: dir }).then(function (resp) {
        if (!resp || !resp.ok) {
            qa2Log('✗ 扫描失败: ' + ((resp && resp.message) || '未知错误'));
            return;
        }
        var layout = resp.layout || {};
        qa2State.layout = layout;
        qa2State.firstVideoPath = layout.first_video_path || null;
        qa2State.firstVideoInfo = layout.first_video_info || null;

        // 项目名自动填充
        if (resp.project_name_suggest) {
            $('qa2ProjectName').value = resp.project_name_suggest;
        }

        // 填充成片下拉
        var cpSel = $('qa2CpFolder');
        cpSel.innerHTML = '';
        (layout.available_folders || []).forEach(function (f) {
            var opt = document.createElement('option');
            opt.value = f; opt.textContent = f;
            cpSel.appendChild(opt);
        });
        if (layout.cp_folder) cpSel.value = layout.cp_folder;

        // 填充硬字幕多选
        var hardContainer = $('qa2HardSubContainer');
        hardContainer.innerHTML = '';
        qa2State.hardsubVars = {};
        var hardFolders = [];
        // 默认勾选：来自 layout 的 hardsub_vars_default
        if (layout.hardsub_vars_default && typeof layout.hardsub_vars_default === 'object') {
            Object.keys(layout.hardsub_vars_default).forEach(function (f) {
                hardFolders.push(f);
                qa2State.hardsubVars[f] = !!layout.hardsub_vars_default[f];
            });
        }
        // 如果上面没产生任何候选，用 hardsub_folders 兜底
        if (hardFolders.length === 0 && Array.isArray(layout.hardsub_folders)) {
            layout.hardsub_folders.forEach(function (f) {
                if (!(f in qa2State.hardsubVars)) {
                    hardFolders.push(f);
                    qa2State.hardsubVars[f] = true;
                }
            });
        }
        // 把成片也纳入硬字幕版本候选（默认勾选）
        if (layout.cp_folder && !(layout.cp_folder in qa2State.hardsubVars)) {
            qa2State.hardsubVars[layout.cp_folder] = true;
            hardFolders.unshift(layout.cp_folder);
        }
        // 去重渲染
        var rendered = {};
        hardFolders.forEach(function (f) {
            if (rendered[f]) return;
            rendered[f] = true;
            qa2RenderHardSubCheck(f);
        });
        if (Object.keys(qa2State.hardsubVars).length === 0) {
            var hint = document.createElement('span');
            hint.style.color = 'var(--text-sec)';
            hint.style.fontSize = '13px';
            hint.textContent = '（无可用版本）';
            hardContainer.appendChild(hint);
        }

        // 字幕文件标签
        var srtLbl = $('qa2SrtLabel');
        if (layout.srt_folder && layout.srt_count > 0) {
            srtLbl.className = 'qa-info qa-info-ok';
            srtLbl.textContent = '✓ ' + layout.srt_folder + '（' + layout.srt_count + '个 .srt/.ass）';
        } else if (layout.srt_folder) {
            srtLbl.className = 'qa-info qa-info-dim';
            srtLbl.textContent = layout.srt_folder + '（0个字幕）';
        } else {
            srtLbl.className = 'qa-info qa-info-bad';
            srtLbl.textContent = '✗ 未检测到字幕文件夹';
        }

        // 文件校验标签
        var fcLbl = $('qa2FileLabel');
        var fileCounts = layout.file_counts || {};
        var srtCount = layout.srt_count || 0;
        var allVals = [];
        Object.keys(fileCounts).forEach(function (k) { allVals.push(fileCounts[k]); });
        if (layout.srt_folder) allVals.push(srtCount);
        var consistent = allVals.length > 0 && allVals.every(function (v) { return v === allVals[0]; });
        if (consistent && allVals.length > 0) {
            fcLbl.className = 'qa-info qa-info-ok';
            fcLbl.textContent = '✓ 一致（' + allVals[0] + '个 × ' + allVals.length + '个文件夹）';
        } else {
            var parts = [];
            Object.keys(fileCounts).forEach(function (k) { parts.push(k + '=' + fileCounts[k]); });
            if (layout.srt_folder) parts.push('字幕=' + srtCount);
            fcLbl.className = 'qa-info qa-info-bad';
            fcLbl.textContent = '✗ 不一致: ' + (parts.join(' / ') || '空');
        }

        // 字幕区域标签：按分辨率匹配已保存
        qa2UpdateSubRegionLabel();

        qa2Log('✓ 检测到 ' + (layout.available_folders || []).length + ' 个文件夹');
        qa2Log('  成片→' + (layout.cp_folder || '(无)') +
               '  硬字幕版本→' + (Object.keys(qa2State.hardsubVars).join(',') || '(无)') +
               '  字幕→' + (layout.srt_folder || '(无)'));
    }).catch(function (e) {
        qa2Log('✗ 扫描异常: ' + e.message);
        toast('扫描失败: ' + e.message, 'error');
    });
}

// 硬字幕版本复选框渲染（单条）
function qa2RenderHardSubCheck(folder) {
    var container = $('qa2HardSubContainer');
    var label = document.createElement('label');
    label.className = 'qa-check';
    label.style.marginRight = '4px';
    var input = document.createElement('input');
    input.type = 'checkbox';
    input.checked = !!qa2State.hardsubVars[folder];
    input.addEventListener('change', function () {
        qa2State.hardsubVars[folder] = input.checked;
        qa2RefreshFileCheckLabel();  // 数量勾选变化 → 重算一致性
    });
    var span = document.createElement('span');
    span.textContent = folder;
    label.appendChild(input);
    label.appendChild(span);
    container.appendChild(label);
}

// 用户勾选硬字幕版本变化 → 重新计算一致性显示
function qa2RefreshFileCheckLabel() {
    if (!qa2State.layout) return;
    var layout = qa2State.layout;
    var cpFolder = $('qa2CpFolder').value || layout.cp_folder;
    var fileCounts = layout.file_counts || {};
    var srtCount = layout.srt_count || 0;
    var allVals = [];
    // 所有被勾选的硬字幕版本 + 成片
    var folders = [cpFolder];
    Object.keys(qa2State.hardsubVars).forEach(function (f) {
        if (qa2State.hardsubVars[f] && folders.indexOf(f) < 0) folders.push(f);
    });
    folders.forEach(function (f) { if (typeof fileCounts[f] === 'number') allVals.push(fileCounts[f]); });
    if (layout.srt_folder) allVals.push(srtCount);
    var consistent = allVals.length > 0 && allVals.every(function (v) { return v === allVals[0]; });
    var fcLbl = $('qa2FileLabel');
    if (consistent && allVals.length > 0) {
        fcLbl.className = 'qa-info qa-info-ok';
        fcLbl.textContent = '✓ 一致（' + allVals[0] + '个 × ' + allVals.length + '个文件夹）';
    } else {
        var parts = [];
        folders.forEach(function (f) { if (typeof fileCounts[f] === 'number') parts.push(f + '=' + fileCounts[f]); });
        if (layout.srt_folder) parts.push('字幕=' + srtCount);
        fcLbl.className = 'qa-info qa-info-bad';
        fcLbl.textContent = '✗ 不一致: ' + (parts.join(' / ') || '空');
    }
}

// ---------- 字幕区域框选 ----------
function qa2UpdateSubRegionLabel() {
    var info = qa2State.firstVideoInfo;
    if (info && info.width && info.height) {
        var key = info.width + 'x' + info.height;
        if (qa2State.subRegions[key]) {
            qa2State.currentSubRegion = qa2State.subRegions[key];
        }
    }
    var lbl = $('qa2SubRegionLabel');
    var clearBtn = $('qa2SubRegionClear');
    if (qa2State.currentSubRegion) {
        var r = qa2State.currentSubRegion;
        lbl.className = 'qa-info';
        lbl.style.color = 'var(--green)';
        lbl.style.fontWeight = '500';
        lbl.style.flex = '1';
        lbl.textContent = '已框选: X=' + r[0] + '~' + (r[0] + r[2]) + ', Y=' + r[1] + '~' + (r[1] + r[3]) + ' (' + r[2] + '×' + r[3] + ')';
        if (clearBtn) clearBtn.style.display = '';
    } else {
        lbl.className = 'qa-info qa-info-dim';
        lbl.style.flex = '1';
        lbl.textContent = '未框选（使用默认比例 68%~83%）';
        if (clearBtn) clearBtn.style.display = 'none';
    }
}
function qa2ClearSubRegion() {
    var info = qa2State.firstVideoInfo;
    if (info && info.width && info.height) {
        var key = info.width + 'x' + info.height;
        delete qa2State.subRegions[key];
        qa2SaveSubRegions();
    }
    qa2State.currentSubRegion = null;
    qa2UpdateSubRegionLabel();
    qa2Log('✓ 已清除字幕区域框选，将使用默认比例');
}

// ---- SubRegionPicker Web 版 ----
var qa2Picker = {
    canvas: null, ctx: null,
    videoW: 0, videoH: 0,
    dispW: 0, dispH: 0,
    scale: 1,
    startX: 0, startY: 0,
    drawing: false,
    region: null, // [x,y,w,h] 真实坐标
    imgEl: null,
};
function qa2OpenSubPicker() {
    var path = qa2State.firstVideoPath;
    if (!path) {
        toast('请先选择项目目录并确认成片文件夹', 'warning');
        return;
    }
    $('qa2SubModal').classList.add('active');
    qa2Picker.region = qa2State.currentSubRegion ? qa2State.currentSubRegion.slice() : null;
    qa2Log('正在提取预览帧...');
    api('POST', '/api/qa/preview_frame', { video_path: path, max_width: 960 }).then(function (resp) {
        if (!resp || !resp.ok) throw new Error((resp && resp.message) || '提取帧失败');
        qa2Picker.videoW = resp.video_width;
        qa2Picker.videoH = resp.video_height;
        var img = new Image();
        img.onload = function () {
            qa2PickerSetup(img);
        };
        img.src = 'data:' + (resp.mime || 'image/jpeg') + ';base64,' + resp.jpeg;
        qa2Picker.imgEl = img;
    }).catch(function (e) {
        qa2Log('✗ 预览帧失败: ' + e.message);
        toast('预览帧失败: ' + e.message, 'error');
        qa2CloseSubPicker();
    });
}
function qa2CloseSubPicker() {
    $('qa2SubModal').classList.remove('active');
}
function qa2PickerSetup(img) {
    var canvas = $('qa2Canvas');
    var wrap = $('qa2CanvasWrap');
    var maxW = Math.min(960, wrap.clientWidth - 20);
    var maxH = Math.max(200, Math.min(window.innerHeight * 0.6, 900));
    var scaleW = maxW / qa2Picker.videoW;
    var scaleH = maxH / qa2Picker.videoH;
    var s = Math.min(1, scaleW, scaleH);
    qa2Picker.scale = s;
    qa2Picker.dispW = Math.max(1, Math.round(qa2Picker.videoW * s));
    qa2Picker.dispH = Math.max(1, Math.round(qa2Picker.videoH * s));
    canvas.width = qa2Picker.dispW;
    canvas.height = qa2Picker.dispH;
    qa2Picker.canvas = canvas;
    qa2Picker.ctx = canvas.getContext('2d');
    qa2Picker.ctx.clearRect(0, 0, qa2Picker.dispW, qa2Picker.dispH);
    qa2Picker.ctx.drawImage(img, 0, 0, qa2Picker.dispW, qa2Picker.dispH);

    // 有历史框选 → 先画上去
    if (qa2Picker.region) {
        qa2DrawRect();
    }
    qa2UpdatePickerCoord();

    // 解绑旧事件（避免重复绑定）
    if (qa2Picker._onPress) canvas.removeEventListener('mousedown', qa2Picker._onPress);
    if (qa2Picker._onDrag) window.removeEventListener('mousemove', qa2Picker._onDrag);
    if (qa2Picker._onRelease) window.removeEventListener('mouseup', qa2Picker._onRelease);

    qa2Picker._onPress = function (e) {
        var rect = canvas.getBoundingClientRect();
        var x = e.clientX - rect.left;
        var y = e.clientY - rect.top;
        qa2Picker.drawing = true;
        qa2Picker.startX = x;
        qa2Picker.startY = y;
    };
    qa2Picker._onDrag = function (e) {
        if (!qa2Picker.drawing) return;
        var rect = canvas.getBoundingClientRect();
        var x = Math.max(0, Math.min(qa2Picker.dispW, e.clientX - rect.left));
        var y = Math.max(0, Math.min(qa2Picker.dispH, e.clientY - rect.top));
        qa2Picker.region = qa2PickerRawToReal(
            Math.min(qa2Picker.startX, x),
            Math.min(qa2Picker.startY, y),
            Math.abs(x - qa2Picker.startX),
            Math.abs(y - qa2Picker.startY)
        );
        qa2RedrawAll();
    };
    qa2Picker._onRelease = function (e) {
        qa2Picker.drawing = false;
    };
    canvas.addEventListener('mousedown', qa2Picker._onPress);
    window.addEventListener('mousemove', qa2Picker._onDrag);
    window.addEventListener('mouseup', qa2Picker._onRelease);
}

function qa2PickerRawToReal(x, y, w, h) {
    var s = qa2Picker.scale;
    var rx = Math.max(0, Math.round(x / s));
    var ry = Math.max(0, Math.round(y / s));
    var rw = Math.max(1, Math.min(qa2Picker.videoW - rx, Math.round(w / s)));
    var rh = Math.max(1, Math.min(qa2Picker.videoH - ry, Math.round(h / s)));
    return [rx, ry, rw, rh];
}
function qa2RedrawAll() {
    var ctx = qa2Picker.ctx;
    if (!ctx) return;
    ctx.clearRect(0, 0, qa2Picker.dispW, qa2Picker.dispH);
    if (qa2Picker.imgEl) ctx.drawImage(qa2Picker.imgEl, 0, 0, qa2Picker.dispW, qa2Picker.dispH);
    qa2DrawRect();
    qa2UpdatePickerCoord();
}
function qa2DrawRect() {
    var ctx = qa2Picker.ctx;
    if (!ctx || !qa2Picker.region) return;
    var s = qa2Picker.scale;
    var r = qa2Picker.region;
    var x = r[0] * s, y = r[1] * s, w = r[2] * s, h = r[3] * s;
    // 半透明遮罩（矩形外变暗）
    ctx.save();
    ctx.fillStyle = 'rgba(0,0,0,0.45)';
    ctx.beginPath();
    ctx.rect(0, 0, qa2Picker.dispW, qa2Picker.dispH);
    ctx.rect(x + w, y, -w, h); // 反向路径，挖洞
    ctx.fill('evenodd');
    ctx.restore();
    // 框线
    ctx.save();
    ctx.strokeStyle = '#22d3ee';
    ctx.lineWidth = 2;
    ctx.setLineDash([6, 4]);
    ctx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);
    ctx.restore();
    // 尺寸文字
    ctx.save();
    ctx.fillStyle = '#22d3ee';
    ctx.font = 'bold 12px Menlo, Consolas, monospace';
    ctx.fillText(r[2] + '×' + r[3], x + 6, y + 16);
    ctx.restore();
}
function qa2UpdatePickerCoord() {
    var el = $('qa2SubCoord');
    if (!el) return;
    if (qa2Picker.region) {
        var r = qa2Picker.region;
        el.textContent = '真实坐标（' + qa2Picker.videoW + '×' + qa2Picker.videoH + '）：X=' + r[0] + '~' + (r[0] + r[2]) + ',  Y=' + r[1] + '~' + (r[1] + r[3]) + '   区域=' + r[2] + '×' + r[3];
    } else {
        el.textContent = '未框选（字幕区域将用于所有版本的硬字幕检测）';
    }
}
function qa2ConfirmSubRegion() {
    if (!qa2Picker.region) {
        toast('请先在画面上框出字幕区域', 'warning');
        return;
    }
    var region = qa2Picker.region.slice();
    var info = qa2State.firstVideoInfo;
    if (info && info.width && info.height) {
        var key = info.width + 'x' + info.height;
        qa2State.subRegions[key] = region;
        qa2SaveSubRegions();
    }
    qa2State.currentSubRegion = region;
    qa2UpdateSubRegionLabel();
    qa2Log('✓ 字幕区域已框选: X=' + region[0] + '~' + (region[0] + region[2]) +
          ', Y=' + region[1] + '~' + (region[1] + region[3]) +
          '  分辨率=' + qa2Picker.videoW + 'x' + qa2Picker.videoH);
    qa2CloseSubPicker();
    toast('字幕区域已保存', 'success');
}

// ---------- 按钮状态 ----------
function qa2UpdateButtons() {
    var running = qa2State.running;
    $('qa2StartBtn').style.display = running ? 'none' : '';
    $('qa2CancelBtn').style.display = running ? '' : 'none';
    $('qa2HtmlBtn').disabled = !qa2State.lastReportReady;
    $('qa2JsonBtn').disabled = !qa2State.lastReportReady;
    // 通过/失败按钮：质检完成且有项目名时才显示
    var pfRow = $('qa2PassFailRow');
    if (pfRow) {
        var show = qa2State.lastReportReady && !running && qa2State.tmpProjectName;
        pfRow.style.display = show ? 'flex' : 'none';
    }
}

// ---------- 开始检测 ----------
function qa2Start() {
    if (qa2State.running) return;
    var dir = $('qa2Dir').value.trim();
    if (!dir) { toast('请先选择项目目录', 'warning'); return; }
    var projectName = $('qa2ProjectName').value.trim();
    if (!projectName) { toast('请填写项目名称', 'warning'); return; }
    var cpFolder = $('qa2CpFolder').value;
    if (!cpFolder) { toast('请指定成片文件夹', 'warning'); return; }

    // 硬字幕版本：勾选的 + 成片
    var hardsubFolders = [cpFolder];
    Object.keys(qa2State.hardsubVars).forEach(function (f) {
        if (qa2State.hardsubVars[f] && hardsubFolders.indexOf(f) < 0) hardsubFolders.push(f);
    });
    var srtFolder = (qa2State.layout && qa2State.layout.srt_folder) || null;

    var workers = parseInt($('qa2Workers').value) || 4;
    var opts = {
        project_path: dir,
        cp_folder: cpFolder,
        hardsub_folders: hardsubFolders,
        srt_folder: srtFolder,
        opt_blackframes: !!$('qa2OptBlack').checked,
        opt_hardsubs: !!$('qa2OptHard').checked,
        opt_duration: !!$('qa2OptDur').checked,
        opt_filecheck: !!$('qa2OptFile').checked,
        workers: workers,
        sub_region: qa2State.currentSubRegion,
        folder_layout: qa2State.layout || null,
    };

    qa2State.tmpProjectName = projectName;
    qa2State.tmpProjectPath = dir;
    qa2State.lastReportReady = false;
    qa2UpdateButtons();

    qa2ClearLog();
    qa2Log('启动质检: ' + projectName + '  @ ' + dir);
    qa2Log('  成片=' + cpFolder + '  硬字幕版本=[' + hardsubFolders.join(', ') + ']' +
           (srtFolder ? '  字幕=' + srtFolder : ''));
    qa2SetProgress(0, '准备中...');
    qa2ClearResultTable();
    qa2UpdateStats(0, 0, 0, 0);

    api('POST', '/api/project/' + encodeURIComponent(projectName) + '/qa_start', opts).then(function (resp) {
        if (!resp || !resp.ok) throw new Error((resp && resp.message) || '启动失败');
        qa2State.running = true;
        qa2State.startTime = Date.now();
        qa2UpdateButtons();
        qa2Log('✓ 质检已启动，线程数=' + workers);
        qa2StartPolling();
    }).catch(function (e) {
        qa2Log('✗ 启动失败: ' + e.message);
        toast('启动失败: ' + e.message, 'error');
    });
}

function qa2Cancel() {
    var projectName = qa2State.tmpProjectName;
    if (!projectName) return;
    if (!confirm('确定要取消当前质检任务吗？')) return;
    api('POST', '/api/project/' + encodeURIComponent(projectName) + '/qa_cancel', {}).then(function () {
        qa2Log('取消请求已发送');
        toast('已取消', 'warning');
    }).catch(function (e) {
        toast('取消失败: ' + e.message, 'error');
    });
}

function qa2ClearCache() {
    var dir = $('qa2Dir').value.trim();
    var projectName = $('qa2ProjectName').value.trim() || qa2State.tmpProjectName;
    if (!dir && !projectName) { toast('请选择项目目录', 'warning'); return; }
    if (!confirm('清除该项目的断点续检缓存？（将重新检测所有视频）')) return;
    api('POST', '/api/project/' + encodeURIComponent(projectName || '__unknown__') + '/qa_checkpoint_clear',
        { project_path: dir }).then(function () {
        qa2Log('✓ 已清除断点缓存');
        toast('缓存已清除', 'success');
    }).catch(function (e) {
        toast('清除失败: ' + e.message, 'error');
    });
}

// ---------- 进度轮询 ----------
function qa2StartPolling() {
    if (qa2State.pollTimer) clearInterval(qa2State.pollTimer);
    qa2State.pollTimer = setInterval(qa2PollOnce, 1500);
    qa2PollOnce();
}
function qa2StopPolling() {
    if (qa2State.pollTimer) {
        clearInterval(qa2State.pollTimer);
        qa2State.pollTimer = null;
    }
}

function qa2PollOnce() {
    var projectName = qa2State.tmpProjectName;
    if (!projectName) return;
    api('GET', '/api/project/' + encodeURIComponent(projectName) + '/qa_status').then(function (s) {
        if (!s) return;
        var wasRunning = qa2State.running;
        var running = !!s.is_running;
        qa2State.running = running;
        if (!running && wasRunning) {
            // 刚结束：自动刷新按钮、渲染最终结果、尝试打开报告
            qa2StopPolling();
            qa2State.lastReportReady = true;
            qa2State._logIdx = 0;
            qa2UpdateButtons();
            // 自动滚动到结果区
            var resultSection = document.getElementById('qa2ResultBox');
            if (resultSection) {
                setTimeout(function () {
                    resultSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }, 250);
            }
            // 自动在新标签打开 HTML 报告（如果存在）
            if (s.report_html || s.qa_result_file) {
                setTimeout(function () {
                    qa2ExportHtml(true);
                }, 500);
            }
        }
        qa2UpdateButtons();

        // 进度
        var pct = parseFloat(s.progress) || 0;
        var total = parseInt(s.total) || 0;
        var done = parseInt(s.done) || 0;
        var cur = s.current_video || '';
        var label = '';
        if (running) {
            var elapsed = Math.floor((Date.now() - qa2State.startTime) / 1000);
            var eta = parseInt(s.eta) || 0;
            var avg = done > 0 ? (elapsed / done) : 0;
            label = '检测中  ' + done + '/' + total +
                    (cur ? '  当前: ' + cur : '') +
                    '  总 ' + elapsed + 's' +
                    (eta > 0 ? '  剩 ' + eta + 's' : '') +
                    (avg > 0 ? '  均 ' + avg.toFixed(1) + 's/个' : '');
        } else if (s.status === 'done') {
            var passed = parseInt(s.passed) || 0;
            var warn = parseInt(s.warnings) || 0;
            var fail = parseInt(s.failed) || 0;
            var el = parseInt(s.elapsed) || Math.floor((Date.now() - qa2State.startTime) / 1000);
            label = '✅ 检测完成  ' + passed + '通过, ' + warn + '警告, ' + fail + '失败  耗时' + el + 's';
        } else if (s.status === 'cancelled') {
            label = '⚠ 任务已取消';
        } else if (s.status === 'error') {
            label = '✗ 出错: ' + (s.error || '未知错误');
        }
        qa2SetProgress(pct, label);

        // 日志增量
        var logs = s.log || [];
        // 用一个索引记录上次已追加到哪
        if (typeof qa2State._logIdx !== 'number') qa2State._logIdx = 0;
        for (var i = qa2State._logIdx; i < logs.length; i++) {
            // 后端的 log 可能带 [HH:MM:SS] 前缀，也可能不带；这里直接追加
            var line = logs[i] || '';
            // 如果没带时间戳，qa2Log 会自动加
            if (/^\[\d{2}:\d{2}:\d{2}\]/.test(line)) {
                var box = $('qa2Log');
                if (box) {
                    var div = document.createElement('div');
                    div.className = 'log-l';
                    div.textContent = line;
                    box.appendChild(div);
                    box.scrollTop = box.scrollHeight;
                }
            } else {
                qa2Log(line);
            }
        }
        qa2State._logIdx = logs.length;

        // 结果表格
        var results = s.results || [];
        qa2RenderResultTable(results, s);

        // 统计
        var passed = parseInt(s.passed) || 0;
        var warn = parseInt(s.warnings) || 0;
        var fail = parseInt(s.failed) || 0;
        qa2UpdateStats(total, passed, warn, fail);
    }).catch(function (e) {
        // 静默
    });
}

// ---------- UI 更新辅助 ----------
function qa2SetProgress(pct, label) {
    $('qa2ProgressFill').style.width = Math.max(0, Math.min(100, pct)) + '%';
    $('qa2ProgressLabel').textContent = label || ('就绪  ' + pct.toFixed(0) + '%');
}

function qa2ClearResultTable() {
    var body = $('qa2TreeBody');
    if (!body) return;
    body.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-sec);padding:32px">检测中...</td></tr>';
}

function qa2RenderResultTable(results, status) {
    var body = $('qa2TreeBody');
    if (!body) return;
    if (!results || results.length === 0) {
        body.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-sec);padding:32px">' +
            (qa2State.running ? '检测中...' : '选择项目目录并点击「开始检测」') +
            '</td></tr>';
        return;
    }
    var cpFolder = (qa2State.layout && qa2State.layout.cp_folder) ||
                   (status && status.folder_info && status.folder_info.cp_folder) || '';
    body.innerHTML = '';
    // 按自然顺序排序
    results = results.slice().sort(function (a, b) {
        return naturalCmp(a.video || '', b.video || '');
    });
    results.forEach(function (r) {
        var tr = document.createElement('tr');
        var st = r.status || 'pass';
        tr.className = st === 'pass' ? 'qa-pass' : (st === 'warn' ? 'qa-warn' : 'qa-fail');

        var tdVideo = document.createElement('td');
        tdVideo.className = 'center';
        tdVideo.innerHTML = '<span class="video-name">' + escHtml(r.video || '') + '</span>';

        var tdBf = document.createElement('td');
        tdBf.className = 'center';
        var bfMap = r.black_frames || {};
        var bfList = bfMap[cpFolder] || [];
        if (bfList && bfList.length > 0) {
            var totalDur = 0;
            bfList.forEach(function (b) { totalDur += b.duration || 0; });
            tdBf.innerHTML = '<span style="color:var(--orange);font-weight:600">⚠ ' + bfList.length + '段</span><br>' +
                             '<span style="color:var(--text-sec);font-size:11px">' + totalDur.toFixed(2) + 's</span>';
        } else {
            tdBf.innerHTML = '<span style="color:var(--green)">✓ 无</span>';
        }

        var tdHs = document.createElement('td');
        var hsMap = r.hard_sub || {};
        var hsKeys = Object.keys(hsMap);
        if (hsKeys.length === 0) {
            tdHs.innerHTML = '<span style="color:var(--text-sec)">—</span>';
        } else {
            var hsHtml = '';
            hsKeys.forEach(function (folder) {
                var hs = hsMap[folder] || {};
                var has = !!hs.has_hardsub;
                var isCp = (folder === cpFolder);
                var ok = isCp ? has : !has;
                var cls = ok ? 'ok' : 'bad';
                var icon = ok ? '✓' : '✗';
                var avg = typeof hs.avg_density === 'number' ? hs.avg_density.toFixed(2) + '%' : '';
                var short = folder.length > 8 ? folder.slice(0, 7) + '…' : folder;
                hsHtml += '<span class="hs-badge ' + cls + '" title="' + escHtml(folder) + ' 平均密度=' + avg + '">' +
                          escHtml(short) + ':' + icon + '</span>';
            });
            tdHs.innerHTML = hsHtml;
        }

        var tdSt = document.createElement('td');
        tdSt.className = 'center';
        var stMap = { pass: ['ok', '✓ 通过'], warn: ['wn', '⚠ 警告'], fail: ['bd', '✗ 失败'] };
        var sPair = stMap[st] || ['ok', '✓ 通过'];
        tdSt.innerHTML = '<span class="st ' + sPair[0] + '">' + sPair[1] + '</span>';

        var tdTime = document.createElement('td');
        tdTime.className = 'center';
        var t = (r.timing && r.timing.total) || r.timing_seconds || 0;
        tdTime.textContent = t > 0 ? t.toFixed(1) + 's' : '—';

        var tdDetail = document.createElement('td');
        tdDetail.className = 'dtl';
        tdDetail.textContent = r.details || (r.issues && r.issues.length ? r.issues.join('；') : '');

        tr.appendChild(tdVideo);
        tr.appendChild(tdBf);
        tr.appendChild(tdHs);
        tr.appendChild(tdSt);
        tr.appendChild(tdTime);
        tr.appendChild(tdDetail);
        body.appendChild(tr);
    });
}

function qa2UpdateStats(total, passed, warn, fail) {
    var el = $('qa2Stats');
    if (!el) return;
    el.innerHTML =
        '共 <b>' + total + '</b> 个 ｜  ' +
        '<span style="color:var(--green)">✓' + passed + '</span>  ' +
        '<span style="color:var(--orange)">⚠' + warn + '</span>  ' +
        '<span style="color:var(--red)">✗' + fail + '</span>';
}

function escHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
        return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
    });
}
function naturalCmp(a, b) {
    // 简易自然排序：把数字段按数值比
    function pad(s) { return String(s).replace(/(\d+)/g, function (m) { return m.padStart(10, '0'); }); }
    a = pad(a); b = pad(b);
    return a < b ? -1 : (a > b ? 1 : 0);
}

// ---------- 导出 HTML / JSON ----------
// window.open 打开的 URL 不走 fetch 拦截器，需手动补 API key，否则被 /api 鉴权拦截
function _qaApiUrl(path){
  var key = window.__API_KEY__ || '';
  if(!key) return path;
  var sep = path.indexOf('?') >= 0 ? '&' : '?';
  return path + sep + 'key=' + encodeURIComponent(key);
}
function qa2ExportHtml(silent) {
    var projectName = qa2State.tmpProjectName;
    if (!projectName) { if (!silent) toast('暂无可导出的报告', 'warning'); return; }
    // 自动打开：用 dl=0 让浏览器内联显示（HTML 页面）；手动点击下载用 dl=1 强制下载
    var dl = silent ? '0' : '1';
    window.open(_qaApiUrl('/api/project/' + encodeURIComponent(projectName) + '/qa_report?fmt=html&dl=' + dl), '_blank');
}
function qa2ExportJson() {
    var projectName = qa2State.tmpProjectName;
    if (!projectName) { toast('暂无可导出的数据', 'warning'); return; }
    window.open(_qaApiUrl('/api/project/' + encodeURIComponent(projectName) + '/qa_report?fmt=json&dl=1'), '_blank');
}

// ---------- 质检通过 → 跳转交付回传 ----------
function qa2PassToDelivery() {
    var projectName = qa2State.tmpProjectName;
    if (!projectName) { toast('项目名未知', 'warning'); return; }

    toast('✅ 质检通过，正在跳转到交付回传...', 'info');
    qa2Log('→ 跳转到交付回传界面（000交付模式）');

    // 打开交付模态框，强制使用 delivery 模式（根目录 = 000交付 文件夹列表）
    openDeliverablesModal(projectName, 'delivery');

    // 等文件夹列表加载完成 → 自动触发整目录交付（或子文件夹全选回传）
    var attempts = 0;
    var maxAttempts = 30; // 最多等 6s
    var autoTimer = setInterval(function () {
        attempts++;
        if (attempts > maxAttempts) {
            clearInterval(autoTimer);
            toast('⚠ 交付目录加载超时，请手动勾选回传', 'warning');
            return;
        }
        var folders = _deliverablesState.folders || [];
        var subp = _deliverablesState.subpath || '';
        if (_deliverablesState.mode === 'delivery' && folders.length > 0) {
            clearInterval(autoTimer);
            // 场景1：在根目录（subpath=""），通常只有 1 个虚拟文件夹 "000交付" → 直接触发整目录交付
            // 场景2：已进入 "000交付" 内部 → 全选真实子文件夹（00成片、01字幕等）
            if (!subp && folders.length === 1 && folders[0].name === folders[0].path) {
                qa2Log('→ 检测到交付根目录（单文件夹: ' + folders[0].name + '），触发整目录交付');
                _deliverablesState.selectedFolders = {};
                _deliverablesState.selectedFolders[folders[0].name] = true;
                renderDeliverablesModal();
                setTimeout(function () { deliverFolders(); }, 300);
            } else {
                qa2AutoSelectAndDeliver(projectName);
            }
        }
    }, 200);
}

// 自动勾选全部交付文件夹并触发回传
// 注意：本函数用于"已进入 000交付 内部"的场景（folders 是真实子文件夹：00成片、01字幕等）
// 如果在根目录，请走 qa2PassToDelivery 中的整目录交付分支
function qa2AutoSelectAndDeliver(projectName) {
    var folders = _deliverablesState.folders || [];
    if (folders.length === 0) {
        toast('⚠ 交付目录为空，请手动操作', 'warning');
        return;
    }
    // 双重保险：如果只有 1 个文件夹且名字/路径相同（说明是根目录虚拟文件夹），
    // 也直接按整目录交付处理，避免进入子文件夹再全选
    var subp = _deliverablesState.subpath || '';
    if (!subp && folders.length === 1 && folders[0].name === folders[0].path) {
        qa2Log('→ 修正：检测到根目录虚拟文件夹 ' + folders[0].name + '，按整目录交付处理');
        _deliverablesState.selectedFolders = {};
        _deliverablesState.selectedFolders[folders[0].name] = true;
        renderDeliverablesModal();
        toast('📦 整目录交付已启动（' + folders[0].name + '），请查看系统复制进度对话框', 'success');
        setTimeout(function () { deliverFolders(); }, 300);
        return;
    }
    // 正常场景：全选真实子文件夹并触发批量回传
    _deliverablesState.selectedFolders = {};
    folders.forEach(function (f) { _deliverablesState.selectedFolders[f.name] = true; });
    qa2Log('→ 已自动勾选 ' + folders.length + ' 个交付子文件夹: ' + folders.map(function (f) { return f.name; }).join(', '));
    renderDeliverablesModal();

    toast('📦 已自动勾选 ' + folders.length + ' 个文件夹，开始回传到制作部...', 'success');
    // 直接触发文件夹回传
    setTimeout(function () {
        deliverFolders();
    }, 400);
}

// ---------- 质检失败 → 设置项目状态为修改中 ----------
function qa2FailToRevising() {
    var projectName = qa2State.tmpProjectName;
    if (!projectName) { toast('项目名未知', 'warning'); return; }
    if (!confirm('确定将项目「' + projectName + '」标记为「修改中」并返回修改吗？')) return;

    qa2Log('→ 设置项目状态为「修改中」');
    api('POST', '/api/project/' + encodeURIComponent(projectName) + '/custom_status', {
        custom_status: '修改中'
    }).then(function (r) {
        if (r && r.ok) {
            toast('❌ 已标记为「修改中」，请通知剪辑师修改', 'warning');
            // 刷新 dashboard
            if (typeof renderDashboard === 'function') renderDashboard();
        } else {
            toast('标记失败: ' + ((r && r.message) || '未知错误'), 'error');
        }
    }).catch(function (e) {
        toast('标记失败: ' + e.message, 'error');
    });
}

// ---------- 旧版 API 兼容（保留，避免 dashboard 其它地方报错）----------
// 注意：qaRunning / pollQA / qaStartTime 已在 core.js 顶部用 let 声明，此处不重复声明
async function qaOnProjectChange() {
    var name = $('qaProject') ? $('qaProject').value : '';
    if (!name) return;
    try { var d = await api('GET', '/api/project/' + encodeURIComponent(name) + '/source_dir'); if (d && d.path) $('qaPath').value = d.path; } catch (e) { }
}
async function qaStart() {
    var project = $('qaProject') ? $('qaProject').value : '';
    if (!project) { toast('请选择项目', 'warning'); return; }
    qa2Log('请在「质检中心」Tab 使用新版质检功能', 'info');
    switchTab('qa');
}
async function qaCancel() { if (!qaRunning) return; try { await api('POST', '/api/project/' + encodeURIComponent($('qaProject').value) + '/qa_cancel'); } catch (e) { } }
function updateQAButtons() { }
function startQAPolling() { }
async function refreshQAResult() { }
async function loadQAHistory(p) { }
async function loadQAHistoryRun(p, i) { }

// ===== 质检概览统计条（质检中心顶部）=====
async function loadQASummary() {
  const bar = document.getElementById('qaSummaryBar');
  if (!bar) return;
  bar.innerHTML = '<div style="padding:12px 16px;color:#86868b;font-size:13px;text-align:center">加载质检统计...</div>';
  try {
    const d = await api('GET', '/api/qa/summary');
    if (!d || !d.ok) { bar.innerHTML = ''; return; }
    const s = d.summary || {};
    const bs = d.by_status || {};
    const passCount = (bs.pass || []).length;
    const warnCount = (bs.warn || []).length;
    const failCount = (bs.fail || []).length;
    const runCount = (bs.running || []).length;
    const rate = s.pass_rate || 0;

    const rateColor = rate >= 90 ? '#2E7D32' : (rate >= 70 ? '#b8860b' : '#c5221f');
    const failHtml = (bs.fail || []).map(function(p){
      return `<span style="color:#c5221f;font-weight:600" title="${p.project_name}">${p.project_name.length>12?p.project_name.slice(0,12)+'…':p.project_name}(${p.last_fail}失败)</span>`;
    }).join(', ');

    bar.innerHTML = `<div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;background:linear-gradient(90deg,#f8fafc,#eef4ff);border:1px solid #dbe4f0;border-radius:10px;padding:12px 18px;font-size:13px">
      <span style="font-weight:700">🔍 质检概览</span>
      <span>质检 <b>${s.total_run||0}</b> 次 · 视频 <b>${s.total_videos||0}</b> 个</span>
      <span>通过率 <b style="color:${rateColor};font-size:16px">${rate}%</b></span>
      <span>🟢 通过 <b>${s.total_pass||0}</b></span>
      <span>🟡 警告 <b>${s.total_warn||0}</b></span>
      <span>🔴 失败 <b>${s.total_fail||0}</b></span>
      <span style="flex:1"></span>
      <span title="通过 ${passCount} · 警告 ${warnCount} · 失败 ${failCount} · 运行 ${runCount}">
        项目: <b style="color:#2E7D32">${passCount}通过</b> · <b style="color:#b8860b">${warnCount}警告</b> · <b style="color:#c5221f">${failCount}失败</b>
        ${runCount ? ' · ⏳运行中 <b style="color:#0071e3">'+runCount+'</b>' : ''}
      </span>
      <button class="btn btn-sm" onclick="qaDownloadBatchReport()" title="下载跨项目质检汇总报告">📥 批量报告</button>
      <button class="btn btn-sm qa-btn qa-btn-accent" onclick="qaShowBatchStart()" title="对多个进行中项目批量启动质检">⚡ 批量质检</button>
    </div>
    ${failHtml ? `<div style="margin-top:6px;font-size:12px;color:#c5221f;padding:0 4px">⚠️ 未通过质检的项目: ${failHtml}</div>` : ''}`;
  } catch (e) {
    bar.innerHTML = '';
  }
}

// 下载批量质检汇总报告
function qaDownloadBatchReport() {
  window.open('/api/qa/batch_report?dl=1', '_blank');
}

// 批量质检：选择多个进行中项目启动质检
function qaShowBatchStart() {
  const items = (window.allSections || []).reduce(function(acc, sec){
    (sec.projects || []).forEach(function(p){
      const s = String(p.custom_status || '').trim();
      if (s && s !== '已完成' && s !== '质检中') acc.push(p);
    });
    return acc;
  }, []);
  if (items.length === 0) { toast('没有可批量质检的项目', 'warning'); return; }

  // 弹选择框
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay active';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.4);z-index:999;display:flex;align-items:center;justify-content:center';
  const listHtml = items.map(function(p, i){
    return `<label style="display:flex;align-items:center;gap:8px;padding:6px 8px;border-radius:6px;cursor:pointer">
      <input type="checkbox" checked data-idx="${i}" style="width:15px;height:15px">
      <span>${htm(p.name)}</span><span style="color:#86868b;font-size:12px">(${p.custom_status||'未设置'})</span>
    </label>`;
  }).join('');
  overlay.innerHTML = `<div style="background:#fff;border-radius:12px;width:520px;max-height:80vh;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 8px 30px rgba(0,0,0,.2)">
    <div style="padding:14px 18px;border-bottom:1px solid #eee;font-weight:700">⚡ 批量质检 <span style="font-weight:400;color:#86868b;font-size:12px">选择要质检的项目（已排除质检中）</span></div>
    <div style="padding:10px 18px;overflow-y:auto;flex:1">${listHtml}</div>
    <div style="padding:12px 18px;border-top:1px solid #eee;display:flex;justify-content:flex-end;gap:8px">
      <button class="btn btn-sm" onclick="this.closest('.modal-overlay').remove()">取消</button>
      <button class="btn btn-sm btn-primary" onclick="qaDoBatchStart(this)">🚀 开始质检</button>
    </div>
  </div>`;
  document.body.appendChild(overlay);
  overlay._qaItems = items;
}

async function qaDoBatchStart(btn) {
  const overlay = btn.closest('.modal-overlay');
  const items = overlay._qaItems || [];
  const selected = [];
  overlay.querySelectorAll('input[data-idx]').forEach(function(cb){
    if (cb.checked) selected.push(items[parseInt(cb.dataset.idx)]);
  });
  if (selected.length === 0) { toast('请至少选择一个项目', 'warning'); return; }
  const names = selected.map(function(p){ return p.name; });
  btn.disabled = true; btn.textContent = '启动中...';
  try {
    const r = await api('POST', '/api/qa/batch_start', { projects: names, workers: 4 });
    toast(('✅ 已启动 ' + (r.started_count||0) + ' 个项目质检') + ((r.skipped_count||0) ? ('，跳过 ' + r.skipped_count + ' 个') : ''), 'success');
    overlay.remove();
    loadQASummary();
    if (typeof loadProjects === 'function') loadProjects();
  } catch(e) {
    toast('❌ 批量质检失败: ' + e.message, 'error');
    btn.disabled = false; btn.textContent = '🚀 开始质检';
  }
}
