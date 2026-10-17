// Werkstatt (werkstattseite.py, plan opencode-werkstatt): Funktionen → Werkstatt. Testlauf, Code-Messung, Diagnose and
// Reparatur run in the sandbox on the model computer; the panel's fixed rules decide, the code is asked for the three
// with a model. Results come as data: every word through textContent, the patch only as text in a <pre>.
const WK={timer:0,d:null};
const WK_GRUND={ok:['fertig','done'],llm:['Sprachmodell antwortet nicht','language model does not answer'],opencode:['OpenCode fehlt','OpenCode missing'],
  zeit:['Zeit abgelaufen','time is up'],quelle:['Code-Kopie fehlt','code copy missing'],tests:['Tests liefen nicht','tests did not run'],
  abbruch:['abgebrochen','stopped'],fehler:['Fehler','error'],leer:['nichts geändert','nothing changed']};
function wkEl(tag,cls,txt){const e=document.createElement(tag);if(cls)e.className=cls;if(txt!==undefined)e.textContent=txt;return e}
function wkArt(d,a){const x=d.arten&&d.arten[a];return x?(L==='en'?x.en:x.de):a}
function wkZeit(s){return s?new Date(s*1000).toLocaleString():''}
function wkDauer(s){return s>=3600?Math.floor(s/3600)+' h '+Math.round(s%3600/60)+' min':s>=60?Math.round(s/60)+' min':(s||0)+' s'}
function wkShow(d){WK.d=d;const st=$('wkstand');if(!st)return;
  st.textContent=[d.laeuft?(d.art?wkArt(d,d.art)+t(' läuft',' running'):t('Ein Auftrag läuft','An order is running')):t('Bereit','Ready'),
    d.installiert?'OpenCode '+d.version:t('OpenCode fehlt: auf dem Modell-Rechner einmal sudo ./install.sh --werkstatt','OpenCode missing: on the model computer once sudo ./install.sh --werkstatt'),
    d.modell?t('Sprachmodell ','Language model ')+d.modell:t('kein eigenes Sprachmodell (Code-Messung, Diagnose und Reparatur brauchen es)','no own language model (code measurement, diagnosis and repair need it)'),
    ...(d.stand||[]).slice(-3).map(z=>z.replace(/^werkstatt: /,''))].join(' · ');
  const ohne=!d.an||d.laeuft,mitLlm=ohne||!d.installiert||!d.modell;
  $('wktests').disabled=ohne;$('wkmessen').disabled=mitLlm;$('wkdiag').disabled=mitLlm;$('wkrep').disabled=mitLlm;
  const m=$('wkmess');m.textContent='';
  const n=d.nacht||{};if(n.zeit)m.appendChild(wkEl('div','',t('Letzter Testlauf: ','Last test run: ')+wkZeit(n.zeit)+' · '+(n.tests||{}).gruen+t(' grün',' green')+' · '+(n.tests||{}).rot+t(' rot',' red')+' · '+(n.tests||{}).wackelig+t(' wackelig',' flaky')+' · '+wkDauer(n.dauer_s)));
  Object.entries(d.messungen||{}).forEach(([mid,x])=>m.appendChild(wkEl('div','',t('Code-Messung ','Code measurement ')+mid+': '+x.gruen+t(' von ',' of ')+x.von+t(' Reparaturen grün',' repairs green')+' · '+wkZeit(x.zeit)+' · '+wkDauer(x.dauer_s))));
  const box=$('wklist');box.textContent='';
  (d.auftraege||[]).forEach(a=>{const row=wkEl('div','wkitem');
    const was=wkEl('div','wkwas');was.appendChild(wkEl('b','',wkArt(d,a.art)));was.appendChild(document.createTextNode(' · '+wkZeit(a.zeit)+' · '+wkDauer(a.dauer_s)+(a.modell?' · '+a.modell:'')));
    if(a.aufgabe)was.appendChild(wkEl('div','mut',a.aufgabe));row.appendChild(was);
    const g=WK_GRUND[a.grund]||[a.grund,a.grund];row.appendChild(wkEl('span','chip'+(a.grund==='ok'?' ok':' rot'),L==='en'?g[1]:g[0]));
    const ts=a.tests||{};if(ts.gruen||ts.rot)row.appendChild(wkEl('span','chip'+(ts.rot?' rot':' ok'),ts.gruen+t(' grün',' green')+' · '+ts.rot+t(' rot',' red')));
    if(a.art==='messen'&&a.aufgaben&&a.aufgaben.length)row.appendChild(wkEl('span','chip',a.aufgaben.filter(x=>x.ok).length+' / '+a.aufgaben.length));
    if((a.dateien||[]).length)row.appendChild(wkEl('span','chip',a.dateien.length+t(' Dateien',' files')));
    if(a.hat_patch||a.hat_text){const b=wkEl('button','b',a.hat_patch?t('Patch ansehen','View patch'):t('Antwort ansehen','View answer'));b.type='button';b.onclick=()=>wkEins(a.id);row.appendChild(b)}
    const w=wkEl('button','b',t('Verwerfen','Discard'));w.type='button';w.onclick=()=>wkWeg(a.id);row.appendChild(w);
    box.appendChild(row)});
  if(!(d.auftraege||[]).length)box.appendChild(wkEl('div','mut',t('Noch keine Ergebnisse.','No results yet.')))}
async function wkLoad(){clearTimeout(WK.timer);const box=$('wkbox');if(!box||document.body.classList.contains('mgr'))return;
  if(box.offsetParent){try{wkShow(await (await api('/api/admin/werkstatt')).json())}catch(e){$('wkstand').textContent=e.message}}
  WK.timer=setTimeout(wkLoad,WK.d&&WK.d.laeuft?5000:30000)}
async function wkEins(id){const p=$('wkpatch');p.hidden=false;p.textContent=t('Einen Moment …','One moment …');
  try{const a=await (await api('/api/admin/werkstatt/'+encodeURIComponent(id))).json();
    p.textContent=[a.text,a.patch?(a.gekuerzt?t('(gekürzt)\n','(cut)\n'):'')+a.patch:'',(a.tests&&a.tests.rot_namen||[]).length?t('Rot: ','Red: ')+a.tests.rot_namen.join(', '):''].filter(Boolean).join('\n\n')}
  catch(e){p.textContent=e.message}}
async function wkWeg(id){if(!confirm(t('Dieses Ergebnis mit seinem Patch löschen?','Delete this result with its patch?')))return;
  try{wkShow(await (await api('/api/admin/werkstatt/'+encodeURIComponent(id),{method:'DELETE'})).json());$('wkpatch').hidden=true}catch(e){$('wkstand').textContent=e.message}}
async function wkGeben(art){const text=($('wktext').value||'').trim();
  if((art==='diagnose'||art==='reparatur')&&text.length<8){$('wkstand').textContent=t('Bitte das Problem in ein, zwei Sätzen beschreiben.','Please describe the problem in a sentence or two.');return}
  $('wkstand').textContent=t('Einen Moment …','One moment …');
  try{const o={method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(art==='tests'?{}:{art,text})};
    wkShow(await (await api(art==='tests'?'/api/admin/werkstatt/tests':'/api/admin/werkstatt/auftrag',o)).json());
    if(art!=='tests'&&art!=='messen')$('wktext').value='';WK.timer=setTimeout(wkLoad,5000)}
  catch(e){$('wkstand').textContent=e.message}}
if($('wktests')){$('wktests').onclick=()=>wkGeben('tests');$('wkmessen').onclick=()=>wkGeben('messen');
  $('wkdiag').onclick=()=>wkGeben('diagnose');$('wkrep').onclick=()=>wkGeben('reparatur')}
window.wkLoad=wkLoad;
