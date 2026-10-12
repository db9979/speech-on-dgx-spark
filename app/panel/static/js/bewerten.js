// 👍/👎 under an answer (faelle.py, plan einstellungs-assistent.md Punkt 12): only for a profile whose switch is on
// (the server sends a "rate" event with an id only then). 👎 opens five reasons, a short text (200 characters) and
// „Frage mitschicken“ (off: without it the case keeps no words of the question). A vote can be changed.
// Also: Ich → Gespräch „Vorschläge für dich“ (berater.py, Punkt 10): the profile's own settings, taken only here.
const RATE_WHY=[['werkzeug',t('falsches Werkzeug','wrong tool')],['antwort',t('falsche Antwort','wrong answer')],['langsam',t('zu langsam','too slow')],
  ['verstanden',t('nicht verstanden','not understood')],['aussprache',t('falsch ausgesprochen','mispronounced')]];
function rateBar(id){const d=document.createElement('div');d.className='ratebar';d.dataset.rid=id;
  d.innerHTML=`<button type="button" class="b rb" data-rate="up" aria-label="${esc(t('Gute Antwort','Good answer'))}" title="${esc(t('Gute Antwort','Good answer'))}">👍</button>`+
    `<button type="button" class="b rb" data-rate="down" aria-label="${esc(t('Schlechte Antwort','Bad answer'))}" title="${esc(t('Schlechte Antwort','Bad answer'))}">👎</button><span class="mut rmsg"></span>`;
  return d}
async function rateSend(bar,body){const m=bar.querySelector('.rmsg');
  try{await api('/api/chat/rate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.assign({id:bar.dataset.rid},body))});
    bar.querySelectorAll('[data-rate]').forEach(b=>b.classList.toggle('on',b.dataset.rate===(body.good?'up':'down')));
    m.textContent=body.good?t('Danke!','Thanks!'):t('Danke, notiert.','Thanks, noted.');const sh=bar.querySelector('.ratesheet');if(sh)sh.remove()}
  catch(e){m.textContent=e.message}}
function rateSheet(bar){if(bar.querySelector('.ratesheet'))return;const s=document.createElement('div');s.className='ratesheet';
  s.innerHTML=`<div class="rwhy">${RATE_WHY.map(([k,l])=>`<button type="button" class="ld-chip" data-why="${k}">${esc(l)}</button>`).join('')}</div>`+
    `<input class="rtext" maxlength="200" autocomplete="off" placeholder="${esc(t('Was war falsch? (kurz, freiwillig)','What was wrong? (short, optional)'))}" aria-label="${esc(t('Was war falsch?','What was wrong?'))}">`+
    `<label class="mut rq"><input type="checkbox" class="rwith"> ${esc(t('Frage mitschicken (hilft beim Vorschlag)','Send the question along (helps the proposal)'))}</label>`+
    `<div class="row"><button type="button" class="b p" data-rate="send">${esc(t('Melden','Report'))}</button><button type="button" class="b" data-rate="close">${esc(t('Abbrechen','Cancel'))}</button></div>`;
  bar.appendChild(s);s.querySelector('.rtext').focus()}
document.addEventListener('click',e=>{const b=e.target.closest('.ratebar button');if(!b)return;const bar=b.closest('.ratebar');
  if(b.dataset.why){bar.querySelectorAll('[data-why]').forEach(x=>x.classList.toggle('on',x===b&&!b.classList.contains('on')));return}
  const r=b.dataset.rate;if(r==='up')rateSend(bar,{good:true});else if(r==='down')rateSheet(bar);else if(r==='close'){const sh=bar.querySelector('.ratesheet');if(sh)sh.remove()}
  else if(r==='send'){const w=bar.querySelector('[data-why].on');rateSend(bar,{good:false,grund:w?w.dataset.why:'',text:bar.querySelector('.rtext').value.trim().slice(0,200),frage:bar.querySelector('.rwith').checked})}});
// Ich → Gespräch: proposals for the profile's own settings
async function meBerater(){const box=$('mebvbox');if(!box)return;
  let d;try{const r=await fetch('/api/me/berater',{cache:'no-store'});if(!r.ok){box.hidden=true;return}d=await r.json()}catch{box.hidden=true;return}
  box.hidden=!d.on||!(d.props||[]).length;if(box.hidden)return;
  $('mebvlist').innerHTML=d.props.map(p=>`<div class="zrow"><span><b>${esc(t(p.title[0],p.title[1]))}</b><div class="mut">${esc(t(p.why[0],p.why[1]))}</div></span>`+
    `<span style="margin-left:auto;display:flex;gap:6px"><button type="button" class="b p" data-mebv="take" data-id="${esc(p.id)}">${esc(t('Übernehmen','Take'))}</button><button type="button" class="b" data-mebv="skip" data-id="${esc(p.id)}">${esc(t('Nein danke','No thanks'))}</button></span></div>`).join('')}
if($('mebvlist'))$('mebvlist').addEventListener('click',async e=>{const b=e.target.closest('[data-mebv]');if(!b)return;
  try{await api(`/api/me/berater/${encodeURIComponent(b.dataset.id)}/${b.dataset.mebv}`,{method:'POST'});if(b.dataset.mebv==='take'&&typeof loadMe==='function')loadMe();meBerater()}
  catch(err){$('mebvmsg').textContent=err.message}});
window.rateBar=rateBar;window.meBerater=meBerater;
