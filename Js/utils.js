/* ═══ UTILS ═══ */

function ini(n){if(!n)return'?';const p=n.trim().split(/\s+/);return(p[0][0]+(p[1]?p[1][0]:p[0][1]||'')).toUpperCase();}

function hsh(s){let h=0;for(let i=0;i<(s||'').length;i++)h=Math.imul(31,h)+s.charCodeAt(i)|0;return Math.abs(h);}

function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}

function toast(msg){const el=document.getElementById('toast');el.textContent=msg;el.classList.add('show');setTimeout(()=>el.classList.remove('show'),2800);}

init();

function showModal(html){
  closeModal();
  const bg=document.createElement('div');bg.className='mo';
  bg.innerHTML=`<div class="mc">
    <button onclick="closeModal()" style="position:absolute;top:14px;right:16px;background:none;border:none;cursor:pointer;font-size:20px;color:var(--text2);line-height:1;padding:4px 6px;border-radius:4px;z-index:10" title="Chiudi">✕</button>
    <div style="position:relative">${html}</div>
  </div>`;
  bg.addEventListener('click',e=>{if(e.target===bg)closeModal();});
  document.getElementById('modals').appendChild(bg);
}

function closeModal(){document.querySelector('.mo')?.remove();}

function showPage(id,btn){
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.nb').forEach(b=>b.classList.remove('active'));
  document.getElementById('page-'+id).classList.add('active');
  if(btn)btn.classList.add('active');
  // Reset selezione quando si cambia tab
  if(id!=='contacts'&&sel.size>0){sel.clear();}
}

/* ── UTILS ── */

function gv(id){return(document.getElementById(id)?.value||'').trim();}

/* ── REFRESH ── */

function dr(l,v2){return `<div class="df"><span class="dl">${l}</span><span class="dv">${v2}</span></div>`;}