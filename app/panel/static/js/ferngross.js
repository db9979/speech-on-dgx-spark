'use strict';
// Fernzugang → Dateien → große Dateien (ferngross.py, stage 3b): in pieces of 8 MB with the SHA-256 of each piece
// (crypto.subtle), „Pause“ and „Weiter“ at the last whole piece (also after „Trennen“: the same file chosen again);
// „Per Link holen“ lets the server fetch an https address itself; „Vom NAS übertragen“ sends a file of an NAS place.
// The panel checks every piece and the whole file at the end; this page only shows progress, rate and time left.
// Names and texts from the server go in as text only.
const FG={on:false,teil:8388608,max:0,langsam:1024,ups:{},files:{},jobs:[],t:null,nas:'',nasPfad:'',fertig:new Set()};
const FG_GRUND={'zu gross':['Größer als erlaubt.','Larger than allowed.'],voll:['Auf dem Server ist nicht genug Platz frei.','Not enough free space on the server.'],
  pruefsumme:['Die Prüfsumme passt nicht: die Datei wurde gelöscht.','The checksum does not match: the file was deleted.'],
  'gibt es schon':['Die Datei gibt es dort schon („Ersetzen“ überschreibt sie).','The file exists there already ("Replace" overwrites it).'],
  offline:['Der Server erreicht die Adresse nicht.','The server cannot reach the address.'],http:['Die Adresse antwortet mit einem Fehler.','The address answers with an error.'],
  zeit:['Die Adresse antwortet zu langsam.','The address answers too slowly.'],zertifikat:['Das Zertifikat der Adresse ist nicht gültig.','The address\'s certificate is not valid.'],
  umleitung:['Zu viele Weiterleitungen.','Too many redirects.'],'curl fehlt':['Auf dem Server fehlt curl.','curl is missing on the server.'],
  abgebrochen:['Abgebrochen.','Cancelled.'],nas:['Das NAS gibt die Datei nicht.','The NAS does not give the file.'],
  verboten:['Das darf der Benutzer spark auf dem Server nicht.','The user spark may not do that on the server.'],fehlt:['Das gibt es auf dem Server nicht (mehr).','That does not exist on the server (any more).'],
  fehler:['Der Server hat das nicht ausgeführt.','The server did not do that.']};
const fgBase=()=>FZ.fs?`/api/admin/fernzugang/gross/${FZ.fs.id}`:'';
const fgHex=b=>Array.from(new Uint8Array(b),x=>x.toString(16).padStart(2,'0')).join('');
const fgZeit=s=>!isFinite(s)||s<0?'':s<60?Math.round(s)+' s':s<3600?Math.round(s/60)+' min':(s/3600).toFixed(1)+' h';
async function fgJson(p,o){const r=await api(fgBase()+p,o);return r.json()}
const fgPost=(p,b)=>fgJson(p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});
// the view: called when the files open and after every change
async function fgZeig(){const box=$('fzgross');if(!box||!FZ.fs)return;let d;
  try{d=await fgJson('/stand')}catch(e){FG.on=false;box.hidden=true;$('fzgjobs').hidden=true;return}
  FG.on=true;FG.teil=d.teil;FG.max=d.max_mb;FG.langsam=d.langsam_kb;FG.jobs=d.jobs||[];box.hidden=false;
  $('fzgmax').textContent=t('Bis ','Up to ')+fzKB(d.max_mb*1048576)+t(', in Stücken von 8 MB mit Prüfsumme. „Pause“ und „Weiter“ gehen am letzten ganzen Stück weiter.',', in pieces of 8 MB with a checksum. "Pause" and "Resume" go on at the last whole piece.');
  const sel=$('fzgnas'),keep=sel.value;sel.textContent='';sel.appendChild(fzEl('option','',t('– wählen –','– choose –'))).value='';
  for(const n of d.nas||[]){const o=fzEl('option','',n.name);o.value=n.id;sel.appendChild(o)}sel.value=keep;$('fzgnasbox').hidden=!(d.nas||[]).length;
  for(const u of d.uploads||[])FG.ups[u.id]=Object.assign(FG.ups[u.id]||{lauf:false},u);
  for(const id of Object.keys(FG.ups))if(!(d.uploads||[]).some(u=>u.id===id)&&!FG.ups[id].lauf)delete FG.ups[id];
  fgListe();fgUhr()}
function fgUhr(){clearTimeout(FG.t);if(FZ.fs&&FG.jobs.some(j=>j.stand==='laeuft'||j.stand==='pruefen'))FG.t=setTimeout(fgZeig,2000)}
function fgBalken(n,of){const b=fzEl('progress','fzgbar');b.max=of||1;b.value=Math.min(n,of||1);if(!of)b.removeAttribute('value');return b}
function fgListe(){const list=$('fzgjoblist');list.textContent='';let langsam=false;
  for(const u of Object.values(FG.ups)){const r=fzEl('div','fzgrow'),kb=u.lauf&&u.rate?u.rate/1024:0;
    r.append(fzEl('b','',u.name),fgBalken(u.offset,u.groesse),fzEl('span','mut small',fzKB(u.offset)+' / '+fzKB(u.groesse)+(u.lauf&&u.rate?' · '+fzKB(u.rate)+'/s · '+t('noch ','left ')+fgZeit((u.groesse-u.offset)/u.rate):u.lauf?'':' · '+t('pausiert','paused'))));
    if(u.lauf&&u.rate&&kb<FG.langsam&&Date.now()-u.t0>5000)langsam=true;
    const row=fzEl('div','row');
    if(u.lauf)row.appendChild(fzBtn(t('Pause','Pause'),'',()=>{u.pause=true}));else row.appendChild(fzBtn(t('Weiter','Resume'),'p',()=>fgWeiter(u.id)));
    row.appendChild(fzBtn(t('Abbrechen','Cancel'),'danger',()=>fgAbbrechen(u.id)));r.appendChild(row);list.appendChild(r)}
  for(const j of FG.jobs){const r=fzEl('div','fzgrow'),art=j.art==='link'?t('Link','Link'):j.art==='nas'?'NAS':t('Prüfen','Check');
    const stand=j.stand==='laeuft'?fzKB(j.bytes)+(j.groesse?' / '+fzKB(j.groesse):'')+' · '+fzKB(j.kb_s*1024)+'/s'+(j.groesse&&j.kb_s?' · '+t('noch ','left ')+fgZeit((j.groesse-j.bytes)/(j.kb_s*1024)):'')
      :j.stand==='pruefen'?t('Prüfsumme auf dem Server …','Checksum on the server …'):j.stand==='fertig'?t('Fertig · SHA-256 ','Done · SHA-256 ')+j.sha256.slice(0,16)+'…':(FG_GRUND[j.grund]?t(...FG_GRUND[j.grund]):j.grund);
    r.append(fzEl('b','',art+' · '+j.name),fgBalken(j.stand==='fertig'?1:j.bytes,j.stand==='fertig'?1:j.groesse),fzEl('span',j.stand==='fehler'?'err small':'mut small',stand));
    if(j.stand==='laeuft'&&j.kb_s<FG.langsam&&j.bytes>0)langsam=true;
    if(j.stand==='laeuft')r.appendChild(fzBtn(t('Abbrechen','Cancel'),'danger',()=>fgJobStop(j.id)));
    if(j.stand==='fertig'&&!FG.fertig.has(j.id)){FG.fertig.add(j.id);if(FZ.fs)fzListe(FZ.fs.pfad)}
    list.appendChild(r)}
  $('fzgjobs').hidden=!list.childNodes.length;$('fzglangsam').hidden=!langsam}
// 1. in pieces
async function fgHoch(){const f=$('fzgfile').files[0];if(!FZ.fs)return;if(!f){$('fzgfile').click();return}
  if(!(window.crypto&&crypto.subtle)){fzMsg(t('Dieser Browser rechnet hier keine Prüfsumme (nur über https).','This browser computes no checksum here (https only).'),true);return}
  if(f.size>FG.max*1048576){fzMsg(t('Größer als ','Larger than ')+fzKB(FG.max*1048576)+'.',true);return}
  let d;try{d=await fgPost('/hoch',{pfad:FZ.fs.pfad,name:f.name,groesse:f.size,ersetzen:$('fzgreplace').checked})}catch(e){fzMsg(e.message,true);return}
  FG.files[d.id]=f;FG.ups[d.id]={id:d.id,name:f.name,groesse:f.size,offset:0,lauf:false};$('fzgfile').value='';fgLauf(d.id)}
async function fgWeiter(id){const u=FG.ups[id];if(!u)return;let f=FG.files[id];
  if(!f){f=await fgWaehle();if(!f)return;if(f.name!==u.name||f.size!==u.groesse){fzMsg(t('Das ist nicht dieselbe Datei (Name und Größe).','That is not the same file (name and size).'),true);return}FG.files[id]=f}
  try{const d=await fgPost(`/hoch/${id}/weiter`);u.offset=d.offset}catch(e){fzMsg(e.message,true);return}fgLauf(id)}
function fgWaehle(){return new Promise(ok=>{const i=document.createElement('input');i.type='file';i.onchange=()=>ok(i.files[0]||null);i.click()})}
async function fgLauf(id){const u=FG.ups[id],f=FG.files[id];if(!u||!f||u.lauf)return;u.lauf=true;u.pause=false;u.t0=Date.now();const ab=u.offset;fgListe();
  let fehl=0;FZ.fs.laeuft=true;
  try{while(u.offset<u.groesse&&!u.pause&&FZ.fs){const piece=await f.slice(u.offset,Math.min(u.groesse,u.offset+FG.teil)).arrayBuffer();
      const sha=fgHex(await crypto.subtle.digest('SHA-256',piece));
      let r;try{r=await /*raw: no answer and 409/422 each decide the next step of the upload*/fetch(`${fgBase()}/hoch/${id}?offset=${u.offset}`,{method:'PUT',credentials:'same-origin',headers:{'Content-Type':'application/octet-stream','X-Fz-Sha256':sha},body:piece})}catch{r=null}
      if(r&&r.ok){const d=await r.json();u.offset=d.offset;fehl=0;u.rate=(u.offset-ab)/Math.max(.5,(Date.now()-u.t0)/1000);fgListe();continue}
      if(r&&(r.status===409||r.status===422)&&fehl<3){fehl++;try{const d=await fgPost(`/hoch/${id}/weiter`);u.offset=d.offset}catch{}continue}
      if(!r&&fehl<5){fehl++;await new Promise(ok=>setTimeout(ok,2000*fehl));continue}
      let text=t('Die Verbindung ist weg: „Weiter“ geht am letzten ganzen Stück weiter.','The connection is gone: "Resume" goes on at the last whole piece.');
      if(r){try{text=errSay(r.status,(await r.json()).detail)}catch{}}fzMsg(text,true);u.pause=true}
    if(u.offset>=u.groesse&&!u.pause){const d=await fgPost(`/hoch/${id}/fertig`);delete FG.ups[id];delete FG.files[id];fzMsg(t('Alles da, der Server prüft die Prüfsumme …','All there, the server checks the checksum …'));
      FG.jobs.push({id:d.id,art:'hoch',name:u.name,stand:'pruefen',bytes:u.groesse,groesse:u.groesse,kb_s:0,sha256:''})}}
  catch(e){fzMsg(e.message,true)}
  finally{u.lauf=false;if(FZ.fs)FZ.fs.laeuft=false;fgZeig()}}
async function fgAbbrechen(id){const u=FG.ups[id];if(!u||!confirm(t('Den Upload abbrechen? Was schon oben ist, wird gelöscht.','Cancel the upload? What is up there already is deleted.')))return;u.pause=true;
  try{await api(`${fgBase()}/hoch/${id}`,{method:'DELETE'})}catch(e){fzMsg(e.message,true)}delete FG.ups[id];delete FG.files[id];fgZeig()}
// 2. by link
function fgLinkName(){const v=$('fzglink').value,n=$('fzglname');if(n.dataset.selbst)return;try{const p=new URL(v).pathname.split('/').filter(Boolean).pop()||'';n.value=decodeURIComponent(p).slice(0,255)}catch{}}
async function fgHolen(){if(!FZ.fs)return;const url=$('fzglink').value.trim(),name=$('fzglname').value.trim(),sha=$('fzglsha').value.trim().toLowerCase();
  if(!/^https:\/\//.test(url)){fzMsg(t('Nur eine https-Adresse.','An https address only.'),true);return}
  if(!name){fzMsg(t('Erst einen Namen für die Datei.','A name for the file first.'),true);return}
  if(sha&&!/^[0-9a-f]{64}$/.test(sha)){fzMsg(t('Die Prüfsumme hat 64 Zeichen 0-9 a-f.','The checksum has 64 characters 0-9 a-f.'),true);return}
  const b=$('fzglgo');b.disabled=true;
  try{await fgPost('/holen',{url,name,sha256:sha,pfad:FZ.fs.pfad,ersetzen:$('fzgreplace').checked});$('fzglink').value=$('fzglname').value=$('fzglsha').value='';delete $('fzglname').dataset.selbst;fzMsg(t('Der Server holt die Datei …','The server fetches the file …'))}
  catch(e){fzMsg(e.message,true)}finally{b.disabled=false;fgZeig()}}
// 3. from the NAS
async function fgNasListe(p){const nas=$('fzgnas').value,list=$('fzgnaslist'),cr=$('fzgnaspfad');list.textContent='';cr.textContent='';if(!nas||!FZ.fs)return;let d;
  try{d=await fgPost('/nas/liste',{nas,pfad:p})}catch(e){list.appendChild(fzEl('div','err small',e.message));return}
  FG.nas=nas;FG.nasPfad=d.pfad==='/'?'':d.pfad;let acc='';cr.appendChild(fzBtn('/','fzcrumb',()=>fgNasListe('')));
  for(const x of FG.nasPfad.split('/').filter(Boolean)){acc+='/'+x;const to=acc;cr.appendChild(fzBtn(x,'fzcrumb',()=>fgNasListe(to)))}
  for(const n of d.ordner){const r=fzEl('div','fzfrow');r.append(fzEl('span','fzfart dir','▸'),fzBtn(n+'/','fzfname',()=>fgNasListe(FG.nasPfad+'/'+n)),fzEl('span'),fzEl('span'),fzEl('span'));list.appendChild(r)}
  for(const x of d.dateien){const r=fzEl('div','fzfrow'),b=fzBtn(t('Übertragen','Transfer'),'',()=>fgNas(x.name));b.disabled=x.groesse>FG.max*1048576;
    r.append(fzEl('span','fzfart file','·'),fzEl('span','fzfname',x.name),fzEl('span','mut small',fzKB(x.groesse)),fzEl('span'),b);list.appendChild(r)}
  if(!d.ordner.length&&!d.dateien.length)list.appendChild(fzEl('div','mut',t('Der Ordner ist leer.','The folder is empty.')))}
async function fgNas(name){if(!FZ.fs)return;
  try{await fgPost('/nas',{nas:FG.nas,datei:FG.nasPfad+'/'+name,pfad:FZ.fs.pfad,name,ersetzen:$('fzgreplace').checked});fzMsg(t('Die Datei geht vom NAS zum Server …','The file goes from the NAS to the server …'))}
  catch(e){fzMsg(e.message,true)}fgZeig()}
async function fgJobStop(id){try{await api(`${fgBase()}/job/${id}`,{method:'DELETE'})}catch(e){fzMsg(e.message,true)}fgZeig()}
function fgZu(){clearTimeout(FG.t);for(const u of Object.values(FG.ups))u.pause=true;FG.jobs=[];FG.fertig.clear();const l=$('fzgjoblist');if(l)l.textContent='';const n=$('fzgnaslist');if(n)n.textContent=''}
{const k=$('fzgsend');if(k){k.onclick=fgHoch;$('fzglgo').onclick=fgHolen;$('fzglink').oninput=fgLinkName;$('fzglname').oninput=e=>{e.target.dataset.selbst=e.target.value?'1':''};
  if(!$('fzglname').value)delete $('fzglname').dataset.selbst;$('fzgnas').onchange=()=>fgNasListe('')}}
