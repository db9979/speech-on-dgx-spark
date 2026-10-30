// Zustand → Prüfen → Wissen messen (wissensmessung.py, Wissenskarte Stufe 4): start one run (erfundene Dokumente or
// one profile, read only) and show the newest run's numbers with the limits. Numbers only; profile names come from
// the admin list like Personen und Geräte and go in through textContent.
const WM={timer:0,d:null};
// the measured times: key prefix in the result -> [part, de, en]
const WM_ZEIT=[['documents','suche','Dokumentensuche','Document search'],['documents','suche_karte','Suche mit Karte','Search with the map'],
  ['wissensbuch','liste','Wissensbuch: Seiten zur Frage','Knowledge book: pages for a question'],['wissenskarte','view','Karte: Ausschnitt','Map: visible part'],
  ['wissenskarte','view_um','Karte um einen Punkt','Map around a point'],['wissenskarte','rund_um','Rund um einen Punkt (2 Schritte)','Around a point (2 steps)'],
  ['wissenskarte','weg','Weg zwischen zwei Punkten','Way between two points'],['wissenskarte','liste','Karte: Stellen zur Frage','Map: passages for a question']];
const WM_GRENZE={seiten:['Wissensbuch-Seiten','Knowledge book pages'],kanten:['Verbindungen','Connections'],punkte:['Personen, Firmen und Fristen','People, companies and deadlines']};
const WM_STATUS={fertig:['fertig','done'],sprache:['abgebrochen: jemand hat gesprochen','stopped: somebody spoke'],zeit:['abgebrochen: Zeit um','stopped: time is up'],
  fehler:['Fehler','error'],leer:['keine Dokumente','no documents'],alt:['Datenbank einer anderen Version','database of another version']};
const wmN=(v,u='')=>v==null?'–':(typeof v==='number'?v.toLocaleString(L==='en'?'en':'de'):String(v))+u;
function wmRun(r){if(!r)return'';const T=r.teile||{},d=T.documents||{},k=T.wissenskarte||{},b=T.wissensbuch||{};
  const head=`${zAgo(r.zeit)} · ${r.art==='synth'?t(`${wmN(r.anzahl)} erfundene Dokumente`,`${wmN(r.anzahl)} made-up documents`):t('ein Profil, nur lesend','one profile, read only')} · ${t(...(WM_STATUS[r.status]||['?','?']))} · ${wmN(r.dauer_s,' s')}`;
  if(r.status!=='fertig')return `<div class="mut">${esc(head)}</div>`;
  const rows=WM_ZEIT.filter(([p,x])=>(T[p]||{})[x+'_n']).map(([p,x,de,en])=>`<tr><td>${esc(t(de,en))}</td><td>${esc(wmN(T[p][x+'_p50_ms'],' ms'))}</td><td>${esc(wmN(T[p][x+'_p95_ms'],' ms'))}</td></tr>`).join('');
  const zahl=[[t('Dokumente','Documents'),d.dokumente],[t('Stücke','Pieces'),d.stuecke],[t('Vektor-Matrix (float16)','Vector matrix (float16)'),wmN(d.matrix_mb,' MB')],
    [t('Speicher vorher → nachher','Memory before → after'),`${wmN(r.ram_start_mb,' MB')} → ${wmN(r.ram_ende_mb,' MB')}`],[t('Seiten · Punkte · Verbindungen','Pages · points · connections'),`${wmN(b.seiten)} · ${wmN(k.punkte)} · ${wmN(k.kanten)}`],
    [t('Verbindungen je Dokument','Connections per document'),`${wmN(k.kanten_je_dok)} (${t('höchstens','at most')} ${wmN(k.kanten_je_dok_max)})`]];
  const lim=Object.entries(r.engpaesse||{}).map(([g,v])=>`<tr><td>${esc(t(...(WM_GRENZE[g]||[g,g])))}</td><td>${esc(wmN(v.jetzt))}</td><td>${esc(wmN(v.bedarf))}</td><td>${esc(wmN(v.grenze))}</td><td>${v.voll?`<b>${esc(t('voll','full'))}</b>`:esc(t('reicht','enough'))}</td></tr>`).join('');
  return `<div class="mut">${esc(head)}</div>
    <table style="margin-top:8px"><tbody>${zahl.map(([a,v])=>`<tr><td>${esc(a)}</td><td>${esc(typeof v==='number'?wmN(v):v)}</td></tr>`).join('')}</tbody></table>
    <table style="margin-top:8px"><thead><tr><th></th><th>${esc(t('Median','median'))}</th><th>p95</th></tr></thead><tbody>${rows}</tbody></table>
    ${lim?`<table style="margin-top:8px"><thead><tr><th>${esc(t('Grenze','Limit'))}</th><th>${esc(t('jetzt','now'))}</th><th>${esc(t('Bedarf','needed'))}</th><th>${esc(t('höchstens','at most'))}</th><th></th></tr></thead><tbody>${lim}</tbody></table>
    <div class="fh">${esc(t('Bedarf: bei erfundenen Dokumenten, was sie ohne Grenze gebracht hätten; bei einem Profil, was es je Dokument bringt, hochgerechnet auf 5000 Dokumente.','Needed: with made-up documents what they would have brought without the limit; with a profile what it brings per document, projected to 5000 documents.'))}</div>`:''}`}
function wmDraw(d){WM.d=d;const sel=$('wmart');if(!sel)return;
  const want=['synth',...d.profile.map(p=>'p:'+p.id)].join(',');
  if(sel.dataset.have!==want){const keep=sel.value;sel.length=1;for(const p of d.profile){const o=document.createElement('option');o.value='p:'+p.id;o.textContent=t('Profil ','Profile ')+p.name;sel.appendChild(o)}
    sel.dataset.have=want;if([...sel.options].some(o=>o.value===keep))sel.value=keep}
  $('wmanz').hidden=sel.value!=='synth';$('wmanz').min=d.min;$('wmanz').max=d.max;
  const b=$('wmgo');b.disabled=!!(d.laeuft||d.warten);
  b.textContent=d.laeuft?t('Misst gerade …','Measuring …'):d.warten?t(`Wieder in ${Math.ceil(d.warten/60)} min`,`Again in ${Math.ceil(d.warten/60)} min`):t('Messen','Measure');
  const r=d.laeufe||[];
  $('wmout').innerHTML=(d.laeuft?`<div class="mut">${esc(d.art==='synth'?t(`Misst ${wmN(d.anzahl)} erfundene Dokumente …`,`Measuring ${wmN(d.anzahl)} made-up documents …`):t('Misst ein Profil …','Measuring a profile …'))}</div>`:'')+
    (r.length?wmRun(r[0])+(r.length>1?`<details class="qhow"><summary>${esc(t('Frühere Messungen','Earlier measurements'))}</summary>${r.slice(1).map(wmRun).join('')}</details>`:''):(d.laeuft?'':`<div class="mut">${esc(t('Noch keine Messung.','No measurement yet.'))}</div>`));
  clearTimeout(WM.timer);if(d.laeuft&&document.querySelector('section#test.on'))WM.timer=setTimeout(wmAdmin,3000)}
async function wmAdmin(){const r=await apiTry('/api/admin/wissensmessung');if(r.r.ok)wmDraw(r.d)}
if($('wmart'))$('wmart').onchange=()=>{$('wmanz').hidden=$('wmart').value!=='synth'};
if($('wmgo'))$('wmgo').onclick=async()=>{const b=$('wmgo'),v=$('wmart').value;b.disabled=true;$('wmmsg').textContent=t('Startet in einer ruhigen Minute …','Starts in a quiet minute …');
  const body=v==='synth'?{art:'synth',anzahl:+$('wmanz').value}:{art:'profil',profil:v.slice(2)};
  const r=await apiTry('/api/admin/wissensmessung',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  $('wmmsg').textContent=r.r.ok?'':String(r.d.detail||'');if(r.r.ok)wmDraw(r.d);else b.disabled=false};
