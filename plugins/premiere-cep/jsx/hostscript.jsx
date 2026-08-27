// -*- coding: utf-8 -*-
// 视频工作台 · Premiere Pro CEP 扩展脚本（ExtendScript / JSX）
// 由面板通过 csInterface.evalScript() 调用。
// 读取当前 Premiere 项目 / 序列信息，供面板与工作台联动。
//
// 返回约定：单个函数返回 JSON 字符串；错误时返回 {"error": "..."}。
// 注意：ExtendScript 的 JSON 支持有限（AE/PR 内置 ExtendScript JSON 可用）。

// ---------- 工具 ----------
function _jsonStr(obj) {
    // ExtendScript 内置 JSON 对象（PR 支持）
    return JSON.stringify(obj);
}

// 从序列名/文件名提取集号（复用工作台的集号识别思路：EP12 / S01E03 / 第8集 / 纯数字）
function _extractEpisodeNumber(name) {
    if (!name) return null;
    var s = String(name);
    var m;
    m = s.match(/EP[\s_\-]?(\d{1,3})(?!\d)/i);
    if (m) return parseInt(m[1], 10);
    m = s.match(/S\d{1,2}E[\s_\-]?(\d{1,3})(?!\d)/i);
    if (m) return parseInt(m[1], 10);
    m = s.match(/第[\s_\-]*(\d{1,3})[集话]/);
    if (m) return parseInt(m[1], 10);
    m = s.match(/[\s_\-](\d{1,3})[\s_\-]?$/);
    if (m) return parseInt(m[1], 10);
    return null;
}

// ---------- 对外入口 ----------
// 返回当前项目/序列概览（供面板显示 + 查找工作台项目）
function getProjectInfo() {
    var out = { projectName: "", projectPath: "", sequences: [], activeSequence: "", activeEp: null };
    try {
        var pr = app.project;
        if (!pr) return _jsonStr({ error: "未打开任何项目" });
        out.projectName = pr.name || "";
        try { out.projectPath = pr.path || ""; } catch (e) { out.projectPath = ""; }
        // 序列列表（名称 + 集号）
        if (pr.sequences) {
            for (var i = 0; i < pr.sequences.numSequences; i++) {
                var seqName = pr.sequences[i].name || "";
                out.sequences.push({
                    name: seqName,
                    ep: _extractEpisodeNumber(seqName),
                });
            }
        }
        // 当前活动序列
        try {
            if (app.project.activeSequence) {
                out.activeSequence = app.project.activeSequence.name || "";
                out.activeEp = _extractEpisodeNumber(out.activeSequence);
            }
        } catch (e) {}
        return _jsonStr(out);
    } catch (e) {
        return _jsonStr({ error: String(e) });
    }
}

// 供 evalScript 分发的统一入口：window.__workbenchDispatch(name)
// 在 CEP 面板中通过 csInterface.evalScript('__workbenchDispatch("getProjectInfo")') 调用
function __workbenchDispatch(name) {
    if (name === "getProjectInfo") {
        return getProjectInfo();
    }
    return _jsonStr({ error: "未知命令: " + name });
}
