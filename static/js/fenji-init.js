// 分集初始化: FJ 变量, fjLoad, fjSave, loadFenjiProjects
/* ============ Fenji v2 (借鉴分集程序) ============ */
const FJ_KEY_PERSONS = 'wb_fj_persons';
const FJ_KEY_TEMPLATES = 'wb_fj_templates';
const FJ_KEY_HISTORY = 'wb_fj_history';
const FJ_KEY_SESSION = 'wb_fj_session';
const FJ_DEFAULTS = ["张大强","陈陆杰","任显翔","陈春阳","程梦","张靖杰","金文龙","刘梦真","张淯升","杨倩","袁绍杰","陈浩博","王田田","王傲雪","李钊琦"];

let fjPersons = fjLoad(FJ_KEY_PERSONS, FJ_DEFAULTS.slice());
let fjSelected = [];
let fjRanges = {};      // { personName: "1-10,68-70" }
let fjHist = fjLoad(FJ_KEY_HISTORY, []);
let fjSuppressSaveHist = false;

function fjLoad(k, def){ try{ const s = localStorage.getItem(k); if(s) return JSON.parse(s); } catch(e){} return def; }
function fjSave(k, v){ try{ localStorage.setItem(k, JSON.stringify(v)); } catch(e){} }

async function loadFenjiProjects(targetName){
  // 序列守卫：并发调用时只有「最新一次」允许写 DOM。
  // 否则一个较慢的旧的无参调用会在稍后完成，把指定打开的目标项目覆盖掉。
  var _seq = (window._fjLoadSeq || 0) + 1;
  window._fjLoadSeq = _seq;
  var _isLatest = function(){ return window._fjLoadSeq === _seq; };
  // 问题5：始终合并团队设置里的所有成员到剪辑师列表，避免缺人
  try{
    const td = await api('GET','/api/team/members');
    const names = ((td && td.members) || []).map(function(m){ return (m && m.name) || ''; }).filter(Boolean);
    names.forEach(function(n){ if(!fjPersons.includes(n)) fjPersons.push(n); });
    fjSave(FJ_KEY_PERSONS, fjPersons);
    window._teamNames = names;
  }catch(_){}
  try{
    const data = await api('GET','/api/projects/light');
    if(!_isLatest()) return;   // 已被更新的调用取代，放弃写 DOM
    fenjiLight = Array.isArray(data) ? data : (data.projects||[]);
    // 目标项目可能不在 light 列表里（如已完成项目只在 group_completed 桶）：
    // 动态补进去，否则下拉选不中、后续 readFromProject 会拿到空项目名
    if(targetName && !fenjiLight.some(p => p && p.name === targetName)){
      let _te = 0;
      try{
        const _pd = await api('GET','/api/project/'+encodeURIComponent(targetName)+'/episodes_plan');
        _te = (_pd && _pd.total_episodes) || 0;
      }catch(_){}
      if(!_isLatest()) return;
      fenjiLight.unshift({ name: targetName, total_episodes: _te, custom_status: '', department: '' });
    }
    if(fenjiLight.length > 0){
      const savedVal = targetName || $('fjProject').value;
      $('fjProject').innerHTML = '<option value="">— 选择项目 —</option>' +
        fenjiLight.map(p => `<option value="${p.name}">${p.name} (${p.total_episodes||'?'}集)</option>`).join('');
      if(savedVal) $('fjProject').value = savedVal;
      // Also update headTailPerson dropdown
      const sel = $('fjHeadTailPerson');
      if(sel){
        sel.innerHTML = '<option value="">选一位...</option>' + fjPersons.map(p => `<option value="${p}">${p}</option>`).join('');
      }
    }
  }catch(e){ if(!_isLatest()) return; updateLightLists(); }
  if(!_isLatest()) return;
  // 从后端恢复模板/目标路径（重开软件自动恢复）
  try{ if(typeof fjLoadPersistedSettings === 'function') await fjLoadPersistedSettings(); }catch(_){}
  // 加载人员模板
  try{ if(typeof fjLoadPersonTemplates === 'function') await fjLoadPersonTemplates(); }catch(_){}
  if(!_isLatest()) return;
  fjRenderChips();
  fjRenderHeadTail();
  fjRenderHistSelect();
  // 问题1：指定了目标项目时跳过 session 恢复，避免 setTimeout 覆盖跳转目标
  if(!targetName) fjRestoreSession();
  fjRenderTable();
  fjUpdateValidation();
}
async function loadQAProjects(){ await loadFenjiProjects(); }

function fjOnProjectChange(){
  const name = $('fjProject').value;
  // 手动切换项目 → 退出调整模式
  try{ if(typeof fjAdjustMode !== 'undefined' && fjAdjustMode.active){ fjAdjustMode = { active:false, project:'' }; if(typeof fjRenderAdjustBar==='function') fjRenderAdjustBar(); } }catch(_){}
  if(!name){ fjClearAll(); return; }
  // Check reuse from history
  const hit = fjHist.find(h => h.path === name || h.name === name);
  if(hit && confirm(`检测到项目 "${name}" 有历史分集记录，是否沿用上次的人员分配？`)){
    fjSuppressSaveHist = true;
    fjRestoreHistEntry(hit);
    setTimeout(() => { fjSuppressSaveHist = false; }, 100);
    return;
  }
  fjSaveSession();
}

