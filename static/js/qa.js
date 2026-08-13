// QA: qaStart, qaCancel, startQAPolling, loadQAHistory
async function qaOnProjectChange(){
  const name=$('qaProject').value;if(!name){$('qaPath').value='';return}
  try{
    const data=await api('GET',`/api/project/${encodeURIComponent(name)}/source_dir`);
    $('qaPath').value=data.path||data.source_dir||data||'';
  }catch(e){$('qaPath').value=''}
  loadQAHistory(name);
}
async function qaStart(){
  const project=$('qaProject').value;if(!project){toast('请选择项目','warning');return}
  const path=$('qaPath').value;const workers=parseInt($('qaWorkers').value)||4;
  try{
    toast('开始质检...','info');qaStartTime=Date.now();
    await api('POST',`/api/project/${encodeURIComponent(project)}/qa_start`,{project_path:path,workers});
    qaRunning=true;updateQAButtons();startQAPolling();toast('质检已启动','success');
  }catch(e){toast('启动失败: '+e.message,'error')}
}
async function qaCancel(){
  const project=$('qaProject').value;if(!project)return;
  try{
    await api('POST',`/api/project/${encodeURIComponent(project)}/qa_cancel`);
    toast('已取消','warning');qaRunning=false;updateQAButtons();
  }catch(e){toast('取消失败: '+e.message,'error')}
}
function updateQAButtons(){
  $('qaStartBtn').style.display=qaRunning?'none':'';
  $('qaCancelBtn').style.display=qaRunning?'':'none';
}
function startQAPolling(){
  if(pollQA)clearInterval(pollQA);
  pollQA=setInterval(async()=>{
    const project=$('qaProject').value;if(!project)return;
    try{
      const s=await api('GET',`/api/project/${encodeURIComponent(project)}/qa_status`);
      qaRunning=s.is_running!==false;
      const pct=s.progress||0;const label=s.current_video||s.current||'—';
      $('qaProgressFill').style.width=pct+'%';$('qaProgressPct').textContent=pct+'%';$('qaProgressLabel').textContent=label;
      const done=s.done||s.completed||0;const total=s.total||0;const elapsed=Math.floor((Date.now()-qaStartTime)/1000);
      $('qaCounter').textContent=`${done} / ${total} · ${elapsed}秒`;
      if(!qaRunning){updateQAButtons();if(pollQA){clearInterval(pollQA);pollQA=null}await refreshQAResult()}
      await refreshQAResult();
    }catch(e){}
  },2000);
}
async function refreshQAResult(){
  const project=$('qaProject').value;if(!project)return;
  try{
    const r=await api('GET',`/api/project/${encodeURIComponent(project)}/qa_result`);
    const total=r.total||(r.issues?r.issues.length:0);const passed=r.passed||0;const warnings=r.warnings||0;const failed=r.failed||0;
    $('qaNumTotal').textContent=total;$('qaNumPassed').textContent=passed;$('qaNumWarn').textContent=warnings;$('qaNumFailed').textContent=failed;
    const issues=r.issues||[];
    if(issues.length===0){$('qaIssueBody').innerHTML='<tr><td colspan="3" style="text-align:center;color:var(--text-sec);padding:30px">暂无问题</td></tr>'}
    else{$('qaIssueBody').innerHTML=issues.map(it=>{
      const st=String(it.status||'').toLowerCase();
      const cls=st==='pass'?'pass':st==='warn'?'warn':'fail';
      const icon=st==='pass'?'✅':st==='warn'?'⚠️':'❌';
      return`<tr><td>${it.video||it.name||it.file||''}</td><td><span class="qa-badge ${cls}">${icon} ${st||''}</span></td><td>${it.details||it.message||it.reason||''}</td></tr>`;
    }).join('')}
  }catch(e){}
}
async function loadQAHistory(project){
  if(!project)return;
  try{
    const h=await api('GET',`/api/project/${encodeURIComponent(project)}/qa_history`);
    const list=Array.isArray(h)?h:(h.runs||[]);
    const c=$('qaHistory');
    if(list.length===0){c.innerHTML='<div style="padding:20px;text-align:center;color:var(--text-sec)">暂无历史</div>';return}
    c.innerHTML=list.map(r=>{
      const t=new Date(r.started_at||r.timestamp||Date.now());
      const passed=r.passed||0,warn=r.warnings||0,fail=r.failed||0,total=r.total||0;
      return`<div class="history-item" onclick="loadQAHistoryRun('${project}',${list.indexOf(r)})">
        <span class="ts">${t.toLocaleString()}</span>
        <span>✅${passed} ⚠️${warn} ❌${fail} / ${total}</span>
      </div>`;
    }).join('');
  }catch(e){}
}
async function loadQAHistoryRun(project,idx){try{const r=await api('GET',`/api/project/${encodeURIComponent(project)}/qa_history`);const list=Array.isArray(r)?r:(r.runs||[]);if(list[idx]){const run=list[idx];qaRunning=false;updateQAButtons();$('qaProgressFill').style.width='100%';$('qaProgressPct').textContent='100%';$('qaNumTotal').textContent=run.total||0;$('qaNumPassed').textContent=run.passed||0;$('qaNumWarn').textContent=run.warnings||0;$('qaNumFailed').textContent=run.failed||0}}catch(e){}}

/* ============ Settings ============ */
