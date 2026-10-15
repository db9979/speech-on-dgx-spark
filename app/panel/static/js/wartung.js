// Zustand → Wartungspause (wartung.py, admin): before an update of the language model, the speech recognition or the
// speech output the admin pauses those parts; while it holds, a band with the time left, "Weiter" and "+15 min".
// Only names of parts, times and numbers (through esc), never what was asked.
const WP={pick:['llm'],min:30,d:null};
const wpHM=s=>s?new Date(s*1000).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}):'';
const wpPart=(d,k)=>{const x=((d.choices||{}).parts||[]).find(p=>p[0]===k);return x?t(x[1],x[2]):k};
function wpRender(){const d=WP.d,box=$('zwart');if(!box||!d)return;box.hidden=!d.on;if(!d.on)return;
  const list=$('zwartlist');
  if(d.paused){
    const names=(d.parts||[]).map(k=>wpPart(d,k)).join(', ');
    const meta=[t('seit ','since ')+wpHM(d.since),d.by?t('von ','by ')+d.by:'',d.fern?t('auch auf dem Modell-Rechner','also on the model computer'):'',d.overdue?t('Zeit um, wartet auf Antwort','time is up, waiting for an answer'):t('endet spätestens ','ends at the latest ')+wpHM(d.until)].filter(Boolean).join(' · ');
    list.innerHTML=`<div class="zrow"><span class="pill ${d.overdue?'warn':'ok'}">${esc(t('Pause','Paused'))}</span><span><b>${esc(names)}</b><div class="mut">${esc(meta)}</div></span></div>`+
      `<div class="zrow"><span class="pill">${d.asked}</span><span>${esc(t('Anfragen mit dem Wartungssatz beantwortet','Requests answered with the maintenance sentence'))}</span></div>`+
      `<div class="zrow"><span class="pill">${d.held}</span><span>${esc(t('Hintergrundarbeit wartet und läuft danach','Background work waits and runs afterwards'))}</span></div>`;
    $('zwartgo').hidden=true;$('zwartmore').hidden=false;$('zwarton').hidden=false;return}
  const ch=d.choices||{};
  list.innerHTML=`<div class="mut">${esc(t('Was wird aktualisiert?','What is being updated?'))}</div>`+
    (ch.parts||[]).map(p=>`<div class="zrow"><label><input type="checkbox" data-wpart="${esc(p[0])}"${WP.pick.includes(p[0])?' checked':''}> ${esc(t(p[1],p[2]))}</label></div>`).join('')+
    `<div class="zrow"><span class="mut">${esc(t('Höchstens','At most'))}</span><span class="segc">${(ch.minutes||[]).map(m=>`<button type="button" data-wmin="${m}" class="${m===WP.min?'on':''}">${m} min</button>`).join('')}</span></div>`;
  $('zwartgo').hidden=false;$('zwartmore').hidden=true;$('zwarton').hidden=true}
async function zWartung(){if(!$('zwart')||document.hidden)return;
  try{const r=await api('/api/admin/wartung');WP.d=await r.json();wpRender()}catch{}}
async function wpPost(url,body){const m=$('zwartmsg');m.textContent='';
  try{WP.d=await (await api(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})})).json();wpRender()}catch(e){m.textContent=e.message}}
if($('zwartlist')){
  $('zwartlist').addEventListener('change',e=>{const c=e.target.closest('[data-wpart]');if(!c)return;
    WP.pick=[...$('zwartlist').querySelectorAll('[data-wpart]')].filter(x=>x.checked).map(x=>x.dataset.wpart)});
  $('zwartlist').addEventListener('click',e=>{const b=e.target.closest('[data-wmin]');if(!b)return;WP.min=+b.dataset.wmin;wpRender()});
  $('zwartgo').addEventListener('click',()=>{if(!WP.pick.length){$('zwartmsg').textContent=t('Bitte mindestens einen Teil wählen.','Please pick at least one part.');return}
    wpPost('/api/admin/wartung',{parts:WP.pick,minutes:WP.min})});
  $('zwartmore').addEventListener('click',()=>wpPost('/api/admin/wartung',{more:true}));
  $('zwarton').addEventListener('click',()=>wpPost('/api/admin/wartung/weiter'))}
