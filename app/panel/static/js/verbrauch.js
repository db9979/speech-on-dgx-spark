// Verbrauchszähler (verbrauch.py): how much each model works. Zustand → Verbrauch (admin: per model, area, task and
// profile, quotas per day, week and month with an extra for today, empty), the card „Verbrauch heute“ under Monitoring and Ich → Verbrauch (each profile its own
// numbers, its quota, delete). The server sends numbers and fixed names only; profile names go in with esc().
let VB_ON=false,VBZ='30t',VBZME='30t',VBAREA=null;
const VBCOL={gespraech:1,weiche:2,hintergrund:3,assistent:4,pruefen:5,agent:6,begleiter:7,dokumente:8,sonstige:9,alle:1};
// 1 234 · 12,3 Tsd · 1,84 Mio
function vbN(n){n=Number(n)||0;const loc=L==='en'?'en-GB':'de-DE';
  if(n>=1e6)return (n/1e6).toLocaleString(loc,{maximumFractionDigits:2})+t(' Mio',' M');
  if(n>=1e4)return (n/1e3).toLocaleString(loc,{maximumFractionDigits:1})+t(' Tsd',' k');
  return Math.round(n).toLocaleString(loc)}
function vbSec(s){s=Number(s)||0;const loc=L==='en'?'en-GB':'de-DE';
  if(s>=3600)return (s/3600).toLocaleString(loc,{maximumFractionDigits:1})+' h';
  if(s>=60)return Math.round(s/60)+' min';return Math.round(s)+' s'}
function vbAmount(m){return m.unit==='sek'?vbSec(m.amount):m.unit==='tok'?vbN(m.read+m.written)+' '+t('Tokens','tokens'):vbN(m.amount)+' '+t(...m.unit_name)}
const vbPct=(a,b)=>b?Math.round(100*a/b):0;
const vbW=a=>Array.isArray(a)?t(a[0],a[1]):'';
function vbLabel(p,z){if(z==='12m'){const [y,m]=p.split('-');return new Date(+y,+m-1,1).toLocaleDateString(L==='en'?'en-GB':'de-DE',{month:'short'})}
  if(z==='24h')return p.slice(11)+t(' Uhr','h');const [,m,d]=p.split('-');return `${+d}.${+m}.`}
function vbTiles(td){const l=td.llm||{},a=td.asr||{},s=td.tts||{},e=td.embed||{},r=td.rerank||{},b=td.bild||{},q=td.systemone||{};
  const tile=(k,v,sub)=>`<div class="card vb-tile"><div class="k">${esc(k)}</div><div class="v">${esc(v)}</div><div class="mut">${esc(sub)}</div></div>`;
  const more=[e.amount?vbN(e.amount)+t(' Texte Bedeutungssuche',' texts meaning search'):'',r.amount?vbN(r.amount)+t(' nachsortiert',' re-ranked'):'',
    q.amount?vbN(q.amount)+t(' Einordnungen',' classifications'):'',b.amount?vbN(b.amount)+t(' Bilder',' pictures'):''].filter(Boolean);
  return `<div class="vb-tiles">`+tile(t('Sprachmodell heute','Language model today'),vbN((l.read||0)+(l.written||0)),t(`Tokens · ${vbN(l.read)} gelesen, ${vbN(l.written)} geschrieben`,`tokens · ${vbN(l.read)} read, ${vbN(l.written)} written`))+
    tile(t('Aus dem Zwischenspeicher','From the cache'),vbPct(l.cached||0,l.read||0)+' %',t('des Gelesenen, musste nicht neu gerechnet werden','of what was read, not computed again'))+
    tile(t('Sprache heute','Speech today'),vbSec((a.amount||0)+(s.amount||0)),t(`${vbSec(a.amount)} gehört · ${vbSec(s.amount)} gesprochen`,`${vbSec(a.amount)} heard · ${vbSec(s.amount)} spoken`))+
    tile(t('Weitere Modelle heute','Other models today'),vbN((e.amount||0)+(r.amount||0)+(q.amount||0)+(b.amount||0)),more.join(' · ')||t('noch nichts','nothing yet'))+`</div>`}
function vbBars(d,z){const bars=d.bars||[],max=Math.max(1,...bars.map(b=>Object.values(b.by).reduce((x,y)=>x+y,0)));
  const ids=[...new Set(bars.flatMap(b=>Object.keys(b.by)))];
  const cols=bars.map(b=>`<div class="vb-bar" title="${esc(vbLabel(b.p,z)+': '+vbN(Object.values(b.by).reduce((x,y)=>x+y,0)))}">`+
    ids.filter(k=>b.by[k]).map(k=>`<i class="vb-c${VBCOL[k]||9}" style="height:${(100*b.by[k]/max).toFixed(1)}%"></i>`).join('')+`</div>`).join('');
  const step=Math.ceil(bars.length/8);
  const xl=bars.map((b,i)=>`<span>${i%step===0?esc(vbLabel(b.p,z)):''}</span>`).join('');
  const leg=ids.map(k=>`<span><b class="vb-c${VBCOL[k]||9}"></b>${esc(k==='alle'?t('alle Bereiche','all areas'):vbW((d.bereiche||{})[k]))}</span>`).join('');
  return `<div class="vb-bars">${cols}</div><div class="vb-xl">${xl}</div><div class="vb-leg">${leg||esc(t('Noch nichts gezählt.','Nothing counted yet.'))}</div>`}
function vbSeg(id,z,hour){return `<div class="lseg" id="${id}">`+[['24h','24 h'],['30t',t('30 Tage','30 days')],['12m',t('12 Monate','12 months')]].filter(x=>hour||x[0]!=='24h')
  .map(([k,l])=>`<button type="button" data-vbz="${k}"${k===z?' class="on"':''}>${esc(l)}</button>`).join('')+`</div>`}
const VBSPAN={'24h':['24 Stunden','24 hours'],'30t':['30 Tage','30 days'],'12m':['12 Monate','12 months']};
function vbModels(d){if(!(d.models||[]).length)return '';
  return `<div class="card"><h3>${esc(t('Nach Modell','By model'))} · ${esc(t(...VBSPAN[d.zeit]))}</h3><div class="vb-tw"><table class="vb-tab"><thead><tr><th>${esc(t('Modell','Model'))}</th><th class="n">${esc(t('Menge','Amount'))}</th><th class="n">${esc(t('Aufrufe','Calls'))}</th><th class="n">${esc(t('Ø Zeit','Avg. time'))}</th></tr></thead><tbody>`+
    d.models.map(m=>`<tr><td>${esc(vbW(m.name))}${m.estimated?` <span class="pill" title="${esc(t('ohne Meldung des Servers aus der Textlänge geschätzt','estimated from the text length without the server\'s report'))}">${esc(t(m.estimated+' geschätzt',m.estimated+' estimated'))}</span>`:''}</td><td class="n">${esc(vbAmount(m))}</td><td class="n">${esc(vbN(m.calls))}</td><td class="n">${m.ms?esc((m.ms/1000).toLocaleString(L==='en'?'en-GB':'de-DE',{maximumFractionDigits:2})+' s'):'–'}</td></tr>`).join('')+`</tbody></table></div></div>`}
function vbAreas(d){const a=d.areas||[];if(!a.length)return '';const tot=a.reduce((x,y)=>x+y.read+y.written,0);
  return `<div class="card"><h3>${esc(t('Sprachmodell nach Bereich','Language model by area'))} · ${esc(t(...VBSPAN[d.zeit]))}</h3><div class="vb-tw"><table class="vb-tab"><thead><tr><th>${esc(t('Bereich','Area'))}</th><th class="n">${esc(t('gelesen','read'))}</th><th class="n">${esc(t('geschrieben','written'))}</th><th>${esc(t('Anteil','Share'))}</th></tr></thead><tbody>`+
    a.map(x=>{const open=VBAREA===x.id,tasks=open?(d.tasks||[]).filter(k=>k.area===x.id):[];
      return `<tr class="vb-area" data-vbarea="${esc(x.id)}" tabindex="0"><td>${open?'▾':'▸'} ${esc(vbW(x.name))}</td><td class="n">${esc(vbN(x.read))}</td><td class="n">${esc(vbN(x.written))}</td><td><div class="vb-hb"><i style="width:${vbPct(x.read+x.written,tot)}%"></i></div></td></tr>`+
        tasks.map(k=>`<tr class="vb-task"><td>${esc(k.name)}${k.estimated?' <span class="mut">'+esc(t('(geschätzt)','(estimated)'))+'</span>':''}</td><td class="n">${esc(vbN(k.read))}</td><td class="n">${esc(vbN(k.written))}</td><td class="mut">${esc(t(vbN(k.calls)+' Aufrufe',vbN(k.calls)+' calls'))}</td></tr>`).join('')}).join('')+
    `</tbody></table></div><div class="mut vb-note">${esc(t('Ein Klick auf einen Bereich zeigt seine Aufgaben.','A click on an area shows its tasks.'))}</div></div>`}
const VBKIND={gast:['Gäste','Guests'],spark:['Spark selbst','The Spark itself'],geloescht:['Gelöschte Profile','Deleted profiles']};
function vbPeople(d){const p=d.profiles||[];if(!p.length)return '';
  return `<div class="card"><h3>${esc(t('Nach Profil','By profile'))} · ${esc(t(...VBSPAN[d.zeit]))}</h3><div class="vb-tw"><table class="vb-tab"><thead><tr><th>${esc(t('Profil','Profile'))}</th><th class="n">Tokens</th><th class="n">${esc(t('Sprache','Speech'))}</th><th class="n">${esc(t('Bilder','Pictures'))}</th></tr></thead><tbody>`+
    p.map(r=>`<tr><td>${esc(r.kind==='profil'?r.name:t(...VBKIND[r.kind]))}</td><td class="n">${esc(vbN(r.tokens))}</td><td class="n">${esc(vbSec(r.heard+r.spoken))}</td><td class="n">${r.pictures?esc(vbN(r.pictures)):'–'}</td></tr>`).join('')+
    `</tbody></table></div><div class="mut vb-note">${esc(t('Nur Zahlen, nie Fragen oder Antworten. „Spark selbst“: Arbeit ohne Profil (Prüfungen, Messungen, Lernen).','Numbers only, never questions or answers. "The Spark itself": work without a profile (checks, measuring, learning).'))}</div></div>`}
// Kontingent: per period how much is used of the limit; the fullest one decides the bar (full, warned, fine)
const VBZT=['tag','woche','monat'],VBNEU={tag:['neu um 0 Uhr','new at midnight'],woche:['neu am Montag','new on Monday'],monat:['neu am 1.','new on the 1st']};
const VBVOLL={tag:['Tag voll · morgen','Day full · tomorrow'],woche:['Woche voll · ab Montag','Week full · from Monday'],monat:['Monat voll · ab dem 1.','Month full · from the 1st']};
function vbFull(r){const l=r.limits||{},u=r.used||{};let top=null;
  for(const z of VBZT){if(!l[z])continue;const f=(u[z]||0)/l[z];if(!top||f>top.f)top={z,f,u:u[z]||0,l:l[z]}}return top}
function vbBarCls(f,warn){return f>=1?'full':warn&&f*100>=warn?'warn':''}
function vbQuota(d){const q=d.quota||{},p=(d.profiles||[]).filter(r=>r.kind==='profil');if(!q.on||!p.length)return '';
  const head=VBZT.map(z=>`<th class="n">${esc(t(...(q.zeiten||{})[z]||[z,z]))}</th>`).join('');
  return `<div class="card"><h3>${esc(t('Kontingent','Quota'))}</h3><div class="vb-tw"><table class="vb-tab vb-quota"><thead><tr><th>${esc(t('Profil','Profile'))}</th>${head}<th>${esc(t('Stand','Status'))}</th><th></th></tr></thead><tbody>`+
    p.map(r=>{const own=(q.own||{})[r.id]||{},top=vbFull(r);
      const cells=VBZT.map(z=>`<td class="n"><input class="num vb-qin" type="number" min="0" data-vbq="${esc(r.id)}" data-vbqz="${z}" value="${own[z]??''}" placeholder="${esc(String((q.k||{})[z]??''))}" aria-label="${esc(t('Tausend Tokens je ','Thousand tokens per ')+t(...(q.zeiten||{})[z]||[z,z]))}"></td>`).join('');
      const st=!top?`<span class="mut">${esc(t('keine Grenze','no limit'))}</span>`:
        `<div class="vb-hb vb-qbar"><i class="${vbBarCls(top.f,q.warn)}" style="width:${Math.min(100,Math.round(100*top.f))}%"></i></div><span class="mut">${esc(top.f>=1?t(...VBVOLL[top.z]):vbN(top.u)+' / '+vbN(top.l)+' · '+t(...(q.zeiten||{})[top.z]||[top.z,top.z]))}</span>`;
      return `<tr><td>${esc(r.name)}</td>${cells}<td class="vb-qc">${st}${r.extra?` <span class="pill">${esc(t('+'+vbN(r.extra)+' heute','+'+vbN(r.extra)+' today'))}</span>`:''}</td><td class="vb-qc"><button class="b" type="button" data-vbqset="${esc(r.id)}">${esc(t('Setzen','Set'))}</button> <button class="b" type="button" data-vbextra="${esc(r.id)}">${esc(t('+500 heute','+500 today'))}</button></td></tr>`}).join('')+
    `</tbody></table></div><div class="mut vb-note">${esc(t(`Tausend Tokens; leer gilt die Vorgabe, 0 heißt keine Grenze. „+500 heute“ gibt 500 Tausend Tokens mehr bis Mitternacht, für jede Grenze. Admin-Profile haben keine Grenze.`,`Thousand tokens; empty uses the default, 0 means no limit. "+500 today" gives 500 thousand tokens more until midnight, for every limit. Admin profiles have no limit.`))}</div></div>`}
// ---------------------------------------------------------------- Zustand → Verbrauch (admin)
async function loadUsage(){const main=$('usgmain'),off=$('usgoff'),msg=$('usgmsg');if(!main)return;msg.textContent='';
  let d;try{d=await (await api('/api/admin/verbrauch?zeit='+encodeURIComponent(VBZ))).json()}catch(e){msg.textContent=e.message;return}
  off.hidden=!!d.on;main.hidden=!d.on;$('usgseg').hidden=!d.on;$('usgclear').hidden=!d.on;if(!d.on){main.innerHTML='';return}
  main.innerHTML=vbTiles(d.today||{})+`<div class="vb-two"><div class="card"><h3>${esc(VBZ==='24h'?t('Tokens pro Stunde','Tokens per hour'):VBZ==='12m'?t('Tokens pro Monat, nach Bereich','Tokens per month, by area'):t('Tokens pro Tag, nach Bereich','Tokens per day, by area'))}</h3>${vbBars(d,VBZ)}<div class="mut vb-note">${esc(t(`Jetzt ${vbN(d.rate)} Tokens in der letzten Minute.`,`Now ${vbN(d.rate)} tokens in the last minute.`))}</div></div>${vbModels(d)}</div>`+
    `<div class="vb-two">${VBZ==='24h'?'':vbAreas(d)}${VBZ==='24h'?'':vbPeople(d)}</div>`+vbQuota(d);
  main.querySelectorAll('[data-vbarea]').forEach(r=>{const go=()=>{VBAREA=VBAREA===r.dataset.vbarea?null:r.dataset.vbarea;loadUsage()};r.onclick=go;r.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();go()}}});
  main.querySelectorAll('[data-vbqset]').forEach(b=>b.onclick=async()=>{const uid=b.dataset.vbqset;b.disabled=true;
    try{for(const inp of main.querySelectorAll(`[data-vbq="${CSS.escape(uid)}"]`)){if(inp.value===inp.defaultValue)continue;const v=inp.value.trim();
        await api('/api/admin/verbrauch/kontingent',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({uid,zeit:inp.dataset.vbqz,k:v===''?null:Number(v)})})}
      await loadUsage()}catch(e){msg.textContent=e.message;b.disabled=false}});
  main.querySelectorAll('[data-vbextra]').forEach(b=>b.onclick=async()=>{b.disabled=true;
    try{await api('/api/admin/verbrauch/nachschlag',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({uid:b.dataset.vbextra,k:500})});await loadUsage()}catch(e){msg.textContent=e.message;b.disabled=false}})}
function usageInit(){const seg=$('usgseg');if(!seg)return;seg.outerHTML=vbSeg('usgseg',VBZ,true);
  $('usgseg').onclick=e=>{const b=e.target.closest('[data-vbz]');if(!b)return;VBZ=b.dataset.vbz;$('usgseg').querySelectorAll('button').forEach(x=>x.classList.toggle('on',x===b));lzb($('usgbox'),loadUsage)};
  $('usgclear').onclick=async()=>{if(!confirm(t('Alle Zähler leeren? Die Zahlen aller Tage und Monate sind dann weg.','Empty all counters? The numbers of every day and month are gone then.')))return;
    try{await api('/api/admin/verbrauch/leeren',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});await loadUsage()}catch(e){$('usgmsg').textContent=e.message}}}
usageInit();
// ---------------------------------------------------------------- Zustand → Monitoring, card „Verbrauch heute“
async function zUsage(){const box=$('zverbrauch');if(!box||document.hidden)return;
  const {r,d}=await apiTry('/api/admin/verbrauch/heute');if(!r.ok)return;box.hidden=!d.on;if(!d.on)return;
  const row=(k,v)=>`<div class="zrow"><span>${esc(k)}</span><b class="vb-r">${esc(v)}</b></div>`;
  $('zverbrauchlist').innerHTML=row(t('Sprachmodell','Language model'),vbN(d.tokens)+' '+t('Tokens','tokens'))+row(t('davon Zwischenspeicher','of it from the cache'),vbPct(d.cached,d.read)+' %')+
    row(t('Sprache gehört / gesprochen','Speech heard / spoken'),vbSec(d.heard)+' / '+vbSec(d.spoken))+(d.pictures?row(t('Bilder','Pictures'),vbN(d.pictures)):'')+
    (d.top?row(t('Größter Bereich','Largest area'),vbW(d.top.name)+' '+d.top.pct+' %'):'')}
// ---------------------------------------------------------------- Ich → Verbrauch (own numbers)
async function showUse(){const box=$('usebox');if(!box)return;if(!PROFILE||!VB_ON){box.innerHTML='';return}
  let d;try{d=await (await api('/api/profile/verbrauch?zeit='+encodeURIComponent(VBZME))).json()}catch(e){box.innerHTML=`<div class="fh">${esc(e.message)}</div>`;return}
  const q=d.quota||{},l=(d.today||{}).llm||{},a=(d.today||{}).asr||{},s=(d.today||{}).tts||{};
  const lim=q.limits||{},use=q.used||{},ZN={tag:['Heute','Today'],woche:['Diese Woche','This week'],monat:['Dieser Monat','This month']};
  const qbar=q.on?`<div class="card"><h3>${esc(t('Kontingent','Quota'))}</h3>`+VBZT.map(z=>lim[z]?
      `<div class="vb-qrow"><b>${esc(t(...ZN[z]))}</b><div class="vb-hb vb-qbar"><i class="${vbBarCls((use[z]||0)/lim[z],q.warn)}" style="width:${Math.min(100,vbPct(use[z]||0,lim[z]))}%"></i></div><div class="mut vb-qline"><span>${esc(t(`${vbN(use[z])} von ${vbN(lim[z])} Tokens`,`${vbN(use[z])} of ${vbN(lim[z])} tokens`))}</span><span>${esc(t(...VBNEU[z]))}</span></div></div>`:
      `<div class="vb-qrow"><b>${esc(t(...ZN[z]))}</b><div class="mut vb-qline"><span>${esc(t('keine Grenze','no limit'))}</span><span>${esc(t(`${vbN(use[z])} verbraucht`,`${vbN(use[z])} used`))}</span></div></div>`).join('')+
    `<div class="mut vb-note">${esc(t('Ist eine Grenze aufgebraucht, antwortet der Assistent mit einem festen Satz, bis sie neu beginnt. Feste Befehle wie Licht und Uhrzeit gehen weiter.','When a limit is used up, the assistant answers with a fixed sentence until it starts again. Fixed commands such as lights and the time still work.'))}</div></div>`:'';
  box.innerHTML=`<div class="intro">${esc(t('Wie viel der Spark für dich gerechnet hat: Tokens beim Sprachmodell, Sekunden beim Hören und Sprechen. Nur Zahlen, nie Fragen oder Antworten.','How much the Spark computed for you: tokens at the language model, seconds of listening and speaking. Numbers only, never questions or answers.'))}</div>`+
    `<div class="vb-tiles vb-me"><div class="card vb-tile"><div class="k">${esc(t('Tokens heute','Tokens today'))}</div><div class="v">${esc(vbN((l.read||0)+(l.written||0)))}</div></div><div class="card vb-tile"><div class="k">${esc(t('Sprache heute','Speech today'))}</div><div class="v">${esc(vbSec((a.amount||0)+(s.amount||0)))}</div></div></div>`+qbar+
    `<div class="card"><div class="vb-h">${vbSeg('usemeseg',VBZME,false)}<h3>${esc(VBZME==='12m'?t('Tokens pro Monat','Tokens per month'):t('Tokens pro Tag','Tokens per day'))}</h3></div>${vbBars(d,VBZME)}</div>`+vbModels(d)+vbAreas(d)+
    `<div class="row vb-del"><button class="b" type="button" id="usemedel">${esc(t('Meine Zahlen löschen','Delete my numbers'))}</button><span class="mut" id="usememsg"></span></div>`;
  $('usemeseg').onclick=e=>{const b=e.target.closest('[data-vbz]');if(!b)return;VBZME=b.dataset.vbz;showUse()};
  box.querySelectorAll('[data-vbarea]').forEach(r=>{const go=()=>{VBAREA=VBAREA===r.dataset.vbarea?null:r.dataset.vbarea;showUse()};r.onclick=go;r.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();go()}}});
  $('usemedel').onclick=async()=>{if(!confirm(t('Deine Zahlen aller Tage und Monate löschen? Für das Kontingent zählt weiter, was schon verbraucht ist.','Delete your numbers of every day and month? What is used already still counts for the quota.')))return;
    try{await api('/api/profile/verbrauch',{method:'DELETE'});showUse()}catch(e){$('usememsg').textContent=e.message}};
  if(typeof labelTables==='function')labelTables()}   // Ich lies outside main: its tables get their column names here (phone.js)
