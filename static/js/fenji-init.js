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

async function loadFenjiProjects(){
  try{
    const data = await api('GET','/api/projects/light');
    fenjiLight = Array.isArray(data) ? data : (data.projects||[]);
    if(fenjiLight.length > 0){
      const savedVal = $('fjProject').value;
      $('fjProject').innerHTML = '<option value="">— 选择项目 —</option>' +
        fenjiLight.map(p => `<option value="${p.name}">${p.name} (${p.total_episodes||'?'}集)</option>`).join('');
      if(savedVal) $('fjProject').value = savedVal;
      // Also update headTailPerson dropdown
      const sel = $('fjHeadTailPerson');
      if(sel){
        sel.innerHTML = '<option value="">选一位...</option>' + fjPersons.map(p => `<option value="${p}">${p}</option>`).join('');
      }
    }
  }catch(e){ updateLightLists(); }
  // 从后端恢复模板/目标路径（重开软件自动恢复）
  try{ if(typeof fjLoadPersistedSettings === 'function') await fjLoadPersistedSettings(); }catch(_){}
  // 加载人员模板
  try{ if(typeof fjLoadPersonTemplates === 'function') await fjLoadPersonTemplates(); }catch(_){}
  fjRenderChips();
  fjRenderHeadTail();
  fjRenderHistSelect();
  fjRestoreSession();
  fjRenderTable();
  fjUpdateValidation();
}
async function loadQAProjects(){ await loadFenjiProjects(); }

function fjOnProjectChange(){
  const name = $('fjProject').value;
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

