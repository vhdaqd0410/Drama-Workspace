/* 数据备份（融合自「项目档案管理器」backupService）
 * - 查看备份列表 / 立即备份 / 从备份恢复
 * - openBackupDialog() 弹窗，可从设置页或命令面板调用
 */
async function openBackupDialog(){
  const overlay = document.createElement('div');
  overlay.id = 'backupDialogOverlay';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:21000;display:flex;align-items:center;justify-content:center';
  overlay.innerHTML = `
    <div style="background:var(--card,#fff);border-radius:14px;width:560px;max-width:94vw;max-height:86vh;display:flex;flex-direction:column;box-shadow:0 18px 50px rgba(0,0,0,.3);font-family:inherit">
      <div style="padding:16px 20px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--border,#e5e5ea)">
        <h3 style="margin:0">💾 数据备份</h3>
        <button onclick="closeBackupDialog()" style="border:none;background:none;font-size:18px;cursor:pointer">✕</button>
      </div>
      <div style="padding:16px 20px;flex:1;overflow-y:auto">
        <div style="display:flex;gap:8px;margin-bottom:14px">
          <button class="btn btn-primary btn-sm" onclick="backupCreate()">🛡️ 立即备份</button>
          <span style="font-size:12px;color:var(--text-sec);align-self:center">每日自动备份，保留最近 7 份。恢复前会自动备份当前数据。</span>
        </div>
        <div id="backupListBox"><div style="color:var(--text-sec);font-size:13px">加载中...</div></div>
      </div>
    </div>`;
  overlay.addEventListener('mousedown', (e)=>{ if(e.target===overlay) closeBackupDialog(); });
  document.body.appendChild(overlay);
  await loadBackupList();
}
function closeBackupDialog(){
  const o = document.getElementById('backupDialogOverlay');
  if(o) o.remove();
}

async function loadBackupList(){
  const box = document.getElementById('backupListBox');
  if(!box) return;
  try{
    const d = await api('GET','/api/backup/list');
    const list = (d && d.backups) || [];
    if(!list.length){
      box.innerHTML = '<div style="color:var(--text-sec);font-size:13px;padding:8px 0">暂无备份，点击「立即备份」创建</div>';
      return;
    }
    box.innerHTML = list.map(b=>`
      <div style="display:flex;align-items:center;gap:10px;padding:9px 10px;border:1px solid var(--border,#e5e5ea);border-radius:8px;margin-bottom:8px">
        <span style="font-size:16px">🗄</span>
        <div style="flex:1;min-width:0">
          <div style="font-size:13px;font-weight:500">${escHtml(b.name)}</div>
          <div style="font-size:11px;color:var(--text-sec)">${fmtSize(b.size)} · ${b.mtime}</div>
        </div>
        <button class="btn btn-sm danger" onclick="backupRestore('${escHtml(b.name)}')" style="flex-shrink:0">♻️ 恢复</button>
      </div>`).join('');
  }catch(e){
    box.innerHTML = '<div style="color:var(--red);font-size:13px">加载备份失败: '+escHtml(e.message)+'</div>';
  }
}

function fmtSize(n){
  n = Number(n)||0;
  if(n < 1024) return n + ' B';
  if(n < 1048576) return (n/1024).toFixed(1) + ' KB';
  return (n/1048576).toFixed(1) + ' MB';
}

async function backupCreate(){
  try{
    const d = await api('POST','/api/backup/create');
    if(d && d.ok){
      toast('✅ 备份成功','success');
      await loadBackupList();
    } else toast((d&&d.message)||'备份失败','error');
  }catch(e){ toast('备份失败: '+e.message,'error'); }
}

async function backupRestore(name){
  if(!confirm('确定从备份「' + name + '」恢复数据库吗？\n当前数据会先自动备份（archive-pre-restore-*）。\n⚠️ 恢复后需重启软件生效。')) return;
  try{
    const d = await api('POST','/api/backup/restore',{backupName:name});
    if(d && d.ok){
      toast('✅ ' + (d.message||'已恢复，请重启软件'),'success');
    } else toast((d&&d.message)||'恢复失败','error');
  }catch(e){ toast('恢复失败: '+e.message,'error'); }
}
